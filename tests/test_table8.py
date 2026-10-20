"""Byte-stream text: the table8 codec, the stream discoverer and the extraction of a ROM that
uses them, on the synthetic ROM from ``build_table8_rom``."""

import copy

import pytest
from pydantic import ValidationError
from support.synthrom import FAKE8_TBL, T8_END, T8_START

from yomineko.core.discover.stream import find_stream_strings
from yomineko.core.encodings.table8 import UNTIL_PREFIX, Table8Codec
from yomineko.core.encodings.tbl import TableError
from yomineko.core.rom.base import rom_from_bytes
from yomineko.core.roundtrip import verify
from yomineko.extract import extract, line_kind
from yomineko.profile.loader import load_profile
from yomineko.profile.schema import Profile

COMMANDS = {0x00: 0, 0x01: 1, 0x03: 0, 0x0A: UNTIL_PREFIX, 0x0B: 1, 0x35: 0}
BREAKS = {0x00, 0x01, 0x03, 0x0A}


@pytest.fixture(scope="module")
def codec():
    return Table8Codec(FAKE8_TBL, 0xFF, COMMANDS, BREAKS)


@pytest.fixture(scope="module")
def loaded(table8_rom):
    return load_profile(table8_rom.profile_path)


@pytest.fixture(scope="module")
def found(table8_rom, loaded):
    return find_stream_strings(table8_rom.rom, loaded.codec(), loaded.profile)


def write_table(tmp_path, text: str):
    path = tmp_path / "t.tbl"
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------- codec


def test_table_entries_are_counted(codec):
    assert len(codec) == 68  # 61 one-byte codes and 7 two-byte ones in tests/data/fake8.tbl


def test_a_run_ends_at_a_break_and_is_not_consumed_past_it(codec):
    data = bytes([0x81, 0x82, 0xFF, 0x00, 0x83])
    assert codec.parse(data, 0) == (2, "あい", 2)


def test_a_command_inside_a_sentence_becomes_escapes(codec):
    data = bytes([0x81, 0xFF, 0x0B, 0x01, 0x82, 0x00])
    assert codec.parse(data, 0) == (5, "あ{FF}{0B}{01}い", 2)


def test_skip_len_steps_over_commands_codes_and_single_bytes(codec):
    assert codec.skip_len(bytes([0xFF, 0x0A, 0x81, 0x82, 0xFF, 0x00]), 0) == 4  # up to the prefix
    assert codec.skip_len(bytes([0xFF, 0x0A, 0x81, 0x82]), 0) == 4  # no prefix after it
    assert codec.skip_len(bytes([0xFF, 0x01, 0x00, 0x81]), 0) == 3  # a break and its parameter
    assert codec.skip_len(bytes([0xFF, 0x7E, 0x81]), 0) == 2  # an unknown command
    assert codec.skip_len(bytes([0xFA, 0x01, 0x81]), 0) == 2  # a two-byte code
    assert codec.skip_len(bytes([0xFA]), 0) == 1  # a lead byte cut off by the end
    assert codec.skip_len(bytes([0x00, 0x81]), 0) == 1
    assert codec.skip_len(bytes([0xFF]), 0) == 1  # a prefix with nothing after it


def test_a_command_with_parameters_up_to_the_next_prefix_is_never_inline():
    inline = Table8Codec(FAKE8_TBL, 0xFF, {0x0A: UNTIL_PREFIX, 0x35: 0}, set())
    data = bytes([0x81, 0xFF, 0x0A, 0x82, 0x83, 0xFF, 0x35, 0x84, 0x00])
    assert inline.parse(data, 0) == (8, "あ{FF}{0A}{82}{83}{FF}{35}え", 2)
    assert inline.parse(bytes([0x81, 0xFF, 0x0A, 0x82]), 0) == (4, "あ{FF}{0A}{82}", 1)


def test_two_byte_codes_decode_and_unknown_ones_are_escaped(codec):
    assert codec.parse(bytes([0xFA, 0x02, 0xFA, 0xFE, 0x81, 0x00]), 0) == (5, "今{FAFE}あ", 2)


def test_a_two_byte_code_cut_off_at_the_end_stops_the_run(codec):
    assert codec.parse(bytes([0x81, 0xFA]), 0) == (1, "あ", 1)


@pytest.mark.parametrize(
    "data",
    [
        bytes([0x00, 0x81]),  # an unknown byte first
        bytes([0xFF, 0x00, 0x81]),  # a break first
        bytes([0xFF, 0x7E, 0x81]),  # an unknown command first
        bytes([0xFF, 0x0B]),  # a command that runs off the data
        bytes([0xFF, 0x0B, 0x01]),  # commands only: no text
        bytes([0xFA, 0xFE]),  # only an unknown code
        b"",
    ],
)
def test_no_run_unless_it_starts_with_text(codec, data):
    assert codec.parse(data, 0) is None


def test_a_run_is_cut_at_the_limit(codec):
    assert codec.parse(bytes([0x81] * 10), 0, limit=4) == (4, "ああああ", 4)


def test_encode_is_the_inverse_of_parse(codec):
    for raw in ("あ{FF}{0B}{01}い", "今{FAFE}あ", "ねこがおちゃをのむ。", "ａｂｃ！"):
        data = codec.encode(raw)
        assert codec.parse(data, 0)[1] == raw


def test_encode_rejects_text_that_is_not_in_the_table(codec):
    with pytest.raises(ValueError, match="no table entry"):
        codec.encode("あ猫、")  # the comma is not in the table
    with pytest.raises(ValueError, match="no table entry"):
        codec.encode("\\{")  # an escaped brace is not a table entry either


