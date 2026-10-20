"""The survey's detectors, each against the layout the synthetic survey ROM puts it in."""

import struct
import zlib

import pytest
from support.synthrom import SynthRom, lcg_bytes, lz77_compress
from support.synthsurvey import (
    RELATIVE_WORD,
    build_survey_rom,
    huffman_compress,
    rle_compress,
    token_block,
)

from yomineko.core.compression.lz77 import decompress
from yomineko.errors import YominekoError
from yomineko.survey import bios, extent, fonts, plaintext, relative, tables, tokens
from yomineko.survey._words import merge_ranges, u16s, u32s
from yomineko.survey.fonts import FontCandidate
from yomineko.survey.png import encode_png, tile_sheet_png
from yomineko.survey.tokens import TokenRange


@pytest.fixture(scope="module")
def survey_rom():
    return build_survey_rom()


@pytest.fixture(scope="module")
def data(survey_rom):
    return survey_rom[0]


@pytest.fixture(scope="module")
def manifest(survey_rom):
    return survey_rom[1]


# --------------------------------------------------------------- words


def test_word_views_are_little_endian_and_ignore_a_trailing_partial_word():
    blob = bytes([1, 0, 2, 0, 3, 0, 9])
    assert list(u16s(blob)) == [1, 2, 3]
    assert list(u32s(blob)) == [0x20001]
    assert list(u16s(blob, 2, count=1)) == [2]


def test_merge_ranges_joins_adjacent_windows_only():
    assert merge_ranges([0, 10, 20, 40], 10) == [(0, 30), (40, 50)]
    assert merge_ranges([], 10) == []


# ------------------------------------------------------------- extent


def test_entropy_of_constant_and_uniform_bytes():
    assert extent.entropy(b"\x00" * 100) == 0
    assert extent.entropy(bytes(range(256)) * 4) == pytest.approx(8.0)


def test_extent_finds_the_fill_and_the_trailing_fill(data, manifest):
    found = extent.measure_extent(data)
    assert extent.FillRange(*manifest.fill, 0xFF) in found.fills
    assert found.tail_fill_start == len(data.rstrip(b"\x00"))
    assert len(found.entropy) == 1 and 0 < found.entropy[0] < 8


def test_extent_without_a_trailing_fill():
    found = extent.measure_extent(bytes(range(256)) * 32)
    assert found.tail_fill_start is None
    assert found.fills == []


# --------------------------------------------------------------- bios


def test_find_lz77_lists_the_streams(data, manifest):
    streams = bios.find_lz77(data)
    assert [s.offset for s in streams] == sorted([*manifest.lz77.values(), manifest.tokens_lz77])
    pattern = next(s for s in streams if s.offset == manifest.lz77["pattern"])
    assert pattern.size == 1024
    assert pattern.packed == len(lz77_compress(decompress(data, pattern.offset)))


def test_find_lz77_ignores_short_and_broken_headers():
    blob = bytearray(0x200)
    blob[0x100:0x104] = bytes([0x10, 0x00, 0x01, 0x00])  # 256 bytes declared, nothing valid
    blob[0x140:0x144] = bytes([0x10, 0x04, 0x00, 0x00])  # under the 256-byte floor
    assert bios.find_lz77(bytes(blob)) == []


@pytest.mark.parametrize("raw", [b"A" * 40, bytes(range(60)), b"ab" * 3 + b"c" * 200, b"xyzzy"])
def test_rle_round_trip(raw):
    assert bios.decode_rle(rle_compress(raw), 0) == raw


def test_rle_rejects_truncation_and_other_headers():
    packed = rle_compress(b"A" * 40 + bytes(range(50)))
    assert bios.decode_rle(packed[:-3], 0) is None
    assert bios.decode_rle(b"\x31" + packed[1:], 0) is None
    assert bios.decode_rle(packed[:3], 0) is None
    assert bios.decode_rle(b"\x30\x05\x00\x00\x80", 0) is None  # run flag without its byte


@pytest.mark.parametrize("bits", [8, 4])
def test_huffman_round_trip(bits):
    raw = b"abracadabra, abracadabra! " * 5
    if bits == 4:
        raw = bytes(0x10 * (i % 3) + (i * 7) % 13 for i in range(120))
    assert bios.decode_huffman(huffman_compress(raw, bits), 0) == raw


