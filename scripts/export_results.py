"""Publish only reports from the authored fixture runs, never a personal catalog."""

from __future__ import annotations

import hashlib
import json
import shutil
from importlib.metadata import version
from pathlib import Path


def main():
    source, destination = Path("evaluation/reports"), Path("evaluation/results")
    destination.mkdir(parents=True, exist_ok=True)
    names = [
        "minilm-lexical",
        "minilm-semantic",
        "minilm-hybrid",
        "minilm-hybrid-rerank",
        "bge-lexical",
        "bge-semantic",
        "bge-hybrid",
        "minilm-images-ocr",
        "minilm-images-clip",
        "minilm-images-fused",
        "bge-images-fused",
        "media",
        "bge-index",
        "scale-vectors",
    ]
    summaries = []
    for name in names:
        path = source / f"{name}.json"
        if not path.exists():
            raise SystemExit(
                f"Missing {path}; run the documented fixture benchmark first"
            )
        report = json.loads(path.read_text(encoding="utf-8"))
        shutil.copyfile(path, destination / path.name)
        summaries.append(
            {
                "name": name,
                **{
                    key: report[key]
                    for key in (
                        "metrics",
                        "warm_p50_ms",
                        "warm_p95_ms",
                        "cold_search_ms",
                        "peak_process_rss_bytes",
                        "splits",
                        "corpus_hash",
                        "dataset_hash",
                        "profiles",
                        "speech",
                        "timings",
                        "count",
                        "populate_seconds",
                        "build_snapshot_seconds",
                    )
                    if key in report
                },
            }
        )
    environment = {
        package: version(package)
        for package in (
            "torch",
            "sentence-transformers",
            "transformers",
            "faster-whisper",
            "ctranslate2",
            "av",
            "pillow",
            "numpy",
            "faiss-cpu",
        )
    }
    result = {
        "scope": "Authored CC0 fixture runs only; no private user library",
        "fixture_manifest_sha256": hashlib.sha256(
            Path("evaluation/corpus_manifest.json").read_bytes()
        ).hexdigest(),
        "model_dependencies": environment,
        "runs": summaries,
    }
    (destination / "summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(f"Published {len(summaries)} authored-fixture reports")


if __name__ == "__main__":
    main()
