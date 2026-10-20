"""Detector 1: how much of the image is data, and where it is fill or looks compressed."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

ENTROPY_BLOCK = 512 * 1024
MIN_FILL = 4096

_ZERO_FILL = re.compile(b"\\x00{%d,}" % MIN_FILL)
_FF_FILL = re.compile(b"\\xff{%d,}" % MIN_FILL)


@dataclass(frozen=True)
class FillRange:
    start: int
    end: int
    value: int  # 0x00 or 0xFF


@dataclass(frozen=True)
class Extent:
    size: int
    tail_fill_start: int | None  # where a fill run that reaches the end of the image starts
    entropy: list[float]  # bits per byte for each ENTROPY_BLOCK
    fills: list[FillRange]


def entropy(block: bytes) -> float:
    """Shannon entropy in bits per byte (0 for an empty or one-valued block)."""
    total = len(block)
    return sum(-v / total * math.log2(v / total) for v in Counter(block).values())


def fill_ranges(data: bytes) -> list[FillRange]:
    found = [FillRange(m.start(), m.end(), 0x00) for m in _ZERO_FILL.finditer(data)]
    found += [FillRange(m.start(), m.end(), 0xFF) for m in _FF_FILL.finditer(data)]
    return sorted(found, key=lambda r: r.start)


def measure_extent(data: bytes) -> Extent:
    entropies = [
        round(entropy(data[a : a + ENTROPY_BLOCK]), 2) for a in range(0, len(data), ENTROPY_BLOCK)
    ]
    fills = fill_ranges(data)
    tail = fills[-1].start if fills and fills[-1].end == len(data) else None
    return Extent(len(data), tail, entropies, fills)
