"""Build tiny synthetic GBA and Game Boy Color ROMs for tests.

Every ROM is deterministic and about 64 KiB. Each build returns ``(rom_bytes, Manifest)``;
the manifest lists every string the extractor must find, with its offset, readable text,
bank and whether a pointer references it, plus the noise it must reject.

All sentences are written for these tests (weather, cats, tea). Nothing comes from a game,
and the headers carry no logo data.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

POINTER_BASE = 0x08000000
ROM_SIZE = 0x10000
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FAKE_TBL = DATA_DIR / "fake.tbl"
FAKE16_TBL = DATA_DIR / "fake16.tbl"


@dataclass(frozen=True)
class Expected:
    offset: int
    end: int  # offset of the terminator byte
    raw: str  # extractor text: round-trippable, with {XX} escapes and control codes
    text: str  # readable text after the profile's `plain` rules
    kind: str  # "dialogue" or "term"
    referenced: bool
    bank: int  # 0-based bank index (strings within bank_gap of each other share a bank)


@dataclass(frozen=True)
class ExpectedBlock:
    index: int
    rom_offset: int  # where the LZ77 stream starts
    data: bytes  # decompressed: an offset table, then the entries
    entries: list[tuple[int, int]]  # (start, end) of each entry inside ``data``


@dataclass(frozen=True)
class ExpectedRun:
    """A text run inside a compressed block: where it is (offset in the decompressed block) and
    the extractor text."""

    block: int
    entry: int
    offset: int
    end: int  # offset of the token that ends the run (or the end of the entry)
    raw: str


@dataclass
class Manifest:
    strings: list[Expected] = field(default_factory=list)
    blocks: list[ExpectedBlock] = field(default_factory=list)  # compressed script blocks
    runs: list[ExpectedRun] = field(default_factory=list)  # text runs that must be found
    dropped_runs: list[tuple[int, int]] = field(default_factory=list)  # (block, offset): too short
    rejected: dict[int, str] = field(default_factory=dict)  # offset -> why it is not text
    shared_suffix: list[int] = field(default_factory=list)  # pointers into another string
    terms: list[tuple[str, int, int]] = field(default_factory=list)  # (category, index, offset)
    names: list[tuple[str, int, str]] = field(default_factory=list)  # (category, index, text)
    noise: tuple[int, int] = (0, 0)  # (start, end) of the random block

    @property
    def bank_count(self) -> int:
        return len({s.bank for s in self.strings})


def lcg_bytes(seed: int) -> Iterator[int]:
    """Deterministic pseudo-random bytes, independent of the Python version."""
    x = seed
    while True:
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        yield (x >> 16) & 0xFF


class SynthRom:
    def __init__(
        self,
        title: str,
        game_code: str,
        fill: int = 0x00,
        revision: int = 0,
        size: int = ROM_SIZE,
        platform: str = "gba",
    ):
        self.size = size
        self.title = title
        self.game_code = game_code
        self.revision = revision
        self.platform = platform
        self.data = bytearray([fill]) * size
        header = (0, 0xC0) if platform == "gba" else (0x100, 0x150)
        self.data[header[0] : header[1]] = bytes(header[1] - header[0])  # never the fill byte
        self.manifest = Manifest()
        self._used: list[tuple[int, int]] = [header]

    def _claim(self, offset: int, length: int) -> None:
        end = offset + length
        if offset < 0 or end > self.size:
            raise ValueError(f"write at 0x{offset:X} is outside the ROM")
        for a, b in self._used:
            if offset < b and a < end:
                raise ValueError(f"write at 0x{offset:X} overlaps 0x{a:X}-0x{b:X}")
        self._used.append((offset, end))

    def put(self, offset: int, blob: bytes) -> None:
        self._claim(offset, len(blob))
        self.data[offset : offset + len(blob)] = blob

    def add_string(
        self,
        offset: int,
        data: bytes,
        terminator: int,
        *,
        raw: str,
        text: str,
        kind: str,
        bank: int,
        referenced: bool = True,
    ) -> int:
        self.put(offset, data + bytes([terminator]))
        self.manifest.strings.append(
            Expected(offset, offset + len(data), raw, text, kind, referenced, bank)
        )
        return offset

    def add_reject(self, offset: int, data: bytes, terminator: int, why: str) -> int:
        """Bytes a pointer references that must NOT be extracted as text."""
        self.put(offset, data + bytes([terminator]))
        self.manifest.rejected[offset] = why
        return offset

    def add_pointer_table(self, offset: int, targets: list[int]) -> None:
        blob = b"".join((POINTER_BASE + t).to_bytes(4, "little") for t in targets)
        self.put(offset, blob)

    def add_compressed_blocks(
        self,
        table_offset: int,
        start: int,
        entry_sets: list[list[bytes]],
        *,
        extra_words: int = 0,
        align: int = 4,
    ) -> list[ExpectedBlock]:
        """LZ77 blocks laid out from ``start`` and a pointer table to them at ``table_offset``.

        Each element of ``entry_sets`` is the entries of one block. A block is a u32 count, that
        many u32 words (the entry offsets, then ``extra_words`` values that are not offsets,
        like the tail seen in a real game), then the entries. The manifest records what each
        block must decompress to.
        """
        blocks: list[ExpectedBlock] = []
        pos = start
        for index, entries in enumerate(entry_sets):
            n = len(entries) + extra_words
            starts = [4 + 4 * n]
            for e in entries[:-1]:
                starts.append(starts[-1] + len(e))
            extras = [(k + 1) << 20 | 2 for k in range(extra_words)]  # larger than any block
            words = b"".join(w.to_bytes(4, "little") for w in [*starts, *extras])
            data = n.to_bytes(4, "little") + words + b"".join(entries)
            ends = [*starts[1:], len(data)]
            blob = lz77_compress(data, literals_only=index % 2 == 1)  # both encodings
            self.put(pos, blob)
            blocks.append(ExpectedBlock(index, pos, data, list(zip(starts, ends, strict=True))))
            pos = -(-(pos + len(blob)) // align) * align
        self.add_pointer_table(table_offset, [b.rom_offset for b in blocks])
        self.manifest.blocks.extend(blocks)
        return blocks

    def add_struct_table(
        self, offset: int, stride: int, targets: list[int], category: str, field_offset: int = 0
    ) -> None:
        """Entry i = ``stride`` bytes: a text pointer at ``field_offset``, small ints elsewhere."""
        for i, target in enumerate(targets):
            entry = bytearray(stride)
            for j in range(stride):
                entry[j] = (i + 1) if j % 4 == 0 else 0
            entry[field_offset : field_offset + 4] = (POINTER_BASE + target).to_bytes(4, "little")
            self.put(offset + i * stride, bytes(entry))
            self.manifest.terms.append((category, i, target))

    def add_noise(
        self, start: int, length: int, seed: int, low: int, high: int, force_every4: int | None
    ) -> None:
        """Random bytes in [low, high]. ``force_every4`` pins each 4-byte word's top byte so
        no word can look like a 0x08xxxxxx pointer."""
        gen = lcg_bytes(seed)
        blob = bytearray()
        for i in range(length):
            b = low + next(gen) % (high - low + 1)
            if force_every4 is not None and i % 4 == 3:
                b = force_every4
            blob.append(b)
        self.put(start, bytes(blob))
        self.manifest.noise = (start, start + length)

    def _write_header(self) -> None:
        if self.platform != "gba":
            write_gb_header(self.data, self.title, self.game_code, revision=self.revision)
            return
        h = self.data
        h[0:4] = bytes([0xFE, 0xFF, 0xFF, 0xEA])  # ARM branch, like a real ROM
        title = self.title.encode("ascii")[:12].ljust(12, b"\0")
        h[0xA0:0xAC] = title
        h[0xAC:0xB0] = self.game_code.encode("ascii")[:4].ljust(4, b"\0")
        h[0xB0:0xB2] = b"00"
        h[0xB2] = 0x96  # fixed value
        h[0xBC] = self.revision
        h[0xBD] = (-(sum(h[0xA0:0xBD]) + 0x19)) & 0xFF  # complement check

    def finish(self) -> tuple[bytes, Manifest]:
        self._write_header()
        self.manifest.strings.sort(key=lambda s: s.offset)
        return bytes(self.data), self.manifest


# ----------------------------------------------------------------- LZ77 encoder


def lz77_compress(data: bytes, *, literals_only: bool = False) -> bytes:
    """A small GBA BIOS LZ77 (0x10) encoder, for building test ROMs only.

    Greedy: at each position take the longest earlier match (3-18 bytes, up to 4096 back),
    otherwise a literal. ``literals_only`` never emits a reference.
    """
    out = bytearray([0x10]) + len(data).to_bytes(3, "little")
    i = 0
    while i < len(data):
        flags = 0
        items = bytearray()
        for bit in range(7, -1, -1):
            if i >= len(data):
                break
            best_len, best_dist = 0, 0
            if not literals_only:
                for dist in range(1, min(i, 4096) + 1):
                    n = 0
                    while n < 18 and i + n < len(data) and data[i + n - dist] == data[i + n]:
                        n += 1
                    if n > best_len:
                        best_len, best_dist = n, dist
            if best_len >= 3:
                flags |= 1 << bit
                d = best_dist - 1
                items += bytes([(best_len - 3) << 4 | d >> 8, d & 0xFF])
                i += best_len
            else:
                items.append(data[i])
                i += 1
        out.append(flags)
        out += items
    return bytes(out)


# ---------------------------------------------------------------- Shift-JIS ROM


def sjis(*parts: str | bytes) -> bytes:
    return b"".join(p if isinstance(p, bytes) else p.encode("shift_jis") for p in parts)


def build_sjis_rom() -> tuple[bytes, Manifest]:
    """Shift-JIS text with the quirks seen in real GBA games: single-byte kana drawn as
    hiragana, custom glyph bytes, control codes, an unreferenced line, a shared-suffix
    pointer, bank gaps, and noise that must be rejected."""
    r = SynthRom("SYNTH TEST", "TSTJ")
    nul = 0

    s1 = r.add_string(
        0x100,
        sjis("今日はいい天気ですね。"),
        nul,
        raw="今日はいい天気ですね。",
        text="今日はいい天気ですね。",
        kind="dialogue",
        bank=0,
    )
    s2 = r.add_string(  # colour and page codes stay ASCII
        0x140,
        sjis("#CGねこ#Rがおちゃをのむ。#Pおいしいね！"),
        nul,
        raw="#CGねこ#Rがおちゃをのむ。#Pおいしいね！",
        text="ねこがおちゃをのむ。\nおいしいね！",
        kind="dialogue",
        bank=0,
    )
    s3 = r.add_string(  # single-byte kana range, drawn as hiragana by the game
        0x170,
        sjis("ﾃｷﾊ　にげた！"),
        nul,
        raw="ﾃｷﾊ　にげた！",
        text="てきは　にげた！",
        kind="dialogue",
        bank=0,
    )
    s4 = r.add_string(  # custom glyph: lead byte 0x85 is in the profile's custom range
        0x180,
        sjis("ボタン", bytes([0x85, 0x40]), "をおして、つぎへすすもう！"),
        nul,
        raw="ボタン{8540}をおして、つぎへすすもう！",
        text="ボタンをおして、つぎへすすもう！",
        kind="dialogue",
        bank=0,
    )
    s5 = r.add_string(  # control byte 0x0D inside a line
        0x1C0,
        sjis("ねこが", b"\x0d", "ないた。"),
        nul,
        raw="ねこが{0D}ないた。",
        text="ねこが\nないた。",
        kind="dialogue",
        bank=0,
    )
    r.add_string(  # no pointer references this one; found because it follows a NUL
        0x1E0,
        sjis("むかしむかし、あるところに、ねこがすんでいました。"),
        nul,
        raw="むかしむかし、あるところに、ねこがすんでいました。",
        text="むかしむかし、あるところに、ねこがすんでいました。",
        kind="dialogue",
        bank=0,
        referenced=False,
    )
    s7 = r.add_string(
        0x400,
        sjis("お茶をのみましょう。"),
        nul,
        raw="お茶をのみましょう。",
        text="お茶をのみましょう。",
        kind="dialogue",
        bank=1,
    )
    s8 = r.add_string(
        0x800,
        sjis("あしたはあめがふるそうです。ほんとうかな？"),
        nul,
        raw="あしたはあめがふるそうです。ほんとうかな？",
        text="あしたはあめがふるそうです。ほんとうかな？",
        kind="dialogue",
        bank=2,
    )
    r.add_reject(0xA00, bytes([0xB1, 0xB2, 0xB3, 0xB4, 0xB5]), nul, "single-byte kana only")
    r.add_reject(0xA20, sjis("亜唖娃阿哀"), nul, "kanji only, no kana")
    terms = [
        r.add_string(
            off,
            sjis(word),
            nul,
            raw=word,
            text=word,
            kind="term",
            bank=3,
        )
        for off, word in ((0xC00, "おちゃ"), (0xC10, "ねこ"), (0xC20, "つき"))
    ]
    r.add_noise(0x1000, 0x1000, seed=1, low=0x01, high=0xFF, force_every4=0xFF)
    shared = s1 + 6  # a pointer into the middle of the first line
    r.manifest.shared_suffix.append(shared)
    r.add_pointer_table(0x2000, [s1, s2, s3, s4, s5, s7, s8, 0xA00, 0xA20, shared])
    r.add_struct_table(0x3000, 8, terms, "item")
    return r.finish()


# ------------------------------------------------------------------- table ROM


def load_tbl(path: Path = FAKE_TBL) -> dict:
    """A small, independent .tbl reader used only to build test ROMs."""
    keys: dict[str, bytes] = {}
    newline = end = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        if line.startswith("*"):
            newline = bytes.fromhex(line[1:])
        elif line.startswith("/"):
            end = bytes.fromhex(line[1:])
        else:
            hexpart, text = line.split("=", 1)
            keys[text] = bytes.fromhex(hexpart)
    return {"keys": keys, "newline": newline, "end": end}


def tbl_encode(text: str, tbl: dict) -> bytes:
    """Greedy longest-match encode; ``\\n`` becomes the table's newline byte."""
    keys = tbl["keys"]
    longest = max(len(k) for k in keys)
    out = bytearray()
    i = 0
    while i < len(text):
        if text[i] == "\n":
            out += tbl["newline"]
            i += 1
            continue
        for n in range(min(longest, len(text) - i), 0, -1):
            piece = text[i : i + n]
            if piece in keys:
                out += keys[piece]
                i += n
                break
        else:
            raise ValueError(f"no table entry for {text[i]!r}")
    return bytes(out)


