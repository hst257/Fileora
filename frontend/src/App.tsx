import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowSquareOut,
  CheckCircle,
  Clock,
  FileCode,
  FilePdf,
  FilePpt,
  FileText,
  Folder,
  FolderOpen,
  Image,
  MagnifyingGlass,
  ShieldCheck,
  SlidersHorizontal,
  Spinner,
  Stack,
  Trash,
  VideoCamera,
  Waveform,
  X,
} from "@phosphor-icons/react";
import { api } from "./api";
import type {
  AnswerResponse,
  FileDetail,
  Health,
  Job,
  Locator,
  Result,
  SearchResponse,
  Status,
  WatchStatus,
} from "./types";

const examples = [
  "Find my notes about semaphores",
  "Where is my Java implementation of Dijkstra?",
  "AWS load balancing and target groups",
  "The screenshot explaining virtual memory",
];

function HighlightedText({ text, query }: { text: string; query: string }) {
  const terms = [...new Set(query.match(/[\p{L}\p{N}_]{3,}/gu) || [])].filter(
    (term) =>
      !["find", "the", "about", "where", "notes", "files"].includes(
        term.toLowerCase(),
      ),
  );
  if (!terms.length) return <>{text}</>;
  const pattern = new RegExp(
    `(${terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "giu",
  );
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 ? <mark key={index}>{part}</mark> : part,
      )}
    </>
  );
}

export function locationLabel(locator: Locator): string {
  if (locator.slide)
    return `Slide ${locator.slide}${locator.section === "notes" ? " · Speaker notes" : locator.section === "image" ? " · Image text" : ""}`;
  if (locator.page) return `Page ${locator.page}`;
  if (locator.line_start)
    return `Lines ${locator.line_start}${locator.line_end && locator.line_end !== locator.line_start ? "–" + locator.line_end : ""}`;
  if (locator.start_ms !== undefined)
    return `${Math.floor(locator.start_ms / 60000)}:${String(Math.floor(locator.start_ms / 1000) % 60).padStart(2, "0")}`;
  return "Image";
}

export function extractionNote(warning: string): string {
  const partial = warning.match(/^presentation_ocr_partial:(\d+)_/);
  if (partial)
    return `Slide text is searchable. Image OCR stopped early; ${partial[1]} image placements were not processed.`;
  const unreadable = warning.match(/^slide_(\d+):IMAGE_UNREADABLE$/);
  if (unreadable)
    return `An embedded image on Slide ${unreadable[1]} could not be read. Slide text is still searchable.`;
  const timeout = warning.match(/^slide_(\d+):OCR_TIMEOUT$/);
  if (timeout)
    return `Image OCR on Slide ${timeout[1]} reached its time limit. Slide text is still searchable.`;
  return warning.replaceAll("_", " ");
}

function FileIcon({
  modality,
  size = 22,
}: {
  modality: string;
  size?: number;
}) {
  const Icon =
    modality === "document"
      ? FilePdf
      : modality === "presentation"
        ? FilePpt
        : modality === "code"
          ? FileCode
          : modality === "image"
            ? Image
            : modality === "audio"
              ? Waveform
              : modality === "video"
                ? VideoCamera
                : FileText;
  return <Icon size={size} weight="duotone" />;
}

export function App() {
  const [view, setView] = useState<"search" | "library">("search");
  const [status, setStatus] = useState<Status>();
  const [health, setHealth] = useState<Health>();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<SearchResponse>();
  const [answer, setAnswer] = useState<AnswerResponse>();
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Result>();
  const [detail, setDetail] = useState<FileDetail>();
  const [previewError, setPreviewError] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [modality, setModality] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [rootFilter, setRootFilter] = useState("");
  const [pathFilter, setPathFilter] = useState("");
  const [modifiedAfter, setModifiedAfter] = useState("");
  const [rerank, setRerank] = useState(false);
  const [ask, setAsk] = useState(false);
  const [rootPath, setRootPath] = useState("");
  const [libraryBusy, setLibraryBusy] = useState(false);
  const [pendingWatch, setPendingWatch] = useState<boolean>();
  const watchBusy = pendingWatch !== undefined;
  const [jobDetail, setJobDetail] = useState<Job>();
  const input = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | undefined>(undefined);
  const media = useRef<HTMLMediaElement>(null);
  const connected = Boolean(health);
  const indexing = jobs.some((job) =>
    ["queued", "running"].includes(job.state),
  );

  const refresh = useCallback(async () => {
    try {
      const [nextStatus, nextHealth, nextJobs] = await Promise.all([
        api<Status>("/index/status"),
        api<Health>("/health"),
        api<Job[]>("/jobs"),
      ]);
      setStatus(nextStatus);
      setHealth(nextHealth);
      setJobs(nextJobs);
    } catch {
      setHealth(undefined);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => {
      window.clearInterval(timer);
      controller.current?.abort();
    };
  }, [refresh]);

  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setView("search");
        window.requestAnimationFrame(() => input.current?.focus());
      }
      if (event.key === "Escape") {
        setSelected(undefined);
        setFiltersOpen(false);
      }
    };
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, []);

  useEffect(() => {
    setDetail(undefined);
    setPreviewError("");
    if (!selected) return;
    let active = true;
    api<FileDetail>(`/files/${selected.file_id}`)
      .then((value) => {
        if (active) setDetail(value);
      })
      .catch((err) => {
        if (active) setPreviewError(err.message);
      });
    return () => {
      active = false;
    };
  }, [selected]);

  async function search(value = query, selectedModality = modality) {
    if (!value.trim()) {
      input.current?.focus();
      return;
    }
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setQuery(value);
    setView("search");
    setBusy(true);
    setError("");
    setAnswer(undefined);
    setSelected(undefined);
    const filters: Record<string, unknown> = {};
    if (selectedModality) filters.modality = selectedModality;
    if (rootFilter) filters.root_id = Number(rootFilter);
    if (pathFilter) filters.path_prefix = pathFilter;
    if (modifiedAfter)
      filters.modified_after = new Date(
        modifiedAfter + "T00:00:00",
      ).toISOString();
    try {
      const payload = { query: value, mode, filters, rerank, limit: 10 };
      if (ask) {
        const result = await api<AnswerResponse>("/answer", {
          method: "POST",
          body: JSON.stringify(payload),
          signal: abort.signal,
        });
        if (!abort.signal.aborted) {
          setAnswer(result);
          setResponse(result.retrieval);
        }
      } else {
        const result = await api<SearchResponse>("/search", {
          method: "POST",
          body: JSON.stringify(payload),
          signal: abort.signal,
        });
        if (!abort.signal.aborted) setResponse(result);
      }
    } catch (err) {
      if (!abort.signal.aborted) setError((err as Error).message);
    } finally {
      if (controller.current === abort) setBusy(false);
    }
  }

  async function addRoot(event: React.FormEvent) {
    event.preventDefault();
    setLibraryBusy(true);
    setError("");
    try {
      await api("/roots", {
        method: "POST",
        body: JSON.stringify({ path: rootPath }),
      });
      setRootPath("");
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLibraryBusy(false);
    }
  }

  async function rescan(verify = false) {
    setLibraryBusy(true);
    setError("");
    try {
      await api("/index/jobs", {
        method: "POST",
        body: JSON.stringify({ verify }),
      });
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLibraryBusy(false);
    }
  }

  async function setWatching(enabled: boolean) {
    setPendingWatch(enabled);
    setError("");
    try {
      const watch = await api<WatchStatus>("/index/watch", {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      });
      setHealth((current) => (current ? { ...current, watch } : current));
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPendingWatch(undefined);
    }
  }

  async function forget(id: number) {
    if (
      !window.confirm(
        "Remove this folder from Fileora and forget its indexed content? Your original files will stay in place.",
      )
    )
      return;
    setError("");
    try {
      await api(`/roots/${id}`, { method: "DELETE" });
      setResponse(undefined);
      setSelected(undefined);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function inspectJob(job: Job) {
    try {
      setJobDetail(await api<Job>(`/jobs/${job.id}`));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const asset =
    selected?.evidence.find((e) => e.asset_url)?.asset_url ||
    (selected?.modality !== "presentation" &&
    detail?.chunks.find((c) => c.asset)
      ? `/api/v1/assets/${detail.chunks.find((c) => c.asset)!.id}`
      : undefined);
  const loc = selected?.evidence[0]?.locator;
  const previewUrl = selected
    ? `/api/v1/files/${selected.file_id}/preview${loc?.page ? "#page=" + loc.page : ""}`
    : "";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault();
            setView("search");
          }}
        >
          <FolderOpen weight="fill" size={28} />
          <span>
            fileora<span className="brand-dot">.</span>
          </span>
        </a>
        <p className="workspace-label">PERSONAL WORKSPACE</p>
        <nav aria-label="Main navigation">
          <button
            className={view === "search" ? "nav-item active" : "nav-item"}
            onClick={() => setView("search")}
          >
            <MagnifyingGlass size={20} weight="bold" />
            Search<kbd>⌘ K</kbd>
          </button>
          <button
            className={view === "library" ? "nav-item active" : "nav-item"}
            onClick={() => setView("library")}
          >
            <Stack size={20} weight="bold" />
            My library<span className="nav-count">{status?.files ?? 0}</span>
          </button>
        </nav>
        <div className="sidebar-folders">
          <div className="section-label">
            INDEXED FOLDERS
            <button
              aria-label="Add a folder"
              onClick={() => setView("library")}
            >
              +
            </button>
          </div>
          {status?.roots.length ? (
            status.roots.map((root) => (
              <button
                key={root.id}
                className="folder-nav"
                title={root.path}
                onClick={() => {
                  setRootFilter(String(root.id));
                  setView("search");
                  setFiltersOpen(true);
                }}
              >
                <Folder size={17} />
                <span>
                  {root.path
                    .replace(/\\/g, "/")
                    .split("/")
                    .filter(Boolean)
                    .at(-1)}
                </span>
                {root.status !== "ready" && <span className="dot warning" />}
              </button>
            ))
          ) : (
            <p className="muted small">
              Choose the folders you want to search.
            </p>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="privacy-note">
            <ShieldCheck size={22} weight="duotone" />
            <div>
              <strong>On your device</strong>
              <p>Your files stay with you.</p>
            </div>
          </div>
          <div className="connection">
            <span className={`dot ${connected ? "online" : ""}`} />
            {connected
              ? "Local service connected"
              : "Connecting to local service"}
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <span>
            Workspace <span className="slash">/</span>{" "}
            <strong>{view === "search" ? "Search" : "My library"}</strong>
          </span>
          <div className="topbar-status">
            {indexing ? (
              <>
                <Spinner className="spin" size={15} />
                Indexing files
              </>
            ) : (
              <>
                <ShieldCheck size={15} />
                {connected ? "Private by design" : "Service unavailable"}
              </>
            )}
          </div>
        </header>
        {error && (
          <div className="alert error" role="alert">
            <span>{error}</span>
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={18} />
            </button>
          </div>
        )}

        {view === "search" ? (
          <div className={`search-page ${response ? "has-results" : ""}`}>
            <div className="search-intro">
              <div className="eyebrow">
                <span className="tiny-square" />
                YOUR PERSONAL SEARCH ENGINE
              </div>
              <h1>
                {response ? (
                  "A little closer to what you need."
                ) : (
                  <>
                    Your files.
                    <br />
                    <span>A thought away.</span>
                  </>
                )}
              </h1>
              <p>Search the way you think. Find the things you saved.</p>
            </div>
            <form
              className="search-form"
              onSubmit={(event) => {
                event.preventDefault();
                void search();
              }}
            >
              <MagnifyingGlass size={25} />
              <input
                ref={input}
                aria-label="Search your files"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="What are you looking for?"
                autoComplete="off"
              />
              {busy ? (
                <button
                  className="search-submit"
                  type="button"
                  aria-label="Cancel search"
                  onClick={() => {
                    controller.current?.abort();
                    setBusy(false);
                  }}
                >
                  <X size={20} />
                </button>
              ) : (
                <button
                  className="search-submit"
                  type="submit"
                  aria-label="Run search"
                >
                  <ArrowRight size={22} />
                </button>
              )}
            </form>
            <div className="search-tools">
              <div className="type-filters" aria-label="File type filters">
                {[
                  ["", "All files"],
                  ["document", "PDFs"],
                  ["presentation", "PPTs"],
                  ["code", "Code"],
                  ["image", "Images"],
                  ["audio", "Audio"],
                  ["video", "Video"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    className={
                      modality === value
                        ? "type-filter selected"
                        : "type-filter"
                    }
                    onClick={() => {
                      setModality(value);
                      if (response) void search(query, value);
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <button
                className={`filter-toggle ${filtersOpen ? "selected" : ""}`}
                onClick={() => setFiltersOpen(!filtersOpen)}
              >
                <SlidersHorizontal size={18} />
                Filters
              </button>
            </div>
            {filtersOpen && (
              <div className="filter-panel">
                <label>
                  Retrieval
                  <select
                    aria-label="Retrieval mode"
                    value={mode}
                    onChange={(event) => setMode(event.target.value)}
                  >
                    <option value="hybrid">Hybrid</option>
                    <option value="semantic">Semantic</option>
                    <option value="lexical">Exact terms</option>
                  </select>
                </label>
                <label>
                  Folder
                  <select
                    value={rootFilter}
                    onChange={(event) => setRootFilter(event.target.value)}
                  >
                    <option value="">All folders</option>
                    {status?.roots.map((root) => (
                      <option key={root.id} value={root.id}>
                        {root.path}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Path starts with
                  <input
                    value={pathFilter}
                    onChange={(event) => setPathFilter(event.target.value)}
                    placeholder="notes/"
                  />
                </label>
                <label>
                  Modified after
                  <input
                    type="date"
                    value={modifiedAfter}
                    onChange={(event) => setModifiedAfter(event.target.value)}
                  />
                </label>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={rerank}
                    onChange={(event) => setRerank(event.target.checked)}
                  />
                  Rerank passages
                </label>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={ask}
                    onChange={(event) => setAsk(event.target.checked)}
                  />
                  Answer from my files
                </label>
                <button className="text-button" onClick={() => void search()}>
                  Apply filters <ArrowRight size={15} />
                </button>
              </div>
            )}
            {busy && (
              <div className="search-loading" role="status">
                <Spinner className="spin" size={20} />
                {ask
                  ? "Reading your retrieved excerpts…"
                  : "Looking through your library…"}
              </div>
            )}
            {answer && (
              <section className="answer-panel">
                <div className="section-label">ANSWER FROM YOUR FILES</div>
                <p>{answer.answer}</p>
                {answer.notice && (
                  <p className="small muted">{answer.notice}</p>
                )}
                <div className="citations">
                  {answer.citations.map((citation) => (
                    <button
                      key={citation.id}
                      onClick={() => {
                        const result = response?.results.find(
                          (r) => r.file_id === citation.file_id,
                        );
                        if (result) setSelected(result);
                      }}
                    >
                      [{citation.id}] {citation.name} ·{" "}
                      {locationLabel(citation.locator)}
                    </button>
                  ))}
                </div>
              </section>
            )}
            {response?.warnings.map((warning) => (
              <div className="alert warning-alert" key={warning}>
                {warning}
              </div>
            ))}
            {response ? (
              <div className="results-area">
                <div className="results-heading">
                  <span>
                    <strong>{response.results.length}</strong> matching{" "}
                    {response.results.length === 1 ? "file" : "files"}
                  </span>
                  <span>
                    {response.latency_ms.toLocaleString()} ms · {response.mode}
                  </span>
                </div>
                <div
                  className={`results-grid ${selected ? "with-preview" : ""}`}
                >
                  <div className="results-list">
                    {response.results.length ? (
                      response.results.map((result, index) => (
                        <button
                          key={result.file_id}
                          className={`result-row ${selected?.file_id === result.file_id ? "selected" : ""}`}
                          onClick={() => setSelected(result)}
                        >
                          <div className={`file-icon ${result.modality}`}>
                            <FileIcon modality={result.modality} />
                          </div>
                          <div className="result-content">
                            <div className="result-title">
                              <h2>{result.name}</h2>
                              <span className="file-type">
                                {result.extension.slice(1).toUpperCase()}
                              </span>
                            </div>
                            <p className="result-path">
                              {result.relative_path}
                            </p>
                            <p className="snippet">
                              <HighlightedText
                                text={
                                  result.evidence[0]?.snippet ||
                                  "Visual match in your library."
                                }
                                query={response.query}
                              />
                            </p>
                            <div className="result-meta">
                              {result.match_kind && (
                                <span>
                                  {result.match_kind === "terms"
                                    ? "Term match"
                                    : result.match_kind === "semantic"
                                      ? "Related by meaning"
                                      : "Visual similarity"}
                                </span>
                              )}
                              <span>
                                {locationLabel(
                                  result.evidence[0]?.locator || {},
                                )}
                              </span>
                              {result.evidence[0]?.symbol && (
                                <span>{result.evidence[0].symbol}</span>
                              )}
                              {result.aliases.length > 0 && (
                                <span>{result.aliases.length + 1} copies</span>
                              )}
                              <span>Match #{index + 1}</span>
                            </div>
                          </div>
                          <ArrowRight className="row-arrow" size={18} />
                        </button>
                      ))
                    ) : (
                      <div className="empty-results">
                        <MagnifyingGlass size={35} />
                        <h2>No matches this time.</h2>
                        <p>
                          Try a different phrase, fewer filters, or index
                          another folder.
                        </p>
                        <button
                          className="text-button"
                          onClick={() => setView("library")}
                        >
                          Check your library <ArrowRight size={16} />
                        </button>
                      </div>
                    )}
                  </div>
                  {selected && (
                    <aside className="preview-panel" aria-label="File preview">
                      <div className="preview-header">
                        <span>FILE PREVIEW</span>
                        <button
                          aria-label="Close preview"
                          onClick={() => setSelected(undefined)}
                        >
                          <X size={18} />
                        </button>
                      </div>
                      <div className="preview-file">
                        <FileIcon modality={selected.modality} size={26} />
                        <h2>{selected.name}</h2>
                        <p>{selected.relative_path}</p>
                      </div>
                      {previewError && (
                        <p role="alert" className="small">
                          {previewError}
                        </p>
                      )}
                      {detail && !detail.source_available ? (
                        <div className="alert warning-alert">
                          This source has changed or is unavailable. Rescan to
                          refresh it.
                        </div>
                      ) : (
                        <>
                          {asset && (
                            <img
                              className="image-preview"
                              src={asset}
                              alt={`Preview of ${selected.name}`}
                            />
                          )}{" "}
                          {detail &&
                            ["audio", "video"].includes(detail.modality) &&
                            (detail.modality === "video" ? (
                              <video
                                controls
                                ref={media as React.RefObject<HTMLVideoElement>}
                                src={previewUrl}
                                onLoadedMetadata={() => {
                                  if (media.current)
                                    media.current.currentTime =
                                      (loc?.start_ms || 0) / 1000;
                                }}
                              />
                            ) : (
                              <audio
                                controls
                                ref={media as React.RefObject<HTMLAudioElement>}
                                src={previewUrl}
                                onLoadedMetadata={() => {
                                  if (media.current)
                                    media.current.currentTime =
                                      (loc?.start_ms || 0) / 1000;
                                }}
                              />
                            ))}
                          <div className="preview-excerpts">
                            {selected.warnings.map((warning) => (
                              <p className="small muted" key={warning}>
                                Extraction note: {extractionNote(warning)}
                              </p>
                            ))}
                            {selected.evidence
                              .filter((item) => item.snippet)
                              .map((item) => (
                                <div key={item.chunk_id}>
                                  <div className="excerpt-location">
                                    {locationLabel(item.locator)}
                                    {item.symbol ? " · " + item.symbol : ""}
                                  </div>
                                  <pre>
                                    <HighlightedText
                                      text={item.snippet}
                                      query={response.query}
                                    />
                                  </pre>
                                </div>
                              ))}
                          </div>
                          {detail?.source_available && (
                            <a
                              className="open-file"
                              href={previewUrl}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {selected.modality === "presentation"
                                ? "Download original"
                                : "Open original"}{" "}
                              <ArrowSquareOut size={17} />
                            </a>
                          )}
                        </>
                      )}
                      <div className="preview-footer">
                        <ShieldCheck size={16} />
                        Previewed locally
                      </div>
                    </aside>
                  )}
                </div>
              </div>
            ) : (
              <div className="discovery">
                <div className="section-label">A FEW WAYS TO START</div>
                <div className="example-grid">
                  {examples.map((example, index) => (
                    <button
                      key={example}
                      onClick={() => {
                        const type =
                          index === 3 ? "image" : index === 1 ? "code" : "";
                        setModality(type);
                        void search(example, type);
                      }}
                    >
                      <span className="example-icon">
                        {index === 0 ? (
                          <FileText size={22} weight="duotone" />
                        ) : index === 1 ? (
                          <FileCode size={22} weight="duotone" />
                        ) : index === 2 ? (
                          <Stack size={22} weight="duotone" />
                        ) : (
                          <Image size={22} weight="duotone" />
                        )}
                      </span>
                      <span>{example}</span>
                      <ArrowRight size={17} />
                    </button>
                  ))}
                </div>
                <div className="library-summary">
                  <FolderOpen size={21} weight="duotone" />
                  <span>
                    {status?.files ? (
                      <>
                        <strong>{status.files.toLocaleString()} files</strong>{" "}
                        across {status.roots.length}{" "}
                        {status.roots.length === 1 ? "folder" : "folders"}.
                        Ready when you are.
                      </>
                    ) : (
                      <>Your library starts with a folder.</>
                    )}
                  </span>
                  <button
                    className="text-button"
                    onClick={() => setView("library")}
                  >
                    {status?.files ? "Manage library" : "Add a folder"}{" "}
                    <ArrowRight size={15} />
                  </button>
                </div>
              </div>
            )}
            <footer className="search-footer">
              <ShieldCheck size={14} />
              Local processing. No uploads. No cloud account.
            </footer>
          </div>
        ) : (
          <div className="library-page">
            <div className="eyebrow">YOUR INDEXED COLLECTION</div>
            <h1>A home for what you know.</h1>
            <p className="page-description">
              Choose your folders. Fileora keeps a searchable index on this
              device.
            </p>
            <div className="library-statistics">
              <div>
                <strong>{status?.files.toLocaleString() ?? "0"}</strong>
                <span>indexed files</span>
              </div>
              <div>
                <strong>{status?.chunks.toLocaleString() ?? "0"}</strong>
                <span>pieces of evidence</span>
              </div>
              <div>
                <strong>{status?.roots.length ?? "0"}</strong>
                <span>indexed folders</span>
              </div>
            </div>
            <section
              className="watch-section"
              aria-label="Automatic library updates"
            >
              <div className="section-heading">
                <div>
                  <h2>Keep my library current</h2>
                  <p className="small muted">
                    Automatically index edits, new files, renames, and deletions
                    in your selected folders while Fileora is running.
                  </p>
                </div>
                <label className="watch-control">
                  <input
                    type="checkbox"
                    role="switch"
                    aria-label="Watch folders"
                    checked={pendingWatch ?? health?.watch?.enabled ?? false}
                    disabled={watchBusy || !health?.watch}
                    onChange={(event) => void setWatching(event.target.checked)}
                  />
                  Watch folders
                </label>
              </div>
              <p className="small muted" role="status">
                {watchBusy
                  ? "Updating automatic scans…"
                  : health?.watch?.state === "watching"
                    ? `Watching ${health.watch.watched_roots} ${health.watch.watched_roots === 1 ? "folder" : "folders"}.`
                    : health?.watch?.state === "waiting"
                      ? "Automatic updates are on. Add a folder to begin."
                      : health?.watch?.state === "polling"
                        ? "Some folder watchers are unavailable. Periodic scans are keeping your library current."
                        : health?.watch?.state === "stopped"
                          ? "The indexing worker has stopped. Restart Fileora to resume automatic updates."
                          : "Automatic updates are off. Rescan whenever you want to refresh your library."}
              </p>
              {health?.watch?.enabled && (
                <p className="small muted">
                  A full verification runs every{" "}
                  {Math.round(health.watch.reconcile_seconds / 60)} minutes.
                  Your preference is saved on this device. Turning this off lets
                  the current scan finish.
                </p>
              )}
              {health?.watch?.errors.map((item) => (
                <p className="small watch-warning" key={item.path}>
                  Could not watch {item.path}. It will be checked during the
                  next full scan.
                </p>
              ))}
            </section>
            {!health?.semantic_ready && (
              <div className="model-notice">
                <FileText size={22} />
                <div>
                  <strong>
                    Start with exact terms, or prepare semantic search.
                  </strong>
                  <p>
                    Stop Fileora, run this in your activated environment, then
                    restart and rescan:
                  </p>
                  <code>
                    {health?.model_setup_command ||
                      "fileora models download sentence-transformers/all-MiniLM-L6-v2"}
                  </code>
                </div>
              </div>
            )}
            <section className="folder-section">
              <div className="section-heading">
                <h2>Folders</h2>
                <div className="actions">
                  <button
                    className="secondary-button"
                    disabled={indexing || libraryBusy || !status?.roots.length}
                    onClick={() => void rescan(true)}
                  >
                    Verify all files
                  </button>
                  <button
                    className="primary-button"
                    disabled={indexing || libraryBusy || !status?.roots.length}
                    onClick={() => void rescan()}
                  >
                    {indexing ? (
                      <Spinner className="spin" size={16} />
                    ) : (
                      <ArrowDown size={16} />
                    )}
                    Rescan library
                  </button>
                </div>
              </div>
              <form
                className="add-folder"
                onSubmit={(event) => void addRoot(event)}
              >
                <Folder size={22} />
                <input
                  aria-label="Folder path"
                  placeholder="Paste an absolute folder path, e.g. C:\Users\you\Documents\Notes"
                  value={rootPath}
                  onChange={(event) => setRootPath(event.target.value)}
                  required
                />
                <button
                  className="primary-button"
                  disabled={libraryBusy || !rootPath.trim()}
                >
                  Add folder
                </button>
              </form>
              <p className="small muted">
                Only selected folders are indexed. Hidden folders, dependencies,
                and common secret files are skipped.
              </p>
              <div className="folder-list">
                {status?.roots.map((root) => (
                  <div className="folder-row" key={root.id}>
                    <FolderOpen size={23} weight="duotone" />
                    <div>
                      <strong>
                        {root.path
                          .replace(/\\/g, "/")
                          .split("/")
                          .filter(Boolean)
                          .at(-1)}
                      </strong>
                      <p>{root.path}</p>
                    </div>
                    <span className={`root-status ${root.status}`}>
                      {root.status === "ready" ? "Connected" : "Unavailable"}
                    </span>
                    <button
                      aria-label={`Forget ${root.path}`}
                      title="Forget indexed content; keep original files"
                      disabled={indexing}
                      onClick={() => void forget(root.id)}
                    >
                      <Trash size={19} />
                    </button>
                  </div>
                ))}
              </div>
            </section>
            <section className="jobs-section">
              <div className="section-heading">
                <h2>Indexing activity</h2>
                <span className="small muted">
                  {indexing
                    ? "Running in the background"
                    : "Up to date with the last scan"}
                </span>
              </div>
              {jobs.length ? (
                jobs.slice(0, 6).map((job) => (
                  <div className="job-row" key={job.id}>
                    <span>
                      {["queued", "running"].includes(job.state) ? (
                        <Spinner className="spin" size={21} />
                      ) : job.state === "completed" ? (
                        <CheckCircle size={21} weight="duotone" />
                      ) : (
                        <Clock size={21} />
                      )}
                    </span>
                    <button
                      className="job-info"
                      onClick={() => void inspectJob(job)}
                    >
                      <strong>
                        {job.state === "completed"
                          ? "Library scan completed"
                          : `Library scan ${job.state}`}
                      </strong>
                      <span>
                        {job.indexed} indexed · {job.skipped} skipped ·{" "}
                        {job.deleted} removed · {job.failed} failed
                      </span>
                    </button>
                    {["queued", "running"].includes(job.state) && (
                      <button
                        className="text-button"
                        onClick={() =>
                          void api(`/jobs/${job.id}/cancel`, { method: "POST" })
                            .then(refresh)
                            .catch((err) => setError(err.message))
                        }
                      >
                        Cancel
                      </button>
                    )}
                    <time>
                      {new Date(
                        job.created_at.replace(" ", "T") + "Z",
                      ).toLocaleString()}
                    </time>
                  </div>
                ))
              ) : (
                <p className="muted">Add a folder and run your first scan.</p>
              )}
              {jobDetail && (
                <div className="job-detail">
                  <div className="section-heading">
                    <strong>Scan details</strong>
                    <button
                      aria-label="Close scan details"
                      onClick={() => setJobDetail(undefined)}
                    >
                      <X size={18} />
                    </button>
                  </div>
                  {!health?.media_enabled && (
                    <p>
                      Audio and video files are skipped because transcription is
                      off.
                    </p>
                  )}
                  {jobDetail.errors?.length ? (
                    jobDetail.errors.map((item, index) => (
                      <p key={index}>
                        <strong>{item.relative_path || "Folder scan"}</strong>
                        <br />
                        {item.code}: {item.message}
                      </p>
                    ))
                  ) : (
                    <p>No errors recorded for this scan.</p>
                  )}
                </div>
              )}
            </section>
            <div className="library-privacy">
              <ShieldCheck size={24} />
              <div>
                <h3>A private index, under your control.</h3>
                <p>
                  Removing a folder forgets its indexed text, vectors, and
                  previews. It does not delete your files.
                </p>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
