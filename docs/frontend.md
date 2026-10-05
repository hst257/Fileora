# Frontend design and maintenance

## Audit and direction

The original workspace used a warm neutral canvas, olive accent, Segoe UI body text, Georgia display headings, a folder mark, and the `fileora.` wordmark. Search and My library are the two primary views; there are no public routes, analytics, or SEO migration requirements. Source evidence, file-type filters, library controls, and keyboard search are established interactions.

The main problems were excessive introductory space, small evidence text, folders below several setup explanations, hard-coded light backgrounds, and search/library/preview logic combined in one large component. Evolve the existing identity into a practical search workspace. Preserve the wordmark, navigation labels, API contracts, local-only assets, and evidence semantics.

Use the existing React, native CSS, and Phosphor foundation. The app opens directly into its search workspace. Motion communicates state changes and honors reduced-motion preferences.

## Current visual reference

The repository's [DESIGN.md](../DESIGN.md) is an exact copy of the supplied Video Editor Background Effect document. It defines Fileora's palette. Search, library controls, and evidence previews retain their established layout and contracts.

Use the near-black `#0A0908` canvas, amber `#EEB057` actions, white text, zinc borders, and quieter charcoal surface shades to retain the workspace hierarchy. Workspace panels and controls keep 8px radii. Headings use locally bundled [Inter](https://github.com/rsms/inter); workspace body text and metadata retain the monospace stack. Its license is in `frontend/public/fonts/Inter-LICENSE.txt`. No font requests leave localhost.

New browser sessions default to dark appearance; saved light, dark, and system choices remain respected. The light variant uses warm neutral surfaces with darker amber text for sufficient contrast, while action fills retain the reference amber. Separate `--accent` fills from `--accent-ink` text.

The visual skin passed the production build, formatting, 19 frontend tests, 15 browser flows, and accessibility checks across 12 states with no reported violations. A comparison against the pre-skin stylesheet confirmed that layout, spacing, responsive, and animation declarations are unchanged. Updated screenshots include both appearances.

## Search flow

The app opens directly into the original workspace, with Search/My library navigation, indexed folders, appearance, the search field, file-type tabs, and example queries. There is no separate landing section.

Search queries and options are managed by `useSearch`. **Ctrl+K** focuses workspace search directly, including from My library. Example queries remain visible in the empty search view, and file-type tabs apply the existing backend filters.

Compact previews make the workspace inert until dismissed. Keyboard focus stays inside the dialog and returns to the selected result after closing it. Responsive navigation, search controls, and evidence panes retain their original behavior.

The landing experiments were reverted on October 4, 2026 using the saved pre-landing source files. The earlier frontend refactor, visual palette, and Phosphor icons remain in place. Production build, formatting, 19 component tests, and 15 browser flows passed after restoration. Axe reported no violations across 12 light/dark desktop/mobile states. Screenshots use the authored isolated catalog.

## Conventions

- Define light/dark colors, spacing, radii, and layer values in `src/tokens.css`. Follow `DESIGN.md` for visual styling and use warning/error colors only for their semantic states.
- Keep view composition in `App.tsx`; place workspace components in `src/components/`, stateful service hooks in `src/hooks/`, and evidence formatting in `src/lib/`.
- Preserve accessible control names, focus indicators, source locations, matching-frame selection, original-file URLs, and media seeking behavior when changing layouts.
- Use authored, isolated catalogs for browser screenshots. Never publish personal library paths or content.
- Verify desktop and mobile layouts, light/dark appearance, loading/empty/error states, keyboard navigation, and reduced motion. Run frontend tests, production build, formatting, and the existing Playwright flows before delivery.

## Refactor verification

The refactor keeps the existing backend and API contracts. Search, library controls, source previews, appearance, and service state now have focused components/hooks. Appearance supports light, dark, and the system preference; the saved choice stays on the device. Compact previews contain keyboard focus, dismiss with Escape, and restore focus to the selected result. Superseded searches cannot replace newer results.

Validation on October 3, 2026: production build and Prettier passed, with 19 Vitest tests and 15 Playwright flows passing. Browser checks cover widths from 320 to 1440 pixels, theme persistence, reduced motion, folder scope, OCR overlays, transcription preferences, and timestamp playback. Screenshots use an isolated catalog containing authored fixtures.

Automated WCAG checks reported no violations across 12 light/dark desktop/mobile states, including text and image previews. Before the visual skin update, Lighthouse scored performance/accessibility/best practices at 100/100/100 on desktop and 90/100/100 on mobile. These are local laboratory results for the initial workspace, not measurements of model inference or large-library search performance.
