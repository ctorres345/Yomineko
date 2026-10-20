"""Find the offsets the ROM points to: aligned little-endian 32-bit words in text regions."""

from __future__ import annotations

import struct
import sys
from array import array

from yomineko.core.rom import gb
from yomineko.profile.schema import Region


def scan_pointers(data: bytes, base: int, regions: list[Region], align: int = 4) -> set[int]:
    """File offsets inside ``regions`` that some aligned word in ``data`` points at.

    A word ``v`` points at offset ``v - base``. The whole ROM is scanned for pointers (code
    and tables live outside the text regions); only their targets are filtered by region.
    """
    lo = min(r.start for r in regions)
    hi = max(r.end for r in regions)
    low_v, high_v = base + lo, base + hi
    targets: set[int] = set()
    if align == 4 and len(data) >= 4:
        words = array("I")
        if words.itemsize == 4:
            words.frombytes(data[: len(data) // 4 * 4])
            if sys.byteorder == "big":
                words.byteswap()
            targets.update(v - base for v in words if low_v <= v < high_v)
        else:  # pragma: no cover - 'I' is 4 bytes on every supported platform
            targets.update(_scan_slow(data, low_v, high_v, base, 4))
    else:
        targets.update(_scan_slow(data, low_v, high_v, base, align))
    return {t for t in targets if any(r.start <= t < r.end for r in regions)}


def pointed_at_in_bank(data: bytes, offset: int) -> bool:
    """Game Boy: whether the address of ``offset`` is stored somewhere in its own bank, as a
    16-bit little-endian word. Code reaches the data of the bank it sits in that way, so a
    message with such a pointer is one the game shows. A word that matches by chance does
    happen (about one start in twenty)."""
    bank_start = offset - offset % gb.BANK_SIZE
    word = gb.bank_address(offset).to_bytes(2, "little")
    return data.find(word, bank_start, bank_start + gb.BANK_SIZE) != -1


def _scan_slow(data: bytes, low_v: int, high_v: int, base: int, align: int) -> set[int]:
    out = set()
    for i in range(0, len(data) - 3, align):
        v = struct.unpack_from("<I", data, i)[0]
        if low_v <= v < high_v:
            out.add(v - base)
    return out
