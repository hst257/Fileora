import type { Locator } from "../types";

export function locationLabel(locator: Locator): string {
  if (locator.slide)
    return `Slide ${locator.slide}${locator.section === "notes" ? " · Speaker notes" : locator.section === "image" ? " · Image text" : ""}`;
  if (locator.page) return `Page ${locator.page}`;
  if (locator.line_start)
    return `Lines ${locator.line_start}${locator.line_end && locator.line_end !== locator.line_start ? "-" + locator.line_end : ""}`;
  if (locator.start_ms !== undefined)
    return `${Math.floor(locator.start_ms / 60000)}:${String(Math.floor(locator.start_ms / 1000) % 60).padStart(2, "0")}`;
  return "Image";
}

export function extractionNote(warning: string): string {
  if (warning.startsWith("transcription_unavailable:"))
    return "Video frames are searchable, but the audio could not be transcribed. Check local speech setup and rescan.";
  if (warning === "no_audio_stream")
    return "This video has no audio track. Its sampled frames are searchable.";
  if (warning === "frame_limit_reached")
    return "Video sampling reached its frame limit. Later visuals may be missing.";
  const partial = warning.match(/^presentation_ocr_partial:(\d+)_/);
  if (partial)
    return `Slide text is searchable. Image OCR stopped early; ${partial[1]} image placements were not processed.`;
  const unreadable = warning.match(/^slide_(\d+):IMAGE_UNREADABLE$/);
  if (unreadable)
    return `An embedded image on Slide ${unreadable[1]} could not be read. Slide text is still searchable.`;
  const timeout = warning.match(/^slide_(\d+):OCR_TIMEOUT$/);
  if (timeout)
    return `Image OCR on Slide ${timeout[1]} reached its time limit. Slide text is still searchable.`;
  return warning.replaceAll("_", " ");
}
