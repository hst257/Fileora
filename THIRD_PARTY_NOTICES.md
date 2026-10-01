# Third-party notices

Application code is MIT licensed; these dependencies and weights retain their own licenses. Inspect the precise locked versions and upstream licenses before redistributing a packaged application.

- MiniLM (`sentence-transformers/all-MiniLM-L6-v2`), BGE-small-en-v1.5, the MS MARCO MiniLM cross-encoder: model repositories publish Apache-2.0 licenses.
- OpenAI CLIP: MIT; official Transformers checkpoint converted locally to safetensors during explicit setup.
- faster-whisper: MIT; Whisper model weights originate from OpenAI's MIT release, converted by Systran.
- React, Vite, FastAPI, NumPy, Pillow, PyTorch, FAISS, pypdf, PyAV, Tree-sitter, Watchdog, Sentence Transformers, and Transformers: see upstream distributions and bundled license files for exact terms.
- Tesseract / Tesseract.js and English language data: Apache-2.0. Portable OCR npm packages are installed locally and are not vendored in source control.
- Phosphor icons: MIT. Fonts use the operating system's installed fonts; no font files are distributed.
- Swagger UI: Apache-2.0; current npm assets are copied into the local frontend build. Install analytics are disabled with `scarfSettings.enabled=false` and the setup environment.
- Optional synthetic speech fixture tool: `@echogarden/espeak-ng-emscripten` 0.3.5, GPL-3.0. It is a separate developer fixture generator, not imported or distributed by the application. Its upstream license accompanies the installed npm package.

The authored study notes, code examples, diagrams, PDFs, and synthetic lecture script in `evaluation/` are dedicated to the public domain under CC0-1.0. They are illustrative fixtures, not authoritative educational or cloud configuration advice. No private user files or scraped copyrighted lecture material are included.
