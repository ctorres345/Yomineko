"""Find the text runs inside compressed blocks.

The blocks are read with ``core.containers`` (a pointer table, LZ77, an entry table; a block
may also be stored without compression). Inside
an entry the data is a stream of 16-bit tokens: glyph ids that make text, and command tokens
that may be followed by arguments. An argument can have the value of a glyph id, so the
profile's ``encoding.skip`` says how many tokens follow each command; those are never text.
A run of text is a line. Its address is a virtual address (``containers.virtual_address``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from yomineko.core.containers import Block, read_blocks, read_plain_block, virtual_address
from yomineko.core.discover.strings import FoundString
from yomineko.core.encodings.base import Codec
from yomineko.profile.schema import Profile


@dataclass
class CompressedResult:
    strings: list[FoundString]
    # starts of runs that parsed as text but did not re-encode identically
    unstable: list[int] = field(default_factory=list)


def read_profile_blocks(data: bytes, profile: Profile) -> list[Block]:
    """Every block of the profile: those of the pointer tables, numbered in table order, then
    the uncompressed ones."""
    blocks: list[Block] = []
    if profile.compressed is None:
        return blocks
    for table in profile.compressed.tables:
        for block in read_blocks(
            data, table.base, table.count, table.stride, profile.text.pointer_base
        ):
            blocks.append(replace(block, index=len(blocks)))
    for region in profile.compressed.uncompressed:
        blocks.append(read_plain_block(data, region.start, region.end, len(blocks)))
    return blocks


def find_compressed_strings(
    blocks: list[Block], codec: Codec, profile: Profile
) -> CompressedResult:
    """The text runs of every entry of ``blocks``, in block and offset order."""
    cfg = profile.compressed
    min_chars = cfg.min_chars if cfg else 1
    skip = profile.encoding.skip
    strings: list[FoundString] = []
    unstable: list[int] = []
    for block in blocks:
        for entry, (start, end) in enumerate(block.entries):
            data = block.data
            scene = f"{block.index:02d}/{entry:03d}"
            pos = start + (start & 1)  # tokens are 16-bit words
            while pos + 2 <= end:
                # a run never crosses into the next entry (whole 16-bit tokens only)
                run = codec.parse(data, pos, limit=(end - pos) & ~1)
                if run is None:
                    token = data[pos] | data[pos + 1] << 8
                    pos += 2 * (1 + skip.get(token, 0))
                    continue
                run_end, raw, jp = run
                if jp >= min_chars:
                    address = virtual_address(block.index, pos)
                    try:
                        same = codec.encode(raw) == data[pos:run_end]
                    except ValueError:
                        same = False
                    if same:
                        strings.append(
                            FoundString(
                                address,
                                virtual_address(block.index, run_end),
                                raw,
                                True,
                                scene,
                            )
                        )
                    else:
                        unstable.append(address)
                pos = run_end
    return CompressedResult(strings, unstable)
