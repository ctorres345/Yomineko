"""Profile schema v1: a data-only description of one game, keyed by ROM checksum.

A profile holds offsets, encodings and control-code rules. It never holds game text.
"""

from __future__ import annotations

import re
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROFILE_SCHEMA_VERSION: Final = 1
PROFILE_ID: Final = re.compile(r"^[a-z0-9][a-z0-9-]*$")  # also a folder name
GB_BANK_SIZE: Final = 0x4000  # a Game Boy cartridge is a row of 16 KiB banks


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_regex(pattern: str) -> str:
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(f"invalid regular expression {pattern!r}: {e}") from e
    return pattern


class RomInfo(_Model):
    sha1: str = Field(pattern=r"^[0-9a-f]{40}$")
    game_code: str = Field(pattern=r"^.{3}J$")  # four characters; a Japanese release ends in J
    revision: int = 0


class Encoding(_Model):
    # "table16": the text is a stream of 16-bit little-endian tokens (glyph ids); a text run ends
    # at the first token that is not in the table (see core/encodings/table16.py)
    # "table8": a byte stream of one-byte codes and lead+index kanji, with prefixed commands
    # (see core/encodings/table8.py)
    type: Literal["shift_jis", "table", "table16", "table8"]
    # the byte that ends a string; for table8 it ends the entries of `records` and `strings`
    # tables only (a line ends at a break)
    terminator: int = Field(default=0, ge=0, le=255)
    # "hiragana": the single-byte "half-width katakana" range is drawn as hiragana
    single_byte_kana: Literal["native", "hiragana"] = "native"
    # inclusive lead-byte ranges used for custom glyphs, kept as {XXXX} escapes
    custom_leads: list[tuple[int, int]] = Field(default_factory=list)
    table: str | None = None  # .tbl path, relative to the profile file
    # table16 only: command token -> how many argument tokens follow it. Arguments are never
    # text, even when their value is also a glyph id.
    skip: dict[int, int] = Field(default_factory=dict)
    # table8 only: commands are `command_prefix`, a command byte and parameter bytes.
    # `commands` maps each command byte to its parameter count (-1: up to the next prefix byte);
    # `line_breaks` lists the commands that end a line, the others sit inside a sentence.
    command_prefix: int | None = Field(default=None, ge=0, le=255)
    commands: dict[int, int] = Field(default_factory=dict)
    line_breaks: list[int] = Field(default_factory=list)
    # table8 only: bytes that draw a fixed string the game keeps in its own ROM, as
    # byte -> file offset of that string (table codes up to the terminator). The string is
    # read from the user's ROM, never stored here, and becomes the table text "<string>":
    # the marks keep it apart from the same characters spelled out, and `plain` rules remove
    # them.
    rom_strings: dict[int, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _table_required(self) -> Encoding:
        if self.type in ("table", "table16", "table8") and not self.table:
            raise ValueError(f"encoding.type '{self.type}' needs encoding.table")
        if self.skip and self.type != "table16":
            raise ValueError("encoding.skip is only for encoding.type 'table16'")
        if (self.commands or self.line_breaks or self.command_prefix is not None) and (
            self.type != "table8"
        ):
            raise ValueError(
                "encoding.command_prefix, commands and line_breaks are only for 'table8'"
            )
        if self.commands and self.command_prefix is None:
            raise ValueError("encoding.commands needs encoding.command_prefix")
        if self.rom_strings and self.type != "table8":
            raise ValueError("encoding.rom_strings is only for encoding.type 'table8'")
        for byte, offset in self.rom_strings.items():
            if not 0 <= byte <= 255 or offset < 0:
                raise ValueError(f"encoding.rom_strings {byte:#x}: not a byte and an offset")
        for cmd, count in self.commands.items():
            if not 0 <= cmd <= 255 or not -1 <= count <= 16:
                raise ValueError(f"encoding.commands {cmd:#x}: {count} is not a valid entry")
        for cmd in self.line_breaks:
            if cmd not in self.commands:
                raise ValueError(f"encoding.line_breaks {cmd:#x} is not listed in commands")
        for token, count in self.skip.items():
            if not 0 <= token <= 0xFFFF or not 1 <= count <= 16:
                raise ValueError(f"encoding.skip {token:#x}: {count} is not a valid entry")
        return self


class Region(_Model):
    """A byte range of the ROM, as file offsets. On a Game Boy cartridge ``{bank: n}`` names
    the whole of 16 KiB bank ``n`` instead; it is read as the file offsets ``n * 0x4000`` to
    ``(n + 1) * 0x4000``, which is all that is kept."""

    start: int = Field(default=0, ge=0)
    end: int = Field(default=0, ge=0)
    bank: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _whole_bank(cls, value: object) -> object:
        if not isinstance(value, dict) or value.get("bank") is None:
            return value
        bank = value["bank"]
        if set(value) != {"bank"} or type(bank) is not int or bank < 0:
            raise ValueError("a banked region is {bank: n} alone, n a bank number")
        return {"start": bank * GB_BANK_SIZE, "end": (bank + 1) * GB_BANK_SIZE}

    @model_validator(mode="after")
    def _ordered(self) -> Region:
        if self.end <= self.start:
            raise ValueError("region end must be greater than start")
        return self


class TextConfig(_Model):
    # byte ranges of the ROM that hold plain text; may be empty when all the text is compressed
    regions: list[Region] = Field(default_factory=list)
    pointer_base: int = 0x08000000
    pointer_align: int = Field(default=4, ge=1)
    bank_gap: int = Field(default=0x40, ge=0)


class Unreferenced(_Model):
    min_japanese: int = Field(default=3, ge=0)
    min_kana_ratio: float = Field(default=0.8, ge=0, le=1)


class Frame(_Model):
    """How a message is laid out, for a game whose text bytes are also common in code and data.

    A message is a run of commands. The ``start`` command is followed by text; the others
    (``commands``: command byte -> number of parameter bytes) are stepped over. Text is table
    codes and ``breaks`` (each ends a line) up to an end byte: one of ``ends`` and the message
    is over, ``resume`` and commands follow (as a command, ``resume`` ends the message). Bytes
    that do not fit this are not a message, and nothing is read from them."""

    start: int = Field(ge=0, le=255)
    breaks: list[int] = Field(default_factory=list)
    ends: list[int] = Field(min_length=1)
    resume: int | None = Field(default=None, ge=0, le=255)
    commands: dict[int, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _bytes(self) -> Frame:
        for value in (*self.breaks, *self.ends, *self.commands):
            if not 0 <= value <= 255:
                raise ValueError(f"frame: {value:#x} is not a byte")
        for cmd, count in self.commands.items():
            if not 0 <= count <= 16:
                raise ValueError(f"frame.commands {cmd:#x}: {count} is not a parameter count")
        if self.commands and self.resume is None:
            raise ValueError("frame.commands needs frame.resume: commands follow it")
        marks = [self.start, *self.breaks, *self.ends, *self.commands]
        if self.resume is not None:
            marks.append(self.resume)
        if len(set(marks)) != len(marks):
            raise ValueError("frame: a byte can have one role only")
        return self


class Discover(_Model):
    min_score: float = Field(default=0.7, ge=0, le=1)
    unreferenced: Unreferenced = Field(default_factory=Unreferenced)
    # regexes stripped from a string before it is scored (control codes, placeholders)
    ignore: list[str] = Field(default_factory=list)
    # table8 only: a run of text in a region is kept as a line when it has at least this many
    # kana and kanji, and they are at least this share of its kana, kanji and Latin letters
    # (graphics data that happens to decode has odd letters between the kana)
    stream_min_chars: int = Field(default=2, ge=1)
    stream_min_jp_ratio: float = Field(default=0.7, ge=0, le=1)
    # table8 only: text is read from whole messages and nowhere else. A message is kept when
    # a pointer in its own bank leads to it (Game Boy), or when its text, with the `ignore`
    # patterns removed, has at least `unreferenced.min_japanese` kana and kanji.
    frame: Frame | None = None

    @field_validator("ignore")
    @classmethod
    def _regexes(cls, v: list[str]) -> list[str]:
        return [_check_regex(p) for p in v]


class PlainRule(_Model):
    pattern: str
    replace: str = ""

    @field_validator("pattern")
    @classmethod
    def _regex(cls, v: str) -> str:
        return _check_regex(v)


class Kinds(_Model):
    dialogue_min_length: int = Field(default=12, ge=0)


class TableSpec(_Model):
    """A table of names, ``count`` entries from ``base``.

    ``pointers``: entry ``i`` holds a text pointer at ``base + i*stride + field``.
    ``records``: entry ``i`` is the text itself, ``stride`` bytes at ``base + i*stride``, padded
    with the encoding's terminator. ``strings``: the texts follow one another, each ended by the
    terminator."""

    category: str
    kind: Literal["pointers", "records", "strings"] = "pointers"
    base: int = Field(ge=0)
    stride: int = Field(default=0, ge=0)
    count: int = Field(gt=0)
    field: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _shape(self) -> TableSpec:
        if (self.stride == 0) != (self.kind == "strings"):
            raise ValueError(
                f"a '{self.kind}' table {'takes no' if self.stride else 'needs a'} stride"
            )
        if self.field and self.kind != "pointers":
            raise ValueError("tables: 'field' is only for kind 'pointers'")
        return self


class PointerTable(_Model):
    """``count`` pointers, ``stride`` bytes apart from ``base``, to compressed blocks."""

    base: int = Field(ge=0)
    count: int = Field(gt=0)
    stride: int = Field(default=4, gt=0)


class CompressedText(_Model):
    """Text kept in compressed blocks. Each block opens with an entry count and entry offsets
    (core/containers.py). Lines inside have no ROM offset: they get virtual addresses."""

    scheme: Literal["lz77"] = "lz77"  # GBA BIOS LZ77 (type 0x10)
    tables: list[PointerTable] = Field(min_length=1)
    # blocks of the same layout that the game keeps without compression, as file offsets. They
    # are numbered after the blocks of `tables`, so adding one never moves an existing line id.
    uncompressed: list[Region] = Field(default_factory=list)
    min_chars: int = Field(default=2, ge=1)  # shortest run of text kept as a line


class SentenceCaps(_Model):
    """Most sentences of a structural kind a deck may hold; None means no limit."""

    name_quote: int | None = Field(default=None, ge=0)  # lines that open with 〇〇「
    name_subject: int | None = Field(default=None, ge=0)  # lines that open with 〇〇は　 and so on


class Sentences(_Model):
    """How sentence selection treats this game. Addresses and counts only, never text."""

    # file-offset ranges whose lines never enter a deck on their own (e.g. rule-text tables)
    exclude_ranges: list[Region] = Field(default_factory=list)
    caps: SentenceCaps = Field(default_factory=SentenceCaps)


class Profile(_Model):
    schema_version: Literal[1] = PROFILE_SCHEMA_VERSION
    id: str = Field(pattern=PROFILE_ID.pattern)
    title: str
    platform: Literal["gba", "gbc"]
    rom: RomInfo
    encoding: Encoding
    text: TextConfig
    discover: Discover = Field(default_factory=Discover)
    plain: list[PlainRule] = Field(default_factory=list)
    kinds: Kinds = Field(default_factory=Kinds)
    tables: list[TableSpec] = Field(default_factory=list)
    compressed: CompressedText | None = None
    sentences: Sentences = Field(default_factory=Sentences)

    @model_validator(mode="after")
    def _has_text(self) -> Profile:
        if not self.text.regions and self.compressed is None:
            raise ValueError("a profile needs text.regions or a compressed block")
        if self.compressed is not None and self.encoding.type != "table16":
            raise ValueError("compressed text needs encoding.type 'table16'")
        if self.encoding.type == "table8" and not self.text.regions:
            raise ValueError("encoding.type 'table8' needs text.regions")
        if self.discover.frame is not None and self.encoding.type != "table8":
            raise ValueError("discover.frame is only for encoding.type 'table8'")
        if self.discover.frame is not None and self.encoding.command_prefix is not None:
            # a prefixed break would end a run inside the message, which the frame does not know
            raise ValueError("discover.frame cannot be combined with encoding.command_prefix")
        if self.encoding.type == "table16" and any(t.kind != "pointers" for t in self.tables):
            raise ValueError("tables of kind 'records' or 'strings' need a one-byte terminator")
        return self