def build_tbl_rom() -> tuple[bytes, Manifest]:
    """The same kind of text under a made-up table encoding (tests/data/fake.tbl):
    two-byte multi-character entries, a newline byte, a placeholder token, 0xFF terminator
    and 0xFF-filled unused space like a real flash dump."""
    tbl = load_tbl()
    end = tbl["end"][0]
    r = SynthRom("SYNTH TBL", "TBLJ", fill=end)

    def enc(raw: str) -> bytes:
        return tbl_encode(raw, tbl)

    t1 = r.add_string(
        0x100,
        enc("ねこが<NAME>をのむ。"),
        end,
        raw="ねこが<NAME>をのむ。",
        text="ねこが〇〇をのむ。",
        kind="dialogue",
        bank=0,
    )
    t2 = r.add_string(
        0x120,
        enc("きょうは\nいいてんきですね。"),
        end,
        raw="きょうは\nいいてんきですね。",
        text="きょうは\nいいてんきですね。",
        kind="dialogue",
        bank=0,
    )
    r.add_string(
        0x180,
        enc("むかしむかし、ねこがいました。"),
        end,
        raw="むかしむかし、ねこがいました。",
        text="むかしむかし、ねこがいました。",
        kind="dialogue",
        bank=1,
        referenced=False,
    )
    r.add_reject(0xA00, bytes([0xC0, 0xC1, 0xC2]), end, "bytes not in the table")
    terms = [
        r.add_string(0x400, enc("おちゃ"), end, raw="おちゃ", text="おちゃ", kind="term", bank=2),
        r.add_string(0x410, enc("つき"), end, raw="つき", text="つき", kind="term", bank=2),
    ]
    r.add_noise(0x1000, 0x1000, seed=2, low=0x60, high=0xDF, force_every4=None)
    r.add_pointer_table(0x2000, [t1, t2, 0xA00])
    r.add_struct_table(0x3000, 8, terms, "item")
    return r.finish()


