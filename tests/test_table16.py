import pytest
from support.synthrom import FAKE16_TBL, load_tbl16, tokens

from yomineko.core.encodings.table16 import Table16Codec
from yomineko.core.encodings.tbl import TableError


@pytest.fixture
def codec():
    return Table16Codec(FAKE16_TBL)


@pytest.fixture
def tbl():
    return load_tbl16()


def test_a_run_ends_at_the_first_token_that_is_not_in_the_table(codec, tbl):
    data = tokens(tbl, "ねこ", 0x0003, "おちゃ")
    end, text, jp = codec.parse(data, 0)
    assert (end, text, jp) == (4, "ねこ", 2)
    assert codec.parse(data, 6) == (len(data), "おちゃ", 3)  # ends with the data


def test_parse_and_encode_are_inverse(codec, tbl):
    data = tokens(tbl, "てんきがいいですね。", 0x0E)
    end, text, _ = codec.parse(data, 0)
    assert codec.encode(text) == data[:end]


def test_no_token_at_the_start_means_no_run(codec, tbl):
    assert codec.parse(tokens(tbl, 0x0003, "ね"), 0) is None
    assert codec.parse(b"", 0) is None
    assert codec.parse(b"\x80", 0) is None  # half a token


def test_japanese_count_leaves_out_digits_and_latin(codec, tbl):
    assert codec.parse(tokens(tbl, "12"), 0)[2] == 0
    assert codec.parse(tokens(tbl, "1ねこ"), 0)[2] == 2


def test_the_limit_caps_the_run_length_in_bytes(codec, tbl):
    data = tokens(tbl, "ねこねこねこ")
    assert codec.parse(data, 0, limit=4)[0] == 4


def test_parse_can_start_in_the_middle(codec, tbl):
    data = tokens(tbl, 0x0003, "ねこ", 0x0003)
    assert codec.parse(data, 2) == (6, "ねこ", 2)


def test_encoding_a_character_with_no_entry_raises(codec):
    with pytest.raises(ValueError, match="no table entry"):
        codec.encode("A")


def test_the_table_knows_how_many_glyphs_it_has(codec):
    assert len(codec) == 95


def test_literal_braces_roundtrip(tmp_path):
    table = tmp_path / "braces.tbl"
    table.write_text("0090={\n0091=}\n0092=\\\n0093=a\n", encoding="utf-8")
    codec = Table16Codec(table)
    data = bytes([0x93, 0, 0x90, 0, 0x91, 0, 0x92, 0])
    _end, text, _ = codec.parse(data, 0)
    assert text == "a\\{\\}\\\\"
    assert codec.encode(text) == data


def test_a_multi_character_entry_uses_the_longest_match(tmp_path):
    table = tmp_path / "multi.tbl"
    table.write_text("0100=ね\n0101=こ\n0102=ねこ\n", encoding="utf-8")
    codec = Table16Codec(table)
    assert codec.encode("ねこ") == (0x0102).to_bytes(2, "little")
    assert codec.encode("ね") == (0x0100).to_bytes(2, "little")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("ZZ=a\n", r"bad\.tbl:1"),
        ("12345=a\n", r"bad\.tbl:1"),
        ("0100=\n", r"bad\.tbl:1"),
        ("0100=a\n0100=b\n", r"bad\.tbl:2: token 0100 appears twice"),
        ("0100=a\n0101=a\n", r"bad\.tbl:2: 'a' is already the text of token 0100"),
    ],
)
def test_bad_tables_are_reported_with_line_numbers(tmp_path, content, message):
    table = tmp_path / "bad.tbl"
    table.write_text(content, encoding="utf-8")
    with pytest.raises(TableError, match=message):
        Table16Codec(table)


def test_missing_table_file_is_reported(tmp_path):
    with pytest.raises(TableError, match="cannot read table"):
        Table16Codec(tmp_path / "nope.tbl")


def test_end_token_and_newline_lines_are_ignored(tmp_path):
    table = tmp_path / "ctl.tbl"
    table.write_text("# comment\n\n/FFFF\n*0001\n0100=a\n", encoding="utf-8")
    assert len(Table16Codec(table)) == 1
