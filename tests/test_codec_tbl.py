import pytest
from support.synthrom import FAKE_TBL

from yomineko.core.encodings.tbl import TableCodec, TableError


@pytest.fixture
def codec():
    return TableCodec(FAKE_TBL, terminator=0xFF)


def test_every_fixture_string_parses_and_reencodes_identically(tbl_rom, codec):
    for s in tbl_rom.manifest.strings:
        end, raw, _jp = codec.parse(tbl_rom.rom, s.offset)
        assert (end, raw) == (s.end, s.raw)
        assert codec.encode(raw) == tbl_rom.rom[s.offset : s.end]


def test_longest_match_wins(codec):
    # E001 is a two-byte entry for two characters; 0x50 0x4B... are single entries
    assert codec.parse(bytes([0xE0, 0x01, 0xFF]), 0)[1] == "ねこ"
    assert codec.encode("ねこ") == bytes([0xE0, 0x01])


def test_newline_and_placeholder_entries(codec):
    _end, text, _ = codec.parse(bytes([0x01, 0xFE, 0xF0, 0xFF]), 0)
    assert text == "あ\n<NAME>"
    assert codec.encode(text) == bytes([0x01, 0xFE, 0xF0])


def test_unmapped_byte_means_not_text(codec):
    assert codec.parse(bytes([0x01, 0xC0, 0xFF]), 0) is None


def test_unterminated_is_not_text(codec):
    assert codec.parse(bytes([0x01, 0x02]), 0) is None


def test_japanese_count_counts_characters_not_bytes(codec):
    assert codec.parse(bytes([0xE0, 0x01, 0x01, 0xFF]), 0)[2] == 3  # ねこ + あ


def test_encoding_a_character_with_no_entry_raises(codec):
    with pytest.raises(ValueError, match="no table entry"):
        codec.encode("A")


def test_literal_braces_roundtrip(tmp_path):
    table = tmp_path / "braces.tbl"
    table.write_text("01={\n02=}\n03=\\\n04=a\n", encoding="utf-8")
    codec = TableCodec(table, terminator=0xFF)
    _end, text, _ = codec.parse(bytes([0x04, 0x01, 0x02, 0x03, 0xFF]), 0)
    assert text == "a\\{\\}\\\\"
    assert codec.encode(text) == bytes([0x04, 0x01, 0x02, 0x03])


def test_bad_table_lines_are_reported_with_line_numbers(tmp_path):
    table = tmp_path / "bad.tbl"
    table.write_text("01=あ\nZZ=い\n", encoding="utf-8")
    with pytest.raises(TableError, match=r"bad\.tbl:2"):
        TableCodec(table)


def test_missing_table_file_is_reported(tmp_path):
    with pytest.raises(TableError, match="cannot read table"):
        TableCodec(tmp_path / "nope.tbl")