# ---------------------------------------------------------- compressed 16-bit ROM


def load_tbl16(path: Path = FAKE16_TBL) -> dict[str, int]:
    """A small, independent reader of a 16-bit table (text -> token), for building test ROMs."""
    keys: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            hexpart, text = line.split("=", 1)
            keys[text] = int(hexpart, 16)
    return keys


def tokens(tbl: dict[str, int], *parts: int | str) -> bytes:
    """16-bit little-endian tokens: an int is a command or argument word, a str is text."""
    out = bytearray()
    for part in parts:
        if isinstance(part, int):
            out += part.to_bytes(2, "little")
        else:
            for ch in part:
                out += tbl[ch].to_bytes(2, "little")
    return bytes(out)


def build_lz16_rom() -> tuple[bytes, Manifest]:
    """Two LZ77 blocks of entries holding 16-bit token streams: commands with arguments (some
    argument values are also glyph ids), text runs that are kept, runs too short to keep, runs
    that end at the end of an entry, and a table with words that are not offsets."""
    tbl = load_tbl16()
    r = SynthRom("SYNTH LZ16", "LZ1J")
    LINE, WAIT, SPEAKER, POSE = 0x01, 0x03, 0x0E, 0x0B
    ARG_I, ARG_U = tbl["い"], tbl["う"]  # arguments whose values are glyph ids

    keep, drop = "keep", "drop"
    # (kind, text) parts and raw commands: kind is None for a command word
    block_entries: list[list[list[tuple[str | None, int | str]]]] = [
        [  # block 0
            [
                (None, SPEAKER),
                (None, ARG_I),
                (keep, "ねこがおちゃをのむ。"),
                (None, LINE),
                (keep, "「あしたはあめかな？」"),
                (None, WAIT),
            ],
            [
                (None, 0x0C),
                (drop, "あ"),
                (None, 0x0C),
                (keep, "てんきがいいですね。"),
                (None, 0x00),
                (None, POSE),
                (None, ARG_U),
                (keep, "つきがきれいだよ"),
                (None, LINE),
                (drop, "12"),
                (None, WAIT),
            ],
            [(None, 0x00), (keep, "おちゃをのもう！")],  # ends the entry on text
        ],
        [  # block 1
            [
                (keep, "きょうはいいてんき"),
                (None, 0x1E),
                (None, 0x00),
                (None, 0x00),
                (keep, "そらがあおい。"),
            ],
            [(keep, "あめがふってきた！"), (None, WAIT)],  # starts on text right after an entry
            [(None, SPEAKER), (None, tbl["ね"]), (drop, "ー"), (None, WAIT), (keep, "ほんとう？")],
        ],
    ]
    entry_bytes: list[list[bytes]] = []
    placed: list[list[list[tuple[int, str]]]] = []  # per entry: (offset in entry, raw) of kept runs
    dropped: list[list[list[int]]] = []
    for entries in block_entries:
        eb, ep, ed = [], [], []
        for parts in entries:
            data = bytearray()
            runs: list[tuple[int, str]] = []
            gone: list[int] = []
            for kind, part in parts:
                if kind is None:
                    data += tokens(tbl, part)
                    continue
                if kind == keep:
                    runs.append((len(data), str(part)))
                else:
                    gone.append(len(data))
                data += tokens(tbl, str(part))
            eb.append(bytes(data))
            ep.append(runs)
            ed.append(gone)
        entry_bytes.append(eb)
        placed.append(ep)
        dropped.append(ed)

    blocks = r.add_compressed_blocks(0x200, 0x1000, entry_bytes, extra_words=2)
    for bi, block in enumerate(blocks):
        for ei, (start, end) in enumerate(block.entries):
            for offset, raw in placed[bi][ei]:
                run_end = start + offset + 2 * len(raw)
                r.manifest.runs.append(ExpectedRun(bi, ei, start + offset, min(run_end, end), raw))
            for offset in dropped[bi][ei]:
                r.manifest.dropped_runs.append((bi, start + offset))
    return r.finish()


