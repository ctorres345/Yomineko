"""GBA BIOS LZ77 (type 0x10) decompression.

Stream layout: a header byte 0x10, a 24-bit little-endian decompressed size, then groups of
one flag byte and eight items. Flags are read MSB first: 0 is a literal byte, 1 is a
two-byte reference, ``(length - 3) << 4 | (displacement - 1) >> 8`` then the low byte of
``displacement - 1``. A reference copies ``length`` bytes from ``displacement`` bytes back in
the output, byte by byte, so it may overlap what it is writing.
"""

from __future__ import annotations

from yomineko.errors import YominekoError

HEADER_BYTE = 0x10
MAX_SIZE = 4 * 1024 * 1024  # a sanity cap; the format allows 2**24 - 1, a GBA game needs far less


class CompressionError(YominekoError, ValueError):
    """The bytes are not a valid compressed stream."""


def _decode(data: bytes, offset: int) -> tuple[bytes, int]:
    n = len(data)
    if offset < 0 or offset + 4 > n:
        raise CompressionError(f"no LZ77 header at 0x{offset:X}")
    if data[offset] != HEADER_BYTE:
        raise CompressionError(f"0x{offset:X} is not an LZ77 stream (header 0x{data[offset]:02X})")
    size = int.from_bytes(data[offset + 1 : offset + 4], "little")
    if size > MAX_SIZE:
        raise CompressionError(f"LZ77 stream at 0x{offset:X} declares {size} bytes, too large")

    out = bytearray()
    pos = offset + 4
    while len(out) < size:
        if pos >= n:
            raise CompressionError(f"LZ77 stream at 0x{offset:X} ends early")
        flags = data[pos]
        pos += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if not flags >> bit & 1:
                if pos >= n:
                    raise CompressionError(f"LZ77 stream at 0x{offset:X} ends early")
                out.append(data[pos])
                pos += 1
                continue
            if pos + 2 > n:
                raise CompressionError(f"LZ77 stream at 0x{offset:X} ends early")
            hi, lo = data[pos], data[pos + 1]
            pos += 2
            length = (hi >> 4) + 3
            distance = ((hi & 0x0F) << 8 | lo) + 1
            if distance > len(out):
                raise CompressionError(
                    f"LZ77 stream at 0x{offset:X} refers {distance} bytes back "
                    f"with only {len(out)} written"
                )
            start = len(out) - distance
            if distance >= length:  # the copy does not overlap what it writes: one slice
                out += out[start : start + length]
            else:  # it repeats bytes it is writing (a run), so byte by byte
                for i in range(start, start + length):
                    out.append(out[i])
    if len(out) != size:  # the last reference ran past the declared size
        del out[size:]
    return bytes(out), pos - offset


def decompress(data: bytes, offset: int = 0) -> bytes:
    """The decompressed bytes of the stream starting at ``offset``."""
    return _decode(data, offset)[0]


def decompress_measured(data: bytes, offset: int = 0) -> tuple[bytes, int]:
    """The decompressed bytes and how many bytes the stream occupies, from one decode."""
    return _decode(data, offset)


def compressed_size(data: bytes, offset: int = 0) -> int:
    """How many bytes the stream at ``offset`` occupies (without any padding after it)."""
    return _decode(data, offset)[1]
