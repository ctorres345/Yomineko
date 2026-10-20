"""The game check tool: reading a deck back, the sentence figures and the verdict."""

import os
import re

import game_check
import pytest
from game_check import (
    Scorecard,
    check_game,
    judge,
    read_deck,
    render,
    sentence_figures,
)
from support.study import make_line, make_script

from yomineko.export.sentences import select_sentences
from yomineko.pipeline.exporting import ExportRequest, build_export

JAPANESE = re.compile("[぀-ヿ一-鿿]")


def good_card(**kw):
    base = {
        "profile_id": "demo",
        "title": "Demo",
        "verified": True,
        "words": 1000,
        "cards": {"1 Words": 800, "2 Sentences": 1000, "3 Terms": 100},
        "credit_on_cards": True,
        "sentences": 1000,
        "median_length": 20,
        "unclosed": 10,
    }
    base.update(kw)
    return Scorecard(**base)


def test_a_deck_is_read_back_card_by_card():
    deck = build_export(make_script(), ExportRequest(format="anki"))
    reading = read_deck(deck.data)
    assert set(reading.cards) == {"1 Words", "2 Sentences", "3 Terms"}
    assert reading.cards_with_escapes == 0 and reading.credit_on_cards
    assert reading.empty_fields.get("2 Sentences/English") == reading.cards["2 Sentences"]


def test_a_raw_escape_in_a_card_is_counted():
    lines = [
        make_line(1, "ようこそ　あたらしいまちへ。{FF}", [1, 2]),
        make_line(2, "きょうは　いいてんきですね。", [2, 50]),
    ]
    deck = build_export(make_script(lines=lines), ExportRequest(format="anki"))
    assert read_deck(deck.data).cards_with_escapes >= 1


def test_sentence_figures_count_cards_that_stop_mid_sentence_and_repeats():
    script = make_script()
    picked = select_sentences(script, count=10)
    median, unclosed, repeated, escapes = sentence_figures(picked)
    assert median > 0 and unclosed == 0 and repeated == 0 and escapes == 0
    assert sentence_figures([]) == (0.0, 0, 0, 0)


def test_a_clean_game_is_ready():
    assert judge(good_card()).verdict == "ready"


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"rules_unused": 3}, "3 review rules match nothing"),
        ({"unclosed": 300}, "300 of 1000 sentence cards do not end like a sentence"),
        ({"repeated": 4}, "4 repeated sentences"),
        ({"probable_names": 12}, "12 words that look like character names"),
        ({"words": 10}, "only 10 words"),
        ({"cards": {"1 Words": 5, "2 Sentences": 5}}, "no name or term cards"),
    ],
)
def test_a_limit_is_named_and_the_game_still_works(change, fragment):
    card = judge(good_card(**change))
    assert card.verdict == "works, with limits"
    assert any(fragment in p for p in card.problems), card.problems


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"verified": False}, "does not rebuild"),
        ({"cards_with_escapes": 2}, "escape codes"),
        ({"sentences_with_escapes": 1}, "escape codes"),
        ({"credit_on_cards": False}, "credit"),
        ({"empty_fields": {"1 Words/Meaning": 3}}, "without a meaning"),
    ],
)
def test_what_makes_a_game_unusable_is_broken(change, fragment):
    card = judge(good_card(**change))
    assert card.verdict == "broken" and any(fragment in b for b in card.broken)


def test_the_scorecard_holds_counts_only():
    text = render(judge(good_card(unclosed=300)))
    assert "**Verdict: works, with limits**" in text and "limit:" in text
    assert not JAPANESE.search(text)


def test_the_module_can_be_run_as_a_script():
    assert callable(game_check.main) and callable(check_game)


ROM = os.environ.get("YOMINEKO_ROM_MARIO_LUIGI_RPG_JP")


@pytest.mark.realrom
@pytest.mark.skipif(not ROM, reason="set YOMINEKO_ROM_MARIO_LUIGI_RPG_JP to run")
def test_a_real_game_is_checked_end_to_end():
    pytest.importorskip("sudachipy")
    from yomineko.analyze.dictionary.install import dictionary_info

    if dictionary_info() is None:
        pytest.skip("download the dictionary first: yomineko dict download")
    card = check_game(ROM)
    assert card.verdict in {"ready", "works, with limits"} and card.verified
    assert card.cards["2 Sentences"] == 1000 and card.cards_with_escapes == 0
    assert card.rules_applied == card.review_rules > 0


CRYSTAL = os.environ.get("YOMINEKO_ROM_POKEMON_CRYSTAL_JP")


@pytest.mark.realrom
@pytest.mark.skipif(not CRYSTAL, reason="set YOMINEKO_ROM_POKEMON_CRYSTAL_JP to run")
def test_a_game_with_name_tables_and_a_review_is_ready():
    pytest.importorskip("sudachipy")
    from yomineko.analyze.dictionary.install import dictionary_info

    if dictionary_info() is None:
        pytest.skip("download the dictionary first: yomineko dict download")
    card = check_game(CRYSTAL)
    assert card.verdict == "ready", card.problems + card.broken
    assert card.cards["2 Sentences"] == 1000 and card.cards["3 Terms"] > 100
    assert card.rules_applied == card.review_rules > 0 and card.rules_unused == 0
    # names the review drops are no longer counted as left in the word list
    assert card.probable_names <= game_check.MAX_NAMES