# ------------------------------------------------------------ byte-stream ROM

FAKE8_TBL = DATA_DIR / "fake8.tbl"
T8_START, T8_END = 0x400, 0xC00  # the profile's text region
T8_PREFIX = 0xFF


def build_table8_rom() -> tuple[bytes, Manifest]:
    """A stream of one-byte codes and commands inside a region: lines that end at break commands,
    a command with parameters that look like text, a command inside a sentence, an unknown
    two-byte code, runs that must be dropped (one character, mostly Latin letters, leaving the
    region), and a valid line outside the region that must not be read."""
    tbl = load_tbl(FAKE8_TBL)
    r = SynthRom("SYNTH TABLE8", "TB8J")
    manifest = r.manifest

    def t(text: str) -> bytes:
        return tbl_encode(text, tbl)

    def cmd(c: int, *params: int) -> bytes:
        return bytes([T8_PREFIX, c, *params])

    pos = T8_START

    def put(blob: bytes) -> int:
        nonlocal pos
        at = pos
        r.put(at, blob)
        pos += len(blob)
        return at

    def line(blob: bytes, raw: str, text: str) -> None:
        at = put(blob)
        manifest.strings.append(Expected(at, at + len(blob), raw, text, "dialogue", False, 0))

    def drop(blob: bytes, why: str) -> None:
        manifest.rejected[put(blob)] = why

    end = cmd(0x00)
    put(cmd(0x03) + cmd(0x35))  # commands only: no run
    line(t("ねこがおちゃをのむ。"), "ねこがおちゃをのむ。", "ねこがおちゃをのむ。")
    put(end)
    put(cmd(0x0A, 0x81, 0x82, 0x83, 0x84))  # event record whose parameters look like kana
    put(cmd(0x35))
    line(
        t("きょうは　いい天気ですね！"), "きょうは　いい天気ですね！", "きょうは　いい天気ですね！"
    )
    put(end)
    # a command inside a sentence stays in the line, as escapes
    line(
        t("ねこが") + cmd(0x0B, 0x01) + t("おちゃ"),
        "ねこが{FF}{0B}{01}おちゃ",
        "ねこがおちゃ",
    )
    put(end)
    drop(t("あ"), "one character")
    put(cmd(0x01, 0x00))  # a break that has a parameter
    drop(t("あａｂいｃ"), "mostly Latin letters")
    put(end)
    line(t("ねこ") + bytes([0xFA, 0xFE]) + t("ねこ"), "ねこ{FAFE}ねこ", "ねこねこ")
    put(end)
    put(cmd(0x7E))  # an unknown command ends a run and is stepped over
    line(t("あした　あめ？"), "あした　あめ？", "あした　あめ？")
    put(b"\x00\x00\x00")
    line(t("今日は　日よう日！"), "今日は　日よう日！", "今日は　日よう日！")
    put(b"\x00")
    # a run that starts inside the region and leaves it, and a valid line outside it
    r.put(T8_END - 8, t("おちゃをのむねこがいる。" * 4))
    manifest.rejected[T8_END - 8] = "leaves the region"
    r.put(T8_END + 0x100, t("ねこがおちゃをのむ。"))
    manifest.rejected[T8_END + 0x100] = "outside the region"
    return r.finish()


