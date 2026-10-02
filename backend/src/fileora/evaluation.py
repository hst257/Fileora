from __future__ import annotations

import hashlib
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path
from typing import Literal

import numpy as np

from fileora.resources import peak_rss_bytes
from fileora.retrieval import Filters, SearchRequest


def metrics(retrieved: list[str], relevant: set[str], k: int) -> dict[str, float]:
    unique = list(dict.fromkeys(retrieved))[:k]
    hits = [i + 1 for i, path in enumerate(unique) if path in relevant]
    return {
        "precision": len(hits) / k,
        "recall": len(hits) / len(relevant) if relevant else 0,
        "hit_rate": float(bool(hits)),
        "mrr": 1 / hits[0] if hits else 0,
    }


def ndcg(paths: list[str], grades: dict[str, int], k: int) -> float:
    unique = list(dict.fromkeys(paths))[:k]
    dcg = sum((2 ** grades.get(path, 0) - 1) / np.log2(i + 2) for i, path in enumerate(unique))
    ideal = sum(
        (2**grade - 1) / np.log2(i + 2)
        for i, grade in enumerate(sorted(grades.values(), reverse=True)[:k])
    )
    return float(dcg / ideal) if ideal else 0


def run_evaluation(
    service,
    queries_path: Path,
    judgments_path: Path,
    mode: Literal["semantic", "lexical", "hybrid"] = "hybrid",
    split: str | None = None,
    rerank: bool = False,
    repeat: int = 1,
    channels: Literal["all", "text", "vision"] = "all",
) -> dict:
    queries = [
        json.loads(line)
        for line in queries_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    judgments = [
        json.loads(line)
        for line in judgments_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_query: dict = {}
    for judgment in judgments:
        by_query.setdefault(judgment["query_id"], []).append(judgment)
    records, timings = [], []
    cold_latency = None
    for query in queries:
        if split and query["split"] != split:
            continue
        request = SearchRequest(
            query=query["query"],
            mode=mode,
            limit=10,
            filters=Filters(**query.get("filters", {})),
            rerank=rerank,
            channels=channels,
        )
        started = time.perf_counter()
        output = service.search.run(request)
        elapsed = (time.perf_counter() - started) * 1000
        if cold_latency is None:
            cold_latency = elapsed
        grades = {j["path"]: j["grade"] for j in by_query.get(query["id"], [])}
        relevant = {path for path, grade in grades.items() if grade == 2}
        # Resolve duplicate aliases to a judged identity before scoring.
        paths = []
        for result in output["results"]:
            identities = [result["relative_path"], *[a["relative_path"] for a in result["aliases"]]]
            paths.append(next((p for p in identities if p in relevant), identities[0]))
        record = {
            "query_id": query["id"],
            "category": query["category"],
            "split": query["split"],
            "answerable": bool(relevant),
            "results": paths,
            "latency_ms": elapsed,
            "warnings": output["warnings"],
        }
        for k in (1, 5, 10):
            record[f"at_{k}"] = {**metrics(paths, relevant, k), "ndcg": ndcg(paths, grades, k)}
        # Gold source spans are independent of chunk IDs and chunk-size experiments.
        expected_spans = [
            j for j in by_query.get(query["id"], []) if j.get("locator") and j["grade"] == 2
        ]
        evidence_hits = 0
        for judgment in expected_spans:
            for result in output["results"]:
                if result["relative_path"] != judgment["path"]:
                    continue
                gold = judgment["locator"]
                if any(span_matches(e["locator"], gold) for e in result["evidence"]):
                    evidence_hits += 1
                    break
        record["evidence_recall"] = evidence_hits / len(expected_spans) if expected_spans else None
        records.append(record)
        for _ in range(repeat):
            before = time.perf_counter()
            service.search.run(request)
            timings.append((time.perf_counter() - before) * 1000)
    aggregates = aggregate(records)
    categories = {
        category: aggregate([r for r in records if r["category"] == category])
        for category in sorted({r["category"] for r in records})
    }
    try:
        git_revision = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            or "uncommitted"
        )
    except (OSError, subprocess.TimeoutExpired):
        git_revision = "unavailable"
    from importlib.metadata import PackageNotFoundError, version

    dependencies = {}
    for package in (
        "fileora",
        "numpy",
        "faiss-cpu",
        "fastapi",
        "pypdf",
        "pillow",
        "torch",
        "sentence-transformers",
        "transformers",
        "faster-whisper",
        "ctranslate2",
        "av",
        "pytesseract",
        "swagger-ui-bundle",
    ):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            pass
    sizes = {
        "database_bytes": service.store.path.stat().st_size,
        "index_bytes": sum(
            p.stat().st_size for p in (service.settings.data_dir / "indexes").glob("*.faiss")
        ),
        "asset_bytes": sum(
            p.stat().st_size for p in (service.settings.data_dir / "assets").glob("*.jpg")
        ),
    }
    catalog = service.store.status()
    corpus = service.store.rows(
        "SELECT f.relative_path,v.sha256,v.pipeline_hash FROM files f JOIN file_revisions v ON v.id=f.active_revision_id WHERE f.status='ready' ORDER BY f.relative_path,v.sha256"
    )
    lockfile = Path(__file__).resolve().parents[2] / "uv.lock"
    return {
        "dataset_hash": hashlib.sha256(
            queries_path.read_bytes() + judgments_path.read_bytes()
        ).hexdigest(),
        "corpus_hash": hashlib.sha256(json.dumps(corpus, sort_keys=True).encode()).hexdigest(),
        "lock_hash": hashlib.sha256(lockfile.read_bytes()).hexdigest()
        if lockfile.exists()
        else None,
        "catalog_generation": catalog["generation"],
        "corpus_files": catalog["files"],
        "corpus_chunks": catalog["chunks"],
        "features": {
            "ocr": service.settings.enable_ocr,
            "vision": service.settings.enable_vision,
            "media": service.settings.enable_media,
        },
        "git_revision": git_revision,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "dependencies": dependencies,
        "mode": mode,
        "channels": channels,
        "rerank": rerank,
        "match_policy": {
            "single_term_hybrid": "literal",
            "hybrid_min_lexical_terms_for_longer_queries": 2,
            "min_text_cosine": service.settings.text_similarity_floor,
            "min_vision_cosine": service.settings.min_vision_similarity,
        },
        "split": split or "all",
        "device": service.models.device,
        "peak_process_rss_bytes": peak_rss_bytes(),
        "profiles": service.store.status()["profiles"],
        "chunk_tokens": service.settings.chunk_tokens,
        "overlap_tokens": service.settings.overlap_tokens,
        "cold_search_ms": cold_latency,
        "warm_p50_ms": statistics.median(timings) if timings else None,
        "warm_p95_ms": float(np.percentile(timings, 95)) if timings else None,
        "sizes": sizes,
        "metrics": aggregates,
        "categories": categories,
        "splits": {
            key: aggregate([r for r in records if r["split"] == key])
            for key in sorted({r["split"] for r in records})
        },
        "queries": records,
    }


def span_matches(actual: dict, expected: dict) -> bool:
    if "slide" in expected and actual.get("slide") != expected["slide"]:
        return False
    if "section" in expected and actual.get("section") != expected["section"]:
        return False
    if "page" in expected and actual.get("page") != expected["page"]:
        return False
    for start, end in (
        ("line_start", "line_end"),
        ("start_ms", "end_ms"),
        ("char_start", "char_end"),
    ):
        if start in expected:
            if start not in actual or end not in actual:
                return False
            if actual[start] > expected.get(end, expected[start]) or actual[end] < expected[start]:
                return False
    return True


def aggregate(records: list[dict]) -> dict:
    answerable = [r for r in records if r["answerable"]]
    missing = [r for r in records if not r["answerable"]]
    evidence = [r["evidence_recall"] for r in records if r.get("evidence_recall") is not None]
    return {
        "queries": len(records),
        "answerable": len(answerable),
        "evidence_recall": statistics.mean(evidence) if evidence else None,
        "at_1": averages(answerable, 1),
        "at_5": averages(answerable, 5),
        "at_10": averages(answerable, 10),
        "no_match_false_positive_rate": sum(bool(r["results"]) for r in missing) / len(missing)
        if missing
        else None,
    }


def averages(records: list[dict], k: int) -> dict:
    return {
        key: statistics.mean(r[f"at_{k}"][key] for r in records) if records else 0
        for key in ("precision", "recall", "hit_rate", "mrr", "ndcg")
    }
