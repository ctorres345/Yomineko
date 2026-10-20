import pytest
from support.synthrom import write_gb_header

from yomineko.core.rom import gb


def rom(**header) -> bytearray:
    data = bytearray(0x8000)
    data[0x4000:0x4004] = b"\x12\x34\x56\x78"  # something for the whole-ROM checksum
    write_gb_header(data, **header)
    return data


def test_color_cartridge_with_a_code():
    header = gb.parse_header(bytes(rom(revision=2)))
    assert (header.title, header.game_code, header.revision) == ("SYNTH TEST", "TSTJ", 2)
    assert header.color and header.japanese and header.checksum_ok


def test_region_comes_from_the_code_before_the_destination_byte():
    assert not gb.parse_header(bytes(rom(game_code="TSTE", destination=0x00))).japanese
    assert gb.parse_header(bytes(rom(game_code="TSTJ", destination=0x01))).japanese


def test_older_cartridge_has_no_code_and_uses_the_destination_byte():
    title = "SYNTHETIC TITLE"
    home = gb.parse_header(bytes(rom(title=title, game_code="", color=False)))
    assert (home.title, home.game_code, home.color) == (title, "", False)
    assert home.japanese
    abroad = gb.parse_header(bytes(rom(title=title, game_code="", color=False, destination=1)))
    assert not abroad.japanese


def test_a_color_title_whose_last_bytes_cannot_be_a_code_is_read_whole():
    header = gb.parse_header(bytes(rom(title="SYNTH-TEST-with", game_code="")))
    assert (header.title, header.game_code) == ("SYNTH-TEST-with", "")


def test_a_color_title_that_ends_like_a_code_is_read_as_a_title_and_a_code():
    # nothing in the header tells the two apart; the region then follows the last letter
    header = gb.parse_header(bytes(rom(title="SYNTHETICTITLEX", game_code="")))
    assert (header.title, header.game_code, header.japanese) == ("SYNTHETICTI", "TLEX", False)


def test_damaged_rom_checksum_is_reported_not_fatal():
    data = rom()
    data[0x4000] ^= 0xFF
    assert not gb.parse_header(bytes(data)).checksum_ok


@pytest.mark.parametrize("damage", ["short", "odd size", "header checksum", "empty"])
def test_not_a_game_boy_rom(damage):
    data = rom()
    if damage == "short":
        data = data[:0x14F]
    elif damage == "odd size":
        data += b"\0"
    elif damage == "header checksum":
        data[0x14D] ^= 0xFF
    else:
        data = bytearray(0x8000)
        data[0x14D] = 0xE7  # the checksum of an all-zero header
    assert not gb.looks_like_gb(bytes(data))
    with pytest.raises(ValueError, match="not a Game Boy ROM"):
        gb.parse_header(bytes(data))
