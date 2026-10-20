"""The learner's level: words the dictionary ranks as common are skipped by the deck, the word
export and the sentence picker alike."""

import csv
import io

import pytest
from support.study import make_script
from support.tokens import FakeTokenizer, tok
from typer.testing import CliRunner

from yomineko.analyze.vocabulary import analyze
from yomineko.cli.app import app
from yomineko.core.rom.base import rom_from_bytes
from yomineko.errors import YominekoError
from yomineko.export.level import (
    LEVELS,
    NotRankedError,
    choose_words,
    is_skipped,
    parse_level,
)
from yomineko.export.sentences import select_sentences
from yomineko.export.study import build_study
from yomineko.export.words_export import select_words
from yomineko.extract import extract
from yomineko.model import DictionarySource, Word
from yomineko.pipeline.choices import Choices, load_choices, save_choices
from yomineko.pipeline.exporting import ExportRequest, build_export
from yomineko.pipeline.workspace import Workspace
from yomineko.profile.loader import load_profile
from yomineko.script_io import write_script

KOTO = 9000001  # 事, nf02: among the 1,000 commonest
IRAI = 9000004  # 依頼, nf10: among the 5,000 commonest
JISHIN = 9000006  # 地震, nf20: among the 10,000 commonest
SUGOI = 9000011  # すごい, common but unranked (60): never skipped

KOTO_T = tok("こと")
IRAI_T = tok("依頼", reading="いらい", normalized="依頼")
JISHIN_T = tok("地震", reading="じしん", normalized="地震")
SUGOI_T = tok("すごい", pos="形容詞", sub_pos="一般")


def word(entry_id, rank, freq=10):
    return Word(jmdict_id=entry_id, written=f"w{entry_id}", kana="k", freq=freq, jmdict_rank=rank)


# ---------------------------------------------------------------------- levels


def test_the_levels_skip_the_bands_of_their_word_counts():
    assert [info.max_rank for info in LEVELS.values()] == [0, 2, 10, 20]
    assert [info.name for info in LEVELS.values()] == [
        "Just starting",
        "The basics",
        "Intermediate",
        "Advanced",
    ]
    assert LEVELS["basics"].description == "Skip the 1,000 most common words"
    assert LEVELS["starting"].description == "Make cards for every word"


@pytest.mark.parametrize(
    ("rank", "skipped_from"),
    [(1, "basics"), (2, "basics"), (3, "intermediate"), (10, "intermediate"), (11, "advanced")],
)
def test_a_word_is_skipped_from_the_level_whose_band_holds_it(rank, skipped_from):
    order = list(LEVELS)
    for level in order:
        expected = order.index(level) >= order.index(skipped_from)
        assert is_skipped(word(1, rank), level) is expected, level


@pytest.mark.parametrize("rank", [21, 48, 60, 100, None])
def test_rarer_and_unranked_words_are_never_skipped(rank):
    assert not any(is_skipped(word(1, rank), level) for level in LEVELS)


def test_parse_level_names_the_choices():
    assert parse_level("advanced") == "advanced"
    with pytest.raises(YominekoError, match="starting, basics, intermediate, advanced"):
        parse_level("N5")


def test_choose_words_counts_cards_skipped_and_rare():
    script = make_script(
        words=[word(1, 1, 50), word(2, 30, 40), word(3, 2, 3), word(4, 100, 2), word(5, 60, 9)]
    )
    choice = choose_words(script, level="basics", min_freq=4)
    assert (choice.cards, choice.skipped, choice.rare) == (2, 1, 1)
    # the sample lists skipped words even when they are seen too rarely for a card anyway
    assert [w.jmdict_id for w in choice.sample] == [1, 3]
    starting = choose_words(script, level="starting", min_freq=4)
    assert (starting.cards, starting.skipped, starting.rare, starting.sample) == (3, 0, 2, [])


def test_the_sample_shows_the_ten_skipped_words_seen_most_often():
    script = make_script(words=[word(i, 1, 100 - i) for i in range(1, 15)])
    assert [w.jmdict_id for w in choose_words(script, level="basics", min_freq=1).sample] == list(
        range(1, 11)
    )


def test_a_level_needs_words_that_know_their_rank():
    script = make_script()  # words analysed before schema 4: no rank
    assert choose_words(script, level="starting", min_freq=1).cards == 60
    with pytest.raises(NotRankedError, match="analyze"):
        choose_words(script, level="basics", min_freq=1)
    with pytest.raises(NotRankedError):
        select_words(script, 1, "advanced")


# ----------------------------------------------- one selection, every consumer


def ranked_script():
    """The study script with words 1-10 in the commonest band and the rest rarely seen."""
    script = make_script()
    words = [
        w.model_copy(update={"jmdict_rank": 1 if w.jmdict_id <= 10 else 40}) for w in script.words
    ]
    return script.model_copy(update={"words": words})


def test_select_words_leaves_out_the_skipped_words_and_keeps_ranks():
    script = ranked_script()
    picked = select_words(script, 1, "basics")
    assert [rank for rank, _ in picked][:2] == [11, 12] and len(picked) == 50


