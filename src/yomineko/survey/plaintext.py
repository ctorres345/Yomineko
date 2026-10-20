"""Detector 3: plain Shift-JIS kana in the ROM.

A hiragana run is a lead byte 0x82 followed by a trail in 0x9F-0xF1, repeated; katakana is 0x83
with a trail in 0x40-0x96. ASCII on its own is mostly Thumb code, so it counts only where it
touches Japanese text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_CHARS = 4
EXAMPLES = 20

_HIRAGANA = re.compile(b"(?:\\x82[\\x9f-\\xf1]){%d,}" % MIN_CHARS)
_KATAKANA = re.compile(b"(?:\\x83[\\x40-\\x96]){%d,}" % MIN_CHARS)
_ASCII_BEFORE = re.compile(rb"[\x20-\x7e]{4,}$")
_ASCII_AFTER = re.compile(rb"^[\x20-\x7e]{4,}")


@dataclass(frozen=True)
class PlainText:
    hiragana_runs: int
    katakana_runs: int
    ascii_neighbours: int  # hiragana runs with 4 or more ASCII bytes right before or after
    examples: list[tuple[int, int]]  # (offset, length in bytes) of the first hiragana runs


def find_plain_text(data: bytes) -> PlainText:
    hira = list(_HIRAGANA.finditer(data))
    neighbours = 0
    for m in hira:
        before = data[max(0, m.start() - 32) : m.start()]
        after = data[m.end() : m.end() + 32]
        if _ASCII_BEFORE.search(before) or _ASCII_AFTER.search(after):
            neighbours += 1
    kata = sum(1 for _ in _KATAKANA.finditer(data))
    return PlainText(
        len(hira), kata, neighbours, [(m.start(), m.end() - m.start()) for m in hira[:EXAMPLES]]
    )
