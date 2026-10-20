"""Synthetic ROM and save states for the survey tests.

One 128 KiB ROM holds a sample of every layout the survey looks for: plain kana, an offset table,
pointer tables to several kinds of target, BIOS streams, fill, a one-colour font, 16-bit token
streams (raw and compressed) and a word stored as a gojuon-ordered table. The manifest says where
each one is. All sentences are written for the tests; nothing comes from a game.
"""

from __future__ import annotations

import heapq
import struct
import zlib
from collections import Counter, deque
from dataclasses import dataclass, field

from support.synthrom import POINTER_BASE, SynthRom, lcg_bytes, lz77_compress, sjis

SURVEY_ROM_SIZE = 0x20000
RELATIVE_WORD = "ねこがすむ"  # indices in gojuon order: 23, 9, 5, 12, 32


# ---------------------------------------------------------------- encoders


def rle_compress(data: bytes) -> bytes:
    """A small GBA BIOS run-length (0x30) encoder."""
    out = bytearray([0x30]) + len(data).to_bytes(3, "little")
    literals = bytearray()

    def flush() -> None:
        while literals:
            chunk = literals[:128]
            out.append(len(chunk) - 1)
            out.extend(chunk)
            del literals[:128]

    i = 0
    while i < len(data):
        j = i
        while j < len(data) and data[j] == data[i] and j - i < 130:
            j += 1
        if j - i >= 3:
            flush()
            out += bytes([0x80 | (j - i - 3), data[i]])
            i = j
        else:
            literals.append(data[i])
            i += 1
    flush()
    return bytes(out)


def huffman_compress(data: bytes, bits: int = 8) -> bytes:
    """A small GBA BIOS Huffman (0x24 or 0x28) encoder; needs at least two distinct symbols."""
    symbols = list(data) if bits == 8 else [n for b in data for n in (b & 15, b >> 4)]
    heap: list[tuple[int, int, object]] = [
        (w, i, s) for i, (s, w) in enumerate(sorted(Counter(symbols).items()))
    ]
    heapq.heapify(heap)
    tie = len(heap)
    while len(heap) > 1:
        a, b = heapq.heappop(heap), heapq.heappop(heap)
        heapq.heappush(heap, (a[0] + b[0], tie, (a[2], b[2])))
        tie += 1
    root = heap[0][2]
    if not isinstance(root, tuple):
        raise ValueError("Huffman needs two distinct symbols")

    table: dict[int, int] = {}
    codes: dict[int, str] = {}
    next_pair = 2
    queue: deque[tuple[tuple, int, str]] = deque([(root, 1, "")])
    while queue:
        (left, right), index, path = queue.popleft()
        pair = next_pair
        next_pair += 2
        offset = (pair - ((index & ~1) + 2)) // 2
        assert 0 <= offset <= 63
        flags = (0x80 if not isinstance(left, tuple) else 0) | (
            0x40 if not isinstance(right, tuple) else 0
        )
        table[index] = flags | offset
        for slot, child, bit in ((pair, left, "0"), (pair + 1, right, "1")):
            if isinstance(child, tuple):
                queue.append((child, slot, path + bit))
            else:
                table[slot] = child
                codes[child] = path + bit
    table[0] = next_pair // 2 - 1
    tree = bytes(table.get(i, 0) for i in range(next_pair))
    stream = "".join(codes[s] for s in symbols)
    stream += "0" * (-len(stream) % 32)
    words = b"".join(
        int(stream[k : k + 32], 2).to_bytes(4, "little") for k in range(0, len(stream), 32)
    )
    pad = bytes(-len(tree) % 4)
    header = bytes([0x20 | bits]) + len(data).to_bytes(3, "little")
    return header + tree + pad + words


# ------------------------------------------------------------------- ROM


def token_block(seed: int, words: int = 4096) -> bytes:
    """16-bit tokens like a glyph-id script: a few dozen very common values, 256 in all."""
    pool = [*range(0x80, 0x100), *range(0x180, 0x200)]
    gen = lcg_bytes(seed)
    out = bytearray()
    for _ in range(words):
        a, b = next(gen), next(gen)
        pick = pool[a % 40] if b < 180 else pool[(a << 1 | b & 1) % len(pool)]
        out += pick.to_bytes(2, "little")
    return bytes(out)


