import pytest
from support.study import line_id, make_line, make_script, make_words

from yomineko.export.sentences import (
    NotReanalysedError,
    clean_for_card,
    order_sentences,
    select_sentences,
)
from yomineko.export.words_export import NotAnalysedError

GOOD = "きょうは　いいてんきですね。"


def script_of(*specs, **kw):
    """Lines from (number, text, word ids) tuples over the 60-word list."""
    return make_script(lines=[make_line(n, t, ids) for n, t, ids in specs], **kw)


def chosen_numbers(sentences):
    return [s.line.address for s in sentences]


# ------------------------------------------------------------------- readiness


def test_a_script_without_words_must_be_analysed_first():
    script = make_script(words=[], lines=[make_line(1, GOOD)])
    with pytest.raises(NotAnalysedError, match="yomineko analyze"):
        select_sentences(script)


def test_a_script_whose_lines_lack_words_must_be_analysed_again():
    script = make_script(lines=[make_line(1, GOOD)])
    with pytest.raises(NotReanalysedError, match="again"):
        select_sentences(script)


# --------------------------------------------------------------------- filters

BAD_LINES = [
    "%s　きょうはいいてんき",  # a format code
    "abc　きょうはいいてんき",  # Latin words
    "きょうは[いいてんき]です",  # brackets
    "ひにち：きょうはいいてんき",  # a colon
    "ああ",  # too short to be a sentence
    "きょうは。",  # body under 6 characters
    "きょうはいいてんきなので",  # ends on a particle: a fragment
    "きょうは　いいてんき（です",  # an aside in the middle
    "〇〇〇〇〇〇　きょうはいいてんきですね。",  # three name placeholders
    "き" * 61,  # too long
]


@pytest.mark.parametrize("bad", BAD_LINES)
def test_filters_leave_out_what_is_not_a_good_sentence(bad):
    script = script_of((1, GOOD, [2, 50]), (2, bad, [3, 51]))
    assert chosen_numbers(select_sentences(script)) == [1]


def test_a_line_needs_two_known_words():
    script = script_of((1, GOOD, [2]), (2, "そのほんは　とてもおもしろい。", [3, 51]))
    assert chosen_numbers(select_sentences(script)) == [2]


def test_words_below_the_minimum_frequency_do_not_count():
    words = make_words()
    words[50] = words[50].model_copy(update={"freq": 1})  # id 51
    script = script_of(
        (1, GOOD, [2, 51]), (2, "そのほんは　とてもおもしろい。", [3, 52]), words=words
    )
    assert chosen_numbers(select_sentences(script, min_freq=4)) == [2]
    assert chosen_numbers(select_sentences(script, min_freq=1)) == [1, 2]


def test_repeats_terms_and_unreadable_lines_are_ignored():
    script = make_script(
        lines=[
            make_line(1, GOOD, [2, 50]),
            make_line(2, GOOD, [2, 50], duplicate_of=line_id(1)),
            make_line(3, "そのほんは　とてもおもしろい。", [3, 51], kind="term"),
            make_line(4, "", [3, 51]),
        ]
    )
    assert chosen_numbers(select_sentences(script)) == [1]


def test_at_most_three_lines_share_an_opening():
    texts = [f"あいうえおかきくけこ{tail}" for tail in "まみむめも"]
    script = script_of(*[(i, t, [2, 50 + i]) for i, t in enumerate(texts, start=1)])
    assert len(select_sentences(script)) == 3


def test_lines_that_differ_only_in_pronoun_or_ending_count_once():
    script = script_of(
        (1, "ボクはあいうえおかきくけ。", [2, 50]),
        (2, "ワタシはあいうえおかきくけ。", [2, 51]),
        (3, "そのほんは　とてもおもしろい", [3, 52]),
        (4, "そのほんは　とてもおもしろいね", [3, 53]),
    )
    assert chosen_numbers(select_sentences(script)) == [1, 3]


# ------------------------------------------------- the review's and profile's say


def test_excluded_ids_and_address_ranges_are_never_chosen():
    script = script_of(
        (1, GOOD, [2, 50]),
        (2, "そのほんは　とてもおもしろい。", [3, 51]),
        (3, "あしたは　みんなであそぼう。", [4, 52]),
    )
    chosen = select_sentences(script, exclude_ids=[line_id(1)], exclude_ranges=[(3, 4)])
    assert chosen_numbers(chosen) == [2]


def test_a_pinned_line_is_chosen_even_if_the_filters_would_reject_it():
    script = script_of((1, GOOD, [2, 50]), (2, "ああ", [3]), (3, "ああ。", [4]))
    chosen = select_sentences(script, pin_ids=[line_id(2)], exclude_ranges=[(0, 100)])
    assert chosen_numbers(chosen) == [2]  # the range keeps out the rest, not the pin


def test_an_excluded_line_cannot_be_pinned_by_accident():
    script = script_of((1, GOOD, [2, 50]))
    assert select_sentences(script, pin_ids=[line_id(1)], exclude_ids=[line_id(1)]) == []


# --------------------------------------------------------------------- caps

QUOTES = [
    (1, "〇〇「あしたはいいてんきだよ」", [2, 50]),
    (2, "〇〇「そのほんはおもしろい」", [3, 51]),
    (3, "〇〇「きょうはみんなでたべる」", [4, 52]),
]
SUBJECTS = [
    (4, "〇〇は　ようこそあたらしいまちへ。", [5, 53]),
    (5, "〇〇の　ほんをよんでみたいな。", [6, 54]),
]


