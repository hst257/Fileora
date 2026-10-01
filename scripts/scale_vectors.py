"""Synthetic vector/catalog capacity test; not an ingestion or relevance benchmark."""

from __future__ import annotations

import argparse
import json
import platform
import threading
import time
from pathlib import Path

import faiss
import numpy as np
from fileora.config import Settings
from fileora.indexing import VectorIndexes
from fileora.resources import peak_rss_bytes
from fileora.storage import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100_000)
    args = parser.parse_args()
    if not 1 <= args.count <= 100_000:
        parser.error("count must be between 1 and 100000")
    settings = Settings(data_dir=Path(f".fileora/scale-{args.count}"), device="cpu")
    settings.prepare()
    store = Store(settings.data_dir)
    profile = {"id": "synthetic-384", "dimension": 384}
    rng = np.random.default_rng(20261001)
    started = time.perf_counter()
    with store.connect() as db:
        db.execute("DELETE FROM roots")
        db.execute("DELETE FROM index_state")
        db.execute("DELETE FROM embedding_profiles")
        db.execute("INSERT INTO roots(id,path) VALUES(1,'synthetic-vector-fixture')")
        db.execute(
            "INSERT INTO files(id,root_id,path,path_key,relative_path,name,extension,modality,size,mtime_ns,status,active_revision_id) VALUES(1,1,'synthetic','synthetic','synthetic','synthetic','.txt','text',0,0,'ready',1)"
        )
        db.execute(
            "INSERT INTO file_revisions(id,file_id,sha256,pipeline_hash) VALUES(1,1,'synthetic','synthetic')"
        )
        db.execute(
            "INSERT INTO embedding_profiles VALUES(?,?,'seed-20261001',384,'{}','text')",
            (profile["id"], "synthetic-capacity-test"),
        )
        db.execute("INSERT INTO index_state(profile_id) VALUES(?)", (profile["id"],))
        for start in range(0, args.count, 1000):
            count = min(1000, args.count - start)
            vectors = rng.normal(size=(count, 384)).astype(np.float32)
            vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
            db.executemany(
                "INSERT INTO chunks(id,revision_id,ordinal,kind,text,text_hash,locator) VALUES(?,1,?,'text','synthetic vector','synthetic','{}')",
                [(start + i + 1, start + i) for i in range(count)],
            )
            db.executemany(
                "INSERT INTO embeddings(id,chunk_id,profile_id,input_hash,vector) VALUES(?,?,?,?,?)",
                [
                    (
                        start + i + 1,
                        start + i + 1,
                        profile["id"],
                        str(start + i),
                        vector.tobytes(),
                    )
                    for i, vector in enumerate(vectors)
                ],
            )
        Store.changed(db)
    populated = time.perf_counter() - started
    indexes = VectorIndexes(store, settings, threading.RLock())
    started = time.perf_counter()
    index = indexes.get(profile)
    built = time.perf_counter() - started
    allowed = set(range(1, args.count + 1, 10))
    timings = {"unfiltered": [], "filtered_10_percent": []}
    for _ in range(30):
        query = rng.normal(size=384).astype(np.float32)
        query /= np.linalg.norm(query)
        for label, subset in (("unfiltered", None), ("filtered_10_percent", allowed)):
            before = time.perf_counter()
            hits = indexes.search(profile, query, subset, limit=10)
            timings[label].append((time.perf_counter() - before) * 1000)
            assert len(hits) == min(
                10, len(allowed) if subset is not None else args.count
            )
            assert subset is None or all(chunk_id in allowed for chunk_id, _ in hits)
    report = {
        "kind": "synthetic normalized vectors; excludes model inference, extraction, FTS and relevance",
        "seed": 20261001,
        "platform": platform.platform(),
        "count": index.ntotal,
        "dimension": 384,
        "faiss": faiss.__version__,
        "numpy": np.__version__,
        "populate_seconds": populated,
        "build_snapshot_seconds": built,
        "peak_process_rss_bytes": peak_rss_bytes(),
        "database_bytes": store.path.stat().st_size,
        "snapshot_bytes": sum(
            p.stat().st_size for p in (settings.data_dir / "indexes").glob("*.faiss")
        ),
        "timings": {
            label: {
                "p50_ms": float(np.median(values)),
                "p95_ms": float(np.percentile(values, 95)),
            }
            for label, values in timings.items()
        },
    }
    output = Path("evaluation/reports/scale-vectors.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