# ----------------------------------------------------------------- Game Boy header


def write_gb_header(
    data: bytearray,
    title: str = "SYNTH TEST",
    game_code: str = "TSTJ",
    *,
    color: bool = True,
    destination: int = 0x00,
    revision: int = 0,
) -> None:
    """A Game Boy header in place, with both checksums right and no logo data. Call it last:
    the second checksum covers the whole ROM. Without ``game_code`` the title takes the code's
    bytes too, as on older cartridges."""
    name = title.encode("ascii")
    if game_code:
        data[0x134:0x13F] = name[:11].ljust(11, b"\0")
        data[0x13F:0x143] = game_code.encode("ascii")[:4].ljust(4, b"\0")
    else:
        data[0x134:0x143] = name[:15].ljust(15, b"\0")
    data[0x143] = 0xC0 if color else 0x00
    data[0x14A] = destination
    data[0x14C] = revision
    x = 0
    for b in data[0x134:0x14D]:
        x = (x - b - 1) & 0xFF
    data[0x14D] = x
    data[0x14E:0x150] = b"\0\0"
    data[0x14E:0x150] = (sum(data) & 0xFFFF).to_bytes(2, "big")


# ------------------------------------------------------- Game Boy Color ROM

FAKE_FRAME_TBL = DATA_DIR / "fake-frame.tbl"
GBC_BANK = 0x4000
# the frame of a message in the synthetic profile (tests/data/profiles/synth-gbc.yaml)
F_START, F_LINE, F_PAGE, F_END, F_END_WAIT, F_RESUME = 0x02, 0x0A, 0x0D, 0x03, 0x04, 0x1F
F_NUMBER, F_SOUND = 0x10, 0x11  # commands between texts: two parameter bytes, and none
F_NOT_TEXT = 0x7E  # neither a table code nor part of the frame
GBC_RECORDS, GBC_RECORD_SIZE, GBC_STRINGS = 0xC100, 5, 0xC200
GBC_WORDS = {0x40: (0xC300, "おちゃ"), 0x41: (0xC310, "は　")}  # byte: where its word is


