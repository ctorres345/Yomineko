"""16-bit token tables: text stored as little-endian glyph ids.

Some games draw text from a font and store each character as the glyph's index in a 16-bit
word, mixed with command words and their arguments. The ``.tbl`` has one ``HHHH=text`` line per
glyph (the key is the token value as 1-4 hex digits). A text run is a stretch of tokens that are
all in the table; it ends at the first token that is not (a command, or the end of the data).
Which tokens are commands with arguments is the discoverer's business, not the codec's.

Every token must map to a different text, so that re-encoding gives the original words back.
"""

from __future__ import annotations

from pathlib import Path

from yomineko.core.encodings.base import LITERAL_ESCAPES, Parsed
from yomineko.core.encodings.tbl import TableError

_JAPANESE_FROM = 0x3000  # CJK punctuation, kana, kanji and full-width forms


class Table16Codec:
    # not used: a run ends at the first token that is not in the table
    terminator = 0

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._decode: dict[int, str] = {}
        self._encode: dict[str, int] = {}
        self._load()
        self._max_text = max((len(t) for t in self._encode), default=1)

    def _load(self) -> None:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            raise TableError(f"cannot read table {self.path}: {e}") from e
        for lineno, line in enumerate(lines, 1):
            line = line.rstrip("\r")
            if not line or line.startswith(("#", "*", "/")):
                continue
            try:
                key, text = line.split("=", 1)
                key = key.strip()
                if not 1 <= len(key) <= 4 or not text:
                    raise ValueError("a key is 1-4 hex digits and the text is not empty")
                token = int(key, 16)
            except ValueError as e:
                raise TableError(f"{self.path}:{lineno}: bad table line {line!r}: {e}") from e
            if token in self._decode:
                raise TableError(f"{self.path}:{lineno}: token {token:04X} appears twice")
            if text in self._encode:
                raise TableError(
                    f"{self.path}:{lineno}: {text!r} is already the text of token "
                    f"{self._encode[text]:04X}; a table16 must map back uniquely"
                )
            self._decode[token] = text
            self._encode[text] = token

    def __len__(self) -> int:
        return len(self._decode)

    def knows(self, token: int) -> bool:
        """Whether a 16-bit token is a glyph of the table (and so can be text)."""
        return token in self._decode

    def parse(self, data: bytes, start: int, limit: int = 4096) -> Parsed | None:
        """The run of table tokens at ``start``. ``end`` is the offset of the first token that
        is not in the table (or the end of ``data``); ``None`` if the very first is not."""
        out: list[str] = []
        jp = 0
        i = start
        n = len(data)
        while i + 2 <= n and i - start < limit:
            text = self._decode.get(data[i] | data[i + 1] << 8)
            if text is None:
                break
            out.append("".join(LITERAL_ESCAPES.get(c, c) for c in text))
            jp += sum(1 for c in text if ord(c) >= _JAPANESE_FROM)
            i += 2
        if i == start:
            return None
        return i, "".join(out), jp

    def encode(self, text: str) -> bytes:
        out = bytearray()
        i = 0
        while i < len(text):
            if text[i] == "\\" and i + 1 < len(text) and text[i + 1] in LITERAL_ESCAPES:
                piece, step = text[i + 1], 2  # an escaped literal
            else:
                for size in range(min(self._max_text, len(text) - i), 0, -1):
                    piece, step = text[i : i + size], size
                    if piece in self._encode:
                        break
                else:
                    raise ValueError(f"no table entry for {text[i]!r}")
            token = self._encode.get(piece)
            if token is None:
                raise ValueError(f"no table entry for {piece!r}")
            out += token.to_bytes(2, "little")
            i += step
        return bytes(out)
