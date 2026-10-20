import csv
import io
import json

from yomineko.export import csv_export
from yomineko.export.json_export import render_json
from yomineko.export.select import select_lines
from yomineko.model import GameInfo, Line, Script, Term, Translation

SHA1 = "0123456789abcdef0123456789abcdef01234567"


def line(address, text, kind="dialogue", duplicate_of=None, translation=None, raw=None):
    return Line(
        id=f"{0x08000000 + address:08X}",
        address=address,
        bank="bank_000000",
        raw=raw if raw is not None else text,
        text=text,
        kind=kind,
        duplicate_of=duplicate_of,
        translation=translation,
    )


def make_script() -> Script:
    return Script(
        generator="test",
        game=GameInfo(profile_id="demo", title="Demo", platform="gba", rom_sha1=SHA1),
        lines=[
            line(0x300, "さん。"),
            line(0x100, "おちゃ", kind="term"),
            line(0x200, "おちゃ", kind="term", duplicate_of="08000100"),
            line(0x400, "", raw="#CG#R"),  # control codes only: no readable text
        ],
        terms=[Term(jp="おちゃ", category="item", index=0, line_id="08000100")],
    )


def addresses(lines):
    return [x.address for x in lines]


# ------------------------------------------------------------------ selection


def test_default_selection_is_unique_readable_lines_in_rom_order():
    assert addresses(select_lines(make_script())) == [0x100, 0x300]


def test_all_keeps_repeats_and_empty_lines():
    assert addresses(select_lines(make_script(), include_all=True)) == [0x100, 0x200, 0x300, 0x400]


def test_kind_filter():
    assert addresses(select_lines(make_script(), kind="term")) == [0x100]
    assert addresses(select_lines(make_script(), kind="dialogue")) == [0x300]
    assert addresses(select_lines(make_script(), include_all=True, kind="term")) == [0x100, 0x200]


# ------------------------------------------------------------------------ CSV


def parse_csv(text):
    return list(csv.reader(io.StringIO(text)))


def test_csv_has_the_documented_columns_and_formats():
    text, count = csv_export.render_csv(make_script())
    rows = parse_csv(text)
    assert tuple(rows[0]) == csv_export.COLUMNS
    assert count == 2 and len(rows) == 3
    assert rows[1] == ["08000100", "0x100", "bank_000000", "term", "おちゃ", "おちゃ", "", ""]


def test_csv_uses_unix_line_endings_and_excel_friendly_encoding():
    text, _ = csv_export.render_csv(make_script())
    assert "\r" not in text
    assert csv_export.ENCODING == "utf-8-sig"
    assert text.encode(csv_export.ENCODING).startswith(b"\xef\xbb\xbf")


def test_csv_includes_translations_with_their_source():
    script = make_script()
    script.lines[0] = line(
        0x300, "さん。", translation=Translation(text="Three.", source="reviewed")
    )
    rows = parse_csv(csv_export.render_csv(script)[0])
    row = next(r for r in rows if r[1] == "0x300")
    assert row[-2:] == ["Three.", "reviewed"]


def test_csv_quotes_commas_quotes_and_newlines_so_they_roundtrip():
    tricky = 'a,b "quoted"\nsecond line'
    script = make_script()
    script.lines = [line(0x100, tricky, raw=tricky)]
    rows = parse_csv(csv_export.render_csv(script)[0])
    assert rows[1][4] == tricky and rows[1][5] == tricky


# ----------------------------------------------------------------------- JSON


def test_json_export_is_a_valid_narrowed_script():
    text, count = render_json(make_script(), kind="term")
    assert count == 1
    data = json.loads(text)
    assert data["schema_version"] == 4
    assert [x["address"] for x in data["lines"]] == [0x100]
    assert len(data["terms"]) == 1, "terms are kept as they are"
    assert Script.model_validate(data).lines[0].text == "おちゃ"


def test_json_export_keeps_japanese_readable():
    text, _ = render_json(make_script())
    assert "おちゃ" in text and "\\u" not in text


def test_json_export_does_not_change_the_original_script():
    script = make_script()
    render_json(script, kind="term")
    assert len(script.lines) == 4
