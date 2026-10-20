import pytest

from yomineko.core.encodings.sjis import ShiftJISCodec
from yomineko.core.encodings.tbl import TableCodec
from yomineko.profile.loader import (
    ProfileError,
    find_profile,
    load_profile,
    packaged_profiles,
    resolve_profile,
)

PMD_SHA1 = "4bc9370edebb3da5bdf768eeced689fda3f8b77b"


def test_load_a_profile_and_build_its_codec(sjis_rom, tbl_rom):
    sjis = load_profile(sjis_rom.profile_path)
    assert sjis.profile.id == "synth-sjis"
    assert isinstance(sjis.codec(), ShiftJISCodec)
    tbl = load_profile(tbl_rom.profile_path)
    assert isinstance(tbl.codec(), TableCodec)
    assert tbl.codec().terminator == 0xFF


def test_table_path_is_relative_to_the_profile_file(tbl_rom):
    codec = load_profile(tbl_rom.profile_path).codec()
    assert codec.path.name == "fake.tbl" and codec.path.is_file()


def test_missing_file(tmp_path):
    with pytest.raises(ProfileError, match="cannot read"):
        load_profile(tmp_path / "nope.yaml")


def test_invalid_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("id: [unclosed", encoding="utf-8")
    with pytest.raises(ProfileError, match="not valid YAML"):
        load_profile(path)


def test_schema_violations_name_the_field(tmp_path, sjis_rom):
    text = sjis_rom.profile_path.read_text(encoding="utf-8")
    path = tmp_path / "bad.yaml"
    path.write_text(text.replace("platform: gba", "platform: nds"), encoding="utf-8")
    with pytest.raises(ProfileError, match="platform"):
        load_profile(path)


def test_a_yaml_file_that_is_not_a_mapping(tmp_path):
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="invalid profile"):
        load_profile(path)


def test_the_packaged_pmd_profile_loads_and_has_the_known_checksum():
    profiles = {p.profile.id: p for p in packaged_profiles()}
    pmd = profiles["pmd-red-jp"]
    assert pmd.profile.rom.sha1 == PMD_SHA1
    assert pmd.profile.rom.game_code == "B24J"
    assert pmd.profile.encoding.single_byte_kana == "hiragana"
    assert len(pmd.profile.tables) == 18


def test_the_packaged_profiles_are_read_once(monkeypatch):
    from yomineko.profile import loader

    loader._packaged_profiles.cache_clear()
    reads = []
    real = loader.load_profile
    monkeypatch.setattr(loader, "load_profile", lambda path: reads.append(path) or real(path))
    first = packaged_profiles()
    first.clear()  # a caller changing its list does not change the next caller's
    second = packaged_profiles()
    assert second and len(reads) == len(second)


def test_yaml_is_read_with_libyaml_when_it_is_there():
    import yaml

    from yomineko.profile.loader import load_yaml

    if not yaml.__with_libyaml__:
        pytest.skip("PyYAML was built without libyaml")
    from yomineko.profile import loader

    assert loader._YAML_LOADER is yaml.CSafeLoader
    assert load_yaml("a: [1, x]\n") == {"a": [1, "x"]}
    with pytest.raises(yaml.YAMLError):
        load_yaml("a: !!python/object:os.system {}\n")


def test_find_profile_by_checksum(sjis_rom):
    assert find_profile(PMD_SHA1).profile.id == "pmd-red-jp"
    assert find_profile("0" * 40) is None
    extra = load_profile(sjis_rom.profile_path)
    assert find_profile(sjis_rom.sha1, [extra]).profile.id == "synth-sjis"


def test_resolve_by_id_or_path(sjis_rom):
    assert resolve_profile("pmd-red-jp").profile.id == "pmd-red-jp"
    assert resolve_profile(str(sjis_rom.profile_path)).profile.id == "synth-sjis"


def test_resolve_unknown_id_lists_the_packaged_ones():
    with pytest.raises(ProfileError, match="pmd-red-jp"):
        resolve_profile("no-such-game")


def test_the_packaged_gyakuten_saiban_table_is_complete_and_unique():
    from yomineko.core.encodings.table16 import Table16Codec

    loaded = resolve_profile("gyakuten-saiban-jp")
    codec = loaded.codec()
    assert isinstance(codec, Table16Codec)
    assert len(codec) == 1352  # one character per glyph id 0x80-0x5C7, no gaps, no repeats
    first = codec.parse(bytes([0x80, 0x00]), 0)
    assert first == (2, "0", 0)
    assert codec.parse(bytes([0xC0, 0x00]), 0)[2] == 1  # the first hiragana
    assert codec.parse(bytes([0x7F, 0x00]), 0) is None  # below the font: a command
    assert loaded.profile.compressed.tables[0].count == 17


def test_the_packaged_crystal_table_holds_characters_and_names_but_no_strings_of_the_game():
    import re

    loaded = resolve_profile("pokemon-crystal-jp")
    table = (loaded.path.parent / loaded.profile.encoding.table).read_text(encoding="utf-8")
    entries = [line.split("=", 1) for line in table.splitlines() if not line.startswith("#")]
    marked = [text for _, text in entries if len(text) > 1]
    assert len(entries) == 198 and len(marked) == 9
    assert all(re.fullmatch("<name[0-9A-F]{2}>", text) for text in marked)
    # the 17 bytes that draw a fixed string: only where each string is in the ROM
    strings = loaded.profile.encoding.rom_strings
    assert len(strings) == 17 and all(0x127C <= at < 0x12D0 for at in strings.values())
    assert not {f"{byte:02X}" for byte in strings} & {key for key, _ in entries}
    with pytest.raises(ProfileError, match="cannot be built without one"):
        loaded.codec()
