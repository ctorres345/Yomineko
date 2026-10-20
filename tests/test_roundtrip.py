import pytest

from yomineko.core.rom.base import rom_from_bytes
from yomineko.core.roundtrip import LengthChanged, rebuild, verify
from yomineko.extract import extract
from yomineko.profile.loader import load_profile


@pytest.fixture(params=["sjis_rom", "tbl_rom"])
def parts(request):
    synth = request.getfixturevalue(request.param)
    loaded = load_profile(synth.profile_path)
    result = extract(rom_from_bytes(synth.rom), loaded)
    return synth, loaded.codec(), result.script.lines


def test_rebuild_is_byte_identical(parts):
    synth, codec, lines = parts
    assert rebuild(synth.rom, lines, codec) == synth.rom


def test_verify_reports_a_clean_roundtrip(parts):
    synth, codec, lines = parts
    result = verify(synth.rom, lines, codec)
    assert result.ok
    assert result.sha1 == result.expected_sha1 == synth.sha1
    assert result.mismatches == result.length_changes == []


def test_a_same_length_edit_is_written_and_flagged(sjis_rom):
    loaded = load_profile(sjis_rom.profile_path)
    codec = loaded.codec()
    lines = extract(rom_from_bytes(sjis_rom.rom), loaded).script.lines
    target = next(line for line in lines if line.raw == "お茶をのみましょう。")
    edited = [
        line.model_copy(update={"raw": "お茶をのみましょうか"}) if line is target else line
        for line in lines
    ]
    rebuilt = rebuild(sjis_rom.rom, edited, codec)
    assert rebuilt != sjis_rom.rom
    assert rebuilt[target.address : target.address + 20] == "お茶をのみましょうか".encode(
        "shift_jis"
    )
    result = verify(sjis_rom.rom, edited, codec)
    assert not result.ok
    assert result.mismatches == [target.address]


def test_a_length_change_is_refused_by_rebuild_and_reported_by_verify(sjis_rom):
    loaded = load_profile(sjis_rom.profile_path)
    codec = loaded.codec()
    lines = extract(rom_from_bytes(sjis_rom.rom), loaded).script.lines
    target = lines[0]
    longer = [lines[0].model_copy(update={"raw": target.raw + "ね"}), *lines[1:]]
    with pytest.raises(LengthChanged) as err:
        rebuild(sjis_rom.rom, longer, codec)
    assert err.value.address == target.address
    result = verify(sjis_rom.rom, longer, codec)
    assert not result.ok
    assert result.length_changes == [target.address]


def test_text_the_encoding_cannot_represent_is_a_mismatch(tbl_rom):
    loaded = load_profile(tbl_rom.profile_path)
    lines = extract(rom_from_bytes(tbl_rom.rom), loaded).script.lines
    bad = [lines[0].model_copy(update={"raw": "A"}), *lines[1:]]
    result = verify(tbl_rom.rom, bad, loaded.codec())
    assert not result.ok
    assert result.mismatches == [lines[0].address]


def test_rebuild_refuses_a_line_with_no_text_in_the_rom(sjis_rom):
    loaded = load_profile(sjis_rom.profile_path)
    lines = extract(rom_from_bytes(sjis_rom.rom), loaded).script.lines
    ghost = lines[0].model_copy(update={"address": 0x1800})  # inside the noise block
    with pytest.raises(ValueError, match="no text at"):
        rebuild(sjis_rom.rom, [ghost], loaded.codec())