def font_block(units: int, unit: int = 128) -> bytes:
    """A one-colour 4bpp font: glyph cells whose first and last 16 bytes are always blank."""
    gen = lcg_bytes(77)
    out = bytearray()
    for _ in range(units):
        cell = bytearray(unit)
        for k in range(16, unit - 16):
            cell[k] = (0x00, 0x03, 0x30, 0x33)[next(gen) & 3]
        out += cell
    return bytes(out)


@dataclass
class SurveyManifest:
    plain: list[int] = field(default_factory=list)  # hiragana runs
    ascii_before: int = 0  # the run that has ASCII right before it
    katakana: int = 0
    offset_u16: int = 0  # (130 entries, opens its own block)
    offset_u32: int = 0  # (130 entries, does not)
    pointer_table: int = 0  # 40 pointers to one of each kind of target, then more
    pointer_labels: dict[str, int] = field(default_factory=dict)  # label -> target offset
    ascending_table: int = 0
    lz77: dict[str, int] = field(default_factory=dict)  # name -> offset
    rle: int = 0
    huffman: int = 0
    fill: tuple[int, int] = (0, 0)
    font: tuple[int, int] = (0, 0)
    tokens_raw: int = 0
    tokens_lz77: int = 0
    word8: int = 0
    word16: int = 0


def build_survey_rom() -> tuple[bytes, SurveyManifest]:
    r = SynthRom("SYNTH SURVEY", "SRVY", size=SURVEY_ROM_SIZE)
    m = SurveyManifest()

    # plain text: three hiragana runs (one with ASCII before it) and a katakana run
    r.put(0x100, sjis("ねこがおちゃをのむ"))
    r.put(0x120, sjis("きょうはいいてんき"))
    r.put(0x140, b"#CG0" + sjis("あしたはあめがふる"))
    m.plain, m.ascii_before = [0x100, 0x120, 0x144], 0x144
    r.put(0x180, sjis("カメラタオル"))
    m.katakana = 0x180

    # offset tables: u16 that opens its own block, u32 that does not
    r.put(0xFFE, bytes([0xFF, 0xFF]))  # a larger word before the table: the run starts at 0x1000
    r.put(0x1000, b"".join((260 + 6 * i).to_bytes(2, "little") for i in range(130)))
    r.put(0x1800, b"".join((5000 + 8 * i).to_bytes(4, "little") for i in range(130)))
    m.offset_u16, m.offset_u32 = 0x1000, 0x1800

    # BIOS streams
    pattern = bytes(i * 7 % 251 for i in range(1024))
    r.put(0x3000, lz77_compress(pattern))
    r.put(0x4000, rle_compress(b"A" * 50 + bytes(range(30)) + b"B" * 80 + b"C" * 7 + b"xyz" * 4))
    r.put(0x5000, huffman_compress(b"abracadabra, abracadabra! " * 12))
    m.lz77["pattern"], m.rle, m.huffman = 0x3000, 0x4000, 0x5000

    # fill
    r.put(0x6000, b"\xff" * 0x2000)
    m.fill = (0x6000, 0x8000)

    # one target of each kind the pointer table label can name
    r.put(0x2400, struct.pack("<4I", *(POINTER_BASE + 0x3000 + 4 * i for i in range(4))))
    r.put(0x2600, b"".join(v.to_bytes(2, "little") for v in range(1, 17)))
    noise = bytes(0x20 + b % 0x60 for b, _ in zip(lcg_bytes(5), range(0x800), strict=False))
    r.put(0x9000, noise)
    targets = {
        "lz77": 0x3000,
        "huffman": 0x5000,
        "rle": 0x4000,
        "pointers": 0x2400,
        "sjis-kana": 0x100,
        "small-values": 0x2600,
        "fill": 0x1F000,
        "other": 0x9000,
    }
    m.pointer_labels = targets
    cycle = list(targets.values())
    r.add_pointer_table(0x2000, [cycle[i % 8] for i in range(40)])
    m.pointer_table = 0x2000
    r.add_pointer_table(0x2200, [0x9000 + 0x40 * i for i in range(32)])
    m.ascending_table = 0x2200

    # a one-colour font
    r.put(0xA000, font_block(96))
    m.font = (0xA000, 0xD000)

    # token streams: raw, and inside an LZ77 block
    r.put(0x10000, token_block(11))
    block = lz77_compress(token_block(12), literals_only=True)
    r.put(0x14000, block)
    m.tokens_raw, m.tokens_lz77 = 0x10000, 0x14000

    # a word stored as a table of ids in gojuon order: one byte per kana, then two
    r.put(0xE000, bytes(0x20 + i for i in (23, 9, 5, 12, 32)))
    r.put(0xE200, b"".join((0x100 + i).to_bytes(2, "little") for i in (23, 9, 5, 12, 32)))
    m.word8, m.word16 = 0xE000, 0xE200
    data, _ = r.finish()
    return data, m