def test_a_cap_limits_a_structural_kind():
    chosen = select_sentences(script_of(*QUOTES, *SUBJECTS), caps={"name_quote": 1})
    assert len([s for s in chosen if s.line.address <= 3]) == 1
    assert len([s for s in chosen if s.line.address >= 4]) == 2  # name_subject has no cap


def test_each_kind_has_its_own_cap_and_pins_use_up_the_room():
    script = script_of(*QUOTES, *SUBJECTS)
    chosen = select_sentences(
        script, caps={"name_quote": 2, "name_subject": 0}, pin_ids=[line_id(1)]
    )
    assert chosen_numbers(chosen).count(1) == 1
    assert len([s for s in chosen if s.line.address <= 3]) == 2
    assert not [s for s in chosen if s.line.address >= 4]


# ------------------------------------------------------------------- greedy


def test_the_first_pick_teaches_the_commonest_words_and_the_second_looks_elsewhere():
    script = script_of(
        (1, "ようこそ　あたらしいまちへ。", [1, 2]),
        (2, "あしたは　みんなであそぼう。", [1, 2]),
        (3, "そのほんは　とてもおもしろい。", [3, 4]),
    )
    assert chosen_numbers(select_sentences(script, count=1)) == [1]
    assert chosen_numbers(select_sentences(script, count=2)) == [1, 3]  # not the twin of line 1


def test_a_better_length_wins_over_a_slightly_better_word_set():
    long_line = "あ" * 5 + "い" * 40 + "う。"  # over 40 characters: scaled down
    script = script_of(
        (1, long_line, [1, 2]),
        (2, "そのほんは　とてもおもしろい。", [1, 3]),
    )
    assert chosen_numbers(select_sentences(script, count=1)) == [2]


def test_ties_go_to_the_earlier_line_and_the_result_is_in_rom_order():
    script = script_of(
        (5, "そのほんは　とてもおもしろい。", [1, 2]),
        (3, "ようこそ　あたらしいまちへ。", [1, 2]),
        (9, "あしたは　みんなであそぼう。", [30, 31]),
    )
    assert chosen_numbers(select_sentences(script, count=1)) == [5]  # first in the script's order
    assert chosen_numbers(select_sentences(script)) == [3, 5, 9]


def test_selection_is_repeatable():
    script = make_script()
    assert select_sentences(script) == select_sentences(script)


def test_the_count_limits_the_result_including_pins():
    script = script_of(
        (1, "ようこそ　あたらしいまちへ。", [1, 2]),
        (2, "そのほんは　とてもおもしろい。", [3, 4]),
        (3, "あしたは　みんなであそぼう。", [5, 6]),
    )
    chosen = select_sentences(script, count=2, pin_ids=[line_id(3)])
    assert len(chosen) == 2 and 3 in chosen_numbers(chosen)


# ----------------------------------------------------------- order and cleaning


def test_frequency_order_is_easiest_first_by_tier_then_length():
    script = script_of(
        (1, "ようこそ　あたらしいまちへ。", [1, 2]),
        (2, "そのほんは　とてもおもしろい。", [3, 59]),  # rarest word: rank 58, tier 0
        (3, "あしたは　みんなであそぼう。", [4, 5]),
    )
    chosen = select_sentences(script)
    ordered = [s.line.address for s in order_sentences(chosen, "frequency")]
    assert ordered == [1, 3, 2]  # all tier 0: shortest first, then ROM order
    assert [s.line.address for s in order_sentences(chosen, "rom")] == [1, 2, 3]


def test_a_rarer_tier_comes_later():
    words = make_words(400)
    script = script_of(
        (1, "ようこそ　あたらしいまちへ。", [1, 2]),
        (2, "あしたは　みんなであそぼう。", [3, 300]),
        (3, "そのほんは　とてもおもしろい。", [4, 5]),
        words=words,
    )
    ordered = [s.line.address for s in order_sentences(select_sentences(script), "frequency")]
    assert ordered[-1] == 2


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("あ\nい", "あ　い"),
        ("  あ   い  ", "あ　い"),
        ("あー！！！！", "あー！！"),
        ("あーーーーい", "あーーい"),
        ("あ……………", "あ……"),
        ("あ〜〜〜い", "あ〜い"),
    ],
)
def test_clean_for_card(raw, clean):
    assert clean_for_card(raw) == clean


# ----------------------------------------------------------- sentence export


def test_the_csv_carries_translations_and_the_credit():
    from yomineko.export.sentences_export import render_sentences_csv
    from yomineko.model import Translation

    translated = make_line(1, GOOD, [2, 50]).model_copy(
        update={"translation": Translation(text="Nice weather, isn't it?", source="reviewed")}
    )
    script = make_script(lines=[translated])
    text, count = render_sentences_csv(script, select_sentences(script))
    assert count == 1
    assert '08000001,きょうは　いいてんきですね。,"Nice weather, isn\'t it?",0,2 50' in text
    assert text.rstrip().endswith("CC BY-SA 4.0")


def test_a_line_that_stops_at_a_comma_loses_to_a_whole_sentence_with_the_same_words():
    whole = "きょうは　いいてんきですね。"
    cut = "きょうは　いいてんきですから、"
    script = script_of((1, cut, [2, 50]), (2, whole, [2, 50]))
    assert chosen_numbers(select_sentences(script, count=1)) == [2]


def test_a_cut_line_is_still_used_when_there_is_nothing_better():
    script = script_of((1, "きょうは　いいてんきですから、", [2, 50]))
    assert chosen_numbers(select_sentences(script, count=1)) == [1]
