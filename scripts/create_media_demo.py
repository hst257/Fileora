"""Offline synthetic lecture fixture, with independently known section timestamps."""

from __future__ import annotations

import json
import math
import subprocess
import wave
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SECTIONS = [
    (
        "Semaphores",
        "A semaphore coordinates concurrent threads. The wait operation decrements a counter and may block a thread. The signal operation increments the counter and wakes a waiting thread. A binary semaphore protects a critical section.",
        [
            "semaphore wait operation",
            "threads waiting for a signal",
            "binary semaphore critical section",
            "increment semaphore counter",
            "coordinate concurrent threads",
            "decrement counter and block",
            "semaphore synchronization lecture",
        ],
    ),
    (
        "Paging",
        "Paging divides virtual memory into pages and physical memory into frames. A page table maps a virtual page to a physical frame. The translation lookaside buffer caches address translations. A page fault means a page must be loaded from storage.",
        [
            "lecture explaining paging",
            "virtual memory physical frames",
            "page table address mapping",
            "translation lookaside buffer",
            "page fault storage",
            "divide memory into pages",
            "cached address translations",
        ],
    ),
    (
        "Normalization",
        "Database normalization removes redundant data and update anomalies. A functional dependency means one attribute determines another. Third normal form removes transitive dependencies. A lossless decomposition preserves the original relation when the tables are joined.",
        [
            "database normalization lecture",
            "remove redundant data",
            "third normal form dependencies",
            "functional dependency attributes",
            "lossless table decomposition",
            "update anomalies in a database",
        ],
    ),
]


def narrated_video(video_path: Path, audio_path: Path, output_path: Path) -> None:
    """Mux authored speech into the slide fixture without re-encoding its video."""
    packets = []
    with (
        av.open(str(video_path)) as video,
        av.open(str(audio_path)) as audio,
        av.open(str(output_path), "w") as output,
    ):
        video_out = output.add_stream_from_template(video.streams.video[0])
        audio_out = output.add_stream("aac", rate=22050)
        audio_out.layout = "mono"
        for packet in video.demux(video=0):
            if packet.dts is not None:
                packet.stream = video_out
                packets.append(packet)
        for frame in audio.decode(audio=0):
            packets.extend(audio_out.encode(frame))
        packets.extend(audio_out.encode())
        for packet in sorted(
            packets, key=lambda packet: float(packet.dts * packet.time_base)
        ):
            output.mux(packet)


def main():
    folder = Path("evaluation/media_corpus").resolve()
    folder.mkdir(parents=True, exist_ok=True)
    temporary = Path(".fileora/media-fixtures").resolve()
    temporary.mkdir(parents=True, exist_ok=True)
    recordings, gold = [], []
    cursor = 0.0
    params = None
    for index, (title, text, queries) in enumerate(SECTIONS):
        txt, wav = (
            temporary / f"section-{index}.txt",
            temporary / f"section-{index}.wav",
        )
        txt.write_text(text, encoding="utf-8")
        subprocess.run(
            [
                "node",
                str(Path("scripts/speech/synthesize.mjs").resolve()),
                str(txt),
                str(wav),
            ],
            check=True,
        )
        with wave.open(str(wav), "rb") as audio:
            params = audio.getparams()
            data = audio.readframes(audio.getnframes())
            seconds = audio.getnframes() / audio.getframerate()
        recordings.append(data)
        gold.append(
            {
                "title": title,
                "text": text,
                "start_ms": int(cursor * 1000),
                "end_ms": int((cursor + seconds) * 1000),
                "queries": queries,
            }
        )
        cursor += seconds
    assert params
    audio_path = folder / "computer_science_lecture.wav"
    with wave.open(str(audio_path), "wb") as output:
        output.setparams(params)
        output.writeframes(b"".join(recordings))
    output = av.open(str(folder / "computer_science_lecture.mp4"), "w")
    video = output.add_stream("libx264", rate=1)
    video.width, video.height, video.pix_fmt = 960, 540, "yuv420p"
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = (
        ImageFont.truetype(str(font_path), 28)
        if font_path.exists()
        else ImageFont.load_default(size=28)
    )
    for second in range(math.ceil(cursor)):
        section = next(
            (s for s in gold if s["start_ms"] <= second * 1000 < s["end_ms"]), gold[-1]
        )
        image = Image.new("RGB", (960, 540), "#f7f6f3")
        draw = ImageDraw.Draw(image)
        import textwrap

        draw.text((55, 55), section["title"], font=font, fill="#2f342b")
        draw.multiline_text(
            (55, 125),
            textwrap.fill(section["text"], 56),
            font=font,
            fill="#4e5548",
            spacing=15,
        )
        frame = av.VideoFrame.from_ndarray(np.asarray(image), format="rgb24")
        for packet in video.encode(frame):
            output.mux(packet)
    for packet in video.encode():
        output.mux(packet)
    # The MP4 deliberately tests silent-video support; the WAV tests speech retrieval.
    output.close()
    narrated_video(
        folder / "computer_science_lecture.mp4",
        audio_path,
        folder / "computer_science_narrated.mp4",
    )
    queries, judgments = [], []
    for section in gold:
        for phrase in section["queries"]:
            qid = f"media-{len(queries) + 1}"
            queries.append(
                {
                    "id": qid,
                    "query": phrase,
                    "category": "lecture",
                    "family": section["title"],
                    "split": "dev",
                    "filters": {"modality": "audio"},
                }
            )
            judgments.append(
                {
                    "query_id": qid,
                    "path": audio_path.name,
                    "grade": 2,
                    "locator": {
                        "start_ms": section["start_ms"],
                        "end_ms": section["end_ms"],
                    },
                }
            )
    Path("evaluation/media_queries.jsonl").write_text(
        "\n".join(json.dumps(q) for q in queries) + "\n", encoding="utf-8"
    )
    Path("evaluation/media_judgments.jsonl").write_text(
        "\n".join(json.dumps(q) for q in judgments) + "\n", encoding="utf-8"
    )
    Path("evaluation/media_gold.json").write_text(
        json.dumps(gold, indent=2), encoding="utf-8"
    )
    print(
        f"Created a {cursor:.1f}s synthetic lecture, silent video, and {len(queries)} temporal queries"
    )


if __name__ == "__main__":
    main()
