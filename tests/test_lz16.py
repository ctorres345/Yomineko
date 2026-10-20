"""Text inside compressed blocks: found, addressed, extracted and checked at the decompressed
level, on the synthetic ROM from ``build_lz16_rom``."""

import copy

import pytest
from support.synthrom import POINTER_BASE, load_tbl16, tokens

from yomineko.core.containers import VIRTUAL_BASE, Block, split_virtual, virtual_address
from yomineko.core.discover.compressed import find_compressed_strings, read_profile_blocks
from yomineko.core.rom.base import rom_from_bytes
from yomineko.core.roundtrip import verify
from yomineko.extract import extract
from yomineko.profile.loader import LoadedProfile, load_profile
from yomineko.profile.schema import Profile


@pytest.fixture
def loaded(lz16_rom):
    return load_profile(lz16_rom.profile_path)


@pytest.fixture
def result(lz16_rom, loaded):
    return extract(rom_from_bytes(lz16_rom.rom), loaded)


def test_every_expected_run_is_found_and_nothing_else(lz16_rom, result):
    found = [(x.address, x.raw) for x in result.script.lines]
    expected = [(virtual_address(r.block, r.offset), r.raw) for r in lz16_rom.manifest.runs]
    assert found == expected


def test_lines_carry_virtual_ids_banks_and_scenes(lz16_rom, result):
    for line, run in zip(result.script.lines, lz16_rom.manifest.runs, strict=True):
        address = virtual_address(run.block, run.offset)
        assert line.id == f"{address:08X}"
        assert address >= VIRTUAL_BASE and line.id.startswith("C")
        assert line.bank == f"block_{run.block:02d}"
        assert line.scene == f"{run.block:02d}/{run.entry:03d}"
        assert line.referenced
        assert line.text == run.raw


def test_the_run_list_counts_match_the_blocks(lz16_rom, result):
    assert len(result.strings) == len(lz16_rom.manifest.runs) == 9
    assert len(result.banks) == len(result.blocks) == 2
    assert result.unstable == []
    assert [len(b) for b in result.banks] == [5, 4]


def test_arguments_that_look_like_glyphs_are_not_text(lz16_rom, result):
    # the speaker command is followed by the token of a hiragana: the line must not start with it
    first = result.script.lines[0]
    assert first.raw.startswith("ねこ")
    assert not any(x.raw.startswith(("い", "う")) for x in result.script.lines)


def test_runs_too_short_to_keep_are_dropped(lz16_rom, result):
    kept = {split_virtual(x.address) for x in result.script.lines}
    for block, offset in lz16_rom.manifest.dropped_runs:
        assert (block, offset) not in kept
    assert len(lz16_rom.manifest.dropped_runs) == 3


def test_a_run_at_the_end_of_an_entry_does_not_continue_into_the_next(lz16_rom, result):
    by_scene = {}
    for x in result.script.lines:
        by_scene.setdefault(x.scene, []).append(x.raw)
    assert by_scene["01/000"] == ["きょうはいいてんき", "そらがあおい。"]
    assert by_scene["01/001"] == ["あめがふってきた！"]


def test_without_the_skip_rules_arguments_pollute_the_text(lz16_rom, loaded):
    data = copy.deepcopy(loaded.profile.model_dump())
    data["encoding"]["skip"] = {}
    bare = LoadedProfile(Profile.model_validate(data), loaded.path)
    lines = extract(rom_from_bytes(lz16_rom.rom), bare).script.lines
    assert any(x.raw.startswith(("い", "う")) for x in lines)


def test_min_chars_one_keeps_the_short_runs(lz16_rom, loaded):
    data = copy.deepcopy(loaded.profile.model_dump())
    data["compressed"]["min_chars"] = 1
    profile = Profile.model_validate(data)
    blocks = read_profile_blocks(lz16_rom.rom, profile)
    found = find_compressed_strings(blocks, loaded.codec(), profile)
    raws = [s.raw for s in found.strings]
    assert "あ" in raws and "ー" in raws
    assert "12" not in raws  # digits are not Japanese, whatever the length


def test_blocks_are_numbered_across_tables(lz16_rom, loaded):
    data = copy.deepcopy(loaded.profile.model_dump())
    table = data["compressed"]["tables"][0]
    data["compressed"]["tables"] = [table, table]
    blocks = read_profile_blocks(lz16_rom.rom, Profile.model_validate(data))
    assert [b.index for b in blocks] == [0, 1, 2, 3]


