import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { SearchResponse } from "../types";

export type SearchOptions = {
  modality: string;
  mode: string;
  rootFilter: string;
  pathFilter: string;
  modifiedAfter: string;
  rerank: boolean;
};
const defaults: SearchOptions = {
  modality: "",
  mode: "hybrid",
  rootFilter: "",
  pathFilter: "",
  modifiedAfter: "",
  rerank: false,
};

export function useSearch() {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<SearchOptions>(defaults);
  const [response, setResponse] = useState<SearchResponse>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | undefined>(undefined);

  useEffect(() => () => controller.current?.abort(), []);

  function updateOptions(value: Partial<SearchOptions>) {
    setOptions((current) => ({ ...current, ...value }));
  }

  async function search(value = query, overrides: Partial<SearchOptions> = {}) {
    if (!value.trim()) return;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const next = { ...options, ...overrides };
    setOptions(next);
    setQuery(value);
    setBusy(true);
    setResponse(undefined);
    setError("");
    const filters: Record<string, unknown> = {};
    if (next.modality) filters.modality = next.modality;
    if (next.rootFilter) filters.root_id = Number(next.rootFilter);
    if (next.pathFilter) filters.path_prefix = next.pathFilter;
    try {
      if (next.modifiedAfter)
        filters.modified_after = new Date(
          next.modifiedAfter + "T00:00:00",
        ).toISOString();
      const result = await api<SearchResponse>("/search", {
        method: "POST",
        body: JSON.stringify({
          query: value,
          mode: next.mode,
          filters,
          rerank: next.rerank,
          limit: 10,
        }),
        signal: abort.signal,
      });
      if (!abort.signal.aborted) setResponse(result);
    } catch (err) {
      if (!abort.signal.aborted) setError((err as Error).message);
    } finally {
      if (controller.current === abort) setBusy(false);
    }
  }

  function cancel() {
    controller.current?.abort();
    setBusy(false);
  }
  function clearFilters() {
    const next = { ...defaults, modality: options.modality };
    setOptions(next);
    return next;
  }

  return {
    query,
    setQuery,
    options,
    updateOptions,
    response,
    setResponse,
    busy,
    error,
    setError,
    search,
    cancel,
    clearFilters,
  };
}

export type SearchState = ReturnType<typeof useSearch>;
