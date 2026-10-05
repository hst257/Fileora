import { ArrowRight, MagnifyingGlass } from "@phosphor-icons/react";
import { locationLabel } from "../lib/evidence";
import type { Result, SearchResponse } from "../types";
import { FileIcon } from "./FileIcon";
import { HighlightedText } from "./HighlightedText";

export function SearchResults({
  response,
  selected,
  onSelect,
  onLibrary,
}: {
  response: SearchResponse;
  selected?: Result;
  onSelect: (result: Result) => void;
  onLibrary: () => void;
}) {
  return (
    <div className="results-list" aria-label="Search results">
      {response.results.length ? (
        response.results.map((result, index) => (
          <button
            key={result.file_id}
            className={`result-row ${selected?.file_id === result.file_id ? "selected" : ""}`}
            aria-pressed={selected?.file_id === result.file_id}
            onClick={() => onSelect(result)}
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
              <p className="result-path" title={result.relative_path}>
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
                  <span className="match-label">
                    {result.match_kind === "terms"
                      ? "Term match"
                      : result.match_kind === "semantic"
                        ? "Related by meaning"
                        : "Visual similarity"}
                  </span>
                )}
                <span>{locationLabel(result.evidence[0]?.locator || {})}</span>
                {result.evidence[0]?.symbol && (
                  <span>{result.evidence[0].symbol}</span>
                )}
                {result.aliases.length > 0 && (
                  <span>{result.aliases.length + 1} copies</span>
                )}
                <span className="match-order">Match #{index + 1}</span>
              </div>
            </div>
            <ArrowRight className="row-arrow" size={18} />
          </button>
        ))
      ) : (
        <div className="empty-results">
          <div className="empty-icon">
            <MagnifyingGlass size={28} />
          </div>
          <h2>No matches this time.</h2>
          <p>Try a different phrase, fewer filters, or index another folder.</p>
          <button className="text-button" onClick={onLibrary}>
            Check your library
            <ArrowRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
