import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { App, extractionNote, locationLabel } from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Source locations", () => {
  it("explains partial image OCR without suggesting that native slide text failed", () => {
    expect(
      extractionNote(
        "presentation_ocr_partial:12_images_not_processed;native_text_indexed",
      ),
    ).toContain("Slide text is searchable");
    expect(extractionNote("slide_85:IMAGE_UNREADABLE")).toContain("Slide 85");
    expect(extractionNote("slide_2:OCR_TIMEOUT")).toContain(
      "Slide text is still searchable",
    );
  });
  it("formats pages, lines and timestamps", () => {
    expect(locationLabel({ page: 14 })).toBe("Page 14");
    expect(locationLabel({ line_start: 82, line_end: 89 })).toBe("Lines 82–89");
    expect(locationLabel({ start_ms: 125000 })).toBe("2:05");
    expect(locationLabel({ slide: 2 })).toBe("Slide 2");
    expect(locationLabel({ slide: 2, section: "notes" })).toBe(
      "Slide 2 · Speaker notes",
    );
    expect(locationLabel({ slide: 3, section: "image" })).toBe(
      "Slide 3 · Image text",
    );
  });
});

describe("Workspace", () => {
  function mockService(
    empty = false,
    watchFailure = false,
    presentation = false,
  ) {
    let watchEnabled = false;
    const watch = () => ({
      enabled: watchEnabled,
      state: watchEnabled ? "waiting" : "off",
      observer_active: false,
      worker_active: true,
      watched_roots: 0,
      reconcile_seconds: 900,
      errors: [],
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options?: RequestInit) => {
        if (url.endsWith("/session"))
          return new Response(JSON.stringify({ token: "local-test-token" }));
        if (url.endsWith("/health"))
          return new Response(
            JSON.stringify({
              semantic_ready: true,
              status: "ready",
              text_model: "local-model",
              watch: watch(),
            }),
          );
        if (url.endsWith("/index/status"))
          return new Response(
            JSON.stringify({
              files: 1,
              chunks: 1,
              roots: [],
              modalities: [],
              profiles: [],
              failures: [],
            }),
          );
        if (url.endsWith("/jobs")) return new Response("[]");
        if (url.endsWith("/files/1"))
          return new Response(
            JSON.stringify({
              id: 1,
              name: "lecture.pptx",
              modality: "presentation",
              source_available: true,
              warnings: [],
              chunks: [
                {
                  id: 2,
                  text: "Unrelated slide image",
                  kind: "ocr",
                  asset: "other.jpg",
                  locator: { slide: 99 },
                },
              ],
            }),
          );
        if (url.endsWith("/index/watch")) {
          if (watchFailure)
            return new Response(
              JSON.stringify({
                error: { message: "Could not save automatic updates" },
              }),
              { status: 500 },
            );
          expect(options?.method).toBe("PUT");
          expect(new Headers(options?.headers).get("x-fileora-token")).toBe(
            "local-test-token",
          );
          watchEnabled = JSON.parse(String(options?.body)).enabled;
          return new Response(JSON.stringify(watch()));
        }
        if (url.endsWith("/search")) {
          expect(new Headers(options?.headers).get("x-fileora-token")).toBe(
            "local-test-token",
          );
          return new Response(
            JSON.stringify({
              query: "semaphores",
              results: empty
                ? []
                : [
                    {
                      file_id: 1,
                      name: presentation ? "lecture.pptx" : "notes.md",
                      relative_path: "notes.md",
                      path: "C:/notes.md",
                      modality: presentation ? "presentation" : "text",
                      match_kind: "terms",
                      extension: presentation ? ".pptx" : ".md",
                      evidence: [
                        {
                          chunk_id: 1,
                          snippet: "Critical sections use semaphores.",
                          locator: presentation
                            ? { slide: 2, section: "notes" }
                            : { line_start: 1 },
                          kind: "text",
                          symbol: "",
                          asset_url: null,
                        },
                      ],
                      aliases: [],
                      warnings: [],
                    },
                  ],
              warnings: [],
              latency_ms: 10,
              mode: "hybrid",
            }),
          );
        }
        return new Response("{}");
      }),
    );
  }

  it("submits a query and renders real service results", async () => {
    mockService();
    render(<App />);
    fireEvent.change(screen.getByLabelText("Search your files"), {
      target: { value: "semaphores" },
    });
    fireEvent.click(screen.getByLabelText("Run search"));
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "notes.md" }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("heading", { name: "notes.md" }).closest("button"),
    ).toHaveTextContent("Critical sections use semaphores.");
    expect(
      screen.getByText("semaphores", { selector: "mark" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Term match")).toBeInTheDocument();
  });

  it("shows an empty state when the current file type has no matches", async () => {
    mockService(true);
    render(<App />);
    fireEvent.change(screen.getByLabelText("Search your files"), {
      target: { value: "BCNF" },
    });
    fireEvent.click(screen.getByLabelText("Run search"));
    await waitFor(() =>
      expect(screen.getByText("No matches this time.")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Images" }));
    await waitFor(() => {
      const requests = vi
        .mocked(fetch)
        .mock.calls.filter(([url]) => String(url).endsWith("/search"));
      expect(requests).toHaveLength(2);
      expect(JSON.parse(String(requests[1][1]?.body))).toMatchObject({
        query: "BCNF",
        mode: "hybrid",
        filters: { modality: "image" },
      });
    });
    expect(screen.getByText("No matches this time.")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "notes.md" }),
    ).not.toBeInTheDocument();
  });

  it("shows the folder setup flow", async () => {
    mockService();
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /My library/ }));
    expect(screen.getByLabelText("Folder path")).toBeInTheDocument();
    expect(screen.getByText("A home for what you know.")).toBeInTheDocument();
  });

  it("previews slide evidence and downloads the original without an unrelated slide image", async () => {
    mockService(false, false, true);
    render(<App />);
    fireEvent.change(screen.getByLabelText("Search your files"), {
      target: { value: "semaphores" },
    });
    fireEvent.click(screen.getByLabelText("Run search"));
    const heading = await screen.findByRole("heading", {
      name: "lecture.pptx",
    });
    fireEvent.click(heading.closest("button")!);
    await screen.findByRole("link", { name: "Download original" });
    expect(screen.getAllByText("Slide 2 · Speaker notes")).toHaveLength(2);
    expect(
      screen.queryByRole("img", { name: "Preview of lecture.pptx" }),
    ).not.toBeInTheDocument();
  });

  it("filters PowerPoint searches by the presentation modality", async () => {
    mockService(true);
    render(<App />);
    fireEvent.change(screen.getByLabelText("Search your files"), {
      target: { value: "BCNF" },
    });
    fireEvent.click(screen.getByLabelText("Run search"));
    await waitFor(() =>
      expect(screen.getByText("No matches this time.")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "PPTs" }));
    await waitFor(() => {
      const requests = vi
        .mocked(fetch)
        .mock.calls.filter(([url]) => String(url).endsWith("/search"));
      expect(requests).toHaveLength(2);
      expect(JSON.parse(String(requests[1][1]?.body))).toMatchObject({
        filters: { modality: "presentation" },
      });
    });
  });

  it("saves automatic updates through the service and reflects the resulting state", async () => {
    mockService();
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /My library/ }));
    const toggle = screen.getByRole("switch", { name: "Watch folders" });
    await waitFor(() => expect(toggle).toBeEnabled());
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    await waitFor(() => expect(toggle).toBeChecked());
    expect(
      screen.getByText("Automatic updates are on. Add a folder to begin."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Your preference is saved on this device/),
    ).toBeInTheDocument();
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);
    await waitFor(() => expect(toggle).not.toBeChecked());
    expect(screen.getByText(/Automatic updates are off/)).toBeInTheDocument();
  });

  it("restores the watch switch when saving the preference fails", async () => {
    mockService(false, true);
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /My library/ }));
    const toggle = screen.getByRole("switch", { name: "Watch folders" });
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);
    expect(toggle).toBeChecked();
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Could not save automatic updates",
      ),
    );
    expect(toggle).not.toBeChecked();
    expect(toggle).toBeEnabled();
  });
});
