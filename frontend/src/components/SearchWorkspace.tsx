import type { RefObject } from "react";
import {
  ArrowRight,
  FileCode,
  FileText,
  FolderOpen,
  Image,
  MagnifyingGlass,
  ShieldCheck,
  SlidersHorizontal,
  Spinner,
  Stack,
  X,
} from "@phosphor-icons/react";
import type { SearchOptions, SearchState } from "../hooks/useSearch";
import type { Result, Status } from "../types";
import { FilePreview } from "./FilePreview";
import { SearchFilters } from "./SearchFilters";
import { SearchResults } from "./SearchResults";

const examples = [
  { text: "Find my notes about semaphores", modality: "", Icon: FileText },
  {
    text: "Where is my Java implementation of Dijkstra?",
    modality: "code",
    Icon: FileCode,
  },
  { text: "AWS load balancing and target groups", modality: "", Icon: Stack },
  {
    text: "The screenshot explaining virtual memory",
    modality: "image",
    Icon: Image,
  },
];
const modalities = [
  ["", "All files"],
  ["document", "PDFs"],
  ["presentation", "PPTs"],
  ["code", "Code"],
  ["image", "Images"],
  ["audio", "Audio"],
  ["video", "Video"],
];

export function SearchWorkspace({
  state,
  status,
  input,
  selected,
  onSelect,
  onClosePreview,
  onSearch,
  onLibrary,
  filtersOpen,
  onFilters,
}: {
  state: SearchState;
  status?: Status;
  input: RefObject<HTMLInputElement | null>;
  selected?: Result;
  onSelect: (result: Result) => void;
  onClosePreview: () => void;
  onSearch: (value?: string, options?: Partial<SearchOptions>) => void;
  onLibrary: () => void;
  filtersOpen: boolean;
  onFilters: (value: boolean) => void;
}) {
  const { response, query, busy, options } = state;
  const filterCount = [
    options.rootFilter,
    options.pathFilter,
    options.modifiedAfter,
    options.rerank,
    options.mode !== "hybrid",
  ].filter(Boolean).length;
  const root = status?.roots.find(
    (item) => String(item.id) === options.rootFilter,
  );
  return (
    <div className={`search-page ${response || busy ? "has-results" : ""}`}>
      <div className="search-intro">
        <h1>
          {response || busy ? (
            "Find what you need."
          ) : (
            <>
              Your files.<span>A thought away.</span>
            </>
          )}
        </h1>
        <p>Search the way you think. Find the things you saved.</p>
      </div>
      <form
        className="search-form"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          onSearch();
        }}
      >
        <MagnifyingGlass size={23} />
        <input
          ref={input}
          aria-label="Search your files"
          value={query}
          onChange={(event) => state.setQuery(event.target.value)}
          placeholder="What are you looking for?"
          autoComplete="off"
        />
        <kbd aria-hidden="true">Ctrl K</kbd>
        <button
          className="search-submit"
          type={busy ? "button" : "submit"}
          aria-label={busy ? "Cancel search" : "Run search"}
          onClick={busy ? state.cancel : undefined}
        >
          {busy ? <X size={21} /> : <ArrowRight size={21} />}
        </button>
      </form>
      <div className="search-tools">
        <div className="type-filters" aria-label="File type filters">
          {modalities.map(([value, label]) => (
            <button
              key={value}
              className={`type-filter ${options.modality === value ? "selected" : ""}`}
              aria-pressed={options.modality === value}
              onClick={() => {
                state.updateOptions({ modality: value });
                if (response || busy) onSearch(query, { modality: value });
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          className={`filter-toggle ${filtersOpen || filterCount ? "selected" : ""}`}
          aria-expanded={filtersOpen}
          aria-controls="search-filters"
          onClick={() => onFilters(!filtersOpen)}
        >
          <SlidersHorizontal size={18} />
          Filters
          {filterCount > 0 && (
            <span className="filter-count">{filterCount}</span>
          )}
        </button>
      </div>
      {filtersOpen && (
        <SearchFilters
          options={options}
          roots={status?.roots ?? []}
          busy={busy}
          onChange={state.updateOptions}
          onApply={() => onSearch()}
          onReset={() => {
            const next = state.clearFilters();
            if (response) onSearch(query, next);
          }}
        />
      )}
      {root && (
        <div className="active-scope">
          <FolderOpen size={15} />
          <span title={root.path}>
            Searching in{" "}
            {root.path.replace(/\\/g, "/").split("/").filter(Boolean).at(-1)}
          </span>
          <button
            className="icon-button"
            aria-label="Search all folders"
            onClick={() => {
              state.updateOptions({ rootFilter: "" });
              if (response) onSearch(query, { rootFilter: "" });
            }}
          >
            <X size={14} />
          </button>
        </div>
      )}
      {busy && (
        <div className="search-loading" role="status">
          <Spinner className="spin" size={20} />
          <span>Looking through your library…</span>
        </div>
      )}
      {response?.warnings.map((warning) => (
        <div className="alert warning-alert" key={warning}>
          {warning}
        </div>
      ))}
      {response ? (
        <section className="results-area" aria-label="Results">
          <div className="results-heading" role="status">
            <span>
              <strong>{response.results.length}</strong> matching{" "}
              {response.results.length === 1 ? "file" : "files"}
              <span className="results-query"> for “{response.query}”</span>
            </span>
            <span>
              {response.latency_ms.toLocaleString()} ms · {response.mode}
            </span>
          </div>
          <div className={`results-grid ${selected ? "with-preview" : ""}`}>
            <SearchResults
              response={response}
              selected={selected}
              onSelect={onSelect}
              onLibrary={onLibrary}
            />
            {selected && (
              <FilePreview
                key={selected.file_id}
                selected={selected}
                query={response.query}
                onClose={onClosePreview}
              />
            )}
          </div>
        </section>
      ) : (
        !busy && (
          <div className="discovery">
            <div className="section-label">A few ways to start</div>
            <div className="example-grid">
              {examples.map(({ text, modality, Icon }) => (
                <button key={text} onClick={() => onSearch(text, { modality })}>
                  <span className="example-icon">
                    <Icon size={22} />
                  </span>
                  <span>{text}</span>
                  <ArrowRight size={17} />
                </button>
              ))}
            </div>
            <div className="library-summary">
              <FolderOpen size={21} />
              <span>
                {status?.files ? (
                  <>
                    <strong>{status.files.toLocaleString()} files</strong>{" "}
                    across {status.roots.length}{" "}
                    {status.roots.length === 1 ? "folder" : "folders"}. Ready
                    when you are.
                  </>
                ) : (
                  "Your library starts with a folder."
                )}
              </span>
              <button className="text-button" onClick={onLibrary}>
                {status?.files ? "Manage library" : "Add a folder"}
                <ArrowRight size={15} />
              </button>
            </div>
          </div>
        )
      )}
      <footer className="search-footer">
        <ShieldCheck size={14} />
        Local processing. No uploads. No cloud account.
      </footer>
    </div>
  );
}
