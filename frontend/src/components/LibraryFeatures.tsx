import { FileText } from "@phosphor-icons/react";
import type { LibraryState } from "../hooks/useLibrary";

export function LibraryFeatures({ library }: { library: LibraryState }) {
  const {
    health,
    indexing,
    pendingMedia,
    pendingWatch,
    watchBusy,
    setMedia,
    setWatching,
  } = library;
  return (
    <aside className="library-features" aria-label="Library settings">
      <h2 className="features-heading">Library settings</h2>{" "}
      <section className="watch-section" aria-label="Automatic library updates">
        <div className="section-heading">
          <div>
            <h2>Keep my library current</h2>
            <p className="small muted">
              Automatically index edits, new files, renames, and deletions in
              your selected folders while Fileora is running.
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
            {Math.round(health.watch.reconcile_seconds / 60)} minutes. Your
            preference is saved on this device. Turning this off lets the
            current scan finish.
          </p>
        )}
        {health?.watch?.errors.map((item) => (
          <p className="small watch-warning" key={item.path}>
            Could not watch {item.path}. It will be checked during the next full
            scan.
          </p>
        ))}
      </section>
      <section
        className="image-search-status"
        aria-label="Image search capabilities"
      >
        <h2>Search inside images</h2>
        <p className="small muted">
          Find screenshots by their words, or describe what you remember seeing.
          Processing stays on this device.
        </p>
        <div className="image-capabilities">
          <div>
            <strong>Text in images</strong>
            <span>
              {!health
                ? "Checking…"
                : !health.ocr_enabled
                  ? "Off"
                  : health.ocr_ready
                    ? "Available locally"
                    : "OCR setup needed"}
            </span>
          </div>
          <div>
            <strong>Images by description</strong>
            <span>
              {!health
                ? "Checking…"
                : !health.vision_enabled
                  ? "Off"
                  : health.vision_ready
                    ? "Available locally"
                    : "CLIP model setup needed"}
            </span>
          </div>
        </div>
        <details className="feature-help">
          <summary>How image search works</summary>{" "}
          <p className="small muted">
            Use the Images filter with a phrase such as “a diagram of virtual
            memory”. A single keyword requires a text match; Semantic mode can
            explore related images.
          </p>
        </details>
        {health &&
          ((health.ocr_enabled && !health.ocr_ready) ||
            (health.vision_enabled && !health.vision_ready)) && (
            <p className="small">
              Stop Fileora and run setup to prepare the missing local tools,
              then restart and rescan.
            </p>
          )}
      </section>
      <section
        className="image-search-status"
        aria-label="Media search capabilities"
      >
        <h2>Search inside recordings</h2>
        <label className="watch-control">
          <input
            type="checkbox"
            role="switch"
            aria-label="Transcribe audio and video"
            checked={pendingMedia ?? health?.media_enabled ?? false}
            disabled={!health || indexing || pendingMedia !== undefined}
            onChange={(event) => void setMedia(event.target.checked)}
          />
          Transcribe audio and video
        </label>
        <p className="small muted">
          This choice is saved for future launches. After enabling it, rescan
          your recording folders. Wait for scans to finish before changing it.
        </p>
        <p className="small muted">
          Transcription runs locally and can take time on CPU.
        </p>
        <div className="image-capabilities">
          <div>
            <strong>Spoken words</strong>
            <span>
              {!health
                ? "Checking…"
                : !health.media_enabled
                  ? "Off"
                  : health.transcription_ready
                    ? "Available locally"
                    : "Speech setup needed"}
            </span>
          </div>
          <div>
            <strong>Video frames</strong>
            <span>
              {!health
                ? "Checking…"
                : !health.media_enabled
                  ? "Off"
                  : health.media_ready
                    ? "Available locally"
                    : "Media setup needed"}
            </span>
          </div>
        </div>
        <details className="feature-help">
          <summary>Recording search tips</summary>{" "}
          <p className="small muted">
            Use Audio or Video to narrow your search. Open a result and choose a
            timestamp to jump to its evidence; playback starts when you press
            Play.
          </p>
        </details>
        {health &&
          (!health.media_enabled ||
            !health.transcription_ready ||
            !health.media_ready) && (
            <p className="small">
              Turn on transcription above. If local speech tools are missing,
              stop Fileora and run <code>scripts/setup.ps1 -Media</code>, then
              restart and rescan your recording folders.
            </p>
          )}
      </section>
      {health && !health.semantic_ready && (
        <div className="model-notice">
          <FileText size={22} />
          <div>
            <strong>Start with exact terms, or prepare semantic search.</strong>
            <p>
              Stop Fileora, run this in your activated environment, then restart
              and rescan:
            </p>
            <code>
              {health?.model_setup_command ||
                "fileora models download sentence-transformers/all-MiniLM-L6-v2"}
            </code>
          </div>
        </div>
      )}
    </aside>
  );
}
