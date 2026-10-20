"""Tests of the synthetic ROM builder itself (no yomineko code involved)."""

import itertools
import struct

import pytest
from support.synthrom import (
    POINTER_BASE,
    ROM_SIZE,
    SynthRom,
    build_gbc_rom,
    build_lz16_rom,
    build_sjis_rom,
    build_table8_rom,
    build_tbl_rom,
    load_tbl,
    tbl_encode,
)

BUILDERS = [build_sjis_rom, build_tbl_rom, build_lz16_rom, build_table8_rom]


@pytest.mark.parametrize("build", [*BUILDERS, build_gbc_rom])
def test_builds_are_deterministic(build):
    assert build()[0] == build()[0]


@pytest.mark.parametrize("fixture", ["sjis_rom", "tbl_rom", "lz16_rom", "table8_rom", "gbc_rom"])
def test_profile_sha1_matches_the_built_rom(fixture, request):
    synth = request.getfixturevalue(fixture)
    assert synth.profile_data["rom"]["sha1"] == synth.sha1, (
        f"update rom.sha1 in {synth.profile_path.name} to {synth.sha1}"
    )


@pytest.mark.parametrize("build", BUILDERS)
def test_header_is_valid(build):
    rom, _ = build()
    assert len(rom) == ROM_SIZE
    assert rom[0xB2] == 0x96
    assert rom[0xBD] == (-(sum(rom[0xA0:0xBD]) + 0x19)) & 0xFF
    assert not any(rom[4:0xA0]), "no logo data in the synthetic header"


def test_game_boy_color_header_is_valid():
    rom, _ = build_gbc_rom()
    assert len(rom) == ROM_SIZE
    assert rom[0x134:0x13D] == b"SYNTH GBC" and rom[0x13F:0x143] == b"SGCJ"
    assert rom[0x143] == 0xC0 and rom[0x104:0x134] == bytes(0x30)  # colour flag, no logo data
    x = 0
    for b in rom[0x134:0x14D]:
        x = (x - b - 1) & 0xFF
    assert rom[0x14D] == x
    assert int.from_bytes(rom[0x14E:0x150], "big") == (sum(rom) - rom[0x14E] - rom[0x14F]) & 0xFFFF


def test_every_manifest_string_is_in_the_rom_with_its_terminator(sjis_rom, tbl_rom):
    for synth, terminator in ((sjis_rom, 0x00), (tbl_rom, 0xFF)):
        for s in synth.manifest.strings:
            assert synth.rom[s.end] == terminator
            assert synth.rom[s.offset : s.end], "strings are not empty"
            assert terminator not in synth.rom[s.offset : s.end]


def test_referenced_flag_matches_the_pointers_in_the_rom(sjis_rom, tbl_rom):
    for synth in (sjis_rom, tbl_rom):
        pointed = set()
        for i in range(0, len(synth.rom) - 3, 4):
            v = struct.unpack_from("<I", synth.rom, i)[0]
            if POINTER_BASE <= v < POINTER_BASE + ROM_SIZE:
                pointed.add(v - POINTER_BASE)
        for s in synth.manifest.strings:
            assert (s.offset in pointed) == s.referenced, hex(s.offset)
        assert set(synth.manifest.rejected) <= pointed
        assert set(synth.manifest.shared_suffix) <= pointed


def test_noise_block_holds_no_pointer_like_words(sjis_rom, tbl_rom):
    for synth in (sjis_rom, tbl_rom):
        start, end = synth.manifest.noise
        assert end - start == 0x1000
        for i in range(start, end, 4):
            assert synth.rom[i + 3] != 0x08


def test_sjis_noise_contains_no_terminator_bytes(sjis_rom):
    start, end = sjis_rom.manifest.noise
    assert 0x00 not in sjis_rom.rom[start:end]


def test_banks_follow_the_gap_rule(sjis_rom, tbl_rom):
    for synth in (sjis_rom, tbl_rom):
        strings = synth.manifest.strings
        for prev, cur in itertools.pairwise(strings):
            same_bank = cur.offset - prev.end <= 0x40
            assert same_bank == (cur.bank == prev.bank), hex(cur.offset)


def test_struct_table_entries_point_at_term_strings(sjis_rom):
    for category, index, offset in sjis_rom.manifest.terms:
        entry = 0x3000 + index * 8
        ptr = struct.unpack_from("<I", sjis_rom.rom, entry)[0]
        assert category == "item"
        assert ptr == POINTER_BASE + offset


def test_overlapping_writes_are_refused():
    r = SynthRom("X", "XXXX")
    r.put(0x100, b"abc")
    with pytest.raises(ValueError, match="overlaps"):
        r.put(0x101, b"z")
    with pytest.raises(ValueError, match="outside"):
        r.put(ROM_SIZE - 1, b"zz")


def test_tbl_encoder_uses_longest_match_and_newline():
    tbl = load_tbl()
    assert tbl_encode("ねこ", tbl) == bytes([0xE0, 0x01])
    assert tbl_encode("ねが", tbl) == bytes([tbl["keys"]["ね"][0], tbl["keys"]["が"][0]])
    assert tbl_encode("あ\nあ", tbl)[1:2] == tbl["newline"]
    with pytest.raises(ValueError):
        tbl_encode("A", tbl)


def test_lz16_manifest_runs_are_in_the_decompressed_blocks(lz16_rom):
    from support.synthrom import load_tbl16

    tbl16 = {token: text for text, token in load_tbl16().items()}
    blocks = {b.index: b for b in lz16_rom.manifest.blocks}
    for run in lz16_rom.manifest.runs:
        data = blocks[run.block].data[run.offset : run.end]
        decoded = "".join(
            tbl16[int.from_bytes(data[i : i + 2], "little")] for i in range(0, len(data), 2)
        )
        assert decoded == run.raw
        start, end = blocks[run.block].entries[run.entry]
        assert start <= run.offset < run.end <= end


def test_lz16_blocks_are_lz77_streams_the_pointer_table_leads_to(lz16_rom):
    from yomineko.core.compression.lz77 import decompress

    for block in lz16_rom.manifest.blocks:
        assert decompress(lz16_rom.rom, block.rom_offset) == block.data
