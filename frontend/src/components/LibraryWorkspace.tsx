import { ShieldCheck } from "@phosphor-icons/react";
import type { LibraryState } from "../hooks/useLibrary";
import { FoldersPanel } from "./FoldersPanel";
import { IndexingActivity } from "./IndexingActivity";
import { LibraryFeatures } from "./LibraryFeatures";

export function LibraryWorkspace({
  library,
  onForget,
}: {
  library: LibraryState;
  onForget: (id: number) => Promise<void>;
}) {
  const { status } = library;
  return (
    <div className="library-page">
      <header className="library-intro">
        <h1>A home for what you know.</h1>
        <p className="page-description">
          Choose your folders. Fileora keeps a searchable index on this device.
        </p>
      </header>
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
      <div className="library-layout">
        <div className="library-primary">
          <FoldersPanel library={library} onForget={onForget} />
          <IndexingActivity library={library} />
        </div>
        <LibraryFeatures library={library} />
      </div>
      <div className="library-privacy">
        <ShieldCheck size={24} />
        <div>
          <h3>A private index, under your control.</h3>
          <p>
            Removing a folder forgets its indexed text, vectors, and previews.
            It does not delete your files.
          </p>
        </div>
      </div>
    </div>
  );
}
