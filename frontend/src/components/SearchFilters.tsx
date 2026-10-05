import { ArrowRight, X } from "@phosphor-icons/react";
import type { SearchOptions } from "../hooks/useSearch";
import type { Root } from "../types";

export function SearchFilters({
  options,
  roots,
  onChange,
  onApply,
  onReset,
  busy,
}: {
  options: SearchOptions;
  roots: Root[];
  onChange: (value: Partial<SearchOptions>) => void;
  onApply: () => void;
  onReset: () => void;
  busy: boolean;
}) {
  return (
    <section
      id="search-filters"
      className="filter-panel"
      aria-label="Advanced search filters"
    >
      <label>
        Retrieval
        <select
          aria-label="Retrieval mode"
          value={options.mode}
          onChange={(event) => onChange({ mode: event.target.value })}
        >
          <option value="hybrid">Hybrid</option>
          <option value="semantic">Semantic</option>
          <option value="lexical">Exact terms</option>
        </select>
      </label>
      <label>
        Folder
        <select
          value={options.rootFilter}
          onChange={(event) => onChange({ rootFilter: event.target.value })}
        >
          <option value="">All folders</option>
          {roots.map((root) => (
            <option key={root.id} value={root.id}>
              {root.path}
            </option>
          ))}
        </select>
      </label>
      <label>
        Path starts with
        <input
          value={options.pathFilter}
          onChange={(event) => onChange({ pathFilter: event.target.value })}
          placeholder="notes/"
        />
      </label>
      <label>
        Modified after
        <input
          type="date"
          value={options.modifiedAfter}
          onChange={(event) => onChange({ modifiedAfter: event.target.value })}
        />
      </label>
      <div className="filter-actions">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={options.rerank}
            onChange={(event) => onChange({ rerank: event.target.checked })}
          />
          Rerank passages
        </label>
        <div className="actions">
          <button className="text-button" onClick={onReset}>
            <X size={14} />
            Reset filters
          </button>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={onApply}
          >
            Apply filters
            <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </section>
  );
}
