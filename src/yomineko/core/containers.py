"""Compressed blocks that hold the script, and the addresses of text inside them.

A *block* is an LZ77 stream a pointer table points at, or a byte range of the ROM with the
same layout stored without compression. Once decompressed it starts with a
little-endian u32 entry count and that many u32 offsets; each offset is the start of one
*entry* (a scene or text bank), which ends where the next begins, the last at the end of the
block.

Text inside a block has no ROM offset, so it gets a *virtual address*: ``VIRTUAL_BASE``, the
block index in bits 20 and up, and the offset inside the decompressed block in the low 20
bits. The top byte 0xC0-0xCF can never be a real GBA bus address (ROM is 0x08-0x0D), so a
virtual address never collides with one, and everything that sorts or ranges over addresses
keeps working.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from yomineko.core.compression.lz77 import decompress
from yomineko.errors import YominekoError

VIRTUAL_BASE = 0xC0000000
BLOCK_SHIFT = 20
BLOCK_LIMIT = 1 << BLOCK_SHIFT  # most bytes a block may hold
MAX_BLOCKS = 256


class ContainerError(YominekoError, ValueError):
    """A pointer table or offset table does not describe a valid set of blocks."""


@dataclass(frozen=True)
class Block:
    index: int
    rom_offset: int  # where the block (the compressed stream, if it is one) starts in the ROM
    data: bytes  # decompressed
    entries: list[tuple[int, int]]  # (start, end) of each entry inside ``data``


def virtual_address(block: int, offset: int) -> int:
    if not 0 <= block < MAX_BLOCKS:
        raise ContainerError(f"block {block} is outside 0-{MAX_BLOCKS - 1}")
    if not 0 <= offset < BLOCK_LIMIT:
        raise ContainerError(f"offset 0x{offset:X} does not fit in a block")
    return VIRTUAL_BASE + (block << BLOCK_SHIFT) + offset


def is_virtual(address: int) -> bool:
    return VIRTUAL_BASE <= address < VIRTUAL_BASE + (MAX_BLOCKS << BLOCK_SHIFT)


def split_virtual(address: int) -> tuple[int, int]:
    """``(block, offset)`` of a virtual address."""
    if not is_virtual(address):
        raise ContainerError(f"0x{address:08X} is not a virtual address")
    rel = address - VIRTUAL_BASE
    return rel >> BLOCK_SHIFT, rel & (BLOCK_LIMIT - 1)


def read_offset_table(block: bytes) -> list[tuple[int, int]]:
    """The ``(start, end)`` of every entry of a decompressed block.

    The block opens with a u32 count ``n`` and ``n`` u32 words; the first entry starts at
    ``4 + 4 * n``. The words are entry offsets for as long as they strictly increase and stay
    inside the block. In the one game seen so far the last few words of the table are not
    offsets (they are far larger than the block), so the run stops at the first one that is
    not; those words are ignored.
    """
    if len(block) < 8:
        raise ContainerError("block is too short for an offset table")
    n = struct.unpack_from("<I", block, 0)[0]
    first = 4 + 4 * n
    if n == 0 or first > len(block):
        raise ContainerError(f"offset table claims {n} entries in a block of {len(block)} bytes")
    words = struct.unpack_from(f"<{n}I", block, 4)
    if words[0] != first:
        raise ContainerError(
            f"first entry starts at {words[0]}, not right after the table ({first})"
        )
    starts = [words[0]]
    for w in words[1:]:
        if w <= starts[-1] or w > len(block):
            break
        starts.append(w)
    ends = [*starts[1:], len(block)]
    return list(zip(starts, ends, strict=True))


def read_blocks(
    rom: bytes, table_base: int, count: int, stride: int, pointer_base: int
) -> list[Block]:
    """Follow ``count`` pointers at ``table_base`` (``stride`` apart), decompress each target
    and read its offset table."""
    if count > MAX_BLOCKS:
        raise ContainerError(f"{count} blocks is more than the {MAX_BLOCKS} a game may have")
    blocks: list[Block] = []
    for i in range(count):
        at = table_base + i * stride
        if at + 4 > len(rom):
            raise ContainerError(f"pointer {i} at 0x{at:X} is outside the ROM")
        target = struct.unpack_from("<I", rom, at)[0] - pointer_base
        if not 0 <= target < len(rom):
            raise ContainerError(f"pointer {i} at 0x{at:X} does not point into the ROM")
        blocks.append(_block(i, target, decompress(rom, target)))
    return blocks


def read_plain_block(rom: bytes, start: int, end: int, index: int) -> Block:
    """The block stored without compression in ``rom[start:end]``, as block ``index``."""
    if index >= MAX_BLOCKS:
        raise ContainerError(f"block {index} is more than the {MAX_BLOCKS} a game may have")
    if not 0 <= start < end <= len(rom):
        raise ContainerError(f"block {index} at 0x{start:X}-0x{end:X} is outside the ROM")
    return _block(index, start, rom[start:end])


def _block(index: int, rom_offset: int, data: bytes) -> Block:
    if len(data) >= BLOCK_LIMIT:
        raise ContainerError(f"block {index} is too large ({len(data)} bytes)")
    try:
        entries = read_offset_table(data)
    except ContainerError as e:
        raise ContainerError(f"block {index} at 0x{rom_offset:X}: {e}") from e
    return Block(index, rom_offset, data, entries)
