"""Fast views of a ROM as 16- and 32-bit little-endian words."""

from __future__ import annotations

import sys
from array import array

ROM_BASE = 0x08000000  # where the cartridge appears on the GBA bus


def u16s(data: bytes, offset: int = 0, count: int | None = None) -> array[int]:
    """The 16-bit little-endian words starting at ``offset`` (a trailing odd byte is ignored)."""
    end = len(data) if count is None else min(len(data), offset + 2 * count)
    words: array[int] = array("H")
    words.frombytes(data[offset : offset + (end - offset) // 2 * 2])
    if sys.byteorder == "big":  # pragma: no cover - the CI machines are little-endian
        words.byteswap()
    return words


def u32s(data: bytes, offset: int = 0) -> array[int]:
    """The 32-bit little-endian words starting at ``offset`` (trailing bytes are ignored)."""
    words: array[int] = array("I")
    if words.itemsize != 4:  # pragma: no cover - not true on any supported platform
        raise RuntimeError("this Python has a 2- or 8-byte unsigned int")
    words.frombytes(data[offset : offset + (len(data) - offset) // 4 * 4])
    if sys.byteorder == "big":  # pragma: no cover
        words.byteswap()
    return words


def merge_ranges(starts: list[int], width: int) -> list[tuple[int, int]]:
    """Merge sorted window starts of equal ``width`` into ``(start, end)`` ranges."""
    ranges: list[tuple[int, int]] = []
    for s in starts:
        if ranges and s == ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], s + width)
        else:
            ranges.append((s, s + width))
    return ranges