def build_gbc_rom() -> tuple[bytes, Manifest]:
    """Four 16 KiB banks with a Game Boy Color header. Banks 1 and 2 hold framed messages:
    with and without a pointer to them in their bank, several lines, two texts around a
    command, a word byte next to the same word spelled out, a name byte, and katakana words
    written with hiragana codes. Around them, bytes that read as text but are no message: no
    start command, a byte that is not text, an unknown command, no end byte, too little text,
    text that runs into the next bank. Bank 3 has a message outside the regions, two name
    tables (fixed records, and strings that follow one another) and the two fixed words that
    bytes 0x40 and 0x41 stand for, which the codec reads from the ROM."""
    tbl = load_tbl(FAKE_FRAME_TBL)
    for byte, (_, word) in GBC_WORDS.items():  # as the codec names them once it has the ROM
        tbl["keys"][f"<{word}>"] = bytes([byte])
    r = SynthRom("SYNTH GBC", "SGCJ", fill=0xFF, platform="gbc")
    manifest = r.manifest

    def t(text: str) -> bytes:
        return tbl_encode(text, tbl)

    def message(
        at: int, *parts: int | str | tuple[str, str], why: str = "", referenced: bool = False
    ) -> None:
        """An int is one byte; a str is a line; a (raw, text) pair is a line whose readable
        text differs. With ``why`` the bytes must not be read as text."""
        blob = bytearray()
        for part in parts:
            if isinstance(part, int):
                blob.append(part)
                continue
            raw, text = part if isinstance(part, tuple) else (part, part)
            data = t(raw)
            start = at + len(blob)
            if not why:
                manifest.strings.append(
                    Expected(start, start + len(data), raw, text, "dialogue", referenced, 0)
                )
            blob += data
        r.put(at, bytes(blob))
        if why:
            manifest.rejected[at] = why

    def pointer(at: int, target: int) -> None:
        """The address of ``target`` in its bank, where the bank is switched in at 0x4000."""
        r.put(at, (GBC_BANK + target % GBC_BANK).to_bytes(2, "little"))

    # bank 1
    pointer(0x4010, 0x4120)
    message(0x4120, F_START, "おはよう！", F_END, referenced=True)  # short, but pointed at
    message(
        0x4220,
        F_START,
        "きょうは　いい　てんきですね。",
        F_LINE,
        "ねこが　にわで　ねている。",
        F_PAGE,
        ("クりームを　なめた。", "クリームを　なめた。"),
        F_END,
    )
    message(0x4320, F_START, "ねこ。", F_END, why="too little text and no pointer")
    message(  # a parameter with the value of the start command or a character is not read
        0x4420,
        F_START,
        ("<name48><は　><おちゃ>を　のんだ。", "〇〇は　おちゃを　のんだ。"),
        F_RESUME,
        F_NUMBER,
        F_START,
        0x80,
        F_START,
        "おちゃは　おいしい？",
        F_END_WAIT,
    )
    message(  # ends between two texts
        0x4520, F_START, "あしたは　あめが　ふるそうです。", F_RESUME, F_SOUND, F_RESUME
    )
    message(0x4620, "ねこが　おちゃを　のむ。", F_END, why="no start command")
    message(
        0x4720,
        F_START,
        "きょうは　さむい",
        F_NOT_TEXT,
        "ですね。",
        F_END,
        why="a byte that is not text",
    )
    message(
        0x4820,
        F_START,
        "きょうは　さむいですね。",
        F_RESUME,
        0x77,
        F_START,
        "ねこ！",
        F_END,
        why="an unknown command between two texts",
    )
    message(
        0x4920,
        F_START,
        "<おちゃ><おちゃ><おちゃ>",
        F_END,
        why="its kana are all inside marked entries",
    )
    message(0x4A20, F_START, "そらが　あおい　いいてんきだ。", why="no end byte")
    message(0x7FF0, F_START, "ねこがにわでねているよきょうも", why="runs into the next bank")

    # bank 2
    r.put(0x8000, t("いいてんきだ。") + bytes([F_END]))
    pointer(0x8010, 0x8320)
    message(  # the same address as the first message, whose pointer is in bank 1
        0x8120, F_START, "おはよう！", F_END, why="the pointer to its address is in another bank"
    )
    message(
        0x8220,
        F_START,
        "ゆきが　ふっている。",
        F_LINE,
        "へやへ　もどろう。",
        F_PAGE,
        ("へンな　ねこが　いる。", "ヘンな　ねこが　いる。"),
        F_END,
    )
    message(0x8320, F_START, "またね！", F_END, referenced=True)

    # bank 3: not a text region
    message(0xC020, F_START, "ねこが　おちゃを　のんでいる。", F_END, why="outside the regions")
    end = bytes([F_RESUME])  # the profile's terminator
    for at, word in GBC_WORDS.values():  # the fixed words two bytes stand for
        r.put(at, t(word) + end)
    records = ["ねこ", "ゆきだるま", "クりーム", "つき"]  # the second fills its record
    r.put(GBC_RECORDS, b"".join(t(name).ljust(GBC_RECORD_SIZE, end) for name in records))
    strings = [t("そら"), t("<おちゃ>のは"), b"", bytes([0x80, F_NOT_TEXT]), t("あめ")]
    r.put(GBC_STRINGS, b"".join(name + end for name in strings))
    manifest.names += [
        ("animal", 0, "ねこ"),
        ("animal", 1, "ゆきだるま"),
        ("animal", 2, "クリーム"),
        ("animal", 3, "つき"),
        ("thing", 0, "そら"),
        ("thing", 1, "おちゃのは"),
        # entry 2 is empty and entry 3 holds a byte that is not text: no names
        ("thing", 4, "あめ"),
    ]
    return r.finish()
