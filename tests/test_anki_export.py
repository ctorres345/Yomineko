import json
import sqlite3
import zipfile
from contextlib import closing

import pytest
from support.study import make_script, make_words

from yomineko.export.anki import (
    CSS,
    MODEL_VERSION,
    SENTENCE_MODEL,
    TERM_MODEL,
    WORD_MODEL,
    jisho,
    stable_id,
    write_apkg,
)
from yomineko.export.sentences import select_sentences
from yomineko.export.study import build_study

TIMESTAMP = 1_700_000_000.0


def study_of(script=None, **kw):
    script = script or make_script()
    return build_study(script, select_sentences(script), min_freq=4, **kw)


def read_deck(apkg, tmp_path):
    """(notes, models, decks) from the collection inside an .apkg."""
    with zipfile.ZipFile(apkg) as z:
        z.extract("collection.anki2", tmp_path)
    with closing(sqlite3.connect(tmp_path / "collection.anki2")) as db:
        notes = db.execute("select guid, mid, flds, tags from notes order by guid").fetchall()
        models, decks = db.execute("select models, decks from col").fetchone()
    return notes, json.loads(models), json.loads(decks)


@pytest.fixture
def deck(tmp_path):
    dest = tmp_path / "out" / "demo.apkg"
    count = write_apkg(study_of(), dest, timestamp=TIMESTAMP)
    return dest, count, read_deck(dest, tmp_path)


def test_the_deck_holds_a_note_per_word_sentence_and_term(deck):
    dest, count, (notes, models, _) = deck
    assert dest.is_file() and count == len(notes) == 60 + 5 + 1
    assert {m["name"] for m in models.values()} == {
        "yomineko Word",
        "yomineko Sentence",
        "yomineko Term",
    }


def test_decks_are_named_under_the_game_and_credit_the_dictionary(deck):
    _, _, (_, _, decks) = deck
    names = sorted(d["name"] for d in decks.values() if d["name"] != "Default")
    assert names == ["Demo Game::1 Words", "Demo Game::2 Sentences", "Demo Game::3 Terms"]
    assert all("CC BY-SA" in d["desc"] for d in decks.values() if d["name"] != "Default")


def test_a_chosen_deck_name_replaces_the_title(tmp_path):
    dest = tmp_path / "d.apkg"
    write_apkg(study_of(), dest, deck_name="My::Deck", timestamp=TIMESTAMP)
    _, _, decks = read_deck(dest, tmp_path)
    assert "My:Deck::1 Words" in {d["name"] for d in decks.values()}


def test_note_fields_are_filled_and_escaped(deck):
    _, _, (notes, models, _) = deck
    by_model = {models[str(mid)]["name"]: [] for _, mid, _, _ in notes}
    for _, mid, flds, _ in notes:
        by_model[models[str(mid)]["name"]].append(flds.split("\x1f"))
    word = next(f for f in by_model["yomineko Word"] if f[7] == "1")
    assert word[:3] == ["こと", "事", "こと"]
    assert "<li>meaning 1; extra 1</li>" in word[3] and "ようこそ" in word[4]
    assert "jisho.org/search/%E4%BA%8B" in word[6]
    sentence = next(f for f in by_model["yomineko Sentence"] if f[4] == "08000003")
    assert sentence[0] == "そのほんは　とてもおもしろい。" and "<b>ことば44</b>" in sentence[2]
    assert by_model["yomineko Term"] == [
        [
            "ボタン",
            "button",
            "item",
            '<a href="https://jisho.org/search/%E3%83%9C%E3%82%BF%E3%83%B3">Jisho</a>',
        ]
    ]


def test_html_in_game_text_is_escaped(tmp_path):
    from support.study import make_line

    script = make_script()
    script = script.model_copy(
        update={"lines": [make_line(1, "<b>きょう</b>は　いいてんきですね。", [2, 50])]}
    )
    dest = tmp_path / "e.apkg"
    write_apkg(study_of(script), dest, timestamp=TIMESTAMP)
    flds = [n[2] for n in read_deck(dest, tmp_path)[0] if "08000001" in n[2]]
    assert flds and "&lt;b&gt;きょう&lt;/b&gt;" in flds[0] and "<b>きょう" not in flds[0]


