from support.study import make_script, make_words

from yomineko.export.sentences import select_sentences
from yomineko.export.study import HELP_MAX_WORDS, build_study
from yomineko.model import Translation


def study_of(script=None, **kw):
    script = script or make_script()
    kw.setdefault("min_freq", 4)
    return build_study(script, select_sentences(script), **kw)


def test_the_study_set_carries_the_game_and_the_credit():
    study = study_of()
    assert (study.title, study.profile_id) == ("Demo Game", "demo")
    assert "CC BY-SA" in study.credit


def test_words_are_ranked_and_shown_the_way_the_prototype_did():
    words = study_of().words
    assert [w.rank for w in words[:3]] == [1, 2, 3] and len(words) == 60
    first = words[0]
    assert (first.front, first.kana, first.kanji) == ("こと", "こと", "事")  # kanji line kept
    assert words[1].kanji == ""  # written == kana: nothing to add
    assert first.meanings == ("meaning 1; extra 1", "second 1")


def test_a_word_uses_its_shortest_chosen_sentence_as_the_example():
    words = {w.jmdict_id: w for w in study_of().words}
    assert words[1].example == "ようこそ　あたらしいまちへ。"  # 13 characters beats 14
    assert words[30].example == ""  # in no sentence
    translated = make_script()
    line = translated.lines[0].model_copy(
        update={"translation": Translation(text="Welcome to the new town.", source="reviewed")}
    )
    translated = translated.model_copy(update={"lines": [line, *translated.lines[1:]]})
    assert {w.jmdict_id: w for w in study_of(translated).words}[1].example_english == (
        "Welcome to the new town."
    )


def test_the_min_freq_decides_which_words_get_cards_but_not_their_rank():
    words = make_words()
    words[59] = words[59].model_copy(update={"freq": 2})
    study = study_of(make_script(words=words), min_freq=3)
    assert len(study.words) == 59 and study.min_freq == 3
    study = study_of(make_script(words=words), min_freq=1)
    assert study.words[-1].rank == 60


def test_sentences_list_only_help_for_the_uncommon_words():
    by_text = {s.text: s for s in study_of().sentences}
    help_words = by_text["そのほんは　とてもおもしろい。"].words
    assert [g.kana for g in help_words] == ["ことば44", "ことば51"]  # ranks 44 and 51 only
    assert help_words[0].meaning == "meaning 44"  # the first gloss of the first sense


def test_sentence_help_is_capped():
    script = make_script(lines=[])
    ids = list(range(41, 58))
    from support.study import make_line

    script = script.model_copy(
        update={"lines": [make_line(1, "ようこそ　あたらしいまちへ。", ids)]}
    )
    study = study_of(script)
    assert len(study.sentences[0].words) == HELP_MAX_WORDS


def test_sentences_follow_the_order_asked_for():
    script = make_script()
    picked = select_sentences(script)
    rom = build_study(script, picked, min_freq=4, order="rom")
    assert [s.line_id for s in rom.sentences] == sorted(s.line_id for s in rom.sentences)
    easy = build_study(script, picked, min_freq=4, order="frequency")
    assert [s.tier for s in easy.sentences] == sorted(s.tier for s in easy.sentences)


def test_terms_need_a_dictionary_match_and_appear_once():
    terms = study_of().terms
    assert [(t.jp, t.category, t.meaning, t.jmdict_id) for t in terms] == [
        ("ボタン", "item", "button", 900)
    ]


def test_only_the_asked_for_decks_are_built():
    study = study_of(decks=["terms"])
    assert (len(study.words), len(study.sentences), len(study.terms)) == (0, 0, 1)
    study = study_of(decks=["words", "sentences"])
    assert study.terms == [] and study.words and study.sentences


# ---------------------------------------------------------- the player's name


def named_script():
    from support.study import make_line

    lines = [
        make_line(1, "〇〇は　あたらしいまちへ。", [1, 2]),
        make_line(2, "そのほんは　とてもおもしろい。", [3, 44]),
    ]
    return make_script(lines=lines)


def test_cards_show_a_stand_in_name_instead_of_the_placeholder():
    study = study_of(named_script())
    sentence = next(s for s in study.sentences if s.line_id == "08000001")
    assert sentence.text == "ハルは　あたらしいまちへ。"
    assert sentence.lookup == "〇〇は　あたらしいまちへ。", "the dictionary link keeps the original"
    assert {w.jmdict_id: w for w in study.words}[1].example == "ハルは　あたらしいまちへ。"


def test_the_stand_in_name_can_be_chosen():
    script = named_script()
    study = build_study(script, select_sentences(script), min_freq=4, player_name="タロウ")
    assert any(s.text.startswith("タロウは") for s in study.sentences)
    again = build_study(script, select_sentences(script), min_freq=4, player_name="〇〇")
    assert any(s.text.startswith("〇〇は") for s in again.sentences)
