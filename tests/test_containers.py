import struct

import pytest
from support.synthrom import POINTER_BASE, SynthRom, lz77_compress

from yomineko.core.compression.lz77 import CompressionError
from yomineko.core.containers import (
    BLOCK_LIMIT,
    MAX_BLOCKS,
    VIRTUAL_BASE,
    ContainerError,
    is_virtual,
    read_blocks,
    read_offset_table,
    read_plain_block,
    split_virtual,
    virtual_address,
)

ENTRY_SETS = [
    [b"abcdefgh" * 3, b"\x01\x00" * 10, b"zz"],
    [b"x" * 40],
    [b"ab" * 100, b"cd" * 30, b"\x00\x00", b"q" * 5, b"hello hello hello"],
]


@pytest.fixture
def synth():
    r = SynthRom("SYNTH LZ", "LZ77")
    blocks = r.add_compressed_blocks(0x200, 0x1000, ENTRY_SETS)
    rom, manifest = r.finish()
    return rom, manifest, blocks


def test_blocks_read_back_equal_the_manifest(synth):
    rom, manifest, _ = synth
    got = read_blocks(rom, 0x200, len(ENTRY_SETS), 4, POINTER_BASE)
    assert [(b.index, b.rom_offset, b.data, b.entries) for b in got] == [
        (b.index, b.rom_offset, b.data, b.entries) for b in manifest.blocks
    ]


def test_entries_cover_the_block_after_the_table(synth):
    rom, _, _ = synth
    for block, entries in zip(read_blocks(rom, 0x200, 3, 4, POINTER_BASE), ENTRY_SETS, strict=True):
        assert block.entries[0][0] == 4 + 4 * len(entries)
        assert block.entries[-1][1] == len(block.data)
        assert [block.data[a:b] for a, b in block.entries] == entries


def test_a_stride_larger_than_four_reads_the_pointer_at_each_slot():
    r = SynthRom("SYNTH LZ", "LZ77")
    blocks = r.add_compressed_blocks(0x800, 0x1000, [[b"ab" * 4], [b"cd" * 4]])
    rom, _ = r.finish()
    wide = bytearray(rom)
    for i, b in enumerate(blocks):  # re-lay the table with 8-byte slots
        wide[0x200 + i * 8 : 0x200 + i * 8 + 4] = (POINTER_BASE + b.rom_offset).to_bytes(
            4, "little"
        )
    assert [b.data for b in read_blocks(bytes(wide), 0x200, 2, 8, POINTER_BASE)] == [
        b.data for b in blocks
    ]


def test_trailing_words_that_are_not_offsets_are_ignored():
    r = SynthRom("SYNTH LZ", "LZ77")
    r.add_compressed_blocks(0x200, 0x1000, ENTRY_SETS, extra_words=3)
    rom, manifest = r.finish()
    got = read_blocks(rom, 0x200, len(ENTRY_SETS), 4, POINTER_BASE)
    for block, entries in zip(got, ENTRY_SETS, strict=True):
        assert [block.data[a:b] for a, b in block.entries] == entries
    assert [b.entries for b in got] == [b.entries for b in manifest.blocks]


def test_a_single_entry_block_spans_everything_after_the_table():
    block = struct.pack("<2I", 1, 8) + b"abcd"
    assert read_offset_table(block) == [(8, 12)]


@pytest.mark.parametrize(
    ("block", "message"),
    [
        (b"\x04\x00", "too short"),
        (struct.pack("<2I", 0, 8) + b"\x00" * 8, "claims 0 entries"),
        (struct.pack("<2I", 40, 8) + b"\x00" * 8, "claims 40 entries"),  # table longer than block
        (struct.pack("<3I", 2, 99, 100) + b"\x00" * 8, "not right after the table"),
    ],
)
def test_malformed_offset_tables_are_rejected(block, message):
    with pytest.raises(ContainerError, match=message):
        read_offset_table(block)


