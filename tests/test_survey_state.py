"""Save-state reading: containers, the I/O block, the text-tile rectangle and its source."""

import struct

import pytest
from support.synthsurvey import (
    IO_AT,
    build_state,
    wrap_png_state,
    wrap_rastate,
    wrap_rzip,
)

from yomineko.survey import state
from yomineko.survey.state import StateError


@pytest.fixture(scope="module")
def parts():
    return build_state()


WRAPPERS = {
    "bare": lambda s: s,
    "rastate": wrap_rastate,
    "rzip": lambda s: wrap_rzip(wrap_rastate(s)),
    "png": wrap_png_state,
}


@pytest.mark.parametrize("kind", WRAPPERS)
def test_every_container_unwraps_to_the_same_state(parts, kind):
    assert state.unwrap_state(WRAPPERS[kind](parts.state)) == parts.state


def test_the_text_rectangle_is_found_and_traced(parts):
    found = state.analyze_state(wrap_rastate(parts.state), parts.rom)
    assert (found.io_offset, found.dispcnt, found.mode) == (IO_AT, 0x0100, 0)
    assert [(x.index, x.char_base, x.screen_base, x.colors8) for x in found.layers] == [
        (0, 0x8000, 0x5000, False)
    ]
    text = found.text
    assert text is not None
    assert (text.layer, text.column, text.row) == (0, 2, 4)
    assert (text.width, text.height, text.first_tile) == (6, 3, 100)
    assert text.tiles == 18
    assert (text.in_rom_exact, text.in_rom_shape) == (1, 2)
    assert text.in_ewram == 18
    assert text.ewram_mirror == parts.mirror


def test_tiles_that_are_only_in_vram_have_no_mirror():
    parts = build_state(mirrored=False)
    text = state.analyze_state(parts.state, parts.rom).text
    assert text is not None
    assert (text.in_ewram, text.ewram_mirror) == (0, None)


def test_no_rectangle_when_the_map_is_empty():
    parts = build_state(text=False)
    assert state.analyze_state(parts.state, parts.rom).text is None


def test_an_io_block_away_from_the_usual_place_is_searched_for():
    parts = build_state(io_at=0x600)
    found = state.analyze_state(parts.state, parts.rom)
    assert found.io_offset == 0x600
    assert found.text is not None and found.text.first_tile == 100


def test_a_state_without_video_registers_is_refused():
    with pytest.raises(StateError, match="I/O"):
        state.analyze_state(bytes(0x70000), b"")


@pytest.mark.parametrize(
    ("blob", "message"),
    [
        (b"#RZIPv\x01#" + struct.pack("<IQ", 4096, 100) + b"\x05\x00\x00\x00junk!", "damaged"),
        (b"#RZIPv\x01#" + struct.pack("<IQ", 4096, 100), "ends early"),
        (b"#RZIPv\x01#", "damaged RetroArch"),
        (b"RASTATE\x01" + b"CHEV" + (3).to_bytes(4, "little") + b"abc\x00\x00\x00\x00\x00", "MEM"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00IEND\x00\x00\x00\x00", "no mGBA state"),
    ],
)
def test_damaged_containers_are_refused(blob, message):
    with pytest.raises(StateError, match=message):
        state.unwrap_state(blob)


def test_a_damaged_png_state_chunk_is_refused():
    body = b"not zlib"
    png = b"\x89PNG\r\n\x1a\n" + len(body).to_bytes(4, "big") + b"gbAs" + body + bytes(4)
    with pytest.raises(StateError, match="damaged mGBA"):
        state.unwrap_state(png)


def test_a_tile_cut_short_by_the_end_of_vram_is_not_looked_up():
    layer = state.Layer(0, 0, 0, 0, False, 0)
    one = b"\x01"
    vram = one * 32 + one * 5  # the second tile is only 5 bytes long
    found = state._match_tiles(layer, (0, 0, 2, 1, 0), vram, one * 5 + b"zzz", b"", b"")
    assert (found.tiles, found.in_rom_exact) == (1, 0)
