"""Detector 6: 16-bit token streams (text stored as glyph ids).

In an 8 KB window of a token stream a few dozen values (the common kana and the commands) make up
most of the words, there are a few hundred to a thousand distinct values, nearly all of them
small, and few zeros. Compressed ROMs show nothing in the raw image, so the detector also runs
on the decoded LZ77 blocks.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from yomineko.core.compression.lz77 import CompressionError, decompress
from yomineko.survey._words import merge_ranges, u16s
from yomineko.survey.bios import Stream

WINDOW = 8192
MIN_BLOCK = 4096  # decoded blocks shorter than this are not scanned
TOP_SHARE = 0.45
DISTINCT = (120, 1500)
SMALL_VALUE = 0x1000
SMALL_SHARE = 0.9
MAX_ZERO_SHARE = 0.25


@dataclass(frozen=True)
class TokenRange:
    source: str  # "rom" or "lz77@0xOFFSET" for a decoded block
    start: int  # offset in the ROM, or in the decoded block
    end: int


def is_token_window(window: bytes) -> bool:
    words = u16s(window)
    total = len(words)
    if total == 0:
        return False
    counts = Counter(words)
    if not DISTINCT[0] <= len(counts) <= DISTINCT[1] or counts[0] / total >= MAX_ZERO_SHARE:
        return False
    top = sum(v for _, v in counts.most_common(64)) / total
    small = sum(v for k, v in counts.items() if k < SMALL_VALUE) / total
    return top > TOP_SHARE and small > SMALL_SHARE


def _scan(data: bytes, source: str) -> list[TokenRange]:
    window = min(WINDOW, len(data) // 2 * 2)
    starts = [
        a for a in range(0, len(data) - window + 1, window) if is_token_window(data[a : a + window])
    ]
    return [TokenRange(source, s, e) for s, e in merge_ranges(starts, window)]


def find_token_streams(data: bytes, streams: list[Stream]) -> list[TokenRange]:
    """Token-stream ranges in the raw image, then in every decoded LZ77 block."""
    found = _scan(data, "rom")
    for s in streams:
        if s.size < MIN_BLOCK:
            continue
        try:
            block = decompress(data, s.offset)
        except CompressionError:  # pragma: no cover - find_lz77 already decoded it
            continue
        found += _scan(block, f"lz77@0x{s.offset:X}")
    return found
