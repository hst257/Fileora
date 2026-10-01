# Evaluation and measured results

These are reproducible **synthetic fixture measurements**, taken on this Windows laptop with Python 3.11.8 and CPU inference. They demonstrate functioning retrieval and identify tradeoffs. They are not representative personal-library accuracy claims.

Full per-query reports and their hashes/profile revisions are committed in [`evaluation/results`](../evaluation/results/summary.json). The scripts write fresh reports to ignored `evaluation/reports/`; `export_results.py` copies only the explicitly named authored-fixture runs. No personal corpus reports are published.

## Corpus and judgments

- 17 authored files: ten Markdown topics, two source files, two text PDFs, and three screenshot reproductions of study text. MiniLM produces 24 active evidence units at the default 192-token/32-overlap budget.
- 100 text queries: 90 answerable and ten unrelated/no-match queries. Entire topic families are split into 60 development and 40 test queries; query paraphrases from the same family never cross the split.
- File-level grade 2 identifies relevant files; page/line locators are authored independently of chunk IDs. Duplicate aliases receive one identity's credit. Screenshots that reproduce topic text are relevant to the unrestricted topic queries too. An early coverage audit corrected these omitted labels before the final results below; no similarity threshold was tuned against test labels.
- Thirty image queries cover only three synthetic screenshots, all development fixtures. This is a pipeline smoke test, not an image generalization test.
- Optional media includes one 86.9-second locally synthesized English lecture with three independently known sections and a silent slide video. Twenty queries are restricted to audio. File recall on a one-file audio corpus is trivial; section-overlap evidence recall and transcript WER provide the useful checks.

Precision@K divides by K, including when fewer than K results exist. Recall@K counts all grade-2 files; Hit@K measures whether any relevant file is found. MRR and nDCG are file-level, not chunk-level. Answerable queries alone contribute to these ranking averages. Unrelated queries separately contribute to the no-match false-positive rate. Source evidence recall requires an excerpt overlapping the judged page/line/time locator and is independent of chunk identifiers.

## Original text baselines before relevance filtering

CLIP is disabled in this comparison to isolate text retrieval. OCR text remains searchable in both catalogs. The same source corpus and judgments are used; BGE/MiniLM tokenizers can produce different passage boundaries and pipeline hashes.

| Configuration | Hit@1 | Hit@5 | Recall@5 | MRR@5 | Warm p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 lexical (MiniLM catalog) | 94.4% | 98.9% | 98.9% | 0.9667 | 56.0 ms |
| MiniLM semantic | 87.8% | 100% | 99.3% | 0.9328 | 69.1 ms |
| MiniLM hybrid | 94.4% | 100% | 100% | 0.9722 | 73.7 ms |
| BGE semantic | 88.9% | 100% | 98.5% | 0.9324 | 77.2 ms |
| BGE hybrid | 93.3% | 100% | 100% | 0.9667 | 86.9 ms |
| MiniLM hybrid + cross-encoder | 98.9% | 100% | 100% | 0.9944 | 576.5 ms |

The default remains MiniLM hybrid. BGE provides no hybrid benefit on this small fixture. Reranking improves the first result but costs about eight times the measured p95; it is opt-in. These choices require rechecking on a representative corpus rather than extrapolating the fixture result.

**Original no-match false positives: BM25 3/10; semantic and hybrid 10/10.** These saved baseline reports predate the keyword/weak-neighbor fix. Rank scores are not confidence, and structural citation checks do not solve answerability.

## Current relevance filtering

Default hybrid single-term queries require a literal match. Longer queries need two lexical terms or a vector candidate above the model-specific raw-cosine floor (MiniLM 0.35, BGE 0.55, CLIP 0.28). These initial heuristics were checked with authored examples and the existing benchmark; they were not calibrated on a representative private library. The saved reports now include `match_policy` so results can be distinguished from the unfiltered baselines.

The current MiniLM hybrid rerun on the same 100 text queries (CLIP disabled) returned results for **0/10 unrelated queries**, versus 10/10 previously. Hit@1 is 93.3%, Hit@5/Recall@5 is 98.9%, and MRR@5 is 0.9611. One of the 90 answerable queries is now missed: stricter abstention trades some recall for fewer misleading results. Warm p95 was 62.7 ms in this run. The 30-query image fusion rerun retained 100% Hit@1 (56.2 ms warm p95); this three-image fixture still cannot establish image generalization.

See [`relevance-minilm-hybrid.json`](../evaluation/results/relevance-minilm-hybrid.json) and [`relevance-minilm-images.json`](../evaluation/results/relevance-minilm-images.json) for the full current reports. BGE and reranker rows above remain historical baselines; they have not been remeasured with this policy. To reproduce the current reports with the prepared authored-fixture catalog:

```powershell
.\.venv\Scripts\fileora.exe --data-dir .fileora/benchmark --models-dir .fileora/models --device cpu --ocr evaluate --mode hybrid --output evaluation/reports/relevance-minilm-hybrid.json
.\.venv\Scripts\fileora.exe --data-dir .fileora/benchmark --models-dir .fileora/models --device cpu --ocr --vision evaluate --mode hybrid --queries evaluation/image_queries.jsonl --judgments evaluation/image_judgments.jsonl --output evaluation/reports/relevance-minilm-images.json
```