@pytest.mark.parametrize(
    ("words", "kept"),
    [
        ((16, 24, 20), 2),  # decreasing: the run stops
        ((16, 16, 24), 1),  # equal: the run stops
        ((16, 24, 99), 2),  # past the end of the block
    ],
)
def test_the_offset_run_stops_at_the_first_word_that_is_not_an_increasing_offset(words, kept):
    block = struct.pack("<4I", 3, *words) + b"\x00" * 16
    assert len(read_offset_table(block)) == kept


def test_pointer_problems_name_the_block(synth):
    rom, _, _ = synth
    with pytest.raises(ContainerError, match="outside the ROM"):
        read_blocks(rom, len(rom) - 2, 1, 4, POINTER_BASE)
    with pytest.raises(ContainerError, match="does not point into the ROM"):
        read_blocks(rom, 0x2000, 1, 4, POINTER_BASE)  # zeros: below the pointer base
    with pytest.raises(ContainerError, match="more than"):
        read_blocks(rom, 0x200, MAX_BLOCKS + 1, 4, POINTER_BASE)


def test_a_target_that_is_not_lz77_is_a_compression_error(synth):
    rom, _, _ = synth
    broken = bytearray(rom)
    broken[0x200:0x204] = (POINTER_BASE + 0x3000).to_bytes(4, "little")  # fill bytes, not 0x10
    with pytest.raises(CompressionError):
        read_blocks(bytes(broken), 0x200, 1, 4, POINTER_BASE)


def test_a_bad_offset_table_inside_a_good_stream_names_the_block():
    r = SynthRom("SYNTH LZ", "LZ77")
    r.put(0x1000, lz77_compress(struct.pack("<3I", 2, 99, 100) + b"\x00" * 8))
    r.add_pointer_table(0x200, [0x1000])
    rom, _ = r.finish()
    with pytest.raises(ContainerError, match=r"block 0 at 0x1000: .*not right after"):
        read_blocks(rom, 0x200, 1, 4, POINTER_BASE)


def test_virtual_addresses_round_trip():
    for block, offset in [(0, 0), (0, 0x1ABB6), (16, 0x0), (255, BLOCK_LIMIT - 1)]:
        address = virtual_address(block, offset)
        assert is_virtual(address)
        assert split_virtual(address) == (block, offset)
    assert virtual_address(0, 0) == VIRTUAL_BASE
    assert virtual_address(1, 2) == 0xC0100002


def test_virtual_addresses_never_look_like_rom_addresses():
    assert virtual_address(0, 0) > 0x0DFFFFFF
    assert not is_virtual(POINTER_BASE + 0x1234)
    assert not is_virtual(VIRTUAL_BASE - 1)
    assert not is_virtual(VIRTUAL_BASE + (MAX_BLOCKS << 20))


@pytest.mark.parametrize("block, offset", [(-1, 0), (MAX_BLOCKS, 0), (0, -1), (0, BLOCK_LIMIT)])
def test_virtual_address_rejects_what_does_not_fit(block, offset):
    with pytest.raises(ContainerError):
        virtual_address(block, offset)


def test_split_rejects_a_real_address():
    with pytest.raises(ContainerError, match="not a virtual address"):
        split_virtual(POINTER_BASE + 0x100)


def test_a_block_stored_without_compression_is_read_in_place(synth):
    rom, manifest, _ = synth
    plain = manifest.blocks[2].data
    image = bytearray(rom)
    image[0x8000 : 0x8000 + len(plain)] = plain
    block = read_plain_block(bytes(image), 0x8000, 0x8000 + len(plain), 7)
    assert (block.index, block.rom_offset, block.data) == (7, 0x8000, plain)
    assert block.entries == manifest.blocks[2].entries


def test_a_plain_block_outside_the_rom_or_without_a_table_is_an_error(synth):
    rom, _, _ = synth
    with pytest.raises(ContainerError, match="outside the ROM"):
        read_plain_block(rom, len(rom) - 8, len(rom) + 8, 0)
    with pytest.raises(ContainerError, match="block 3 at 0x8000: offset table claims 0 entries"):
        read_plain_block(rom, 0x8000, 0x8100, 3)  # zeros: an entry count of 0
    with pytest.raises(ContainerError, match="more than the 256"):
        read_plain_block(rom, 0x8000, 0x8100, MAX_BLOCKS)
