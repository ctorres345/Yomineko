"""Detector 2: BIOS-compressed streams (LZ77, Huffman, run-length).

LZ77 streams are listed by decoding at every 4-aligned header. A Huffman or run-length header
byte on its own is noise, so those are only checked where a pointer in the ROM leads, and only
counted when they decode to exactly the size they declare.
"""

from __future__ import annotations

import struct
from collections.abc import Callable
from dataclasses import dataclass

from yomineko.core.compression.lz77 import CompressionError, decompress_measured
from yomineko.survey._words import ROM_BASE, u32s
from yomineko.survey.extent import entropy

LZ77_MIN_SIZE = 256
LZ77_MAX_SIZE = 0x100000
LZ77_MIN_PACKED = 16
OTHER_MIN_SIZE = 64
OTHER_MAX_SIZE = 0x80000
LARGE_STREAM = 8000
MAX_DECODED_ENTROPY = 7.0  # bits per byte: bytes decoded from random data average about 8
ENTROPY_SAMPLE = 16 * 1024


@dataclass(frozen=True)
class Stream:
    offset: int
    size: int  # decompressed
    packed: int


@dataclass(frozen=True)
class OtherStreams:
    """Pointer targets whose first word looks like a Huffman or run-length header."""

    kind: str  # "huffman" or "rle"
    headers: int  # targets with a plausible header
    decoded: int  # of those, targets that decode to the declared size
    examples: list[tuple[int, int]]  # (offset, decompressed size) of some that decoded


def find_lz77(data: bytes) -> list[Stream]:
    streams: list[Stream] = []
    words = u32s(data)
    i = 0
    limit = len(words)
    while i < limit:
        word = words[i]
        if word & 0xFF == 0x10 and LZ77_MIN_SIZE <= word >> 8 <= LZ77_MAX_SIZE:
            offset = i * 4
            try:
                decoded, packed = decompress_measured(data, offset)
            except CompressionError:
                packed = 0
            if packed >= LZ77_MIN_PACKED:
                streams.append(Stream(offset, len(decoded), packed))
                i += (packed + 3) // 4
                continue
        i += 1
    return streams


def pointer_targets(data: bytes) -> list[int]:
    """Sorted, distinct, 4-aligned ROM offsets that some aligned word points at."""
    end = ROM_BASE + len(data)
    return sorted({w - ROM_BASE for w in u32s(data) if ROM_BASE <= w < end and w % 4 == 0})


def decode_rle(data: bytes, offset: int) -> bytes | None:
    """BIOS run-length (0x30) decode, or None if the stream is not valid."""
    if offset + 4 > len(data) or data[offset] != 0x30:
        return None
    size = int.from_bytes(data[offset + 1 : offset + 4], "little")
    out = bytearray()
    pos = offset + 4
    while len(out) < size:
        if pos >= len(data):
            return None
        flag = data[pos]
        pos += 1
        if flag & 0x80:
            if pos >= len(data):
                return None
            out += bytes([data[pos]]) * ((flag & 0x7F) + 3)
            pos += 1
        else:
            count = flag + 1
            if pos + count > len(data):
                return None
            out += data[pos : pos + count]
            pos += count
    return bytes(out[:size])


def decode_huffman(data: bytes, offset: int) -> bytes | None:
    """BIOS Huffman (0x24: 4-bit, 0x28: 8-bit) decode, or None if the stream is not valid.

    After the 4-byte header comes a size byte (table bytes / 2 - 1) and the tree table, whose
    root is table byte 1. A node holds a child offset and two "leaf" flags; the bit stream is
    32-bit words read from the top bit down.
    """
    n = len(data)
    if offset + 8 > n:
        return None
    kind = data[offset]
    bits = kind & 0x0F
    if kind & 0xF0 != 0x20 or bits not in (4, 8):
        return None
    size = int.from_bytes(data[offset + 1 : offset + 4], "little")
    base = offset + 4
    table = (data[base] + 1) * 2
    pos = offset + 4 + ((table + 3) & ~3)
    if base + table > n:
        return None
    out = bytearray()
    half: int | None = None
    node = 1
    while len(out) < size:
        if pos + 4 > n:
            return None
        (word,) = struct.unpack_from("<I", data, pos)
        pos += 4
        for shift in range(31, -1, -1):
            bit = word >> shift & 1
            info = data[base + node]
            child = (node & ~1) + (info & 0x3F) * 2 + 2 + bit
            if child >= table:
                return None
            if not info >> (7 - bit) & 1:
                node = child
                continue
            value = data[base + child]
            node = 1
            if bits == 8:
                out.append(value)
            elif half is None:
                half = value
            elif half > 15 or value > 15:
                return None
            else:
                out.append(half | value << 4)
                half = None
            if len(out) >= size:
                break
    return bytes(out[:size])


def check_pointer_targets(data: bytes, targets: list[int]) -> list[OtherStreams]:
    """Huffman and run-length streams among the pointer targets (validated by decoding)."""
    kinds: list[tuple[str, Callable[[int], bool], Callable[[bytes, int], bytes | None]]] = [
        ("huffman", lambda b: b & 0xF0 == 0x20 and b & 0x0F in (4, 8), decode_huffman),
        ("rle", lambda b: b == 0x30, decode_rle),
    ]
    results = []
    for kind, header_ok, decode in kinds:
        headers = 0
        decoded = 0
        examples: list[tuple[int, int]] = []
        for t in targets:
            if t + 4 > len(data) or not header_ok(data[t]):
                continue
            size = int.from_bytes(data[t + 1 : t + 4], "little")
            if not OTHER_MIN_SIZE <= size <= OTHER_MAX_SIZE:
                continue
            headers += 1
            result = decode(data, t)
            if result is not None and entropy(result[:ENTROPY_SAMPLE]) < MAX_DECODED_ENTROPY:
                decoded += 1
                if len(examples) < 8:
                    examples.append((t, len(result)))
        results.append(OtherStreams(kind, headers, decoded, examples))
    return results
