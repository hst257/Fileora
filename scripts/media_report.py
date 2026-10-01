"""Evaluate the synthetic speech fixture and calculate token-normalized WER."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fileora.config import Settings
from fileora.evaluation import run_evaluation
from fileora.service import Service


def word_error_rate(reference: str, hypothesis: str) -> dict:
    reference_words = re.findall(r"[a-z0-9]+", reference.lower())
    hypothesis_words = re.findall(r"[a-z0-9]+", hypothesis.lower())
    previous = list(range(len(hypothesis_words) + 1))
    for i, left in enumerate(reference_words, 1):
        current = [i]
        for j, right in enumerate(hypothesis_words, 1):
            current.append(
                min(previous[j] + 1, current[-1] + 1, previous[j - 1] + (left != right))
            )
        previous = current
    return {
        "wer": previous[-1] / len(reference_words),
        "edits": previous[-1],
        "reference_words": len(reference_words),
        "hypothesis_words": len(hypothesis_words),
    }


def main():
    service = Service(
        Settings(data_dir=Path(".fileora"), device="cpu", enable_media=True)
    )
    service.instance.acquire()
    try:
        report = run_evaluation(
            service,
            Path("evaluation/media_queries.jsonl"),
            Path("evaluation/media_judgments.jsonl"),
        )
        rows = service.store.rows(
            "SELECT c.text,c.locator FROM chunks c JOIN files f ON f.active_revision_id=c.revision_id WHERE f.name='computer_science_lecture.wav' AND c.kind='transcript' ORDER BY c.ordinal"
        )
        gold = json.loads(
            Path("evaluation/media_gold.json").read_text(encoding="utf-8")
        )
        reference = " ".join(section["text"] for section in gold)
        hypothesis = " ".join(row["text"] for row in rows)
        report["speech"] = {
            **word_error_rate(reference, hypothesis),
            "reference": reference,
            "hypothesis": hypothesis,
            "model": "Systran/faster-whisper-base.en",
            "segments": len(rows),
        }
        output = Path("evaluation/reports/media.json")
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "metrics": report["metrics"],
                    "speech": report["speech"],
                    "p95_ms": report["warm_p95_ms"],
                },
                indent=2,
            )
        )
    finally:
        service.instance.release()


if __name__ == "__main__":
    main()
