"""Detector 5: where a font could be, and how big one glyph unit is.

A one-colour font is a long stretch with only a handful of byte values and plenty of zeros
(blank pixels). Once a stretch is found, a per-position "ever inked" mask over a candidate unit
size shows the blank margins of a glyph cell: the unit with the most never-inked positions is
the cell size. Tile sheets (PNG) let a person look at the stretch.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from yomineko.survey._words import merge_ranges
from yomineko.survey.png import tile_sheet_png

WINDOW = 1024
MAX_VALUES = 8
ZERO_SHARE = (0.25, 0.92)
MIN_RANGE = 8 * 1024
UNIT_SIZES = (32, 64, 128, 256, 512)
STRIDES = (2, 4, 8, 16, 32)
SAMPLE_BYTES = 64 * 1024
SHEET_BYTES = 32 * 1024
SHEETS = 3


@dataclass(frozen=True)
class FontCandidate:
    start: int
    end: int
    values: list[int]  # the distinct byte values seen


@dataclass(frozen=True)
class Geometry:
    unit: int  # the glyph cell size in bytes that shows the most blank margin
    blank_share: float  # share of positions in the unit never inked
    row_stride: int  # bytes per pixel row (a hint: where the ink pattern repeats best)


def find_font_candidates(data: bytes) -> list[FontCandidate]:
    starts: list[int] = []
    values: dict[int, set[int]] = {}
    for a in range(0, len(data) - WINDOW + 1, WINDOW):
        counts = Counter(data[a : a + WINDOW])
        zeros = counts[0] / WINDOW
        if len(counts) <= MAX_VALUES and ZERO_SHARE[0] <= zeros <= ZERO_SHARE[1]:
            starts.append(a)
            values[a] = set(counts)
    found = []
    for start, end in merge_ranges(starts, WINDOW):
        if end - start >= MIN_RANGE:
            seen: set[int] = set()
            for a in range(start, end, WINDOW):
                seen |= values[a]
            found.append(FontCandidate(start, end, sorted(seen)))
    return found


def estimate_geometry(data: bytes, start: int, end: int) -> Geometry | None:
    """The cell size and row stride of the data in ``[start, end)``, or None if it is too short."""
    region = data[start : min(end, start + SAMPLE_BYTES)]
    best: tuple[float, int] | None = None
    for unit in UNIT_SIZES:
        chunks = len(region) // unit
        if chunks < 8:
            continue
        inked = bytearray(unit)
        for c in range(chunks):
            for k, b in enumerate(region[c * unit : (c + 1) * unit]):
                if b:
                    inked[k] = 1
        blank = 1 - sum(inked) / unit
        if best is None or blank > best[0] + 0.01:  # the smallest unit that is as good
            best = (blank, unit)
    if best is None:
        return None
    mask = bytes(1 if b else 0 for b in region)
    scores = {
        s: sum(a == b for a, b in zip(mask, mask[s:], strict=False)) / max(1, len(mask) - s)
        for s in STRIDES
    }
    return Geometry(best[1], round(best[0], 2), max(scores, key=lambda s: scores[s]))


def candidate_sheets(data: bytes, candidates: list[FontCandidate]) -> dict[str, bytes]:
    """PNG tile sheets (4 bits per pixel) of the largest candidates, keyed by file name."""
    biggest = sorted(candidates, key=lambda c: c.start - c.end)[:SHEETS]
    return {
        f"font-{c.start:06X}.png": tile_sheet_png(
            data[c.start : min(c.end, c.start + SHEET_BYTES)], 4
        )
        for c in biggest
    }