def test_a_codec_without_commands_reads_text_only():
    plain = Table8Codec(FAKE8_TBL)
    assert plain.parse(bytes([0x81, 0xFF, 0x00]), 0) == (1, "あ", 1)
    assert plain.skip_len(bytes([0xFF, 0x00]), 0) == 1


@pytest.mark.parametrize(
    ("table", "message"),
    [
        ("81=あ\n81=い\n", "appears twice"),
        ("81=あ\n82=あ\n", "map back uniquely"),
        ("FA01=茶\nFA01=今\n", "appears twice"),
        ("8=あ\n", "bad table line"),
        ("81=\n", "bad table line"),
        ("zz=あ\n", "bad table line"),
        ("no equals sign\n", "bad table line"),
        ("FA=あ\nFA01=茶\n", "both a one-byte code"),
        ("FF=あ\n", "command prefix"),
        ("FF01=茶\n", "command prefix"),
    ],
)
def test_a_bad_table_is_refused(tmp_path, table, message):
    with pytest.raises(TableError, match=message):
        Table8Codec(write_table(tmp_path, table), 0xFF)


def test_a_missing_table_is_refused(tmp_path):
    with pytest.raises(TableError, match="cannot read"):
        Table8Codec(tmp_path / "nope.tbl")


# --------------------------------------------------------------- discovery


def test_every_expected_line_is_found_and_nothing_else(table8_rom, found):
    got = [(s.start, s.end, s.raw) for s in found.strings]
    want = [(s.offset, s.end, s.raw) for s in table8_rom.manifest.strings]
    assert got == want
    assert found.unstable == []
    assert len(want) == 6


def test_dropped_runs_are_not_lines(table8_rom, found):
    starts = {s.start for s in found.strings}
    assert len(table8_rom.manifest.rejected) == 4
    for offset in table8_rom.manifest.rejected:
        assert offset not in starts


def test_nothing_outside_the_region_is_read(table8_rom, found):
    assert all(s.start >= T8_START and s.end <= T8_END for s in found.strings)


def test_parameters_that_look_like_kana_are_not_text(table8_rom, found):
    assert all("{82}" not in s.raw and "うえ" not in s.raw for s in found.strings)


def test_a_run_that_does_not_re_encode_identically_is_set_aside(tmp_path):
    # 83 is also the two characters of 81 82, so the longest match changes the bytes
    table = write_table(tmp_path, "81=あ\n82=い\n83=あい\n84=う\n")
    codec = Table8Codec(table, 0xFF)
    profile = Profile.model_validate(
        {
            "id": "t",
            "title": "t",
            "platform": "gba",
            "rom": {"sha1": "0" * 40, "game_code": "TSTJ"},
            "encoding": {"type": "table8", "table": "t.tbl"},
            "text": {"regions": [{"start": 0, "end": 16}]},
        }
    )
    data = bytes([0x81, 0x82, 0x84, 0x00, 0x83, 0x84, 0x00])
    result = find_stream_strings(data, codec, profile)
    assert [s.start for s in result.strings] == [4]
    assert result.unstable == [0]


# --------------------------------------------------------------- extraction


@pytest.fixture(scope="module")
def result(table8_rom, loaded):
    return extract(rom_from_bytes(table8_rom.rom, "t.gba"), loaded)


def test_lines_match_the_manifest(table8_rom, result):
    lines = result.script.lines
    assert [(x.address, x.raw, x.text) for x in lines] == [
        (s.offset, s.raw, s.text) for s in table8_rom.manifest.strings
    ]
    assert [x.kind for x in lines] == [line_kind(x.text, 12) for x in lines]
    assert not any(x.referenced for x in lines)
    assert lines[0].id == f"{0x08000000 + lines[0].address:08X}"


def test_commands_inside_a_line_are_hidden_from_the_readable_text(result):
    line = next(x for x in result.script.lines if "{FF}" in x.raw)
    assert (line.raw, line.text) == ("ねこが{FF}{0B}{01}おちゃ", "ねこがおちゃ")


def test_the_rebuilt_rom_is_byte_identical(table8_rom, loaded, result):
    check = verify(table8_rom.rom, result.script.lines, loaded.codec())
    assert check.ok and not check.mismatches and not check.length_changes


def test_the_profile_loads_a_table8_codec(loaded):
    codec = loaded.codec()
    assert isinstance(codec, Table8Codec)
    assert (codec.prefix, codec.breaks) == (0xFF, frozenset(BREAKS))


# ------------------------------------------------------------------ schema


@pytest.fixture
def profile_data(table8_rom):
    return copy.deepcopy(table8_rom.profile_data)


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d: d["encoding"].pop("command_prefix"), "needs encoding.command_prefix"),
        (lambda d: d["encoding"]["commands"].update({0x20: 17}), "not a valid entry"),
        (lambda d: d["encoding"]["commands"].update({0x20: -2}), "not a valid entry"),
        (lambda d: d["encoding"]["line_breaks"].append(0x7E), "not listed in commands"),
        (lambda d: d["text"].update({"regions": []}), "needs text.regions"),
        (lambda d: d["encoding"].pop("table"), "needs encoding.table"),
        (
            lambda d: d["encoding"].update({"type": "table", "table": "x.tbl"}),
            "only for 'table8'",
        ),
    ],
)
def test_bad_table8_profiles_are_refused(profile_data, edit, message):
    edit(profile_data)
    with pytest.raises(ValidationError, match=message):
        Profile.model_validate(profile_data)
