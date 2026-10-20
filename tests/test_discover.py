import struct

import pytest

from yomineko.core.discover.banks import bank_name, group_banks
from yomineko.core.discover.filter import kana_ratio, make_looks_like_text
from yomineko.core.discover.pointers import scan_pointers
from yomineko.core.discover.strings import FoundString, find_strings
from yomineko.profile.loader import load_profile
from yomineko.profile.schema import Region

IGNORE = ["#C.", "#[RPW=]", r"\$[a-z]\d"]


@pytest.fixture(params=["sjis_rom", "tbl_rom"])
def synth(request):
    return request.getfixturevalue(request.param)


# ------------------------------------------------------------------ pointers


def test_scan_pointers_finds_aligned_words_inside_regions():
    data = bytearray(64)
    data[8:12] = struct.pack("<I", 0x08000020)  # -> 0x20
    data[16:20] = struct.pack("<I", 0x08000100)  # -> 0x100, outside the region
    data[21:25] = struct.pack("<I", 0x08000030)  # unaligned: ignored
    assert scan_pointers(bytes(data), 0x08000000, [Region(start=0, end=0x40)]) == {0x20}


def test_scan_pointers_respects_each_region():
    data = bytearray(0x100)
    for at, target in ((0, 0x10), (4, 0x50), (8, 0x90)):
        data[at : at + 4] = struct.pack("<I", 0x08000000 + target)
    regions = [Region(start=0, end=0x20), Region(start=0x80, end=0xA0)]
    assert scan_pointers(bytes(data), 0x08000000, regions) == {0x10, 0x90}


def test_scan_pointers_with_other_alignment_uses_the_generic_path():
    data = bytearray(32)
    data[2:6] = struct.pack("<I", 0x08000010)
    assert scan_pointers(bytes(data), 0x08000000, [Region(start=0, end=0x20)], align=2) == {0x10}
    assert scan_pointers(bytes(data), 0x08000000, [Region(start=0, end=0x20)], align=4) == set()


def test_scan_pointers_on_tiny_input():
    assert scan_pointers(b"\0\0", 0x08000000, [Region(start=0, end=0x10)]) == set()


# -------------------------------------------------------------------- filter


@pytest.mark.parametrize(
    "text",
    ["ねこがおちゃをのむ。", "ボタン", "おちゃ", "お茶をのみましょう。", "ﾃｷﾊ　にげた！", "！！"],
)
def test_real_looking_text_passes(text):
    assert make_looks_like_text(IGNORE, 0.7)(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "ｱｲｳｴｵ",  # half-width only: graphics data
        "亜唖娃阿哀",  # kanji with no kana
        "abc",
        "ねこab12345",  # mostly ASCII noise
        "#CG#R",  # only control codes
    ],
)
def test_noise_is_rejected(text):
    assert not make_looks_like_text(IGNORE, 0.7)(text)


def test_ignore_patterns_are_removed_before_scoring():
    check = make_looks_like_text(IGNORE, 0.7)
    assert check("#CGあい#R")
    assert not make_looks_like_text([], 0.7)("#CGあい#R")  # codes now count against it


def test_a_higher_threshold_rejects_borderline_text():
    text = "ねこがabc"
    assert make_looks_like_text([], 0.5)(text)
    assert not make_looks_like_text([], 0.9)(text)


def test_kana_ratio():
    assert kana_ratio("あいう") == 1.0
    assert kana_ratio("あいab") == 0.5
    assert kana_ratio("") == 0.0


# ------------------------------------------------------------ find_strings


def test_find_strings_matches_the_manifest_exactly(synth):
    profile = load_profile(synth.profile_path)
    result = find_strings(synth.rom, profile.codec(), profile.profile)
    expected = {s.offset: (s.end, s.raw, s.referenced) for s in synth.manifest.strings}
    assert {s.start: (s.end, s.raw, s.referenced) for s in result.strings} == expected
    assert result.unstable == []


def test_rejected_noise_and_shared_suffixes_are_not_found(synth):
    profile = load_profile(synth.profile_path)
    found = {s.start for s in find_strings(synth.rom, profile.codec(), profile.profile).strings}
    for offset in synth.manifest.rejected:
        assert offset not in found
    for offset in synth.manifest.shared_suffix:
        assert offset not in found
    start, end = synth.manifest.noise
    assert not any(start <= a < end for a in found)


def test_unreferenced_line_is_found_only_because_it_follows_a_terminator(sjis_rom):
    profile = load_profile(sjis_rom.profile_path)
    unref = [s for s in sjis_rom.manifest.strings if not s.referenced]
    assert len(unref) == 1
    result = find_strings(sjis_rom.rom, profile.codec(), profile.profile)
    found = {s.start: s for s in result.strings}
    assert found[unref[0].offset].referenced is False


def test_strict_unreferenced_thresholds_drop_the_unreferenced_line(sjis_rom):
    loaded = load_profile(sjis_rom.profile_path)
    strict = loaded.profile.model_copy(
        update={
            "discover": loaded.profile.discover.model_copy(
                update={
                    "unreferenced": loaded.profile.discover.unreferenced.model_copy(
                        update={"min_japanese": 99}
                    )
                }
            )
        }
    )
    found = find_strings(sjis_rom.rom, loaded.codec(), strict).strings
    assert all(s.referenced for s in found)


def test_strings_that_do_not_reencode_identically_are_set_aside(tbl_rom):
    """A game may spell 'ねこ' as two single entries; the table would re-encode it as the
    two-byte entry, so the bytes would not rebuild identically."""
    loaded = load_profile(tbl_rom.profile_path)
    codec = loaded.codec()
    ne, ko = codec.encode("ね"), codec.encode("こ")
    rom = bytearray(tbl_rom.rom)
    spelled_out = ne + ko + codec.encode("が") + b"\xff"
    rom[0x500 : 0x500 + len(spelled_out)] = spelled_out
    rom[0x2010:0x2014] = struct.pack("<I", 0x08000500)  # a pointer to it (free slot)
    result = find_strings(bytes(rom), codec, loaded.profile)
    assert 0x500 in result.unstable
    assert 0x500 not in {s.start for s in result.strings}


# --------------------------------------------------------------------- banks


def make(start, end):
    return FoundString(start, end, "x", True)


def test_group_banks_uses_the_gap_between_end_and_next_start():
    strings = [make(0, 10), make(0x40 + 10, 0x60), make(0x60 + 0x41, 0x80), make(0x1000, 0x1010)]
    banks = group_banks(strings, 0x40)
    assert [[s.start for s in b] for b in banks] == [[0, 0x4A], [0xA1], [0x1000]]


def test_group_banks_of_nothing():
    assert group_banks([], 0x40) == []


def test_bank_name_uses_the_first_address():
    assert bank_name([make(0x1234, 0x1240)]) == "bank_001234"
