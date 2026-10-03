"""Measure scan overhead on an authored lexical-only corpus; no personal files or models."""

from __future__ import annotations

import argparse
import cProfile
import json
import platform
import statistics
import time
from pathlib import Path

from fileora.config import Settings
from fileora.extraction import extract
from fileora.service import Service


class LexicalModels:
    device = "cpu"

    def available(self, model):
        return False

    def tokenizer(self):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--files", type=int, default=1000)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    if args.files < 1 or args.repeat < 1:
        parser.error("--files and --repeat must be positive")
    if not args.label or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for c in args.label
    ):
        parser.error(
            "--label must contain only letters, digits, hyphens, and underscores"
        )
    base = Path(".fileora/rescan-benchmark").resolve()
    folder = base / ("corpus" if args.files == 1000 else f"corpus-{args.files}")
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(args.files):
        path = folder / f"note-{i:05}.md"
        if not path.exists():
            path.write_text(
                f"Document {i}. Semaphores protect critical sections. Paging maps virtual memory.\n",
                encoding="utf-8",
            )
    service = Service(
        Settings(
            data_dir=base
            / ("runtime" if args.files == 1000 else f"runtime-{args.files}")
        ),
        LexicalModels(),
        extractor=extract,
    )
    service.instance.acquire()
    try:
        service.indexer.add_root(str(folder))
        service.indexer.run(service.indexer.create_job())
        reports = {}
        for name, verify in (("quick", False), ("verify", True)):
            samples = []
            profile = cProfile.Profile()
            for _ in range(args.repeat):
                started = time.perf_counter()
                profile.enable()
                job = service.indexer.run(service.indexer.create_job(verify=verify))
                profile.disable()
                elapsed = time.perf_counter() - started
                assert (
                    job["failed"] == 0
                    and job["indexed"] == 0
                    and job["skipped"] == args.files
                ), job
                samples.append(elapsed)
                print(
                    json.dumps(
                        {
                            "label": args.label,
                            "scan": name,
                            "seconds": elapsed,
                            "skipped": job["skipped"],
                        }
                    ),
                    flush=True,
                )
            profile.dump_stats(str(base / f"{args.label}-{name}.prof"))
            reports[name] = {
                "seconds": samples,
                "median_seconds": statistics.median(samples),
            }
        output = {
            "label": args.label,
            "files": args.files,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "scope": "authored small Markdown files; lexical-only; filesystem cache warm; cProfile enabled",
            "scans": reports,
        }
        Path(f"evaluation/reports/rescan-{args.label}.json").write_text(
            json.dumps(output, indent=2), encoding="utf-8"
        )
    finally:
        service.instance.release()


if __name__ == "__main__":
    main()
