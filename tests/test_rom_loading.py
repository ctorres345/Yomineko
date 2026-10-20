import hashlib
import io
import zipfile

import pytest
from support.synthrom import SynthRom, write_gb_header

from yomineko.core.rom import gb, gba
from yomineko.core.rom.base import (
    MAX_ROM_SIZE,
    RomError,
    load_rom,
    load_rom_bytes,
    rom_from_bytes,
)


def test_header_fields(sjis_rom):
    header = gba.parse_header(sjis_rom.rom)
    assert (header.title, header.game_code, header.revision) == ("SYNTH TEST", "TSTJ", 0)
    assert header.checksum_ok


def test_damaged_header_checksum_is_reported_not_fatal(sjis_rom):
    data = bytearray(sjis_rom.rom)
    data[0xBD] ^= 0xFF
    assert not gba.parse_header(bytes(data)).checksum_ok


def test_header_of_something_else_is_refused():
    with pytest.raises(ValueError, match="not a GBA ROM"):
        gba.parse_header(b"\0" * 0x1000)


def test_rom_from_bytes(sjis_rom):
    rom = rom_from_bytes(sjis_rom.rom, "x.gba")
    assert rom.sha1 == hashlib.sha1(sjis_rom.rom).hexdigest() == sjis_rom.sha1
    assert (rom.platform, rom.game_code, rom.source, len(rom)) == ("gba", "TSTJ", "x.gba", 0x10000)


@pytest.mark.parametrize(
    "data",
    [b"", b"\0" * 0xBF, b"\0" * 0x1000, b"\0" * 0x8000],
    ids=["empty", "too short", "no GBA marker", "no Game Boy header"],
)
def test_not_a_rom(data):
    with pytest.raises(RomError, match="not a GBA or Game Boy ROM"):
        rom_from_bytes(data)


# ------------------------------------------------------------------ Game Boy


def gbc_rom(**header) -> bytes:
    return SynthRom("SYNTH GBC", "SGBJ", size=0x8000, platform="gbc", **header).finish()[0]


def test_a_game_boy_color_rom_is_recognised():
    rom = rom_from_bytes(gbc_rom(revision=1), "x.gbc")
    assert (rom.platform, rom.title, rom.game_code, rom.revision) == ("gbc", "SYNTH GBC", "SGBJ", 1)
    assert rom.japanese and len(rom) == 0x8000


def test_an_older_game_boy_rom_has_no_code_and_takes_its_region_from_the_header():
    data = bytearray(0x8000)
    write_gb_header(data, "SYNTHETIC TITLE", "", color=False)
    rom = rom_from_bytes(bytes(data))
    assert (rom.platform, rom.title, rom.game_code) == ("gb", "SYNTHETIC TITLE", "")
    assert rom.japanese
    write_gb_header(data, "SYNTHETIC TITLE", "", color=False, destination=1)
    assert not rom_from_bytes(bytes(data)).japanese


def test_region_of_a_gba_rom_comes_from_its_game_code(sjis_rom):
    assert rom_from_bytes(sjis_rom.rom).japanese
    assert not rom_from_bytes(SynthRom("USA GAME", "USAE", size=0x4000).finish()[0]).japanese


def test_a_game_boy_rom_with_the_gba_marker_byte_is_still_a_game_boy_rom():
    data = bytearray(gbc_rom())
    data[0xB2] = gba.FIXED_BYTE  # in a Game Boy ROM this is ordinary code or data
    write_gb_header(data, "SYNTH GBC", "SGBJ")  # the second checksum covers every byte
    assert gba.looks_like_gba(bytes(data))
    assert rom_from_bytes(bytes(data)).platform == "gbc"
    data[0x4000] ^= 0xFF  # a patched dump: the console never checks the whole-ROM checksum
    assert not gb.parse_header(bytes(data)).checksum_ok
    assert rom_from_bytes(bytes(data)).platform == "gbc"


def test_a_gba_rom_that_passes_the_game_boy_checksum_is_still_a_gba_rom(sjis_rom):
    data = bytearray(sjis_rom.rom)
    data[0x134] = 1  # an all-zero Game Boy header is never taken for one
    x = 0
    for b in data[0x134:0x14D]:  # the Game Boy header checksum: one byte, so 1 dump in 256
        x = (x - b - 1) & 0xFF
    data[0x14D] = x
    assert gb.looks_like_gb(bytes(data)) and gba.parse_header(bytes(data)).checksum_ok
    assert rom_from_bytes(bytes(data)).platform == "gba"


def test_a_gba_rom_with_a_damaged_checksum_still_loads(sjis_rom):
    data = bytearray(sjis_rom.rom)
    data[0xBD] ^= 0xFF
    assert rom_from_bytes(bytes(data)).platform == "gba"
    # even when the one-byte Game Boy checksum happens to be right: the ROM still begins
    # with the branch every GBA ROM begins with
    data[0x134] = 1
    x = 0
    for b in data[0x134:0x14D]:
        x = (x - b - 1) & 0xFF
    data[0x14D] = x
    assert gb.looks_like_gb(bytes(data)) and gba.starts_with_a_branch(bytes(data))
    rom = rom_from_bytes(bytes(data))
    assert (rom.platform, rom.game_code, rom.japanese) == ("gba", "TSTJ", True)


