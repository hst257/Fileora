# Repository Guidelines

Whatever action you can do yourself, Please do yourself, this includes starting apps and verification

## Project Structure & Module Organization

- `backend/src/fileora/`: FastAPI API, CLI, extraction, indexing, retrieval, model loading, and SQLite storage. Keep parsing in extractors and search policy in retrieval.
- `backend/tests/`: pytest correctness and API tests; shared deterministic encoders live in `conftest.py`.
- `frontend/src/`: React/TypeScript workspace, evidence previews, styles, and component tests. `frontend/e2e/` contains Playwright flows.
- `scripts/`: Windows setup/start/check scripts, fixture generators, benchmarks, and portable OCR/speech helpers.
- `evaluation/`: authored corpora, queries, and relevance judgments. `docs/` contains architecture, measurements, and screenshots. `.fileora/` holds ignored runtime data and models.

## Build, Test, and Development Commands

Run from the repository root in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Demo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1
.venv/Scripts/python.exe -m pytest backend/tests -q
```

Setup installs locked dependencies, builds the frontend, and indexes demo fixtures. Add `-Media` for speech dependencies/models; `-NoModels` skips model downloads. Startup serves localhost on port 8765. Check runs Ruff, mypy, pytest, Prettier, Vitest, and the production build.

From `frontend/`, use `npm run dev` for Vite with API proxying, `npm run build` for production, `npm run test` for Vitest, and `npm run test:e2e` for Playwright against a running demo server with Chromium installed.

## Coding Style & Naming Conventions

Use four-space Python indentation, type hints, `snake_case` functions/modules, and `PascalCase` classes. Ruff formats to 100 columns and checks imports; mypy checks backend types. React/TypeScript uses two-space indentation, `PascalCase` components, `camelCase` functions, and Prettier formatting. Update dependency lockfiles when dependencies change.

## UI Icons

Use Phosphor icons from `@phosphor-icons/react` for all interface icons. Import named components, e.g. `import { MagnifyingGlass } from "@phosphor-icons/react"`. Follow existing icon sizes, weights, and theme colors; give icon-only controls accessible labels. Avoid introducing other icon libraries, emoji icons, or hand-drawn SVG icons. Keep custom SVG for evidence overlays and visualizations.

## Testing Guidelines

Name backend tests `test_*.py`, component tests `*.test.tsx`, and browser tests `*.spec.ts`. No numeric coverage threshold is configured. Add focused regressions for changed behavior, especially cache invalidation, cancellation, provenance, and no-match results. Keep default tests model-free; use authored fixtures and isolated catalogs for real OCR/media/model checks. Report benchmark scope and model identities.

## Commit & Pull Request Guidelines

History uses short descriptive subjects, such as `Library Scanning Optimization`, plus milestone subjects such as `Version 4`; no Conventional Commits requirement is established. Prefer specific change summaries. PRs should explain behavior, rationale, validation, and limitations; link relevant issues and include screenshots for UI changes.

## Configuration & Release Scope

V4 is final; focus on performance, reliability, and polish. Preserve local-only inference and selected-folder access. Never commit personal files, catalogs, models, secrets, or generated caches. Stop the server before setup or CLI catalog mutations; one process owns each catalog.
