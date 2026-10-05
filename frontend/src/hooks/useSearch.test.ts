import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { SearchResponse } from "../types";
import { useSearch } from "./useSearch";

vi.mock("../api", () => ({ api: vi.fn() }));
const response = (query: string): SearchResponse => ({
  query,
  results: [],
  latency_ms: 1,
  mode: "hybrid",
  warnings: [],
});
beforeEach(() => vi.mocked(api).mockReset());

describe("search request lifecycle", () => {
  it("ignores out-of-order results and keeps the current request busy", async () => {
    let first!: (value: SearchResponse) => void;
    let second!: (value: SearchResponse) => void;
    vi.mocked(api)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            first = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            second = resolve;
          }),
      );
    const { result } = renderHook(useSearch);
    act(() => {
      void result.current.search("old query");
    });
    act(() => {
      void result.current.search("current query");
    });
    await act(async () => first(response("old query")));
    expect(result.current.response).toBeUndefined();
    expect(result.current.busy).toBe(true);
    await act(async () => second(response("current query")));
    expect(result.current.response?.query).toBe("current query");
    expect(result.current.busy).toBe(false);
  });

  it("does not publish a cancelled response even if the transport finishes", async () => {
    let finish!: (value: SearchResponse) => void;
    vi.mocked(api).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const { result } = renderHook(useSearch);
    act(() => {
      void result.current.search("cancelled");
    });
    act(() => result.current.cancel());
    await act(async () => finish(response("cancelled")));
    expect(result.current.response).toBeUndefined();
    expect(result.current.busy).toBe(false);
    expect(result.current.error).toBe("");
  });

  it("applies folder/type overrides and removes advanced filters on reset", async () => {
    vi.mocked(api).mockResolvedValue(response("notes"));
    const { result } = renderHook(useSearch);
    act(() =>
      result.current.updateOptions({
        pathFilter: "notes/",
        rerank: true,
        mode: "lexical",
      }),
    );
    await act(async () =>
      result.current.search("notes", { rootFilter: "2", modality: "image" }),
    );
    expect(
      JSON.parse(String(vi.mocked(api).mock.calls[0][1]?.body)),
    ).toMatchObject({
      mode: "lexical",
      rerank: true,
      filters: { path_prefix: "notes/", root_id: 2, modality: "image" },
    });
    act(() => result.current.clearFilters());
    await act(async () => result.current.search("notes"));
    expect(
      JSON.parse(String(vi.mocked(api).mock.calls[1][1]?.body)),
    ).toMatchObject({
      mode: "hybrid",
      rerank: false,
      filters: { modality: "image" },
    });
  });
});
