import {
  ArrowDown,
  Folder,
  FolderOpen,
  Spinner,
  Trash,
} from "@phosphor-icons/react";
import type { LibraryState } from "../hooks/useLibrary";

export function FoldersPanel({
  library,
  onForget,
}: {
  library: LibraryState;
  onForget: (id: number) => Promise<void>;
}) {
  const {
    status,
    health,
    indexing,
    libraryBusy,
    pendingMedia,
    rootPath,
    setRootPath,
    addRoot,
    rescan,
  } = library;
  return (
    <section className="folder-section">
      <div className="section-heading">
        <h2>Folders</h2>
        <div className="actions">
          <button
            className="secondary-button"
            disabled={
              indexing ||
              libraryBusy ||
              pendingMedia !== undefined ||
              !health ||
              !status?.roots.length
            }
            onClick={() => void rescan(true)}
          >
            Verify all files
          </button>
          <button
            className="primary-button"
            disabled={
              indexing ||
              libraryBusy ||
              pendingMedia !== undefined ||
              !health ||
              !status?.roots.length
            }
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
      <form className="add-folder" onSubmit={(event) => void addRoot(event)}>
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
          disabled={libraryBusy || indexing || !health || !rootPath.trim()}
        >
          Add folder
        </button>
      </form>
      <p className="small muted">
        Only selected folders are indexed. Hidden folders, dependencies, and
        common secret folders are skipped.
      </p>
      <div className="folder-list">
        {status && !status.roots.length && (
          <div className="folder-empty">
            <FolderOpen size={28} />
            <p>Add a folder to build your library.</p>
          </div>
        )}
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
              disabled={indexing || libraryBusy || !health}
              onClick={() => void onForget(root.id)}
            >
              <Trash size={19} />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
