import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowSquareOut, ShieldCheck, Spinner, X } from "@phosphor-icons/react";
import { api } from "../api";
import { ImageEvidence } from "../ImageEvidence";
import { MediaEvidence } from "../MediaEvidence";
import { usePreviewFocus } from "../hooks/usePreviewFocus";
import { extractionNote, locationLabel } from "../lib/evidence";
import type { Evidence, FileDetail, Result } from "../types";
import { FileIcon } from "./FileIcon";
import { HighlightedText } from "./HighlightedText";

export function FilePreview({
  selected,
  query,
  onClose,
}: {
  selected: Result;
  query: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<FileDetail>();
  const [activeEvidence, setActiveEvidence] = useState<Evidence>();
  const [previewError, setPreviewError] = useState("");
  const { panel, compact } = usePreviewFocus(onClose);
  useEffect(() => {
    const abort = new AbortController();
    api<FileDetail>(`/files/${selected.file_id}`, { signal: abort.signal })
      .then((value) => {
        if (!abort.signal.aborted) setDetail(value);
      })
      .catch((error) => {
        if (!abort.signal.aborted) setPreviewError(error.message);
      });
    return () => abort.abort();
  }, [selected.file_id]);
  const currentEvidence = activeEvidence || selected?.evidence[0];
  const loc = currentEvidence?.locator;
  const fallbackImage = detail?.chunks.find(
    (chunk) =>
      chunk.asset &&
      (selected?.modality === "image" ||
        (selected?.modality === "video" &&
          loc?.start_ms !== undefined &&
          chunk.locator.start_ms !== undefined &&
          chunk.locator.start_ms <= loc.start_ms &&
          (chunk.locator.end_ms ?? chunk.locator.start_ms) > loc.start_ms) ||
        (selected?.modality === "document" &&
          loc?.page &&
          chunk.locator.page === loc.page)),
  );
  const asset =
    currentEvidence?.asset_url ||
    (fallbackImage ? `/api/v1/assets/${fallbackImage.id}` : undefined);
  const picturedEvidence = selected?.evidence.find(
    (item) => item.asset_url === asset,
  );
  const picturedChunk = detail?.chunks.find(
    (chunk) =>
      chunk.id === picturedEvidence?.chunk_id ||
      asset === `/api/v1/assets/${chunk.id}`,
  );
  const imageLocator = picturedEvidence?.locator.boxes
    ? picturedEvidence.locator
    : detail?.chunks.find(
        (chunk) =>
          chunk.asset &&
          chunk.asset === picturedChunk?.asset &&
          chunk.locator.boxes,
      )?.locator;
  const previewUrl = selected
    ? `/api/v1/files/${selected.file_id}/preview${loc?.page ? "#page=" + loc.page : loc?.start_ms !== undefined ? "#t=" + loc.start_ms / 1000 : ""}`
    : "";

  const preview = (
    <>
      {compact && (
        <div
          className="preview-backdrop"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        ref={panel}
        className="preview-panel"
        aria-label="File preview"
        role={compact ? "dialog" : "complementary"}
        aria-modal={compact || undefined}
      >
        <div className="preview-header">
          <span>FILE PREVIEW</span>
          <button aria-label="Close preview" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="preview-file">
          <FileIcon modality={selected.modality} size={26} />
          <h2>{selected.name}</h2>
          <p>{selected.relative_path}</p>
        </div>
        {!detail && !previewError && (
          <div className="preview-loading" role="status">
            <Spinner className="spin" size={18} />
            Loading source evidence…
          </div>
        )}
        {previewError && (
          <p role="alert" className="small">
            {previewError}
          </p>
        )}
        {detail && !detail.source_available ? (
          <div className="alert warning-alert">
            This source has changed or is unavailable. Rescan to refresh it.
          </div>
        ) : (
          <>
            {asset && (
              <ImageEvidence
                key={asset}
                src={asset}
                name={selected.name}
                locator={imageLocator}
                query={query}
              />
            )}{" "}
            {detail &&
              (detail.modality === "audio" || detail.modality === "video") && (
                <MediaEvidence
                  key={selected.file_id}
                  src={`/api/v1/files/${selected.file_id}/preview`}
                  modality={detail.modality}
                  startMs={loc?.start_ms ?? 0}
                />
              )}
            <div className="preview-excerpts">
              {selected.warnings.map((warning) => (
                <p className="small muted" key={warning}>
                  Extraction note: {extractionNote(warning)}
                </p>
              ))}
              {selected.evidence
                .filter(
                  (item) => item.snippet || item.locator.start_ms !== undefined,
                )
                .map((item) => (
                  <div key={item.chunk_id}>
                    <div className="excerpt-location">
                      {item.locator.start_ms !== undefined ? (
                        <button
                          type="button"
                          className="text-button"
                          aria-label={`Jump to ${locationLabel(item.locator)}`}
                          aria-pressed={
                            currentEvidence?.chunk_id === item.chunk_id
                          }
                          onClick={() => setActiveEvidence(item)}
                        >
                          {locationLabel(item.locator)}
                        </button>
                      ) : (
                        locationLabel(item.locator)
                      )}
                      {item.symbol ? " · " + item.symbol : ""}
                    </div>
                    <pre>
                      <HighlightedText text={item.snippet} query={query} />
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
    </>
  );
  return compact ? createPortal(preview, document.body) : preview;
}
