# Privacy, limits, and recovery

## Data flow

The application binds to `127.0.0.1`. Inference loads local artifacts with `local_files_only=True` and remote model code disabled. Downloads occur only through the explicit setup/model command. There are no hosted embeddings, analytics, external fonts, or paid LLM calls. Optional Ollama requests must resolve to a loopback HTTP endpoint.

Only selected roots are traversed. UNC shares, overlapping roots, runtime roots, symlinks, and Windows junctions/reparse points are rejected/skipped. Relative source paths are revalidated at preview time, including parent links and source stat changes. Native HTML source previews serve original PDFs/images/audio/video; code/text is served as plain text with nosniff headers.

Automatic updates are off by default for a new catalog. Enabling **Watch folders** saves a boolean preference locally and observes only the selected roots while Fileora runs. Relevant events trigger reconciliation; periodic full verification catches missed events. The Library reports unavailable watchers and folders. Disabling automatic updates clears pending event hints and lets queued/running jobs finish. The preference persists across normal restarts; no background service is installed.

The API validates loopback Host, exact Origin, cross-site fetch metadata, and a per-process token for mutations. CSP and frame denial protect the workspace. These controls prevent common browser cross-origin attacks; they are not authentication against another program or account already able to read the user's local files. Do not expose the service through a reverse proxy or bind it to a public network.

## What is stored

PowerPoint image OCR is cached locally in `ocr-cache/ppt-*.json` with extracted words, boxes, and a thumbnail identity. These files contain source-derived text and have the same privacy implications as catalog passages. Normal scan/forget cleanup removes unreferenced PowerPoint cache entries and unfinished cache writes; abrupt process/system crashes can leave temporary files until subsequent cleanup. Reused OCR workers stay local and terminate when their presentation finishes.

PowerPoint text and speaker notes are indexed like other passages; embedded-image OCR may create thumbnails. Original presentations are downloaded as attachments rather than executed or embedded in the browser. Optional legacy `.ppt` conversion creates a temporary local copy and private LibreOffice profile under the runtime directory. Normal completion and supervised cancellation remove these temporary files; an abrupt whole-system/process crash may leave temporary copies until the runtime is cleaned. Fileora never launches slide macros, follows presentation hyperlinks, or edits the original presentation.

`.fileora/catalog.sqlite3` contains absolute folder/file paths, extracted passages and OCR/transcripts, locators, embeddings, and job errors. FAISS files contain vectors, assets contain thumbnails/frames, and models contain downloaded weights. Original files are never edited. Model downloads and package-manager setup use the network and reveal the requested package/model to their hosting services.

The catalog is not encrypted. Use the operating system's account protections and disk encryption for sensitive libraries. Exclusions are not a content classifier. Delete/forget removes logical catalog rows and generated assets/snapshots; SQLite WAL/free pages and operating-system backups can retain previous bytes. Secure erasure of storage is not promised. To fully reset, stop Fileora and remove its explicitly chosen runtime directory using your operating system's tools; verify the path before deleting anything.

Queries are not persisted to the catalog. HTTP access logging is disabled by the launcher. Evaluation reports can contain query text and relative source identities: keep personal reports out of source control. The included public corpus is authored test material.

## Recovery guide

| Situation | Behavior / action |
| --- | --- |
| Interrupted indexing | Completed revisions remain; next server startup requeues unfinished jobs and reconciles |
| Missing/corrupt FAISS file | Automatically rebuilt from SQLite vectors; model re-embedding is unnecessary |
| Missing or unplugged root | Preserved, marked unavailable, and excluded from search; reconnect and verify |
| File moved/deleted | Next complete scan adds the new path/removes the old; hashes avoid redundant text embedding work |
| File changed during parsing | `SOURCE_CHANGED` / processing error; old content hidden; retry after writes finish |
| Missing model | Lexical fallback for hybrid text; prepare model and rescan to create embeddings |
| OCR absent | Prepare portable OCR with `npm ci` in `scripts/ocr`, or install native Tesseract and set `FILEORA_TESSERACT_CMD` |
| OCR/model pipeline settings changed | Keep flags consistent and rescan; pipeline identity forces the required extraction |
| No Ollama | Search still works; answer request returns a useful service error |
| `INSTANCE_RUNNING` | Stop the other CLI/server process; stale lock files alone do not hold an OS lock |
| Slow first search | Includes model loading; later queries keep the model in memory; compare cold and warm timings separately |
| Bad/oversized file | Per-file job error/warning; inspect scan details and exclude or convert the source |

Back up SQLite and its model manifests with the service stopped. Index snapshots can be regenerated. A future schema version requires an explicit migration; the current release refuses unknown schema versions.
