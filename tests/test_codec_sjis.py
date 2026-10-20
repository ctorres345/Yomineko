import pytest

from yomineko.core.encodings.sjis import ShiftJISCodec

PMD_LEADS = [(0x84, 0x87), (0xEB, 0xFC)]


@pytest.fixture
def codec():
    return ShiftJISCodec(PMD_LEADS)


def parse(codec, data: bytes):
    return codec.parse(data + b"\0", 0)


def test_every_fixture_string_parses_and_reencodes_identically(sjis_rom, codec):
    for s in sjis_rom.manifest.strings:
        end, raw, jp = codec.parse(sjis_rom.rom, s.offset)
        assert (end, raw) == (s.end, s.raw)
        assert jp >= 1
        assert codec.encode(raw) == sjis_rom.rom[s.offset : s.end]


def test_standard_characters_decode(codec):
    assert parse(codec, "ねこ".encode("shift_jis")) == (4, "ねこ", 2)


def test_single_byte_kana_decode_to_halfwidth_and_count_as_japanese(codec):
    _end, text, jp = parse(codec, bytes([0xC3, 0xB7, 0xCA]))
    assert (text, jp) == ("ﾃｷﾊ", 3)
    assert codec.encode(text) == bytes([0xC3, 0xB7, 0xCA])


def test_custom_lead_bytes_become_hex_escapes_and_roundtrip(codec):
    _end, text, _ = parse(codec, bytes([0x85, 0x40]))
    assert text == "{8540}"
    assert codec.encode(text) == bytes([0x85, 0x40])


def test_same_bytes_are_a_real_character_without_a_custom_range():
    plain = ShiftJISCodec()
    assert plain.parse(bytes([0x84, 0x40, 0]), 0)[1] == "А"  # Cyrillic A
    custom = ShiftJISCodec([(0x84, 0x87)])
    assert custom.parse(bytes([0x84, 0x40, 0]), 0)[1] == "{8440}"


def test_control_bytes_are_escaped_but_newline_is_kept(codec):
    _end, text, _ = parse(codec, bytes([0x0D, 0x0A]))
    assert text == "{0D}\n"
    assert codec.encode(text) == bytes([0x0D, 0x0A])


def test_literal_backslash_and_braces_are_escaped_and_roundtrip(codec):
    data = b"a{b}\\c"
    _end, text, _ = parse(codec, data)
    assert text == "a\\{b\\}\\\\c"
    assert codec.encode(text) == data


@pytest.mark.parametrize(
    "bad",
    [
        bytes([0xFD]),  # not a valid lead
        bytes([0x82]),  # lead with no trail before the terminator
        bytes([0x82, 0x20]),  # trail out of range
        bytes([0xA0]),
    ],
)
def test_invalid_bytes_mean_not_text(codec, bad):
    assert parse(codec, bad) is None


def test_unterminated_string_is_not_text(codec):
    assert codec.parse(b"abc", 0) is None
    assert codec.parse(b"a" * 100, 0, limit=10) is None


def test_terminator_is_configurable():
    codec = ShiftJISCodec(terminator=0xFF)
    assert codec.parse(b"ab\xff", 0) == (2, "ab", 0)
    assert codec.parse(b"ab\x00", 0) is None or codec.parse(b"ab\x00", 0)[1] != "ab"
