"""Write greyscale PNGs and tile sheets with the standard library only (Pillow stays optional)."""

from __future__ import annotations

import struct
import zlib

from yomineko.errors import YominekoError


def encode_png(width: int, height: int, pixels: bytes) -> bytes:
    """An 8-bit greyscale PNG; ``pixels`` is ``width * height`` bytes, row by row."""
    if len(pixels) != width * height:
        raise YominekoError("PNG pixel data does not match the image size")

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    rows = b"".join(b"\x00" + pixels[y * width : (y + 1) * width] for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def _tile_rows(tile: bytes, bpp: int) -> list[list[int]]:
    """The 8 rows of 8 pixel values (0 = background) in one 8x8 tile."""
    rows = []
    for y in range(8):
        if bpp == 1:
            rows.append([tile[y] >> x & 1 for x in range(8)])
        elif bpp == 4:
            row = []
            for b in tile[y * 4 : y * 4 + 4]:
                row += [b & 15, b >> 4]
            rows.append(row)
        else:
            rows.append(list(tile[y * 8 : y * 8 + 8]))
    return rows


def tile_sheet_png(data: bytes, bpp: int, tiles_wide: int = 32) -> bytes:
    """Draw ``data`` as 8x8 tiles (1, 4 or 8 bits per pixel), ink dark on a white page."""
    if bpp not in (1, 4, 8):
        raise YominekoError("a tile sheet needs 1, 4 or 8 bits per pixel")
    per_tile = 8 * bpp
    count = len(data) // per_tile
    if count == 0:
        raise YominekoError("not enough data for one tile")
    tiles_high = -(-count // tiles_wide)
    width, height = tiles_wide * 8, tiles_high * 8
    scale = {1: 255, 4: 17, 8: 1}[bpp]
    canvas = bytearray(b"\xff" * (width * height))
    for t in range(count):
        ox, oy = t % tiles_wide * 8, t // tiles_wide * 8
        for y, row in enumerate(_tile_rows(data[t * per_tile : (t + 1) * per_tile], bpp)):
            base = (oy + y) * width + ox
            for x, v in enumerate(row):
                canvas[base + x] = 255 - min(255, v * scale)
    return encode_png(width, height, bytes(canvas))
