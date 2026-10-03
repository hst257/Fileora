# Final V4 performance tuning

V4 is the final feature release. This tuning reduces repeated indexing work while retaining the current extraction quality, source evidence, and changed-file checks.

## Measured rescan overhead

The benchmark uses 1,000 authored small Markdown files on this Windows/Python 3.11 machine. Each file is already indexed. Models are disabled so the measurement isolates catalog traversal, metadata checks, progress updates, and verification hashing. Filesystem caches are warm, cProfile is enabled in both versions, and each result is the median of three sequential scans.

| Scan | Before | Final V4 | Speedup |
| --- | ---: | ---: | ---: |
| Quick rescan | 41.47 s | 1.64 s | 25.3× |
| Verify all files | 41.68 s | 2.29 s | 18.2× |

Every measured run skipped all 1,000 unchanged files, indexed zero files, and reported zero failures. Full verification still reads and SHA-256 hashes every source file. These figures measure warm unchanged-library overhead; they do not predict first-time indexing, large-file hashing, OCR, transcription, network-storage performance, or representative personal-library throughput.

The baseline profile attributed about 102.7 of 124.7 seconds across three quick scans to SQLite connection closure, including repeated WAL cleanup/checkpoint work. Avoiding per-file database lookups and writes removed most of that overhead without changing SQLite durability settings.

Reproduce the current-version benchmark from the project directory, independently of the normal catalog:

```powershell
.venv/Scripts/python.exe scripts/benchmark_rescan.py --label local --files 1000 --repeat 3
```

This creates an authored corpus and isolated catalog under `.fileora/rescan-benchmark/`, saves a JSON report under `evaluation/reports/`, and saves profiles in the benchmark directory. It never reads your selected library folders. Repeated runs warm the same corpus before measurements. The recorded comparison used the immediately preceding implementation as the baseline; running the command on final V4 measures only the current version.

## What changed

- Catalog rows are loaded once per root during a job, and model/pipeline identities are cached per job and file type. Unchanged files avoid repeated SQLite connections and manifest reads.
- Progress updates are batched at 64 processed files or roughly 250 ms between files. Pending progress is flushed before extraction and before terminal job states. Cancellation is checked during traversal at 64 entries or roughly 100 ms, and supervised extraction retains its separate cancellation checks.
- Content-addressed lookup finds compatible active extraction through an indexed SHA-256/pipeline query. Exact copies and renames of the same format can reuse already chunked text, locations, warnings, and preview assets. Filename/path search entries are still rebuilt for the new location.
- Missing preview assets force fresh extraction. Pipeline/model/chunking changes that affect the output still invalidate incompatible cache entries. Historical insertion-ordered pipeline hashes and equivalent integer/float PowerPoint OCR budgets remain compatible.
- Unrelated feature switches avoid unnecessary extraction: media settings do not reparse notes, code, PDFs, presentations, or images, and OCR settings do not reparse ordinary text/code or audio. Enabling visual indexing can add cached or newly computed image/frame embeddings using existing extraction.
- Text and visual embedding-cache reads use bounded batches. Identical passages are encoded once per missing batch; cached visual vectors can be reused for copies instead of running CLIP again. A tokenizer is loaded only when newly extracted text needs chunking.
- Portable OCR shares one worker across scanned pages or sampled frames within a PDF/video extraction. It closes when the extraction completes or fails. PowerPoint keeps its existing deck-scoped worker and image OCR cache.
- Unsupported legacy `.ppt` files fail with the existing conversion guidance before starting an extraction subprocess when LibreOffice is unavailable.

One authored approximately 87-second silent video, with three distinct sampled frames and fresh per-run OCR caches, took **2.24 s before** and **1.49 s after** worker reuse (about 34% less time). Both runs produced identical recognized text, word boxes, and frame intervals. This is a single-fixture comparison, not a general OCR throughput estimate. Native Tesseract use is unchanged.

## Everyday use and limits

Use **Rescan library** for routine updates. It trusts unchanged size and modification time, as before. Use **Verify all files** when you need to detect modifications that preserve both values; native watcher events also force source hashing for affected paths. Changed files still receive a final stat/hash check before their new revision is committed. Deletions are reconciled only after a complete folder traversal.

Stop Fileora, rebuild the UI with `scripts/setup.ps1 -NoModels`, and restart to load the final V4 code. Prepared models and the existing catalog are reusable. The first upgraded scan may add an explicit visual-indexing identity to older images/videos; compatible extraction and embeddings are reused where available.

Changed recordings and OCR-heavy documents still cost CPU time. Larger verification scans are limited by the number and size of bytes that must be read. Per-root metadata caching uses memory proportional to the number of catalog files. One extraction runs at a time; this change does not establish 100K-file scalability or hard process memory limits. OCR resolution, frame sampling, model choice, and SQLite commit guarantees are unchanged.

Regression checks cover copies/renames, source changes during extraction, same-size/same-timestamp verification, missing previews, old pipeline identities, feature switches, job counters, cancellation, and OCR worker cleanup. The standard checks also exercise retrieval, source evidence, API behavior, watcher recovery, and frontend behavior.
