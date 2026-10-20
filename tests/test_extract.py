import hashlib
from dataclasses import replace

import pytest
from support.synthrom import POINTER_BASE, SynthRom, sjis

from yomineko.core.rom.base import rom_from_bytes
from yomineko.extract import (
    ExtractResult,
    NotJapaneseError,
    ProfileMismatch,
    extract,
    line_kind,
)
from yomineko.model import Script
from yomineko.profile.loader import LoadedProfile, load_profile
from yomineko.profile.schema import Profile, TableSpec


@pytest.fixture(params=["sjis_rom", "tbl_rom"])
def run(request) -> tuple:
    synth = request.getfixturevalue(request.param)
    loaded = load_profile(synth.profile_path)
    return synth, extract(rom_from_bytes(synth.rom, "t.gba"), loaded)


def test_lines_match_the_manifest(run):
    synth, result = run
    lines = {line.address: line for line in result.script.lines}
    assert set(lines) == {s.offset for s in synth.manifest.strings}
    for s in synth.manifest.strings:
        line = lines[s.offset]
        assert (line.raw, line.text, line.kind, line.referenced) == (
            s.raw,
            s.text,
            s.kind,
            s.referenced,
        )
        assert line.id == f"{POINTER_BASE + s.offset:08X}"


def test_banks_are_named_by_their_first_address(run):
    synth, result = run
    assert len(result.banks) == synth.manifest.bank_count
    by_expected = {s.offset: s.bank for s in synth.manifest.strings}
    names = {}
    for line in result.script.lines:
        names.setdefault(by_expected[line.address], set()).add(line.bank)
    assert all(len(v) == 1 for v in names.values())
    assert len({next(iter(v)) for v in names.values()}) == len(names)
    assert all(b.startswith("bank_") for v in names.values() for b in v)


def test_terms_follow_the_profile_tables(run):
    synth, result = run
    lines = {line.address: line for line in result.script.lines}
    got = [(t.category, t.index, t.line_id) for t in result.script.terms]
    want = [(c, i, lines[off].id) for c, i, off in synth.manifest.terms]
    assert got == want
    assert [t.jp for t in result.script.terms] == [
        lines[o].text for _, _, o in synth.manifest.terms
    ]


def test_game_info_and_generator(run):
    synth, result = run
    game = result.script.game
    assert game.rom_sha1 == synth.sha1
    assert game.profile_id == synth.profile_data["id"]
    assert game.platform == "gba"
    assert result.script.generator.startswith("yomineko ")


def test_script_survives_a_json_roundtrip(run):
    _, result = run
    assert Script.model_validate_json(result.script.model_dump_json()) == result.script


def test_wrong_checksum_is_refused_unless_told_otherwise(sjis_rom):
    other = bytearray(sjis_rom.rom)
    other[0x20] ^= 0xFF  # change the ROM, keep the header valid
    rom = rom_from_bytes(bytes(other))
    loaded = load_profile(sjis_rom.profile_path)
    with pytest.raises(ProfileMismatch, match="is for ROM"):
        extract(rom, loaded)
    assert isinstance(extract(rom, loaded, check_checksum=False), ExtractResult)


def test_a_rom_that_is_not_japanese_is_refused(sjis_rom):
    rom = replace(rom_from_bytes(sjis_rom.rom), game_code="TSTE", japanese=False)
    loaded = load_profile(sjis_rom.profile_path)
    with pytest.raises(NotJapaneseError, match=r"reads Japanese games.*'TSTE'"):
        extract(rom, loaded)
    no_code = replace(rom, game_code="")  # an older Game Boy cartridge
    with pytest.raises(NotJapaneseError, match=r"reads Japanese games.*outside Japan"):
        extract(no_code, loaded)


def test_line_kind_rule():
    assert line_kind("おちゃ", 12) == "term"
    assert line_kind("あ" * 13, 12) == "dialogue"
    assert line_kind("あ" * 12, 12) == "term"
    assert line_kind("あ\nい", 12) == "dialogue"
    assert line_kind("いいね！", 12) == "dialogue"


def test_repeated_text_points_at_the_first_line_and_empty_text_does_not(sjis_rom):
    sjis_profile_path = sjis_rom.profile_path
    rom = SynthRom("DUPES", "DUPJ")
    for offset, text in (
        (0x100, "おちゃをのむ。"),
        (0x140, "おちゃをのむ。"),
        (0x180, "ねこがいる。"),
    ):
        rom.add_string(offset, sjis(text), 0, raw=text, text=text, kind="dialogue", bank=0)
    rom.add_string(0x1C0, sjis("#CG#R", "あ"), 0, raw="#CG#Rあ", text="あ", kind="term", bank=0)
    rom.add_string(0x1E0, sjis("#CG#R", "あ"), 0, raw="#CG#Rあ", text="あ", kind="term", bank=0)
    rom.add_pointer_table(0x2000, [0x100, 0x140, 0x180, 0x1C0, 0x1E0])
    data, _ = rom.finish()
    template = load_profile(sjis_profile_path).profile.model_dump()
    profile = Profile.model_validate(
        {
            **template,
            "rom": {"sha1": hashlib.sha1(data).hexdigest(), "game_code": "DUPJ"},
            "tables": [],
        }
    )
    result = extract(rom_from_bytes(data), LoadedProfile(profile, None))
    by_address = {line.address: line for line in result.script.lines}
    assert by_address[0x100].duplicate_of is None
    assert by_address[0x140].duplicate_of == by_address[0x100].id
    assert by_address[0x180].duplicate_of is None
    assert by_address[0x1E0].duplicate_of == by_address[0x1C0].id


def test_terms_cover_pointers_to_unextracted_text_and_skip_bad_ones(sjis_rom):
    """Table entries may point at text that is not an extracted line (parsed directly,
    no line id), at nothing (skipped), or run off the end of the ROM (stopped)."""
    loaded = load_profile(sjis_rom.profile_path)
    table = TableSpec(category="mixed", base=0x2000, stride=4, count=12)
    past_end = TableSpec(category="tail", base=0xFFF8, stride=4, count=4)
    profile = loaded.profile.model_copy(update={"tables": [table, past_end]})
    result = extract(rom_from_bytes(sjis_rom.rom), LoadedProfile(profile, loaded.path))

    by_index = {t.index: t for t in result.script.terms if t.category == "mixed"}
    assert by_index[0].line_id == "08000100"  # an extracted line
    assert by_index[7].line_id is None  # single-byte kana: parsed directly, not extracted
    assert by_index[7].jp == "あいうえお"
    assert by_index[8].line_id is None and by_index[8].jp == "亜唖娃阿哀"
    assert by_index[9].line_id is None  # a pointer into the middle of a line
    assert 10 not in by_index and 11 not in by_index  # zero words point nowhere
    assert [t.index for t in result.script.terms if t.category == "tail"] == []