# ------------------------------------------------------------- save states

IO_AT = 0x400  # where mGBA keeps the I/O block in its state
STATE_TAIL = 0x2000


def tile_bytes(n: int) -> bytes:
    """A 4bpp tile whose inked bytes (both nibbles the same, non-zero) depend on ``n``: tiles
    with different numbers have different ink shapes."""
    mask = n * 0x9E3779B1
    return bytes(((n + k) % 15 + 1) * 0x11 if mask >> k & 1 else 0 for k in range(32))


@dataclass
class StateParts:
    state: bytes
    rom: bytes
    first_tile: int
    width: int
    height: int
    mirror: int  # bus address of the EWRAM buffer


def build_state(*, mirrored: bool = True, io_at: int = IO_AT, text: bool = True) -> StateParts:
    """An mGBA state: BG0 with a 6x3 block of text tiles numbered from 100 (one row after
    another) at column 2, row 4; one of the tiles is in the ROM exactly, one only by shape."""
    vram = io_at + 0xC00
    ewram_at = vram + 0x18000 + 0x8000
    state = bytearray(ewram_at + 0x40000 + STATE_TAIL)
    struct.pack_into("<H", state, io_at, 0x0100)  # mode 0, BG0 on
    struct.pack_into("<H", state, io_at + 8, 10 << 8 | 2 << 2)  # screen base 10, char base 2
    first, width, height = 100, 6, 3
    tiles = [tile_bytes(n) for n in range(first, first + width * height)]
    for n, data in zip(range(first, first + width * height), tiles, strict=True):
        at = vram + 0x8000 + n * 32
        state[at : at + 32] = data
    screen = vram + 0xA * 0x800
    for row in range(height if text else 0):
        for col in range(width):
            n = first + row * width + col
            struct.pack_into("<H", state, screen + (4 + row) * 64 + (2 + col) * 2, n)
    if mirrored:
        at = ewram_at + 0x1000
        state[at : at + len(tiles) * 32] = b"".join(tiles)

    shape = bytes(0x22 if b else 0 for b in tiles[1])  # same ink, other colours
    rom = bytes(0x400) + tiles[0] + bytes(0x100) + shape + bytes(0x400)
    return StateParts(bytes(state), rom, first, width, height, 0x02001000)


def wrap_rastate(state: bytes) -> bytes:
    """A RASTATE container with a small block before the MEM block, as RetroArch writes."""

    def block(kind: bytes, body: bytes) -> bytes:
        return kind + struct.pack("<I", len(body)) + body + bytes(-len(body) % 8)

    return b"RASTATE\x01" + block(b"CHEV", b"\x01\x02\x03") + block(b"MEM ", state)


def wrap_rzip(data: bytes, chunk: int = 0x10000) -> bytes:
    out = bytearray(b"#RZIPv\x01#") + struct.pack("<IQ", chunk, len(data))
    for k in range(0, len(data), chunk):
        packed = zlib.compress(data[k : k + chunk])
        out += struct.pack("<I", len(packed)) + packed
    return bytes(out)


def wrap_png_state(state: bytes) -> bytes:
    """A PNG with a gbAs chunk holding the zlib-compressed state, like an mGBA .ssN file."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"gbAs", zlib.compress(state))
        + chunk(b"IEND", b"")
    )
