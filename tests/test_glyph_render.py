"""The glyph table tools: code ranges, message patching, pictures, sheets and the table writer."""

import json

import pytest
from glyph_render import __main__ as cli
from glyph_render import render, sheets, table

from yomineko.core.encodings.table8 import Table8Codec


def test_codes_are_bytes_or_lead_and_index_pairs():
    assert render.parse_codes("00-02") == [b"\x00", b"\x01", b"\x02"]
    assert render.parse_codes("FA00-FA01,41") == [b"\xfa\x00", b"\xfa\x01", b"A"]
    assert len(render.parse_codes("00-F9,FA00-FEFF")) == 250 + 5 * 256


@pytest.mark.parametrize("bad", ["0-9", "00-FF00", "ZZ"])
def test_a_bad_range_is_refused(bad):
    with pytest.raises(ValueError):
        render.parse_codes(bad)


def test_the_message_at_the_pointer_is_replaced_by_the_template():
    rom = bytes(range(32))
    out = render.patch_message(rom, 4, "FF03{code}FF0C", b"\xfa\x42")
    assert out[4:10] == bytes.fromhex("FF03FA42FF0C")
    assert out[:4] == rom[:4] and out[10:] == rom[10:] and len(out) == len(rom)


def test_a_message_that_does_not_fit_is_refused():
    with pytest.raises(ValueError, match="does not fit"):
        render.patch_message(bytes(8), 6, "FFFFFF{code}", b"\x01")


def test_a_picture_is_cropped_to_the_columns_with_ink_and_keeps_every_row():
    window = [
        [0, 0, 0, 0, 0],
        [0, 200, 0, 200, 0],
        [0, 0, 200, 0, 0],
        [0, 0, 0, 0, 0],
    ]
    assert render.to_bitmap(window) == ["...", "#.#", ".#.", "..."]


def test_a_blank_window_has_no_picture():
    assert render.to_bitmap([[0, 0], [0, 10]]) == []
    assert render.to_bitmap([]) == []


def test_glyphs_are_saved_and_grouped_into_sheets(tmp_path):
    glyphs = {f"{b:02x}": ["#.", ".#"] for b in range(5)} | {"05": []}
    path = tmp_path / "g" / "glyphs.json"
    render.save_glyphs(glyphs, path)
    assert json.loads(path.read_text(encoding="utf-8")) == glyphs
    assert sheets.sheet_keys(sheets.load_glyphs(path), per_sheet=2) == [
        ["00", "01"],
        ["02", "03"],
        ["04"],
    ]  # the blank glyph has no place on a sheet


def test_a_sheet_is_a_picture_with_one_cell_per_glyph(tmp_path):
    pytest.importorskip("PIL")
    glyphs = {"41": ["#.", ".#"], "42": ["##", "##"]}
    image = sheets.make_sheet(glyphs, ["41", "42"], per_row=2, scale=2)
    assert image.size == (2 * (sheets.CELL_W * 2 + 4), sheets.CELL_H * 2 + 16)
    path = tmp_path / "glyphs.json"
    render.save_glyphs(glyphs, path)
    written = sheets.write_sheets(path, tmp_path / "out")
    assert [p.suffix for p in written] == [".png"] and written[0].is_file()


def test_a_transcription_becomes_a_table_the_codec_can_read(tmp_path):
    source = tmp_path / "t.tsv"
    source.write_text(
        "# kana and one kanji\n41\tあ\n42\tい\nFA10\t猫\nFA11\tあ\n", encoding="utf-8"
    )
    aliases = table.write_table(table.read_transcription(source), tmp_path / "x.tbl", "My game")
    assert aliases == [("FA11", "あ")]  # drawn by 41 already: left for a `plain` rule
    written = (tmp_path / "x.tbl").read_text(encoding="utf-8")
    assert written.startswith("# My game\n41=あ\n42=い\nFA10=猫")
    codec = Table8Codec(tmp_path / "x.tbl")
    assert len(codec) == 3 and codec.encode("あい猫") == bytes.fromhex("4142FA10")


@pytest.mark.parametrize(
    "line",
    ["4\tあ", "41 あ", "41\t", "ZZ\tあ", "41\tあ\n41\tい"],
    ids=["short", "tab", "empty", "hex", "twice"],
)
def test_a_bad_transcription_line_is_refused(tmp_path, line):
    path = tmp_path / "t.tsv"
    path.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(table.TranscriptionError):
        table.read_transcription(path)


def test_the_table_and_sheets_commands_run(tmp_path, capsys):
    source = tmp_path / "t.tsv"
    source.write_text("41\tあ\n", encoding="utf-8")
    assert cli.main(["table", str(source), "--out", str(tmp_path / "x.tbl")]) == 0
    assert "wrote" in capsys.readouterr().out
    pytest.importorskip("PIL")
    glyphs = tmp_path / "g.json"
    render.save_glyphs({"41": ["#"]}, glyphs)
    assert cli.main(["sheets", str(glyphs), "--out", str(tmp_path / "s")]) == 0
    assert "1 sheets" in capsys.readouterr().out
