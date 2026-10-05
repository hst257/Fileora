import { useCallback, useEffect, useRef, useState } from "react";
import { LibraryWorkspace } from "./components/LibraryWorkspace";
import { SearchWorkspace } from "./components/SearchWorkspace";
import { WorkspaceShell } from "./components/WorkspaceShell";
import type { View } from "./components/WorkspaceShell";
import { useAppearance } from "./hooks/useAppearance";
import { useLibrary } from "./hooks/useLibrary";
import { useSearch } from "./hooks/useSearch";
import type { SearchOptions } from "./hooks/useSearch";
import type { Result } from "./types";

// Preserve the public helper exports used by existing consumers/tests.
export { extractionNote, locationLabel } from "./lib/evidence";

export function App() {
  const [view, setView] = useState<View>("search");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [selected, setSelected] = useState<Result>();
  const input = useRef<HTMLInputElement>(null);
  const library = useLibrary();
  const search = useSearch();
  const { appearance, setAppearance } = useAppearance();
  const closePreview = useCallback(() => setSelected(undefined), []);

  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSelected(undefined);
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

  function runSearch(
    value = search.query,
    options: Partial<SearchOptions> = {},
  ) {
    if (!value.trim()) {
      input.current?.focus();
      return;
    }
    setView("search");
    setSelected(undefined);
    library.setError("");
    void search.search(value, options);
  }

  async function forgetRoot(id: number) {
    if (await library.forget(id)) {
      search.cancel();
      search.setResponse(undefined);
      setSelected(undefined);
      if (search.options.rootFilter === String(id))
        search.updateOptions({ rootFilter: "" });
    }
  }

  function changeView(next: View) {
    setSelected(undefined);
    setView(next);
  }

  return (
    <WorkspaceShell
      view={view}
      onView={changeView}
      status={library.status}
      connected={Boolean(library.health)}
      indexing={library.indexing}
      rootFilter={search.options.rootFilter}
      onRoot={(id) => {
        setView("search");
        setSelected(undefined);
        setFiltersOpen(true);
        search.updateOptions({ rootFilter: id });
        if (search.response || search.busy)
          runSearch(search.query, { rootFilter: id });
      }}
      error={library.error || search.error}
      onDismiss={() => {
        library.setError("");
        search.setError("");
      }}
      appearance={appearance}
      onAppearance={setAppearance}
    >
      {view === "search" ? (
        <SearchWorkspace
          state={search}
          status={library.status}
          input={input}
          selected={selected}
          onSelect={setSelected}
          onClosePreview={closePreview}
          onSearch={runSearch}
          onLibrary={() => changeView("library")}
          filtersOpen={filtersOpen}
          onFilters={setFiltersOpen}
        />
      ) : (
        <LibraryWorkspace library={library} onForget={forgetRoot} />
      )}
    </WorkspaceShell>
  );
}