def test_every_card_footer_credits_jmdict():
    for model in (WORD_MODEL, SENTENCE_MODEL, TERM_MODEL):
        assert "JMdict (EDRDG, CC BY-SA 4.0)" in model.templates[0]["afmt"]
    assert "night" in CSS  # dark mode is handled


def test_tags_name_the_game_and_the_kind(deck):
    _, _, (notes, _, _) = deck
    tags = [set(n[3].split()) for n in notes]
    assert all({"yomineko", "demo"} <= t for t in tags)
    assert sum(1 for t in tags if "word" in t) == 60
    assert sum(1 for t in tags if "sentence" in t) == 5
    assert [t for t in tags if "term" in t] == [{"yomineko", "demo", "term", "item"}]


def test_ids_are_stable_across_builds_and_data_changes(tmp_path):
    first = tmp_path / "a.apkg"
    write_apkg(study_of(), first, timestamp=TIMESTAMP)
    changed = make_script(
        words=[w.model_copy(update={"freq": w.freq + 7}) for w in make_words()],
    )
    second = tmp_path / "b.apkg"
    write_apkg(study_of(changed), second, timestamp=TIMESTAMP)
    (n1, m1, d1), (n2, m2, d2) = read_deck(first, tmp_path), read_deck(second, tmp_path)
    assert [n[0] for n in n1] == [n[0] for n in n2], "GUIDs decide whether a re-import updates"
    assert set(m1) == set(m2) and set(d1) == set(d2)


def test_the_same_data_builds_the_same_deck(tmp_path):
    a, b = tmp_path / "a.apkg", tmp_path / "b.apkg"
    write_apkg(study_of(), a, timestamp=TIMESTAMP)
    write_apkg(study_of(), b, timestamp=TIMESTAMP)
    assert read_deck(a, tmp_path)[0] == read_deck(b, tmp_path)[0]


def test_games_and_decks_do_not_share_deck_ids(tmp_path):
    other = make_script(
        game=make_script().game.model_copy(update={"profile_id": "other", "title": "Other"})
    )
    a, b = tmp_path / "a.apkg", tmp_path / "b.apkg"
    write_apkg(study_of(), a, timestamp=TIMESTAMP)
    write_apkg(study_of(other), b, timestamp=TIMESTAMP)
    (n1, m1, d1), (n2, m2, d2) = read_deck(a, tmp_path), read_deck(b, tmp_path)
    assert set(d1) - {"1"} != set(d2) - {"1"}
    assert set(m1) == set(m2), "note types are shared between games"
    assert {n[0] for n in n1}.isdisjoint({n[0] for n in n2})


def test_only_the_requested_decks_are_written(tmp_path):
    dest = tmp_path / "t.apkg"
    count = write_apkg(study_of(decks=["terms"]), dest, timestamp=TIMESTAMP)
    names = {d["name"] for d in read_deck(dest, tmp_path)[2].values()}
    assert count == 1 and "Demo Game::3 Terms" in names and "Demo Game::1 Words" not in names


def test_stable_id_is_deterministic_and_in_range():
    a = stable_id("x", "y")
    assert a == stable_id("x", "y") != stable_id("x", "z")
    assert 1 << 30 <= a < 1 << 31
    assert stable_id("yomineko", "model", "word", str(MODEL_VERSION)) == WORD_MODEL.model_id


def test_jisho_link_encodes_the_query_and_drops_the_name_placeholder():
    assert (
        jisho("〇〇　ねこ & いぬ")
        == '<a href="https://jisho.org/search/%E3%81%AD%E3%81%93%20%26%20%E3%81%84%E3%81%AC">Jisho</a>'
    )


def test_the_card_shows_the_stand_in_name_but_the_jisho_link_does_not(tmp_path):
    from support.study import make_line

    script = make_script()
    script = script.model_copy(
        update={"lines": [make_line(1, "〇〇は　あたらしいまちへ。", [1, 2])]}
    )
    dest = tmp_path / "n.apkg"
    write_apkg(study_of(script), dest, timestamp=TIMESTAMP)
    fields = next(
        n[2].split("\x1f") for n in read_deck(dest, tmp_path)[0] if n[2].endswith("08000001")
    )
    assert fields[0] == "ハルは　あたらしいまちへ。"
    assert "%E3%83%8F" not in fields[3]  # no ハ from the stand-in in the link
    assert "%E3%81%AF" in fields[3]  # は
