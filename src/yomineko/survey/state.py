"""Detector 8: what a save state says about how a game draws its text.

Given an emulator state taken while a message is on screen, this reads the video registers, finds
the rectangle of text tiles in a background's tile map (tile numbers counting up, one row after
another), and asks whether those tiles come out of the ROM (exactly, or by shape: which pixels are
inked) and whether they are mirrored in RAM. "Not in the ROM, but in RAM" means the text is
rendered at run time from a font that is not stored as plain tiles.

Understood containers: RetroArch ``#RZIP`` (zlib chunks) around a ``RASTATE`` file with a ``MEM ``
block, an mGBA state inside a PNG (the ``gbAs`` chunk), and a bare mGBA state.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from yomineko.errors import YominekoError

IO_SIZE = 0x400
PRAM_SIZE = 0x400
OAM_SIZE = 0x400
VRAM_SIZE = 0x18000
IWRAM_SIZE = 0x8000
EWRAM_SIZE = 0x40000
EWRAM_BASE = 0x02000000
KNOWN_IO_OFFSET = 0x400  # where mGBA puts the I/O block in its state
IO_SEARCH = (0x100, 0x2000)
MIN_RUN = 4  # consecutive tile numbers that count as a run of text tiles
MAX_TILES = 512  # tiles looked up per rectangle

_SHAPE = bytes((1 if b & 15 else 0) | (2 if b >> 4 else 0) for b in range(256))


class StateError(YominekoError):
    """The file is not a save state this survey can read."""


@dataclass(frozen=True)
class Layer:
    index: int
    priority: int
    char_base: int  # byte offset in VRAM
    screen_base: int  # byte offset in VRAM
    colors8: bool  # 256 colours (8 bits per pixel) instead of 16
    size: int  # BGxCNT size code, 0 is 32x32 tiles


@dataclass(frozen=True)
class TextRect:
    layer: int
    column: int
    row: int
    width: int
    height: int
    first_tile: int
    tiles: int  # distinct inked tiles looked up
    in_rom_exact: int
    in_rom_shape: int  # ink pattern found in the ROM, ignoring which colour
    in_ewram: int  # exact tiles found anywhere in EWRAM
    ewram_mirror: int | None  # bus address of the buffer that holds all of them in order
    in_iwram: int


@dataclass(frozen=True)
class StateReport:
    io_offset: int
    dispcnt: int
    mode: int
    layers: list[Layer]  # the enabled background layers
    text: TextRect | None


def unwrap_state(raw: bytes) -> bytes:
    """The bare mGBA state inside a RetroArch, PNG or plain state file."""
    data = raw
    if data[:8] == b"#RZIPv\x01#":
        data = _unrzip(data)
    if data[:7] == b"RASTATE":
        data = _rastate_mem(data)
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        data = _png_state(data)
    return data


def _unrzip(data: bytes) -> bytes:
    try:
        _, total = struct.unpack_from("<IQ", data, 8)
        pos = 20
        out = bytearray()
        while pos < len(data) and len(out) < total:
            (size,) = struct.unpack_from("<I", data, pos)
            pos += 4
            out += zlib.decompress(data[pos : pos + size])
            pos += size
    except (struct.error, zlib.error) as e:
        raise StateError(f"damaged RetroArch state: {e}") from e
    if len(out) != total:
        raise StateError("damaged RetroArch state: it ends early")
    return bytes(out)


def _rastate_mem(data: bytes) -> bytes:
    pos = 8
    while pos + 8 <= len(data):
        kind = data[pos : pos + 4]
        (size,) = struct.unpack_from("<I", data, pos + 4)
        if kind == b"MEM ":
            return data[pos + 8 : pos + 8 + size]
        pos += 8 + ((size + 7) & ~7)
    raise StateError("the RetroArch state has no MEM block")


def _png_state(data: bytes) -> bytes:
    pos = 8
    while pos + 8 <= len(data):
        (size,) = struct.unpack_from(">I", data, pos)
        kind = data[pos + 4 : pos + 8]
        if kind == b"gbAs":
            try:
                return zlib.decompress(data[pos + 8 : pos + 8 + size])
            except zlib.error as e:
                raise StateError(f"damaged mGBA state: {e}") from e
        pos += 12 + size
    raise StateError("the PNG holds no mGBA state")


def _plausible_io(state: bytes, offset: int) -> bool:
    if offset + IO_SIZE + PRAM_SIZE + OAM_SIZE + VRAM_SIZE > len(state):
        return False
    (dispcnt,) = struct.unpack_from("<H", state, offset)
    controls = struct.unpack_from("<4H", state, offset + 8)
    return dispcnt & 7 <= 5 and dispcnt >> 8 & 0xF != 0 and any(controls)


def find_io_block(state: bytes) -> int:
    """Where the I/O registers start: the known place, else the first plausible DISPCNT."""
    if _plausible_io(state, KNOWN_IO_OFFSET):
        return KNOWN_IO_OFFSET
    for offset in range(IO_SEARCH[0], IO_SEARCH[1], 4):
        if _plausible_io(state, offset):
            return offset
    raise StateError("no I/O register block found in the state")


def _layers(io: bytes) -> tuple[int, int, list[Layer]]:
    dispcnt = struct.unpack_from("<H", io, 0)[0]
    layers = []
    for i in range(4):
        if not dispcnt >> (8 + i) & 1:
            continue
        control = struct.unpack_from("<H", io, 8 + 2 * i)[0]
        layers.append(
            Layer(
                i,
                control & 3,
                (control >> 2 & 3) * 0x4000,
                (control >> 8 & 0x1F) * 0x800,
                bool(control & 0x80),
                control >> 14,
            )
        )
    return dispcnt, dispcnt & 7, layers


def _tile_runs(entries: tuple[int, ...]) -> list[tuple[int, int, int]]:
    """(column, length, first tile) of runs of at least MIN_RUN consecutive tile numbers."""
    runs = []
    c = 0
    while c < len(entries):
        d = c
        while d + 1 < len(entries) and (entries[d + 1] & 0x3FF) == (entries[d] & 0x3FF) + 1:
            d += 1
        if d - c + 1 >= MIN_RUN:
            runs.append((c, d - c + 1, entries[c] & 0x3FF))
        c = d + 1
    return runs


def find_text_rect(vram: bytes, layer: Layer) -> tuple[int, int, int, int, int] | None:
    """The biggest block of rows of consecutive tile numbers in the layer's first 32x32 map:
    (column, row, width, height, first tile). Each row continues numbering where the row above
    ended, as a renderer that fills a tile buffer in order would."""
    rows = []
    for r in range(32):
        at = layer.screen_base + r * 64
        if at + 64 > len(vram):
            break
        rows.append(_tile_runs(struct.unpack_from("<32H", vram, at)))
    best: tuple[int, int, int, int, int] | None = None
    for r, runs in enumerate(rows):
        for col, length, first in runs:
            height, nxt = 1, first + length
            while r + height < len(rows) and (col, length, nxt) in rows[r + height]:
                height += 1
                nxt += length
            area = length * height
            if best is None or area > best[2] * best[3]:
                best = (col, r, length, height, first)
    return best


def analyze_state(raw: bytes, rom: bytes) -> StateReport:
    """Read a state file and report how the text on screen is drawn."""
    state = unwrap_state(raw)
    io_at = find_io_block(state)
    io = state[io_at : io_at + IO_SIZE]
    vram_at = io_at + IO_SIZE + PRAM_SIZE + OAM_SIZE
    vram = state[vram_at : vram_at + VRAM_SIZE]
    iwram_at = vram_at + VRAM_SIZE
    iwram = state[iwram_at : iwram_at + IWRAM_SIZE]
    ewram = state[iwram_at + IWRAM_SIZE : iwram_at + IWRAM_SIZE + EWRAM_SIZE]
    dispcnt, mode, layers = _layers(io)

    best: tuple[Layer, tuple[int, int, int, int, int]] | None = None
    for layer in layers:
        rect = find_text_rect(vram, layer)
        if rect and (best is None or rect[2] * rect[3] > best[1][2] * best[1][3]):
            best = (layer, rect)
    text = None
    if best:
        text = _match_tiles(best[0], best[1], vram, rom, iwram, ewram)
    return StateReport(io_at, dispcnt, mode, layers, text)


def _match_tiles(
    layer: Layer,
    rect: tuple[int, int, int, int, int],
    vram: bytes,
    rom: bytes,
    iwram: bytes,
    ewram: bytes,
) -> TextRect:
    col, row, width, height, first = rect
    tile_bytes = 64 if layer.colors8 else 32
    ordered = [
        vram[layer.char_base + t * tile_bytes : layer.char_base + (t + 1) * tile_bytes]
        for t in range(first, first + width * height)
    ]
    # a tile cut short by the end of VRAM would match almost anywhere: leave it out
    distinct = list(dict.fromkeys(t for t in ordered if len(t) == tile_bytes and any(t)))[
        :MAX_TILES
    ]
    shape_rom = rom.translate(_SHAPE)
    exact = sum(rom.find(t) != -1 for t in distinct)
    shape = sum(shape_rom.find(t.translate(_SHAPE)) != -1 for t in distinct)
    in_ewram = sum(ewram.find(t) != -1 for t in distinct)
    in_iwram = sum(iwram.find(t) != -1 for t in distinct)

    mirror = None
    joined = b"".join(ordered)
    lead = next((t for t in ordered if any(t)), b"")
    if lead:
        skip = ordered.index(lead) * tile_bytes
        at = ewram.find(lead)
        while at != -1 and mirror is None:
            start = at - skip
            if start >= 0 and ewram[start : start + len(joined)] == joined:
                mirror = EWRAM_BASE + start
            at = ewram.find(lead, at + 1)
    return TextRect(
        layer.index,
        col,
        row,
        width,
        height,
        first,
        len(distinct),
        exact,
        shape,
        in_ewram,
        mirror,
        in_iwram,
    )
