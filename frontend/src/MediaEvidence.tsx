import { useEffect, useRef, useState } from "react";

export function MediaEvidence({
  src,
  modality,
  startMs,
}: {
  src: string;
  modality: "audio" | "video";
  startMs: number;
}) {
  const player = useRef<HTMLMediaElement>(null);
  const [failed, setFailed] = useState(false);
  function seek() {
    const element = player.current;
    if (!element || element.readyState === 0) return;
    const seconds = Number.isFinite(startMs) ? Math.max(0, startMs / 1000) : 0;
    element.currentTime = Number.isFinite(element.duration)
      ? Math.min(seconds, Math.max(0, element.duration - 0.01))
      : seconds;
  }
  useEffect(() => {
    seek();
  }, [startMs, src]);
  useEffect(() => {
    setFailed(false);
  }, [src]);
  const props = {
    controls: true,
    preload: "metadata",
    src,
    onLoadedMetadata: seek,
    onError: () => setFailed(true),
    "aria-label": `${modality === "video" ? "Video" : "Audio"} evidence player`,
  };
  return (
    <div className="media-evidence">
      {modality === "video" ? (
        <video {...props} ref={player as React.RefObject<HTMLVideoElement>} />
      ) : (
        <audio {...props} ref={player as React.RefObject<HTMLAudioElement>} />
      )}
      {failed && (
        <p role="alert" className="small">
          Your browser could not play this recording. Use Open original to
          download it and play it locally.
        </p>
      )}
    </div>
  );
}
