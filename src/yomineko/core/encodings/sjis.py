"""Shift-JIS with the extensions seen in GBA games.

Ported from the first prototype (``charmap.py``), with the game-specific parts moved
into the profile: the custom-glyph lead bytes and the terminator.

* Standard JIS X 0208 characters decode normally.
* Lead bytes in the profile's ``custom_leads`` are game glyphs (icons, symbols). They are
  kept as ``{XXXX}`` escapes and round-trip unchanged.
* Control bytes below 0x20 (other than newline) are ``{XX}``.
* The single-byte range 0xA1-0xDF decodes to half-width katakana; whether the game draws it
  as hiragana is the profile's ``single_byte_kana`` and is applied in ``plain``.
"""

from __future__ import annotations

from yomineko.core.encodings.base import LITERAL_ESCAPES, TOKEN, Parsed

# Shift-JIS lead-byte ranges, inclusive
_LEAD_RANGES = ((0x81, 0x9F), (0xE0, 0xFC))


def _is_trail(b: int) -> bool:
    return 0x40 <= b <= 0xFC and b != 0x7F


class ShiftJISCodec:
    def __init__(self, custom_leads: list[tuple[int, int]] | None = None, terminator: int = 0):
        self.terminator = terminator
        self.custom = {b for lo, hi in (custom_leads or []) for b in range(lo, hi + 1)}
        all_leads = {b for lo, hi in _LEAD_RANGES for b in range(lo, hi + 1)}
        self.standard = all_leads - self.custom
        # custom glyph bytes outside the standard ranges are still two-byte units
        self._two_byte = self.standard | self.custom

    def parse(self, data: bytes, start: int, limit: int = 4096) -> Parsed | None:
        out: list[str] = []
        jp = 0
        i = start
        n = len(data)
        term = self.terminator
        while i < n and i - start < limit:
            b = data[i]
            if b == term:
                return i, "".join(out), jp
            if b == 0x0A:
                out.append("\n")
                i += 1
            elif 0x20 <= b < 0x7F:
                c = chr(b)
                out.append(LITERAL_ESCAPES.get(c, c))
                i += 1
            elif 0xA1 <= b <= 0xDF:
                out.append(bytes([b]).decode("shift_jis"))
                i += 1
                jp += 1
            elif b in self._two_byte and i + 1 < n and _is_trail(data[i + 1]):
                pair = data[i : i + 2]
                ch = None
                if b in self.standard:
                    try:
                        ch = pair.decode("shift_jis")
                        if ch.encode("shift_jis") != pair:
                            ch = None
                    except UnicodeDecodeError:
                        ch = None
                if ch is None:
                    ch = f"{{{pair[0]:02X}{pair[1]:02X}}}"
                out.append(ch)
                i += 2
                jp += 1
            elif b < 0x20 and b != 0x0A:
                out.append(f"{{{b:02X}}}")
                i += 1
            else:
                return None
        return None

    def encode(self, text: str) -> bytes:
        out = bytearray()
        for m in TOKEN.finditer(text):
            tok = m.group(0)
            if m.group(1):
                out += bytes.fromhex(m.group(1))
            elif tok in ("\\\\", "\\{", "\\}"):
                out += tok[1].encode("ascii")
            elif tok == "\n":
                out.append(0x0A)
            elif ord(tok) < 0x80:
                out += tok.encode("ascii")
            else:
                out += tok.encode("shift_jis")
        return bytes(out)
