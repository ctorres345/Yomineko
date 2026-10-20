import pytest
from support.tinydict import TinyDictionary, noun
from support.tokens import FakeTokenizer, tok

from yomineko.analyze.review import ReviewApplier, parse_review
from yomineko.analyze.worklist import build_worklist, render_worklist
from yomineko.model import Line

KOTO, KOTO_ZITHER, KOTO_CAPITAL = 9000001, 9000002, 9000003
KAERU_FROG = 9000010
KUMO_CLOUD = 9000013


def line(n, text):
    return Line(
        id=f"{0x08000000 + n:08X}", address=n, bank="b", raw=text, text=text, kind="dialogue"
    )


KOTO_TOKEN = tok("こと")
KUMO_TOKEN = tok("くも")  # 雲 (common) with only a rare homophone, 蜘蛛
BUTTON = tok("ボタン", reading="ぼたん")  # a single candidate
KAERU_NOUN = tok("かえる")


@pytest.fixture
def lines():
    return [line(n, f"line{n}") for n in range(1, 8)]


@pytest.fixture
def tokenizer():
    return FakeTokenizer(
        {
            "line1": [KOTO_TOKEN, KUMO_TOKEN, BUTTON],
            "line2": [KOTO_TOKEN, KOTO_TOKEN],
            "line3": [KOTO_TOKEN, KAERU_NOUN],
            "line4": [KOTO_TOKEN, KAERU_NOUN],
            "line5": [KOTO_TOKEN, KAERU_NOUN, KUMO_TOKEN],
            "line6": [KOTO_TOKEN],
            "line7": [KUMO_TOKEN],
        }
    )


def by_id(items):
    return {i.pick.entry_id: i for i in items}


def test_a_word_with_a_common_alternative_is_ambiguous(lines, tokenizer, mini_dict):
    items = by_id(build_worklist(lines, tokenizer, mini_dict, min_freq=1))
    koto = items[KOTO]
    assert koto.freq == 7
    assert [a.entry_id for a in koto.alternatives] == [KOTO_ZITHER, KOTO_CAPITAL]
    assert [a.common for a in koto.alternatives] == [True, False]


def test_words_with_only_rare_alternatives_or_none_are_not_listed(lines, tokenizer, mini_dict):
    items = by_id(build_worklist(lines, tokenizer, mini_dict, min_freq=1))
    assert KUMO_CLOUD not in items  # its only alternative is a rare spider
    assert 9000012 not in items  # ボタン has no alternative at all


def test_min_freq_filters_and_the_list_is_most_frequent_first(lines, tokenizer, mini_dict):
    everything = build_worklist(lines, tokenizer, mini_dict, min_freq=1)
    assert [i.pick.entry_id for i in everything] == [KOTO, KAERU_FROG]
    assert [i.freq for i in everything] == [7, 3]
    assert [i.pick.entry_id for i in build_worklist(lines, tokenizer, mini_dict, min_freq=4)] == [
        KOTO
    ]
    assert build_worklist(lines, tokenizer, mini_dict, min_freq=99) == []


def test_examples_are_distinct_lines_with_their_text_and_limited(lines, tokenizer, mini_dict):
    koto = by_id(build_worklist(lines, tokenizer, mini_dict, min_freq=1))[KOTO]
    assert koto.examples == [("08000001", "line1"), ("08000002", "line2"), ("08000003", "line3")]
    one = by_id(build_worklist(lines, tokenizer, mini_dict, min_freq=1, max_examples=1))[KOTO]
    assert len(one.examples) == 1


def test_words_a_review_already_covers_are_left_out(lines, tokenizer, mini_dict):
    review = ReviewApplier(parse_review({"words": [{"from": KOTO, "to": KOTO_ZITHER}]}), mini_dict)
    items = by_id(build_worklist(lines, tokenizer, mini_dict, review=review, min_freq=1))
    assert KOTO not in items and KAERU_FROG in items


def test_the_pick_and_alternatives_are_described(lines, tokenizer, mini_dict):
    koto = by_id(build_worklist(lines, tokenizer, mini_dict, min_freq=1))[KOTO]
    assert (koto.pick.written, koto.pick.kana, koto.pick.meaning) == (
        "事",
        "こと",
        "thing (abstract); matter",
    )
    assert koto.alternatives[0].written == "琴"


def test_a_word_usually_written_in_kana_still_shows_its_kanji(lines, tokenizer, mini_dict):
    items = by_id(build_worklist(lines, tokenizer, mini_dict, min_freq=1))
    frog = items[KAERU_FROG]
    assert (frog.pick.written, frog.pick.kanji) == ("かえる", "蛙")
    assert "かえる [かえる] (kanji 蛙)" in render_worklist([frog])
    assert "(kanji" not in render_worklist([items[KOTO]]).split("alternatives")[0]


def test_rendering_has_the_warning_ids_and_example_lines(lines, tokenizer, mini_dict):
    text = render_worklist(build_worklist(lines, tokenizer, mini_dict, min_freq=4))
    assert "Contains game text" in text and "do not share or commit" in text
    assert f"id {KOTO}" in text and f"id {KOTO_ZITHER}" in text
    assert "08000001  line1" in text
    assert "{from: <picked id>, to: <right id>}" in text
    assert text.endswith("\n")


