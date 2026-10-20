"""Reject binary data that happens to decode as text.

Ported literally from the first prototype (``kana_ratio``, ``looks_like_text``): the
character ranges and thresholds decide how many strings a real ROM yields, so tidy them
only against the real-ROM counts.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# Always stripped before scoring, in addition to the profile's ``discover.ignore``:
# a literal backslash-n, and any whitespace.
_ALWAYS = r"\\n|[ 　\n]"

_KANA_RATIO_PUNCT = "　、。！？…ー〜「」・"
_PUNCT = "、。！？…ー〜「」・：（）＋－％／"


def kana_ratio(s: str) -> float:
    ok = 0
    for c in s:
        if "぀" <= c <= "ヿ" or "｡" <= c <= "ﾟ" or c in _KANA_RATIO_PUNCT or "０" <= c <= "ｚ":
            ok += 1
    return ok / max(1, len(s))


def make_looks_like_text(ignore: list[str], min_score: float) -> Callable[[str], bool]:
    """Build the text test for a profile: ``ignore`` are regexes (control codes,
    placeholders) removed before scoring."""
    codes = re.compile("|".join([*ignore, _ALWAYS]))

    def looks_like_text(text: str) -> bool:
        t = codes.sub("", text)
        if not t:
            return False
        kana = sum(1 for c in t if "ぁ" <= c <= "ヾ" or "ｦ" <= c <= "ﾝ")
        punct = sum(1 for c in t if c in _PUNCT or "０" <= c <= "ｚ" or "｡" <= c <= "･")
        kanji = sum(1 for c in t if "一" <= c <= "鿿")
        if kana == 0 and not (punct and len(t) <= 3):
            return False
        # Real lines always contain a full-width (two-byte) character; half-width-only
        # matches are almost always graphics data.
        if not any(ord(c) > 0x2000 and not ("｡" <= c <= "ﾟ") for c in t):
            return False
        score = kana + punct + 0.5 * kanji
        return score / len(t) >= min_score

    return looks_like_text