def test_an_uncompressed_block_is_numbered_after_the_table_blocks(lz16_rom, loaded):
    # the first block again, stored without compression in a free part of the ROM
    plain = lz16_rom.manifest.blocks[0].data
    image = bytearray(lz16_rom.rom)
    image[0x8000 : 0x8000 + len(plain)] = plain
    data = copy.deepcopy(loaded.profile.model_dump())
    data["compressed"]["uncompressed"] = [{"start": 0x8000, "end": 0x8000 + len(plain)}]
    both = LoadedProfile(Profile.model_validate(data), loaded.path)
    result = extract(rom_from_bytes(bytes(image)), both, check_checksum=False)
    assert [(b.index, b.rom_offset) for b in result.blocks][2] == (2, 0x8000)
    found = [(x.address, x.raw) for x in result.script.lines]
    runs = lz16_rom.manifest.runs
    assert found[: len(runs)] == [(virtual_address(r.block, r.offset), r.raw) for r in runs]
    assert found[len(runs) :] == [
        (virtual_address(2, r.offset), r.raw) for r in runs if r.block == 0
    ]
    check = verify(bytes(image), result.script.lines, both.codec(), result.blocks)
    assert check.ok and check.decompressed_checked == len(found) == 14


def test_every_argument_of_a_command_is_skipped(loaded):
    # a command with three arguments that all have the value of a glyph id
    tbl = load_tbl16()
    words = tokens(tbl, 0x12, tbl["い"], tbl["う"], tbl["ね"], "そらがあおい。")
    block = Block(0, 0, words, [(0, len(words))])
    raws = {}
    for count in (1, 3):
        data = copy.deepcopy(loaded.profile.model_dump())
        data["encoding"]["skip"] = {0x12: count}
        found = find_compressed_strings([block], loaded.codec(), Profile.model_validate(data))
        raws[count] = [s.raw for s in found.strings]
    assert raws == {1: ["うねそらがあおい。"], 3: ["そらがあおい。"]}


def test_a_profile_without_compressed_text_reads_no_blocks(sjis_rom):
    profile = load_profile(sjis_rom.profile_path).profile
    assert read_profile_blocks(sjis_rom.rom, profile) == []


def test_the_pointer_table_is_what_leads_to_the_blocks(lz16_rom, loaded):
    assert loaded.profile.compressed.tables[0].base == 0x200
    for block in lz16_rom.manifest.blocks:
        at = 0x200 + block.index * 4
        pointer = int.from_bytes(lz16_rom.rom[at : at + 4], "little")
        assert pointer - POINTER_BASE == block.rom_offset


# ------------------------------------------------------------------ verify


def test_verify_checks_every_line_against_the_decompressed_block(lz16_rom, loaded, result):
    check = verify(lz16_rom.rom, result.script.lines, loaded.codec(), result.blocks)
    assert check.ok
    assert check.decompressed_checked == len(result.script.lines) == 9
    assert check.sha1 == check.expected_sha1 == lz16_rom.sha1
    assert check.mismatches == check.length_changes == []


def test_a_changed_line_is_a_mismatch(lz16_rom, loaded, result):
    lines = list(result.script.lines)
    lines[0] = lines[0].model_copy(update={"raw": "ねこがおちゃをのめ。"})
    check = verify(lz16_rom.rom, lines, loaded.codec(), result.blocks)
    assert not check.ok
    assert check.mismatches == [lines[0].address]
    assert check.decompressed_checked == len(lines) - 1


def test_text_the_table_cannot_encode_is_a_mismatch(lz16_rom, loaded, result):
    lines = [result.script.lines[0].model_copy(update={"raw": "ABC"})]
    check = verify(lz16_rom.rom, lines, loaded.codec(), result.blocks)
    assert check.mismatches == [lines[0].address]


def test_a_line_in_a_block_that_was_not_given_is_a_mismatch(lz16_rom, loaded, result):
    check = verify(lz16_rom.rom, result.script.lines, loaded.codec(), result.blocks[:1])
    assert not check.ok
    assert len(check.mismatches) == 4  # the four runs of block 1
    assert check.decompressed_checked == 5


# --------------------------------------------------------------------- CLI


def test_cli_extract_and_verify_report_the_compressed_blocks(lz16_rom, write_rom, tmp_path):
    from typer.testing import CliRunner

    from yomineko.cli.app import app

    runner = CliRunner()
    rom = write_rom(lz16_rom.rom)
    out = tmp_path / "script.json"
    args = ["--profile", str(lz16_rom.profile_path)]
    extracted = runner.invoke(app, ["extract", str(rom), *args, "-o", str(out)])
    assert extracted.exit_code == 0, extracted.output
    assert "Extracted 9 strings in 2 banks" in extracted.output
    verified = runner.invoke(app, ["verify", str(rom), *args])
    assert verified.exit_code == 0, verified.output
    assert "OK: the rebuilt ROM matches the original" in verified.output
    assert "9 lines in 2 compressed blocks re-encode to the exact bytes" in verified.output
