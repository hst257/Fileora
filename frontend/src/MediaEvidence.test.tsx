import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { MediaEvidence } from "./MediaEvidence";

afterEach(cleanup);

it("seeks on metadata and when the matching timestamp changes without autoplay", () => {
  const { rerender } = render(
    <MediaEvidence src="/recording" modality="audio" startMs={30000} />,
  );
  const audio = screen.getByLabelText(
    "Audio evidence player",
  ) as HTMLAudioElement;
  Object.defineProperties(audio, {
    readyState: { value: 1 },
    duration: { value: 120 },
  });
  fireEvent.loadedMetadata(audio);
  expect(audio.currentTime).toBe(30);
  rerender(<MediaEvidence src="/recording" modality="audio" startMs={65000} />);
  expect(audio.currentTime).toBe(65);
  expect(audio.autoplay).toBe(false);
  expect(audio).toHaveAttribute("preload", "metadata");
});

it("bounds seek targets and gives a recovery message for unsupported playback", () => {
  const { rerender } = render(
    <MediaEvidence src="/recording" modality="video" startMs={-5000} />,
  );
  const video = screen.getByLabelText(
    "Video evidence player",
  ) as HTMLVideoElement;
  Object.defineProperties(video, {
    readyState: { value: 1 },
    duration: { value: 10 },
  });
  fireEvent.loadedMetadata(video);
  expect(video.currentTime).toBe(0);
  rerender(
    <MediaEvidence src="/recording" modality="video" startMs={999000} />,
  );
  expect(video.currentTime).toBeCloseTo(9.99);
  fireEvent.error(video);
  expect(screen.getByRole("alert")).toHaveTextContent("Open original");
  rerender(<MediaEvidence src="/another" modality="video" startMs={0} />);
  expect(screen.queryByRole("alert")).toBeNull();
});
