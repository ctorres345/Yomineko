import pytest

from yomineko.core.encodings.plain import _HW, HW_AS_HIRAGANA, make_plain
from yomineko.profile.loader import load_profile


@pytest.fixture
def plain(sjis_rom):
    return make_plain(load_profile(sjis_rom.profile_path).profile)


def test_every_fixture_string_becomes_its_readable_text(sjis_rom, tbl_rom):
    for synth in (sjis_rom, tbl_rom):
        plain = make_plain(load_profile(synth.profile_path).profile)
        for s in synth.manifest.strings:
            assert plain(s.raw) == s.text


def test_single_byte_kana_are_restored_to_hiragana(plain):
    assert plain("ﾃｷﾊ") == "てきは"
    assert plain("ｳ､ｱ") == "う、あ"


def test_hiragana_map_covers_the_documented_range():
    assert len(_HW) == 0xFF9D - 0xFF61 + 1
    assert HW_AS_HIRAGANA["｡"] == "。"
    assert HW_AS_HIRAGANA["ｦ"] == "を"
    assert HW_AS_HIRAGANA["ﾝ"] == "ん"


def test_without_the_hiragana_option_halfwidth_kana_are_left_alone(tbl_rom):
    plain = make_plain(load_profile(tbl_rom.profile_path).profile)
    assert plain("ﾃｷ") == "ﾃｷ"


def test_control_codes_and_rules_apply_in_order(plain):
    assert plain("#CGねこ#Rが#Pいる") == "ねこが\nいる"
    assert plain("$n0は$m0に") == "〇〇は〇〇に"


def test_leftover_hex_escapes_are_dropped_and_literals_unescaped(plain):
    assert plain("あ{8540}い") == "あい"
    assert plain("a\\{b\\}\\\\c") == "a{b}\\c"


def test_whitespace_around_newlines_is_trimmed_and_the_result_stripped(plain):
    assert plain("  あ \n い  ") == "あ\nい"


def test_replacement_text_is_literal_not_a_regex_template(tbl_rom):
    profile = load_profile(tbl_rom.profile_path).profile
    profile = profile.model_copy(
        update={"plain": [type(profile.plain[0])(pattern="X", replace="\\1\\g<0>")]}
    )
    assert make_plain(profile)("aXb") == "a\\1\\g<0>b"
