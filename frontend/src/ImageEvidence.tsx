import { useState } from "react";
import type { Locator } from "./types";

export function matchingBoxes(locator: Locator | undefined, query: string) {
  const width = locator?.width ?? 0;
  const height = locator?.height ?? 0;
  if (
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  )
    return [];
  const terms = new Set(query.toLowerCase().match(/[\p{L}\p{N}_]+/gu) || []);
  const seen = new Set<string>();
  return (locator?.boxes || [])
    .flatMap((box) => {
      if (typeof box.text !== "string") return [];
      if (
        ![box.x, box.y, box.width, box.height].every(Number.isFinite) ||
        box.width <= 0 ||
        box.height <= 0
      )
        return [];
      if (
        !(box.text.toLowerCase().match(/[\p{L}\p{N}_]+/gu) || []).some((word) =>
          terms.has(word),
        )
      )
        return [];
      const x = Math.max(0, box.x),
        y = Math.max(0, box.y);
      const w = Math.min(width, box.x + box.width) - x,
        h = Math.min(height, box.y + box.height) - y;
      if (w <= 0 || h <= 0) return [];
      const key = `${x}:${y}:${w}:${h}`;
      if (seen.has(key)) return [];
      seen.add(key);
      return [{ text: box.text, x, y, width: w, height: h }];
    })
    .slice(0, 200);
}

export function ImageEvidence({
  src,
  name,
  locator,
  query,
}: {
  src: string;
  name: string;
  locator?: Locator;
  query: string;
}) {
  const [highlight, setHighlight] = useState(true);
  const boxes = matchingBoxes(locator, query);
  return (
    <div className="image-evidence">
      <div className="image-evidence-canvas">
        <img className="image-preview" src={src} alt={`Preview of ${name}`} />
        {highlight && boxes.length > 0 && (
          <svg
            className="ocr-highlight-layer"
            viewBox={`0 0 ${locator!.width} ${locator!.height}`}
            aria-label="Matching words in image"
            role="img"
            preserveAspectRatio="none"
          >
            {boxes.map((box, index) => (
              <rect
                key={index}
                {...{
                  x: box.x,
                  y: box.y,
                  width: box.width,
                  height: box.height,
                }}
                vectorEffect="non-scaling-stroke"
              >
                <title>{box.text}</title>
              </rect>
            ))}
          </svg>
        )}
      </div>
      {boxes.length > 0 && (
        <div className="image-evidence-tools">
          <span>
            {boxes.length} matching {boxes.length === 1 ? "word" : "words"}
          </span>
          <button
            type="button"
            className="text-button"
            aria-pressed={highlight}
            onClick={() => setHighlight(!highlight)}
          >
            {highlight ? "Hide highlights" : "Show highlights"}
          </button>
        </div>
      )}
    </div>
  );
}
