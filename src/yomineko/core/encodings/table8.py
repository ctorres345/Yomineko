"""Byte-token tables: text stored as one-byte codes, kanji as a lead byte plus an index byte.

Some games draw text from a font and keep each character as the glyph's code in a byte stream.
The ``.tbl`` has one ``HH=text`` line per one-byte code and one ``HHHH=text`` line per two-byte
code (a lead byte, then an index byte). Commands are introduced by a prefix byte (``0xFF``) and a
command byte, and may carry parameter bytes; the profile says how many.

A *run* is a stretch of tokens that can be read as text, with the commands that sit in the
middle of a sentence kept as ``{XX}`` escapes so the run re-encodes to the exact bytes. It ends
at a command the profile marks as a break, or at a byte that is neither a token nor a command.
Every code must map to a different text so that re-encoding gives the original bytes back; a
two-byte code that is not in the table becomes a ``{XXXX}`` escape.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from yomineko.core.encodings.base import LITERAL_ESCAPES, TOKEN, Parsed
from yomineko.core.encodings.tbl import TableError

_JAPANESE_FROM = 0x3000  # CJK punctuation, kana, kanji and full-width forms
UNTIL_PREFIX = -1  # a command whose parameters run up to the next prefix byte
RUN_LIMIT = 4096  # longest run `parse` reads; extraction and `verify` must use the same value


class Table8Codec:
    # not used: a run ends at a break command or at a byte that is not text
    terminator = 0

    def __init__(
        self,
        path: str | Path,
        prefix: int | None = None,
        commands: Mapping[int, int] | None = None,
        breaks: frozenset[int] | set[int] = frozenset(),
        extra: Mapping[int, str] | None = None,
    ):
        """``extra`` adds one-byte codes that are not in the table file (code -> text), for a
        game that keeps part of its table in the ROM itself."""
        self.path = Path(path)
        self.prefix = prefix
        self.commands = dict(commands or {})
        self.breaks = frozenset(breaks)
        self._decode: dict[int, str] = {}  # code (1 or 2 bytes, as an int) -> text
        self._decode2: dict[int, str] = {}  # (lead << 8 | index) -> text
        self._encode: dict[str, bytes] = {}
        self._leads: set[int] = set()
        self._load()
        for code, text in (extra or {}).items():
            self._add(f"{code:02X}", text, f"{self.path}: byte {code:02X}")
        self._check()
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
                if len(key) not in (2, 4) or not text:
                    raise ValueError("a key is 2 or 4 hex digits and the text is not empty")
                int(key, 16)
            except ValueError as e:
                raise TableError(f"{self.path}:{lineno}: bad table line {line!r}: {e}") from e
            self._add(key, text, f"{self.path}:{lineno}")

    def _add(self, key: str, text: str, where: str) -> None:
        """One entry: ``key`` is 2 or 4 hex digits. Every code and every text is used once."""
        code = int(key, 16)
        if text in self._encode:
            raise TableError(
                f"{where}: {text!r} is already the text of "
                f"{self._encode[text].hex().upper()}; a table8 must map back uniquely"
            )
        if len(key) == 2:
            if code in self._decode:
                raise TableError(f"{where}: code {key.upper()} appears twice")
            self._decode[code] = text
        else:
            if code in self._decode2:
                raise TableError(f"{where}: code {key.upper()} appears twice")
            self._decode2[code] = text
            self._leads.add(code >> 8)
        self._encode[text] = bytes.fromhex(key)

    def _check(self) -> None:
        clash = self._leads & self._decode.keys()
        if clash:
            raise TableError(
                f"{self.path}: byte {min(clash):02X} is both a one-byte code and the lead of a "
                "two-byte code"
            )
        if self.prefix is not None and (self.prefix in self._decode or self.prefix in self._leads):
            raise TableError(f"{self.path}: the command prefix {self.prefix:02X} is in the table")

    def __len__(self) -> int:
        return len(self._decode) + len(self._decode2)

    def _command_end(self, data: bytes, i: int) -> int | None:
        """Offset just past the command at ``i`` (prefix, command, parameters); ``None`` if the
        command is unknown, a break, or runs off the data."""
        if i + 2 > len(data):
            return None
        cmd = data[i + 1]
        if cmd in self.breaks or cmd not in self.commands:
            return None
        count = self.commands[cmd]
        if count == UNTIL_PREFIX:
            nxt = data.find(bytes([self.prefix or 0]), i + 2)
            end = len(data) if nxt == -1 else nxt
        else:
            end = i + 2 + count
        return end if end <= len(data) else None

    def starts_text(self, byte: int) -> bool:
        """Whether a byte is a one-byte code or the lead of a two-byte code."""
        return byte in self._decode or byte in self._leads

    def skip_inline(self, data: bytes, i: int) -> int:
        """``i`` moved past the sentence commands (not breaks) that sit at it, so a line starts
        at its first character and not at a style command in front of it."""
        while self.prefix is not None and i < len(data) and data[i] == self.prefix:
            end = self._command_end(data, i)
            if end is None:
                break
            i = end
        return i

    def skip_len(self, data: bytes, i: int) -> int:
        """How many bytes to step over at ``i`` when it does not start a run: a known command
        with its parameters, an unknown command (just its two bytes), a two-byte code, or one
        byte."""
        if self.prefix is not None and data[i] == self.prefix and i + 2 <= len(data):
            count = self.commands.get(data[i + 1], 0)
            if count == UNTIL_PREFIX:
                nxt = data.find(bytes([self.prefix]), i + 2)
                return (len(data) if nxt == -1 else nxt) - i
            return min(2 + count, len(data) - i)
        if data[i] in self._leads:
            return min(2, len(data) - i)
        return 1

    def parse(self, data: bytes, start: int, limit: int = RUN_LIMIT) -> Parsed | None:
        """The run at ``start``; ``None`` if it does not begin with text (a lone command or an
        unknown byte). ``end`` is the offset of the first byte that ends the run."""
        out: list[str] = []
        jp = 0
        text_seen = False
        i = start
        n = len(data)
        while i < n and i - start < limit:
            b = data[i]
            if self.prefix is not None and b == self.prefix:
                end = self._command_end(data, i)
                if end is None:
                    break
                out.extend(f"{{{x:02X}}}" for x in data[i:end])
                i = end
                continue
            if b in self._leads:
                if i + 2 > n:
                    break
                code = b << 8 | data[i + 1]
                text = self._decode2.get(code)
                if text is None:
                    out.append(f"{{{code:04X}}}")
                else:
                    out.append("".join(LITERAL_ESCAPES.get(c, c) for c in text))
                    jp += sum(1 for c in text if ord(c) >= _JAPANESE_FROM)
                    text_seen = True
                i += 2
                continue
            text = self._decode.get(b)
            if text is None:
                break
            out.append("".join(LITERAL_ESCAPES.get(c, c) for c in text))
            jp += sum(1 for c in text if ord(c) >= _JAPANESE_FROM)
            text_seen = True
            i += 1
        if i == start or not text_seen:
            return None
        return i, "".join(out), jp

    def encode(self, text: str) -> bytes:
        out = bytearray()
        i = 0
        while i < len(text):
            m = TOKEN.match(text, i)
            assert m is not None  # TOKEN matches any single character
            token = m.group(0)
            if token in ("\\\\", "\\{", "\\}"):
                piece, step = token[1], 2
            elif m.group(1):
                out += bytes.fromhex(m.group(1))
                i = m.end()
                continue
            else:
                for size in range(min(self._max_text, len(text) - i), 0, -1):
                    piece, step = text[i : i + size], size
                    if piece in self._encode:
                        break
                else:
                    raise ValueError(f"no table entry for {text[i]!r}")
            code = self._encode.get(piece)
            if code is None:
                raise ValueError(f"no table entry for {piece!r}")
            out += code
            i += step
        return bytes(out)
