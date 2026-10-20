import csv
import io
import json

import pytest

from yomineko.export.words_export import (
    COLUMNS,
    NotAnalysedError,
    render_words_csv,
    render_words_json,
    select_words,
)
from yomineko.model import DictionarySource, GameInfo, Line, Script, Word

SHA1 = "0123456789abcdef0123456789abcdef01234567"


def make_script(with_credit=True):
    words = [
        Word(
            jmdict_id=1,
            written="事",
            kana="こと",
            kanji="事",
            pos="名詞",
            common=True,
            meanings=["thing; matter", "fact"],
            freq=10,
            examples=["08000001", "08000002"],
            jmdict_rank=2,
        ),
        Word(jmdict_id=2, written="かえる", kana="かえる", kanji="蛙", freq=3, pos="名詞"),
        Word(jmdict_id=3, written="琴", kana="こと", kanji="琴", freq=1, pos="名詞"),
    ]
    return Script(
        generator="t",
        game=GameInfo(profile_id="p", title="t", platform="gba", rom_sha1=SHA1),
        lines=[Line(id="08000001", address=1, bank="b", raw="x", text="x", kind="dialogue")],
        words=words,
        dictionary=DictionarySource(date="2026-10-03", source="https://x", credit="THE, CREDIT")
        if with_credit
        else None,
    )


def parse(text):
    return [r for r in csv.reader(io.StringIO(text)) if r and not r[0].startswith("#")]


def test_csv_columns_and_values():
    text, count = render_words_csv(make_script())
    rows = parse(text)
    assert tuple(rows[0]) == COLUMNS and count == 3 and len(rows) == 4
    assert rows[1] == [
        "1",
        "事",
        "こと",
        "事",
        "名詞",
        "10",
        "yes",
        "1",
        "thing; matter | fact",
        "08000001 08000002",
        "2",
    ]
    assert rows[2][6] == "no" and rows[2][-1] == ""  # a word analysed before schema 4


def test_min_freq_filters_but_ranks_stay_put():
    rows = parse(render_words_csv(make_script(), min_freq=3)[0])
    assert [r[0] for r in rows[1:]] == ["1", "2"]
    assert select_words(make_script(), min_freq=4)[0][0] == 1
    assert [rank for rank, _ in select_words(make_script(), min_freq=2)] == [1, 2]


def test_the_file_ends_with_a_credit_comment_for_anki():
    text, _ = render_words_csv(make_script())
    assert text.endswith("# THE, CREDIT\n")
    assert "\r" not in text


def test_no_credit_line_without_a_dictionary():
    text, _ = render_words_csv(make_script(with_credit=False))
    assert "#" not in text


def test_an_unanalysed_script_says_what_to_do():
    script = make_script().model_copy(update={"words": []})
    with pytest.raises(NotAnalysedError, match="yomineko analyze"):
        render_words_csv(script)
    with pytest.raises(NotAnalysedError):
        render_words_json(script)


def test_json_holds_only_the_selected_words_and_the_credit():
    text, count = render_words_json(make_script(), min_freq=3)
    assert count == 2
    data = json.loads(text)
    assert data["lines"] == [] and data["terms"] == []
    assert [w["jmdict_id"] for w in data["words"]] == [1, 2]
    assert data["dictionary"]["credit"] == "THE, CREDIT"
    assert Script.model_validate(data).schema_version == 4
    assert "事" in text and "\\u" not in text
