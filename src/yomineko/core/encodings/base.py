"""Codec protocol and the escaping shared by every encoding.

A codec turns bytes at an offset into *extractor text* and back. Extractor text is exact
and round-trippable: bytes with no character become ``{XX}`` or ``{XXXX}`` escapes, and a
literal ``\\``, ``{`` or ``}`` is written with a backslash. The readable form for humans
comes later, from the profile's ``plain`` rules.
"""

from __future__ import annotations

import re
from typing import Protocol

# (end, text, n_japanese): ``end`` is the offset of the terminator byte
Parsed = tuple[int, str, int]

LITERAL_ESCAPES = {"\\": "\\\\", "{": "\\{", "}": "\\}"}

# one token of extractor text: an escaped literal, a {XX}/{XXXX} byte escape, or any char
TOKEN = re.compile(r"\\\\|\\\{|\\\}|\{([0-9A-F]{2}(?:[0-9A-F]{2})?)\}|.", re.S)


class Codec(Protocol):
    terminator: int

    def parse(self, data: bytes, start: int, limit: int = 4096) -> Parsed | None:
        """Parse one terminated string at ``start``; ``None`` if the bytes are not text."""
        ...

    def encode(self, text: str) -> bytes:
        """Extractor text back to bytes, without the terminator."""
        ...
