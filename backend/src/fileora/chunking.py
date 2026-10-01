from __future__ import annotations

import bisect
import re

from fileora.domain import Unit


def offsets(text: str, tokenizer=None) -> list[tuple[int, int]]:
    if tokenizer is not None:
        return [
            tuple(x)
            for x in tokenizer(
                text, add_special_tokens=False, return_offsets_mapping=True, truncation=False
            )["offset_mapping"]
            if x[1] > x[0]
        ]
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def chunk_units(units: list[Unit], budget: int, overlap: int, tokenizer=None) -> list[Unit]:
    result = []
    if tokenizer is not None:
        budget = min(budget, int(tokenizer.model_max_length) - 4)
    if budget <= overlap:
        raise ValueError("Chunk budget must exceed overlap")
    for unit in units:
        if unit.kind in {"image", "frame"}:
            result.append(unit)
            continue
        tokens = offsets(unit.text, tokenizer)
        lines = [m.start() for m in re.finditer("\n", unit.text)]
        start = 0
        while start < len(tokens):
            stop = min(start + budget, len(tokens))
            if stop < len(tokens):
                char_stop = tokens[stop - 1][1]
                paragraph = unit.text.rfind(
                    "\n\n", tokens[start + int((stop - start) * 0.75)][0], char_stop
                )
                if paragraph >= 0:
                    stop = max(
                        start + overlap + 1,
                        bisect.bisect_left([t[0] for t in tokens], paragraph, start, stop),
                    )
            lo, hi = tokens[start][0], tokens[stop - 1][1]
            locator = dict(unit.locator)
            base = locator.get("char_start", 0)
            locator.update(char_start=base + lo, char_end=base + hi)
            if "line_start" in locator:
                first_line = unit.locator["line_start"]
                locator["line_start"] = first_line + bisect.bisect_left(lines, lo)
                locator["line_end"] = first_line + bisect.bisect_left(lines, hi)
            result.append(Unit(unit.text[lo:hi], unit.kind, locator, unit.symbol, unit.asset))
            if stop == len(tokens):
                break
            start = stop - overlap
    return result
