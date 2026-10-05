import type { ReactNode } from "react";
import {
  Desktop,
  Folder,
  FolderOpen,
  MagnifyingGlass,
  Moon,
  Plus,
  ShieldCheck,
  Spinner,
  Stack,
  Sun,
  X,
} from "@phosphor-icons/react";
import type { Appearance } from "../hooks/useAppearance";
import type { Status } from "../types";

export type View = "search" | "library";

export function WorkspaceShell({
  view,
  onView,
  status,
  connected,
  indexing,
  rootFilter,
  onRoot,
  error,
  onDismiss,
  appearance,
  onAppearance,
  children,
}: {
  view: View;
  onView: (view: View) => void;
  status?: Status;
  connected: boolean;
  indexing: boolean;
  rootFilter: string;
  onRoot: (id: string) => void;
  error: string;
  onDismiss: () => void;
  appearance: Appearance;
  onAppearance: (value: Appearance) => void;
  children: ReactNode;
}) {
  const AppearanceIcon =
    appearance === "dark" ? Moon : appearance === "light" ? Sun : Desktop;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace">
        Skip to content
      </a>
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault();
            onView("search");
          }}
        >
          <FolderOpen weight="fill" size={28} />
          <span>
            fileora<span className="brand-dot">.</span>
          </span>
        </a>
        <p className="workspace-label">Personal workspace</p>
        <nav aria-label="Main navigation">
          <button
            className={`nav-item ${view === "search" ? "active" : ""}`}
            aria-current={view === "search" ? "page" : undefined}
            onClick={() => onView("search")}
          >
            <MagnifyingGlass size={20} />
            Search<kbd aria-hidden="true">Ctrl K</kbd>
          </button>
          <button
            className={`nav-item ${view === "library" ? "active" : ""}`}
            aria-current={view === "library" ? "page" : undefined}
            onClick={() => onView("library")}
          >
            <Stack size={20} />
            My library<span className="nav-count">{status?.files ?? 0}</span>
          </button>
        </nav>
        <div className="sidebar-folders">
          <div className="section-label">
            Indexed folders
            <button
              className="icon-button"
              aria-label="Add a folder"
              onClick={() => onView("library")}
            >
              <Plus size={16} />
            </button>
          </div>
          <div className="folder-navigation">
            {status?.roots.length ? (
              status.roots.map((root) => (
                <button
                  key={root.id}
                  className={`folder-nav ${rootFilter === String(root.id) ? "active" : ""}`}
                  aria-pressed={rootFilter === String(root.id)}
                  title={root.path}
                  onClick={() => onRoot(String(root.id))}
                >
                  <Folder size={17} />
                  <span>
                    {root.path
                      .replace(/\\/g, "/")
                      .split("/")
                      .filter(Boolean)
                      .at(-1)}
                  </span>
                  {root.status !== "ready" && (
                    <span
                      className="dot warning"
                      aria-label="Folder unavailable"
                    />
                  )}
                </button>
              ))
            ) : (
              <p className="muted small">
                Choose the folders you want to search.
              </p>
            )}
          </div>
        </div>
        <div className="sidebar-bottom">
          <label className="appearance-control">
            <AppearanceIcon size={18} />
            <span>Appearance</span>
            <select
              aria-label="Appearance"
              value={appearance}
              onChange={(event) =>
                onAppearance(event.target.value as Appearance)
              }
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
          <div className="privacy-note">
            <ShieldCheck size={22} />
            <div>
              <strong>On your device</strong>
              <p>Your files stay with you.</p>
            </div>
          </div>
          <div className="connection" role="status">
            <span className={`dot ${connected ? "online" : ""}`} />
            {connected
              ? "Local service connected"
              : "Connecting to local service"}
          </div>
        </div>
      </aside>
      <main className="main" id="workspace" tabIndex={-1}>
        <header className="topbar">
          <span className="breadcrumb">
            Workspace<span className="slash">/</span>
            <strong>{view === "search" ? "Search" : "My library"}</strong>
          </span>
          <div className="topbar-status">
            {indexing ? (
              <>
                <Spinner className="spin" size={16} />
                Indexing files
              </>
            ) : (
              <>
                <ShieldCheck size={16} />
                {connected ? "Private by design" : "Service unavailable"}
              </>
            )}
          </div>
        </header>
        {error && (
          <div className="alert error" role="alert">
            <span>{error}</span>
            <button
              className="icon-button"
              aria-label="Dismiss error"
              onClick={onDismiss}
            >
              <X size={18} />
            </button>
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