## Original image baselines and media results

| Image configuration | Hit@1 | MRR@5 | Warm p95 |
| --- | ---: | ---: | ---: |
| OCR + lexical BM25 | 100% | 1.0000 | 26.6 ms |
| CLIP only | 86.7% | 0.9333 | 60.3 ms |
| OCR + MiniLM + CLIP fusion | 100% | 1.0000 | 92.4 ms |
| OCR + BGE + CLIP fusion | 96.7% | 0.9833 | 102.9 ms |

All four return the relevant screenshot within five results because there are only three eligible images. OCR wins on screenshots dominated by readable text. Photographs, diagrams, noisy OCR, and visually similar distractors require a substantially larger independent image test set.

Whisper base.en produced 13 transcript segments and **7 word edits / 108 reference words = 6.48% WER** after lowercasing and punctuation normalization. All 20 temporal queries found at least one returned evidence interval overlapping the judged section. This is not word-level timestamp accuracy, natural-lecture recall, or noisy speech performance. The saved report includes the reference and actual hypothesis so errors such as “wait/weight” remain visible.

## Capacity experiment

`scale_vectors.py` populated the actual SQLite/FAISS implementation with **100,000 seeded random normalized 384-dimensional vectors**. This isolates vector storage, snapshot construction, search, and filtering; it excludes extraction, model encoding, FTS, result grouping, and retrieval relevance.

| Measurement | Result |
| --- | ---: |
| SQLite fixture population | 3.87 s |
| FAISS snapshot build + checksum | 2.48 s |
| Unfiltered vector search p50 / p95 | 12.45 / 14.97 ms |
| Exact filtered search, 10% eligible, p50 / p95 | 149.42 / 170.10 ms |
| Peak parent process RSS | 536.2 MiB |
| SQLite catalog | 208.7 MiB |
| FAISS snapshot | 147.2 MiB |

There were 30 queries per condition. Filtering is slower because it reads eligible BLOBs in batches from SQLite. The snapshot excludes model RAM; RSS is a process high-water mark, not system-wide peak RAM or GPU VRAM. This validates the vector layer's capacity, not end-to-end indexing of 100K real passages.

The 17-file BGE/OCR/CLIP fixture index completed in 20.2 seconds with no file errors and ~1,202 MiB parent peak RSS. Per-file spawned extractor RSS is not included. Exact index matrices and model caches can coexist within the laptop's memory budget, but representative ingestion and GPU measurements remain future work.

## Reproduce

Stop the main server before commands that use `.fileora`; separate benchmark catalogs can share the prepared model cache without duplicating weights. Run from the repository root after setup:

```powershell
.\.venv\Scripts\python.exe scripts/create_demo.py
.\.venv\Scripts\fileora.exe --data-dir .fileora/benchmark --models-dir .fileora/models roots add "$PWD\evaluation\corpus"
.\.venv\Scripts\fileora.exe --data-dir .fileora/benchmark --models-dir .fileora/models --device cpu --ocr --vision index
.\.venv\Scripts\python.exe scripts/benchmark.py

.\.venv\Scripts\fileora.exe --data-dir .fileora models download BAAI/bge-small-en-v1.5 --revision 5c38ec7c405ec4b44b94cc5a9bb96e735b38267a
.\.venv\Scripts\fileora.exe --data-dir .fileora/benchmark-bge --models-dir .fileora/models roots add "$PWD\evaluation\corpus"
.\.venv\Scripts\fileora.exe --data-dir .fileora/benchmark-bge --models-dir .fileora/models --device cpu --text-model BAAI/bge-small-en-v1.5 --ocr --vision index
.\.venv\Scripts\python.exe scripts/benchmark.py --data-dir .fileora/benchmark-bge --text-model BAAI/bge-small-en-v1.5

.\.venv\Scripts\fileora.exe --data-dir .fileora models download cross-encoder/ms-marco-MiniLM-L6-v2 --revision 233902d25c440f23af6f7d6e94d2946bac0bee0a
.\.venv\Scripts\python.exe scripts/benchmark.py --rerank
.\.venv\Scripts\python.exe scripts/scale_vectors.py
```

For media, use `setup.ps1 -Media -Demo`, stop the server, then run `python scripts/media_report.py`. The script expects the generated WAV/MP4 to be indexed in `.fileora` with `--media`. To compare chunk sizes, use another benchmark data directory and pass `--chunk-tokens`/`--overlap-tokens` consistently when indexing and evaluating.

The benchmark runner executes queries serially and repeats each once for warm latency. Model caches are unloaded between configurations, while imports and OS disk caches remain warm; reported “cold” means first search of that configuration in the process, not a cold boot. Run without simultaneous indexing, tests, or builds for timing comparisons. A process high-water RSS accumulates across sequential runs. Small changes in p95 should not be treated as statistically significant.

Every run records dataset/catalog/profile/lock identities, split/category aggregates, source evidence recall, and dependency versions available at evaluation time. The summary additionally records ML dependency versions; its source fixture manifest is the common content identity across differently indexed model catalogs. No benchmark is presented as a deployed or independently audited production outcome.
