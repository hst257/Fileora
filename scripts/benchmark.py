"""Run like-for-like CPU baselines using genuine local models, never test encoders."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fileora.config import Settings
from fileora.evaluation import run_evaluation
from fileora.service import Service


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path(".fileora/benchmark"))
    parser.add_argument("--models-dir", type=Path, default=Path(".fileora/models"))
    parser.add_argument(
        "--text-model", default="sentence-transformers/all-MiniLM-L6-v2"
    )
    parser.add_argument("--rerank", action="store_true")
    args = parser.parse_args()
    settings = Settings(
        data_dir=args.data_dir,
        models_dir=args.models_dir,
        device="cpu",
        text_model=args.text_model,
        enable_ocr=True,
        enable_vision=True,
    )
    service = Service(settings)
    service.instance.acquire()
    try:
        reports = Path("evaluation/reports")
        reports.mkdir(parents=True, exist_ok=True)
        prefix = "bge" if "bge" in args.text_model else "minilm"
        for mode in ("hybrid",) if args.rerank else ("lexical", "semantic", "hybrid"):
            settings.enable_vision = (
                False  # Text comparison includes OCR but isolates CLIP.
            )
            service.models.unload()  # Record a process-local cold model load for each run.
            report = run_evaluation(
                service,
                Path("evaluation/queries.jsonl"),
                Path("evaluation/judgments.jsonl"),
                mode=mode,
                rerank=args.rerank,
            )
            name = f"{prefix}-{mode}{'-rerank' if args.rerank else ''}"
            (reports / f"{name}.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "report": name,
                        "metrics": report["metrics"],
                        "p95_ms": report["warm_p95_ms"],
                    }
                ),
                flush=True,
            )
        if args.rerank:
            return
        for label, mode, vision in (
            ("ocr", "lexical", False),
            ("clip", "semantic", True),
            ("fused", "hybrid", True),
        ):
            settings.enable_vision = vision
            service.models.unload()
            report = run_evaluation(
                service,
                Path("evaluation/image_queries.jsonl"),
                Path("evaluation/image_judgments.jsonl"),
                mode=mode,
                channels="vision" if label == "clip" else "all",
            )
            (reports / f"{prefix}-images-{label}.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "report": f"images-{label}",
                        "metrics": report["metrics"],
                        "p95_ms": report["warm_p95_ms"],
                    }
                ),
                flush=True,
            )
    finally:
        service.instance.release()


if __name__ == "__main__":
    main()