def test_huffman_rejects_truncation_bad_headers_and_bad_trees():
    packed = huffman_compress(b"abracadabra" * 20)
    assert bios.decode_huffman(packed[:-8], 0) is None
    assert bios.decode_huffman(b"\x25" + packed[1:], 0) is None  # 5-bit data does not exist
    assert bios.decode_huffman(b"\x10" + packed[1:], 0) is None
    assert bios.decode_huffman(packed[:6], 0) is None
    broken = bytearray(packed)
    broken[5] = 0xFF  # the root now points past the tree
    assert bios.decode_huffman(bytes(broken), 0) is None
    assert bios.decode_huffman(packed[:5] + bytes([200]) + packed[6:], 0) is None  # table too big


def test_four_bit_huffman_rejects_a_leaf_over_fifteen():
    packed = bytearray(huffman_compress(bytes([0x21, 0x12] * 40), 4))
    tree = 5  # the size byte, then the root
    leaf = tree + 2
    packed[leaf] = 0x90  # not a nibble
    assert bios.decode_huffman(bytes(packed), 0) is None


def test_pointer_targets_are_aligned_and_in_range(data):
    targets = bios.pointer_targets(data)
    assert targets == sorted(set(targets))
    assert 0x3000 in targets and 0x5000 in targets
    assert all(t % 4 == 0 and t < len(data) for t in targets)


def test_other_streams_at_pointer_targets(data, manifest):
    huffman, rle = bios.check_pointer_targets(data, bios.pointer_targets(data))
    assert (huffman.kind, huffman.headers, huffman.decoded) == ("huffman", 1, 1)
    assert (rle.kind, rle.headers, rle.decoded) == ("rle", 1, 1)
    assert huffman.examples == [(manifest.huffman, 312)]
    assert rle.examples == [(manifest.rle, 179)]


def test_random_looking_decodes_do_not_count():
    noise = bytes(b for b, _ in zip(lcg_bytes(9), range(2000), strict=False))
    rom = bytearray(0x1000)
    rom[0:4] = struct.pack("<I", 0x08000040)
    rom[0x40:0x44] = b"\x30\xe8\x03\x00"  # run-length header, 1000 bytes
    rom[0x44 : 0x44 + 2000] = noise
    _, rle = bios.check_pointer_targets(bytes(rom), bios.pointer_targets(bytes(rom)))
    assert (rle.headers, rle.decoded) == (1, 0)


# ---------------------------------------------------------- plain text


def test_plain_text_counts_runs_and_neighbours(data, manifest):
    found = plaintext.find_plain_text(data)
    assert found.hiragana_runs == 3
    assert found.katakana_runs == 1
    assert found.ascii_neighbours == 1
    assert [a for a, _ in found.examples] == manifest.plain
    assert all(n == 18 for _, n in found.examples)


def test_plain_text_needs_four_characters():
    found = plaintext.find_plain_text(b"\x82\xa0\x82\xa2\x82\xa4 \x83\x41\x83\x42")
    assert (found.hiragana_runs, found.katakana_runs) == (0, 0)


# ------------------------------------------------------------- tables


def test_pointer_runs_and_their_targets(data, manifest):
    first, second = tables.find_pointer_runs(data)
    assert (first.offset, first.count, first.ascending) == (manifest.pointer_table, 40, False)
    assert first.labels == dict.fromkeys(manifest.pointer_labels, 1)
    assert (second.offset, second.count, second.ascending) == (manifest.ascending_table, 32, True)
    assert second.labels == {"other": 8}


def test_label_target_names_each_kind(data, manifest):
    for label, offset in manifest.pointer_labels.items():
        assert tables.label_target(data, offset) == label


def test_label_target_with_too_little_data():
    assert tables.label_target(b"\x01\x02", 0) == "other"
    assert tables.label_target(bytes(100), 90) == "other"


def test_offset_runs_and_whether_they_open_their_own_block(data, manifest):
    small, wide = tables.find_offset_runs(data)
    assert (small.offset, small.width, small.count, small.first) == (
        manifest.offset_u16,
        2,
        130,
        260,
    )
    assert small.opens_block
    assert (wide.offset, wide.width, wide.count, wide.first) == (manifest.offset_u32, 4, 130, 5000)
    assert not wide.opens_block


# -------------------------------------------------------------- fonts


def test_font_candidate_range_and_values(data, manifest):
    assert fonts.find_font_candidates(data) == [FontCandidate(*manifest.font, [0, 3, 0x30, 0x33])]


def test_font_geometry_finds_the_glyph_cell(data, manifest):
    geometry = fonts.estimate_geometry(data, *manifest.font)
    assert geometry is not None
    assert (geometry.unit, geometry.blank_share) == (128, 0.25)
    assert geometry.row_stride in fonts.STRIDES