def test_the_sentence_picker_teaches_only_the_words_being_studied():
    script = ranked_script()
    every = select_sentences(script, min_freq=1)
    known = select_sentences(script, min_freq=1, level="basics")
    # line 1 holds words 1 and 2, both known at this level: it teaches nothing
    assert "08000001" in [s.line.id for s in every]
    assert "08000001" not in [s.line.id for s in known]
    for s in known:
        assert s.word_ids and not any(i <= 10 for i in s.word_ids)
    # a known word still counts as a word of the line, and for how hard the line is
    line3 = next(s for s in known if s.line.id == "08000003")
    assert line3.word_ids == (44, 51) and line3.difficulty == 50


def test_just_starting_changes_nothing():
    script = ranked_script()
    assert select_sentences(script, min_freq=1) == select_sentences(
        script, min_freq=1, level="starting"
    )
    assert select_words(script, 1) == select_words(script, 1, "starting")


def test_the_deck_has_no_cards_and_no_help_for_skipped_words():
    script = ranked_script()
    picked = select_sentences(script, min_freq=1, level="basics")
    study = build_study(script, picked, min_freq=1, level="basics")
    assert study.words and all(w.jmdict_id > 10 for w in study.words)
    helped = [g.kana for s in study.sentences for g in s.words]
    assert "こと" not in helped


def test_the_export_request_carries_the_level():
    script = ranked_script()
    every = build_export(script, ExportRequest(format="csv", content="words"))
    fewer = build_export(script, ExportRequest(format="csv", content="words", level="basics"))
    assert every.summary == "Exported 60 words" and fewer.summary == "Exported 50 words"
    deck = build_export(script, ExportRequest(format="xlsx", min_freq=1, level="basics"))
    assert "(50 words," in deck.summary


# --------------------------------------------------------- synthetic ROM, end to end


@pytest.fixture
def analysed(sjis_rom, mini_dict):
    """The synthetic Shift-JIS ROM extracted and analysed against the invented mini JMdict."""
    script = extract(
        rom_from_bytes(sjis_rom.rom, "t.gba"), load_profile(sjis_rom.profile_path)
    ).script
    texts = [x.text for x in script.lines if x.kind == "dialogue" and not x.duplicate_of]
    table = {t: [KOTO_T] for t in texts}
    table[texts[0]] = [KOTO_T, IRAI_T, JISHIN_T, SUGOI_T]
    table[texts[1]] = [KOTO_T, IRAI_T, JISHIN_T]
    table[texts[2]] = [KOTO_T, IRAI_T, JISHIN_T]
    source = DictionarySource(date="2026-01-02", source="https://x", credit="JMdict credit")
    return analyze(script, FakeTokenizer(table), mini_dict, source)


def test_analyze_stores_each_word_s_dictionary_rank(analysed):
    ranks = {w.jmdict_id: w.jmdict_rank for w in analysed.words}
    assert ranks == {KOTO: 2, IRAI: 10, JISHIN: 20, SUGOI: 60}


@pytest.mark.parametrize(
    ("level", "cards"),
    [
        ("starting", [KOTO, IRAI, JISHIN, SUGOI]),
        ("basics", [IRAI, JISHIN, SUGOI]),
        ("intermediate", [JISHIN, SUGOI]),
        ("advanced", [SUGOI]),
    ],
)
def test_each_level_skips_its_band_on_a_synthetic_rom(analysed, level, cards):
    assert [w.jmdict_id for _, w in select_words(analysed, 1, level)] == cards
    choice = choose_words(analysed, level=level, min_freq=1)
    assert choice.cards == len(cards) and choice.skipped == 4 - len(cards)


def test_the_cli_level_flag_on_a_synthetic_rom(analysed, tmp_path):
    path = write_script(analysed, tmp_path / "script.json")
    out = tmp_path / "words.csv"
    args = ["export", str(path), "-f", "csv", "--content", "words", "--min-freq", "1", "-o"]
    result = CliRunner().invoke(app, [*args, str(out), "--level", "intermediate"])
    assert result.exit_code == 0, result.output
    rows = [
        r for r in csv.reader(io.StringIO(out.read_text(encoding="utf-8-sig"))) if r[0][0] != "#"
    ]
    assert [int(r[7]) for r in rows[1:]] == [JISHIN, SUGOI]
    assert rows[1][-1] == "20"
    bad = CliRunner().invoke(app, [*args, str(out), "--level", "N3"])
    assert bad.exit_code == 2


# ------------------------------------------------------------ remembered choices


def test_choices_default_to_just_starting_and_the_deck_minimum(tmp_path):
    assert load_choices(Workspace(tmp_path), "demo") == Choices("starting", 4)


def test_a_new_game_starts_at_the_last_level_picked(tmp_path):
    ws = Workspace(tmp_path)
    save_choices(ws, "first", Choices("intermediate", 7))
    assert load_choices(ws, "first") == Choices("intermediate", 7)
    assert load_choices(ws, "second") == Choices("intermediate", 4)
    save_choices(ws, "second", Choices("basics", 4))
    assert load_choices(ws, "first").level == "intermediate"  # each game keeps its own
    assert load_choices(ws, "third").level == "basics"


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", '{"level": "N1", "min_freq": "x"}', '{"level": 3, "min_freq": true}'],
)
def test_damaged_choices_fall_back_to_the_defaults(tmp_path, content):
    ws = Workspace(tmp_path)
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "choices.json").write_text(content, encoding="utf-8")
    assert load_choices(ws, "demo") == Choices()


def test_a_saved_minimum_is_kept_within_limits(tmp_path):
    ws = Workspace(tmp_path)
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "choices.json").write_text('{"min_freq": 0}', encoding="utf-8")
    assert load_choices(ws, "demo").min_freq == 1