def test_rendering_an_empty_worklist(mini_dict):
    text = render_worklist([])
    assert "0 words to look at" in text


# ------------------------------------------------------------------ probable names

SAN = tok("さん", pos="接尾辞", sub_pos="名詞的")


def name_lines(*texts):
    return [line(n, t) for n, t in enumerate(texts, start=1)]


def names_of(items):
    return {i.pick.entry_id: i.reason for i in items if i.reason}


def test_a_noun_often_followed_by_an_honorific_is_a_probable_name(mini_dict):
    lines = name_lines("a", "b", "c", "d", "e")
    tokenizer = FakeTokenizer(
        {
            "a": [KUMO_TOKEN, SAN],
            "b": [KUMO_TOKEN, SAN],
            "c": [KUMO_TOKEN, SAN],
            "d": [KUMO_TOKEN, SAN],
            "e": [KUMO_TOKEN],
        }
    )
    items = build_worklist(lines, tokenizer, mini_dict, min_freq=4)
    reasons = names_of(items)
    assert list(reasons) == [KUMO_CLOUD]
    assert "probably a name" in reasons[KUMO_CLOUD] and "4 of 5" in reasons[KUMO_CLOUD]
    (item,) = items
    assert item.alternatives == [] and item.freq == 5 and item.examples


HAI, NE = 9200001, 9200002


@pytest.fixture
def surname():
    """Two single-kanji nouns, as a surname that the tokenizer split in two."""
    return TinyDictionary([noun(HAI, "灰", "はい"), noun(NE, "根", "ね")], common={HAI, NE})


def test_a_kanji_always_followed_by_the_same_other_kanji_is_a_probable_name(surname):
    lines = name_lines(*"abcdefghij")
    first, second = tok("灰", reading="はい"), tok("根", reading="ね")
    tokenizer = FakeTokenizer(
        {**{t: [first, second] for t in "abcde"}, **{t: [second] for t in "fghij"}}
    )
    reasons = names_of(build_worklist(lines, tokenizer, surname, min_freq=4))
    assert set(reasons) == {HAI}  # 根 is also seen alone half of the time, so it is not flagged
    assert "followed by the same word in 5 of 5" in reasons[HAI]


def test_the_other_kanji_is_flagged_when_it_nearly_always_comes_after_the_first(surname):
    lines = name_lines(*"abcde")
    tokenizer = FakeTokenizer(
        {t: [tok("灰", reading="はい"), tok("根", reading="ね")] for t in "abcde"}
    )
    assert set(names_of(build_worklist(lines, tokenizer, surname, min_freq=4))) == {HAI, NE}


def test_longer_words_that_often_go_together_are_not_taken_for_names(mini_dict):
    lines = name_lines(*"abcde")
    tokenizer = FakeTokenizer({t: [BUTTON, KUMO_TOKEN] for t in "abcde"})
    assert names_of(build_worklist(lines, tokenizer, mini_dict, min_freq=4)) == {}


class Compounds:
    """A dictionary plus one compound word made of two tokens."""

    def __init__(self, base, compound):
        self._base, self._compound = base, compound

    def ids_by_kanji(self, text):
        return [1] if text == self._compound else self._base.ids_by_kanji(text)

    def __getattr__(self, name):
        return getattr(self._base, name)


def test_two_kanji_that_make_a_dictionary_word_are_not_taken_for_a_name(surname):
    lines = name_lines(*"abcde")
    tokenizer = FakeTokenizer(
        {t: [tok("灰", reading="はい"), tok("根", reading="ね")] for t in "abcde"}
    )
    assert names_of(build_worklist(lines, tokenizer, Compounds(surname, "灰根"), min_freq=4)) == {}


def test_a_word_with_a_review_rule_is_not_suggested_as_a_name(mini_dict):
    lines = name_lines("a", "b", "c", "d")
    tokenizer = FakeTokenizer({t: [KUMO_TOKEN, SAN] for t in "abcd"})
    review = ReviewApplier(parse_review({"words": [{"from": KUMO_CLOUD, "drop": True}]}), mini_dict)
    assert build_worklist(lines, tokenizer, mini_dict, review=review, min_freq=4) == []


def test_an_ambiguous_word_that_is_also_a_name_keeps_its_alternatives(mini_dict):
    lines = name_lines("a", "b", "c", "d")
    tokenizer = FakeTokenizer({t: [KOTO_TOKEN, SAN] for t in "abcd"})
    (item,) = build_worklist(lines, tokenizer, mini_dict, min_freq=4)
    assert item.pick.entry_id == KOTO and item.alternatives and "probably a name" in item.reason


def test_the_rendered_worklist_says_which_words_look_like_names(mini_dict):
    lines = name_lines("a", "b", "c", "d")
    tokenizer = FakeTokenizer({t: [KUMO_TOKEN, SAN] for t in "abcd"})
    text = render_worklist(build_worklist(lines, tokenizer, mini_dict, min_freq=4))
    assert "(1 look like names)" in text and "probably a name: followed by a title" in text