def test_oversized_dump_is_refused(sjis_rom):
    with pytest.raises(RomError, match="larger than"):
        rom_from_bytes(sjis_rom.rom + bytes(MAX_ROM_SIZE), "big.gba")


def test_load_plain_file(sjis_rom, write_rom):
    assert load_rom(write_rom(sjis_rom.rom)).sha1 == sjis_rom.sha1


def test_load_zip_with_one_rom_reads_it_in_memory(sjis_rom, tmp_path):
    archive = tmp_path / "game.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("inside/Game (Test).GBA", sjis_rom.rom)
        zf.writestr("readme.txt", "hello")
    rom = load_rom(archive)
    assert rom.sha1 == sjis_rom.sha1
    assert rom.source == "game.zip:inside/Game (Test).GBA"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["game.zip"], "nothing is unpacked"


@pytest.mark.parametrize("names", [[], ["a.gba", "b.gba"], ["notes.txt"]])
def test_zip_must_hold_exactly_one_rom(sjis_rom, tmp_path, names):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for n in names:
            zf.writestr(n, sjis_rom.rom)
    with pytest.raises(RomError, match="exactly one ROM"):
        load_rom(archive)


def test_load_zip_with_a_game_boy_color_rom(tmp_path):
    archive = tmp_path / "game.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Game (Test).gbc", gbc_rom())
    rom = load_rom(archive)
    assert (rom.platform, rom.source) == ("gbc", "game.zip:Game (Test).gbc")


def test_zip_that_is_not_a_zip(tmp_path):
    fake = tmp_path / "fake.zip"
    fake.write_bytes(b"not a zip")
    with pytest.raises(RomError, match="not a valid zip"):
        load_rom(fake)


def damaged_zip(rom, damage):
    """A zip holding one ROM, with its bytes damaged the way ``damage`` names."""
    buffer = io.BytesIO()
    method = zipfile.ZIP_DEFLATED if damage == "data" else zipfile.ZIP_STORED
    with zipfile.ZipFile(buffer, "w", method) as zf:
        zf.writestr("game.gba", rom)
    data = bytearray(buffer.getvalue())
    local, central = 0, data.rfind(b"PK\x01\x02")
    if damage == "data":  # garbage in the middle of the compressed stream
        start = 30 + len("game.gba")
        data[start : start + 64] = bytes(range(64))
    elif damage == "password":  # the "encrypted" flag
        data[local + 6] |= 1
        data[central + 8] |= 1
    else:  # a compression method this Python cannot read
        data[local + 8] = data[central + 10] = 99
    return bytes(data)


@pytest.mark.parametrize("damage", ["data", "password", "method"])
def test_a_zip_that_cannot_be_unpacked_is_refused_with_a_message(sjis_rom, tmp_path, damage):
    archive = tmp_path / "game.zip"
    archive.write_bytes(damaged_zip(sjis_rom.rom, damage))
    with pytest.raises(RomError, match=r"^game\.zip: "):
        load_rom(archive)
    with pytest.raises(RomError, match=r"^game\.zip: "):
        load_rom_bytes(archive.read_bytes(), "game.zip")


def test_missing_file(tmp_path):
    with pytest.raises(RomError, match="no such file"):
        load_rom(tmp_path / "missing.gba")


def test_file_that_is_not_a_rom(tmp_path):
    other = tmp_path / "notes.gba"
    other.write_bytes(b"x" * 5000)
    with pytest.raises(RomError, match="not a GBA or Game Boy ROM"):
        load_rom(other)


# ------------------------------------------------------------ uploads in memory


def zip_bytes(*members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in members:
            zf.writestr(name, content)
    return buffer.getvalue()


def test_load_rom_bytes_reads_a_raw_dump(sjis_rom):
    rom = load_rom_bytes(sjis_rom.rom, "game.gba")
    assert rom.sha1 == sjis_rom.sha1 and rom.source == "game.gba"


def test_load_rom_bytes_reads_the_one_rom_in_a_zip(sjis_rom):
    rom = load_rom_bytes(zip_bytes(("a/Game.GBA", sjis_rom.rom), ("readme.txt", "x")), "game.zip")
    assert rom.sha1 == sjis_rom.sha1 and rom.source == "game.zip:a/Game.GBA"


def test_load_rom_bytes_needs_exactly_one_rom_in_a_zip(sjis_rom):
    with pytest.raises(RomError, match="found 0"):
        load_rom_bytes(zip_bytes(("readme.txt", "x")), "game.zip")
    with pytest.raises(RomError, match="found 2"):
        load_rom_bytes(zip_bytes(("a.gba", sjis_rom.rom), ("b.gba", sjis_rom.rom)), "game.zip")


def test_load_rom_bytes_refuses_a_damaged_zip_and_a_non_rom(sjis_rom):
    with pytest.raises(RomError, match="not a valid zip"):
        load_rom_bytes(b"PK truncated", "bad.zip")
    with pytest.raises(RomError, match="not a GBA or Game Boy ROM"):
        load_rom_bytes(b"hello", "notes.txt")


def test_a_zip_bomb_is_read_with_a_bound(sjis_rom):
    big = zip_bytes(("big.gba", bytes(MAX_ROM_SIZE + 10)))
    with pytest.raises(RomError, match="larger than"):
        load_rom_bytes(big, "big.zip")
