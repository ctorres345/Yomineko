"""Rebuild a ROM from extracted text and compare it with the original.

``rebuild`` writes each line's ``raw`` text back over the original bytes at its address. It
supports same-length changes only: a line whose re-encoded size differs would shift
everything after it and break every pointer, so that is reported, not attempted.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from yomineko.core.containers import Block, is_virtual, split_virtual
from yomineko.core.encodings.base import Codec
from yomineko.errors import YominekoError
from yomineko.model import Line


class LengthChanged(YominekoError, ValueError):
    def __init__(self, address: int, old: int, new: int):
        super().__init__(f"line at 0x{address:X} changed length ({old} -> {new} bytes)")
        self.address, self.old, self.new = address, old, new


@dataclass
class VerifyResult:
    ok: bool
    sha1: str  # of the rebuilt ROM
    expected_sha1: str  # of the original ROM
    mismatches: list[int] = field(default_factory=list)  # lines that re-encode differently
    length_changes: list[int] = field(default_factory=list)
    # lines inside compressed blocks that re-encode to the exact bytes of the decompressed block
    decompressed_checked: int = 0


def _old_length(rom: bytes, address: int, codec: Codec) -> int | None:
    parsed = codec.parse(rom, address)
    return None if parsed is None else parsed[0] - address


def rebuild(rom: bytes, lines: Iterable[Line], codec: Codec) -> bytes:
    out = bytearray(rom)
    for line in sorted(lines, key=lambda x: x.address):
        new = codec.encode(line.raw)
        old = _old_length(rom, line.address, codec)
        if old is None:
            raise ValueError(f"no text at 0x{line.address:X} in the original ROM")
        if len(new) != old:
            raise LengthChanged(line.address, old, len(new))
        out[line.address : line.address + len(new)] = new
    return bytes(out)


def verify(
    rom: bytes, lines: Iterable[Line], codec: Codec, blocks: Sequence[Block] = ()
) -> VerifyResult:
    """Rebuild from ``lines`` and report whether the result is byte-identical to ``rom``.

    Lines inside compressed blocks (virtual addresses) have no place in the ROM: they are
    checked against the *decompressed* block instead. Their text must re-encode to exactly
    the bytes it was read from. The compressed stream itself is not rebuilt.
    """
    expected = hashlib.sha1(rom).hexdigest()
    out = bytearray(rom)
    mismatches: list[int] = []
    length_changes: list[int] = []
    decompressed = 0
    by_index = {b.index: b for b in blocks}
    for line in sorted(lines, key=lambda x: x.address):
        if is_virtual(line.address):
            index, offset = split_virtual(line.address)
            block = by_index.get(index)
            try:
                new = codec.encode(line.raw)
            except ValueError:
                new = b""
            if block is None or not new or block.data[offset : offset + len(new)] != new:
                mismatches.append(line.address)
            else:
                decompressed += 1
            continue
        old = _old_length(rom, line.address, codec)
        try:
            new = codec.encode(line.raw)
        except ValueError:
            mismatches.append(line.address)
            continue
        if old is None or len(new) != old:
            length_changes.append(line.address)
            continue
        if new != rom[line.address : line.address + old]:
            mismatches.append(line.address)
        out[line.address : line.address + old] = new
    sha1 = hashlib.sha1(out).hexdigest()
    return VerifyResult(
        ok=sha1 == expected and not mismatches and not length_changes,
        sha1=sha1,
        expected_sha1=expected,
        mismatches=mismatches,
        length_changes=length_changes,
        decompressed_checked=decompressed,
    )
