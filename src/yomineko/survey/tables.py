"""Detector 4: pointer runs and offset tables, and what their targets are.

A run of 32 or more aligned words that all point into the ROM is a pointer table; an increasing
run of 16- or 32-bit offsets that opens its own block is an offset table. Most of both, in a
game that is not plain text, lead to animation, object or graphics records rather than text, so
each pointer run is sampled and its targets are given a coarse label.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from yomineko.core.compression.lz77 import CompressionError, decompress
from yomineko.survey._words import ROM_BASE, u16s, u32s
from yomineko.survey.bios import OTHER_MAX_SIZE, OTHER_MIN_SIZE, decode_huffman, decode_rle

POINTER_RUN_MIN = 32
OFFSET_RUN_MIN = 120
OFFSET_MAX_STEP = 700
SAMPLE = 8  # targets labelled per pointer run

_KANA_PAIR = re.compile(b"(?:\\x82[\\x9f-\\xf1]|\\x83[\\x40-\\x96]){2}")


@dataclass(frozen=True)
class PointerRun:
    offset: int
    count: int
    ascending: bool
    labels: dict[str, int]  # label -> how many of the sampled targets have it


@dataclass(frozen=True)
class OffsetRun:
    offset: int
    width: int  # 2 or 4 bytes per entry
    count: int
    first: int
    last: int
    opens_block: bool  # the first offset is about the table's own size


def label_target(data: bytes, offset: int) -> str:
    """A coarse guess at what the bytes at ``offset`` are. Never returns the bytes themselves."""
    head = data[offset : offset + 64]
    if len(head) < 16:
        return "other"
    if head.count(head[0]) == len(head):
        return "fill"
    size = int.from_bytes(head[1:4], "little")
    if head[0] == 0x10 and 256 <= size <= 0x100000:
        try:
            decompress(data, offset)
        except CompressionError:
            pass
        else:
            return "lz77"
    if OTHER_MIN_SIZE <= size <= OTHER_MAX_SIZE:
        if head[0] & 0xF0 == 0x20 and decode_huffman(data, offset) is not None:
            return "huffman"
        if head[0] == 0x30 and decode_rle(data, offset) is not None:
            return "rle"
    end = ROM_BASE + len(data)
    if all(ROM_BASE <= w < end for w in u32s(head)[:4]):
        return "pointers"
    if _KANA_PAIR.search(head[:32]):
        return "sjis-kana"
    if sum(w < 0x1000 for w in u16s(head)) >= 12:
        return "small-values"
    return "other"


def find_pointer_runs(data: bytes, min_len: int = POINTER_RUN_MIN) -> list[PointerRun]:
    words = u32s(data)
    end = ROM_BASE + len(data)
    runs: list[PointerRun] = []
    i = 0
    n = len(words)
    while i < n:
        if not ROM_BASE <= words[i] < end:
            i += 1
            continue
        j = i + 1
        while j < n and ROM_BASE <= words[j] < end:
            j += 1
        if j - i >= min_len:
            targets = [w - ROM_BASE for w in words[i:j]]
            labels = Counter(label_target(data, t) for t in targets[:SAMPLE])
            runs.append(PointerRun(i * 4, j - i, targets == sorted(targets), dict(labels)))
        i = j
    return runs


def find_offset_runs(
    data: bytes, min_len: int = OFFSET_RUN_MIN, max_step: int = OFFSET_MAX_STEP
) -> list[OffsetRun]:
    runs: list[OffsetRun] = []
    for width, values in ((2, u16s(data)), (4, u32s(data))):
        n = len(values)
        i = 0
        while i < n - 1:
            j = i
            while j + 1 < n and 0 < values[j + 1] - values[j] <= max_step:
                j += 1
            count = j - i + 1
            if count >= min_len:
                size = count * width
                first = values[i]
                runs.append(
                    OffsetRun(
                        i * width,
                        width,
                        count,
                        first,
                        values[j],
                        abs(first - size) <= max(8, size // 10),
                    )
                )
                i = j + 1
            else:
                i += 1
    return runs
