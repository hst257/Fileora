# PowerPoint extraction repair

The reported failures came from optional image OCR rather than slow slide-text parsing. Native text extraction on six local lecture decks took approximately 0.08–0.20 seconds per deck. The former implementation created a new portable Tesseract worker for every picture placement, including repeated images, within a 60-second whole-file timeout. One deck also contained a picture relationship that python-pptx exposed as a generic OPC Part; accessing its image raised AttributeError and failed the whole presentation.

The fix retains python-pptx for native text, extracts all slide text/notes first, reuses one portable OCR worker per deck, caches OCR by image/engine identity, and embeds identical passages once per file. The optional image pass defaults to 20 seconds and 48 unique images, with a 1,600-pixel longest edge and priority for large images on slides with little native text. Unsupported images become warnings. Partial image OCR preserves native text and has explicit preview notes. Audio/video processing stays optional; disabled media is skipped rather than recorded as a failed extraction.

The worker-reuse choice follows [Tesseract.js's upstream performance guidance](https://github.com/naptha/tesseract.js/blob/master/docs/performance.md). The [python-pptx loader](https://github.com/scanny/python-pptx/blob/master/src/pptx/opc/package.py) constructs the package graph; the measured native pass was already fast enough that replacing the XML parser would not address the dominant OCR work.

## Measurements

Windows, Python 3.11, CPU, local portable English Tesseract. Each first extraction used the normal spawned supervisor and a shared initially empty test cache; later decks could reuse images from earlier decks. The repeat used direct extraction with the resulting cache. Numbers cover extraction only, excluding embedding, hashing, and catalog publication. Deck identities are anonymized; private documents, paths, extracted text, and OCR are not committed. The public retrieval benchmark and its authored corpus are unchanged.

| Deck | Slides | First extraction (s) | Repeat (s) | Native units | First OCR units |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 173 | 10.38 | 0.41 | 233 | 189 |
| B | 131 | 18.69 | 0.22 | 109 | 72 |
| C | 102 | 20.84 | 19.64 | 78 | 20 |
| D | 87 | 20.61 | 0.94 | 87 | 43 |
| E | 135 | 20.61 | 0.84 | 127 | 43 |
| F | 86 | 12.56 | 0.27 | 85 | 52 |

All six presentations that previously failed extraction now returned native text successfully. B retained one unsupported-image warning. B–F retained partial image-OCR warnings; D and C also reached a per-image OCR time limit. A unit is a slide body, speaker note, or recognized picture placement, so unit counts can exceed slide counts. Duplicate picture placements retain separate source locators while sharing recognition work.

Repeat runs are not uniformly fully cached: C recognized additional uncached images within the same budget, explaining its slower repeat. These results demonstrate failure recovery and bounded responsiveness, not complete image-text coverage or general speedups across every presentation. Regression tests cover preserving native text under exhausted OCR budgets, unsupported picture parts, duplicate image provenance/cache reuse, cache cleanup on forget, media skipping, and duplicate embedding work.

## Applying the update

Restart Fileora, refresh the browser, and rescan. Presentation-specific pipeline changes refresh affected decks without reindexing unchanged other formats. Historical jobs retain their original errors; inspect the newest scan. For native-text-only PowerPoint extraction use `scripts/start.ps1 -PptOcrSeconds 0`. More image coverage can use `-PptOcrSeconds 40 -PptOcrMaxImages 200`; this spends more time and still obeys the overall extraction timeout. Binary `.ppt` conversion remains an optional local LibreOffice path and is not live-validated here.