def test_font_geometry_needs_enough_data():
    assert fonts.estimate_geometry(bytes(100), 0, 100) is None


def test_candidate_sheets_are_png_files(data, manifest):
    candidates = fonts.find_font_candidates(data)
    sheets = fonts.candidate_sheets(data, candidates)
    assert list(sheets) == ["font-00A000.png"]
    assert sheets["font-00A000.png"].startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize(("bpp", "tile_bytes"), [(1, 8), (4, 32), (8, 64)])
def test_tile_sheet_dimensions(bpp, tile_bytes):
    png = tile_sheet_png(bytes(range(256)) * 2, bpp, tiles_wide=4)
    width, height = struct.unpack(">II", png[16:24])
    tiles = 512 // tile_bytes
    assert (width, height) == (32, -(-tiles // 4) * 8)
    idat = png.index(b"IDAT")
    (size,) = struct.unpack(">I", png[idat - 4 : idat])
    rows = zlib.decompress(png[idat + 4 : idat + 4 + size])
    assert len(rows) == height * (width + 1)


def test_tile_sheet_draws_ink_dark_on_white():
    one_tile = bytes([0xFF] + [0] * 7)  # first row all ink, 1 bit per pixel
    png = tile_sheet_png(one_tile, 1, tiles_wide=1)
    idat = png.index(b"IDAT")
    (size,) = struct.unpack(">I", png[idat - 4 : idat])
    rows = zlib.decompress(png[idat + 4 : idat + 4 + size])
    assert rows[1:9] == b"\x00" * 8  # ink
    assert rows[10:18] == b"\xff" * 8  # background


def test_png_errors():
    with pytest.raises(YominekoError, match="does not match"):
        encode_png(2, 2, b"abc")
    with pytest.raises(YominekoError, match="1, 4 or 8"):
        tile_sheet_png(bytes(64), 3)
    with pytest.raises(YominekoError, match="one tile"):
        tile_sheet_png(bytes(4), 4)


# ------------------------------------------------------------- tokens


def test_token_streams_in_the_raw_image_and_in_a_lz77_block(data, manifest):
    found = tokens.find_token_streams(data, bios.find_lz77(data))
    assert found == [
        TokenRange("rom", manifest.tokens_raw, manifest.tokens_raw + 0x2000),
        TokenRange(f"lz77@0x{manifest.tokens_lz77:X}", 0, 0x2000),
    ]


def test_token_window_profile():
    assert tokens.is_token_window(token_block(3, 4096))
    assert not tokens.is_token_window(bytes(8192))  # all zeros
    assert not tokens.is_token_window(b"")
    assert not tokens.is_token_window(bytes(range(256)) * 32)  # flat: no common values


def test_short_decoded_blocks_are_not_scanned():
    rom = SynthRom("TINY", "TINY", size=0x4000)
    rom.put(0x100, lz77_compress(token_block(4, 1000), literals_only=True))  # 2000 bytes
    blob = rom.finish()[0]
    streams = bios.find_lz77(blob)
    assert len(streams) == 1
    assert tokens.find_token_streams(blob, streams) == []


# ----------------------------------------------------------- relative


def test_kana_indices_fold_voicing_small_kana_and_katakana():
    assert relative.kana_indices(RELATIVE_WORD) == [23, 9, 5, 12, 32]
    assert relative.kana_indices("ネコガスム") == [23, 9, 5, 12, 32]
    assert relative.kana_indices("ちょこ") == [16, 37, 9]


@pytest.mark.parametrize("word", ["ねこ", "猫がすむ", "あー　い", ""])
def test_unusable_words_are_refused(word):
    with pytest.raises(YominekoError):
        relative.kana_indices(word)


def test_relative_search_finds_one_and_two_byte_tables(data, manifest):
    hits = relative.relative_search(data, RELATIVE_WORD)
    assert (hits.kana, hits.hits8, hits.hits16) == (5, 1, 1)
    assert hits.blocks8 == [(0, 1)] and hits.blocks16 == [(0, 1)]
    assert hits.expected8 < 1 and hits.expected16 < 1


def test_relative_search_reports_nothing_for_an_absent_word():
    hits = relative.relative_search(bytes(range(0, 256, 3)) * 8, "あきさたな")
    assert (hits.hits8, hits.hits16) == (0, 0)
    assert hits.blocks8 == []
