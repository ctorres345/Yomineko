""".tbl table encodings (the romhacking standard).

Format: one ``HEX=text`` per line (the key may be several bytes), ``/HEX`` is the end token,
``*HEX`` is a line break, ``#`` starts a comment. Decoding takes the longest matching key; a
byte with no entry means the bytes are not text.

Strings whose bytes do not re-encode identically (a game that spells a multi-character
entry as separate single entries, say) are caught by the round-trip check in discovery, not
here.
"""

from __future__ import annotations

from pathlib import Path

from yomineko.core.encodings.base import LITERAL_ESCAPES, Parsed
from yomineko.errors import YominekoError


class TableError(YominekoError, ValueError):
    pass


class TableCodec:
    def __init__(self, path: str | Path, terminator: int = 0):
        self.terminator = terminator
        self.path = Path(path)
        self._decode: dict[bytes, str] = {}
        self._encode: dict[str, bytes] = {}
        self.newline: bytes | None = None
        self._load()
        self._max_key = max((len(k) for k in self._decode), default=1)
        self._max_text = max((len(t) for t in self._encode), default=1)

    def _load(self) -> None:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            raise TableError(f"cannot read table {self.path}: {e}") from e
        for lineno, line in enumerate(lines, 1):
            line = line.rstrip("\r")
            if not line or line.startswith("#"):
                continue
            try:
                if line.startswith("*"):
                    self.newline = bytes.fromhex(line[1:].strip())
                    self._decode[self.newline] = "\n"
                elif line.startswith("/"):
                    continue  # end token: the profile's terminator says which byte it is
                else:
                    key, text = line.split("=", 1)
                    raw = bytes.fromhex(key.strip())
                    if not raw or not text:
                        raise ValueError("empty key or text")
                    self._decode[raw] = text
                    # keep the first key for a text that appears twice
                    self._encode.setdefault(text, raw)
            except ValueError as e:
                raise TableError(f"{self.path}:{lineno}: bad table line {line!r}: {e}") from e
        if self.newline is not None:
            self._encode.setdefault("\n", self.newline)

    def parse(self, data: bytes, start: int, limit: int = 4096) -> Parsed | None:
        out: list[str] = []
        jp = 0
        i = start
        n = len(data)
        while i < n and i - start < limit:
            if data[i] == self.terminator:
                return i, "".join(out), jp
            for size in range(min(self._max_key, n - i), 0, -1):
                text = self._decode.get(data[i : i + size])
                if text is not None:
                    break
            else:
                return None
            if text != "\n":
                jp += len(text)
            out.append("".join(LITERAL_ESCAPES.get(c, c) for c in text) if text != "\n" else text)
            i += size
        return None

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
            try:
                out += self._encode[piece]
            except KeyError:
                raise ValueError(f"no table entry for {piece!r}") from None
            i += step
        return bytes(out)
