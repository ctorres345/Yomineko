"""Extractor text -> readable text for humans, Anki and spreadsheets.

Ported from ``charmap.plain`` in the first prototype. The control-code rewrites are
now the profile's ordered ``plain`` rules; what stays here is the generic part: dropping
leftover ``{..}`` escapes, unescaping, the single-byte-kana remap, and whitespace.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from yomineko.profile.schema import Profile

# Some games draw the single-byte "half-width katakana" range as HIRAGANA (it saves a byte
# per character): the byte for ﾃ is shown as て. Indexed from U+FF61.
_HW = (
    "｡｢｣､･をぁぃぅぇぉゃゅょっーあいうえおかきくけこさしすせそたちつてとなにぬねのは"
    "ひふへほまみむめもやゆよらりるれろわん"
)
HW_AS_HIRAGANA = {chr(0xFF61 + i): c for i, c in enumerate(_HW)}
HW_AS_HIRAGANA.update({"｡": "。", "｢": "「", "｣": "」", "､": "、", "･": "・"})

_LEFTOVER_ESCAPE = re.compile(r"\{[0-9A-F]{2,4}\}")
_NEWLINE_PADDING = re.compile(r"[ \t]*\n[ \t]*")


def _literal(replacement: str) -> Callable[[re.Match[str]], str]:
    """A replacement that is inserted as-is (``re`` would read ``\\1`` in a plain string)."""
    return lambda _match: replacement


def make_plain(profile: Profile) -> Callable[[str], str]:
    rules = [(re.compile(r.pattern), _literal(r.replace)) for r in profile.plain]
    remap = HW_AS_HIRAGANA if profile.encoding.single_byte_kana == "hiragana" else None

    def plain(text: str) -> str:
        t = text
        for pattern, replace in rules:
            t = pattern.sub(replace, t)
        t = _LEFTOVER_ESCAPE.sub("", t)
        t = t.replace("\\{", "{").replace("\\}", "}").replace("\\\\", "\\")
        if remap:
            t = "".join(remap.get(c, c) for c in t)
        t = _NEWLINE_PADDING.sub("\n", t)
        return t.strip()

    return plain
