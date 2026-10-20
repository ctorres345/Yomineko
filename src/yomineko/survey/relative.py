"""Detector 7: relative search for a known word.

When a game's text is a table of ids in an unknown order, the kana usually still keep their
gojuon order, so the *differences* between a word's characters are the same whatever the table's
base value is. The word is typed by the user and never stored or printed: the result holds
counts and offsets only.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise

from yomineko.errors import YominekoError
from yomineko.survey._words import u16s

GOJUON = (
    "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
)
_SMALL = str.maketrans("ぁぃぅぇぉっゃゅょゎ", "あいうえおつやゆよわ")
MIN_KANA = 3
TOP_BLOCKS = 10


@dataclass(frozen=True)
class RelativeHits:
    kana: int
    hits8: int
    hits16: int
    expected8: float  # hits expected from random bytes of this size
    expected16: float
    blocks8: list[tuple[int, int]]  # (offset of a 64 KB block, hits in it), most hits first
    blocks16: list[tuple[int, int]]


def kana_indices(word: str) -> list[int]:
    """Each kana's position in gojuon order; voiced marks, small kana and katakana are folded."""
    out = []
    for ch in word:
        if "ァ" <= ch <= "ヶ":
            ch = chr(ord(ch) - 0x60)
        base = unicodedata.normalize("NFD", ch)[0].translate(_SMALL)
        if base not in GOJUON:
            raise YominekoError("the word must be written in kana only (hiragana or katakana)")
        out.append(GOJUON.index(base))
    if len(out) < MIN_KANA:
        raise YominekoError(f"the word needs at least {MIN_KANA} kana to give a usable pattern")
    return out


def _blocks(offsets: list[int]) -> list[tuple[int, int]]:
    counts = Counter(o >> 16 << 16 for o in offsets)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_BLOCKS]


def relative_search(data: bytes, word: str) -> RelativeHits:
    idx = kana_indices(word)
    steps = [b - a for a, b in pairwise(idx)]
    cumulative = [0]
    for d in steps:
        cumulative.append(cumulative[-1] + d)

    hits8: list[int] = []
    for base in range(256):
        values = [base + c for c in cumulative]
        if min(values) < 0 or max(values) > 255:
            continue
        pattern = bytes(values)
        at = data.find(pattern)
        while at != -1:
            hits8.append(at)
            at = data.find(pattern, at + 1)

    words = u16s(data)
    first = steps[0]
    hits16 = []
    for j, (x, y) in enumerate(pairwise(words)):
        if y - x != first or j + len(steps) >= len(words):
            continue
        if all(words[j + k + 1] - words[j + k] == d for k, d in enumerate(steps)):
            hits16.append(2 * j)

    k = len(steps)
    return RelativeHits(
        len(idx),
        len(hits8),
        len(hits16),
        round(len(data) / 256**k, 1),
        round(len(data) / 2 / 65536**k, 2),
        _blocks(hits8),
        _blocks(hits16),
    )
