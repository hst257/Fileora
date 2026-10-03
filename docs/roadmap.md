# Release scope and next measurements

The implementation provides the five planned functional layers, with optional media and optional answers behind explicit setup. It is a developer-run localhost application, not an installer or a hardened multi-user service.

Validated here: Windows Python 3.11, CPU MiniLM/CLIP inference, portable English OCR, Java/Python parsing, text/PDF/image fixtures, incremental correctness/recovery tests, frontend tests, and a real Chromium workspace flow. Synthetic media and independent time-interval evaluation are included. Ollama contracts are tested through a local HTTP stub; live Qwen generation, CUDA execution, Linux desktop UX, and a representative 100K-chunk library require separate validation.

The [V2 milestone](v2.md) now includes saved Library controls for automatic updates, visible native-watcher/periodic-scan status, ignored-event filtering, and real filesystem tests for create/edit/rename/delete events. Earlier builds already contained the underlying V2 retrieval and indexing components; this milestone completes and validates their automatic-update workflow.

## Engineering limits

PowerPoint native text is fast on the inspected lecture decks; image OCR remains more expensive. Optional slide-image OCR is bounded and can be partial, with readable preview notes. Unsupported picture relationships no longer fail the entire deck. Cache reuse and one portable worker reduce repeated work, but increasing the image budget trades responsiveness for image-text coverage. Audio/video files are skipped while transcription is disabled.

- Exact FAISS rebuild materializes all active profile vectors. At 100K passages a 384-dimensional float32 matrix is ~154 MB before ID/index/Python overhead; 512-dimensional CLIP adds ~205 MB for 100K visual entries. These are estimates, not measured process peaks. Full SQLite vectors plus FAISS intentionally duplicate storage.
- The worker handles one file at a time. A very large text file can still produce a substantial chunk list; child timeout isolation is not a hard memory limit. Files default to 50 MB; media defaults to four hours and 1,500 frames.
- Content hashes reuse text embeddings across renames/copies. Changed visual files recompute CLIP vectors, and changed media files repeat extraction; a shared image/transcript extraction cache is future work.
- Java/Python use function parsing; other code languages use token/line fallback. PowerPoint `.pptx` supports slide text, groups, tables, chart labels, speaker notes, and optional embedded-image OCR. Legacy `.ppt` requires optional LibreOffice; live conversion remains unvalidated here. SmartArt, equations, linked/embedded documents, slide-master text, animations, slide rendering/visual similarity, and embedded audio/video extraction are outside this PowerPoint release. Other Office formats, PDF table reconstruction, archives, handwritten OCR, and multilingual embeddings remain outside this release.
- Scanned PDFs use OCR only for empty text pages; mixed pages and reading order may lose content. V3 highlights query-matched OCR words on image and scanned-page previews with a hide/show control. Older locators without dimensions require rescan; video-frame OCR overlays remain future work.
- Transcript results use Whisper segment intervals. Video sampling can miss brief content, and fixed average-hash suppression can remove similar slides. Browser codec support varies even if PyAV can decode a file.
- Single-term hybrid searches require literal evidence, and model-specific cosine floors suppress weak neighbors before fusion. These heuristics improve abstention on the fixture but can miss useful paraphrases; calibration on independent, representative personal-library data remains future work.
- Answer citations are structurally validated. Supporting-source entailment, prompt-injection robustness, and answer quality need manual evaluation before claims of grounded reliability.
- Watcher events are hints; full scans reconcile every 15 minutes. Metadata-only quick scans can miss changes with identical size/mtime; **Verify all files** forces hashing.
- Folder forget is logical removal, not secure disk erasure. SQLite free pages/WAL/backups are covered in the privacy document.

## Next work, driven by evidence

1. Add a consented, representative personal corpus with 100+ independently authored queries, including ambiguous, adversarial, no-answer, code-symbol, and OCR failures. Preserve family-separated dev/test sets and freeze judgments before model tuning.
2. Repeat the implemented MiniLM/BGE, lexical/semantic/hybrid, reranking, and OCR/CLIP/fusion comparisons on the representative corpus. Add chunk-size experiments within each encoder's real token limit. Report matched source/profile identities rather than comparing incompatible runs.
3. Measure 10K/50K/100K real chunks: stage-level indexing time, peak CPU RSS/VRAM, index rebuild cost, filtered/unfiltered p50/p95, update/delete cost, and disk overhead. Introduce ANN only if exact search misses the practical latency/memory budget.
4. Measure natural noisy lecture WER, timestamp error, temporal Recall@5/10, and scene-sampling misses. Add grouped transcript windows and better scene-change sampling when warranted.
5. Run 30–50 answerability/citation/faithfulness cases with a real local Ollama model. Keep abstention failures and unsupported answers in the report; do not infer reliability from valid citation syntax.
6. Add paginated full-document navigation, OCR correction/video overlays, persisted feature settings, multi-platform packaging, schema migrations, and Windows signed installation after core measurement stabilizes.

Resume bullets should describe the implemented pipeline and cite the exact synthetic benchmark scope. Do not claim 100K-file deployment, GPU acceleration, privacy certification, answer accuracy, or representative recall from these fixtures.
