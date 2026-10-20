import pytest
from support.tokens import FakeTokenizer, tok

from yomineko.analyze.dictionary.xml_parser import Entry, Sense
from yomineko.analyze.tokenizer import Token
from yomineko.analyze.vocabulary import (
    analysable_lines,
    analyze,
    build_vocabulary,
    build_words,
    match_terms,
    meanings,
    usable,
    written_form,
)
from yomineko.model import DictionarySource, GameInfo, Line, Script, Term

SHA1 = "0123456789abcdef0123456789abcdef01234567"


def line(n, text, kind="dialogue", duplicate_of=None):
    return Line(
        id=f"{0x08000000 + n:08X}",
        address=n,
        bank="b",
        raw=text,
        text=text,
        kind=kind,
        duplicate_of=duplicate_of,
    )


KOTO = tok("こと")
IRAI = tok("依頼", reading="いらい", normalized="依頼")
KAERU_VERB = tok("かえる", pos="動詞", sub_pos="一般")
KAERU_NOUN = tok("かえる")
SUGOI = tok("すごい", pos="形容詞", sub_pos="一般")
BUTTON = tok("ボタン", reading="ぼたん")
PARTICLE = tok("が", pos="助詞", sub_pos="格助詞")


# --------------------------------------------------------------------- usable


@pytest.mark.parametrize(
    "token",
    [KOTO, IRAI, KAERU_VERB, SUGOI, tok("ここ", pos="代名詞"), tok("ええ", pos="感動詞")],
)
def test_content_words_are_usable(token):
    assert usable(token)


@pytest.mark.parametrize(
    "token",
    [
        PARTICLE,
        tok("ピカ", sub_pos="固有名詞"),  # proper noun
        tok("三", sub_pos="数詞"),  # numeral
        tok("！", pos="補助記号"),
        tok("ABC"),  # nothing Japanese
        tok("。", pos="名詞"),
    ],
)
def test_other_tokens_are_skipped(token):
    assert not usable(token)


# ------------------------------------------------------------- written form


PLAIN_SENSE = Sense((), (), ("x",))
UK_SENSE = Sense((), ("word usually written using kana alone",), ("b",))


def entry(kanji, kana, senses=None):
    return Entry(1, tuple(kanji), tuple(kana), tuple(senses or [PLAIN_SENSE]))


def test_a_common_kanji_word_is_shown_in_kanji():
    assert written_form(entry([("事", 2)], [("こと", 2)]), "こと") == ("事", "事")


def test_the_most_frequent_kanji_form_is_chosen():
    e = entry([("A", 50), ("B", 10)], [("あ", 10)])
    assert written_form(e, "あ") == ("B", "B")


def test_a_word_usually_written_in_kana_shows_its_reading_and_keeps_the_kanji():
    uk = Sense((), ("word usually written using kana alone",), ("frog",))
    assert written_form(entry([("蛙", 100)], [("かえる", 100)], [uk]), "かえる") == ("かえる", "蛙")


def test_the_uk_tag_only_counts_in_the_first_two_senses():
    plain = Sense((), (), ("a",))
    uk = Sense((), ("word usually written using kana alone",), ("c",))
    e = entry([("甲", 5)], [("あ", 5)], [plain, plain, uk])
    assert written_form(e, "あ") == ("甲", "甲")


def test_uncommon_kanji_with_a_common_reading_show_the_reading():
    assert written_form(entry([("古都", 100)], [("こと", 60)]), "こと") == ("こと", "古都")


def test_uncommon_kanji_and_uncommon_reading_stay_in_kanji():
    assert written_form(entry([("古都", 100)], [("こと", 100)]), "こと") == ("古都", "古都")


def test_a_kana_only_entry_has_no_kanji():
    assert written_form(entry([], [("すごい", 60)]), "すごい") == ("すごい", "")


def test_the_reading_is_matched_between_katakana_and_hiragana():
    e = entry(
        [("釦", 100)],
        [("ボタン", 60)],
        [Sense((), ("word usually written using kana alone",), ("b",))],
    )
    assert written_form(e, "ぼたん") == ("ボタン", "釦")


# ------------------------------------------------------------------- meanings


def test_meanings_skip_rare_senses_and_trim_glosses():
    rare = Sense((), ("archaism",), ("dreadful",))
    main = Sense((), (), ("one", "two", "three", "four"))
    assert meanings(entry([], [("あ", 1)], [rare, main])) == ["one; two; three"]


def test_meanings_stop_at_the_limit():
    senses = [Sense((), (), (str(i),)) for i in range(6)]
    assert meanings(entry([], [("あ", 1)], senses)) == ["0", "1", "2"]
    assert meanings(entry([], [("あ", 1)], senses), limit=1) == ["0"]


def test_if_every_sense_is_rare_the_first_is_used_anyway():
    senses = [Sense((), ("obsolete term",), ("old", "dated")), Sense((), ("rare term",), ("odd",))]
    assert meanings(entry([], [("あ", 1)], senses)) == ["old; dated"]


# ---------------------------------------------------------------- build_words


@pytest.fixture
def lines():
    return [
        line(1, "l1"),
        line(2, "l2"),
        line(3, "〇〇が来た"),
        line(4, "menu", kind="term"),
        line(5, "l1", duplicate_of="08000001"),
        line(6, ""),
    ]


@pytest.fixture
def tokenizer():
    return FakeTokenizer(
        {
            "l1": [KOTO, PARTICLE, IRAI],
            "l2": [KOTO, KOTO, KAERU_VERB, KAERU_NOUN],
            "　が来た": [tok("ピカ", sub_pos="固有名詞"), SUGOI, BUTTON, tok("ゔゔゔ"), tok("ABC")],
        }
    )


def test_only_distinct_dialogue_lines_are_tokenized(lines, tokenizer):
    chosen = analysable_lines(Script(generator="t", game=_game(), lines=lines))
    assert [x.id for x in chosen] == ["08000001", "08000002", "08000003"]


def _game():
    return GameInfo(profile_id="p", title="t", platform="gba", rom_sha1=SHA1)


def words_by_id(words):
    return {w.jmdict_id: w for w in words}


def test_words_are_counted_and_ordered_by_frequency(lines, mini_dict, tokenizer):
    chosen = analysable_lines(Script(generator="t", game=_game(), lines=lines))
    words = build_words(chosen, tokenizer, mini_dict)
    assert words[0].jmdict_id == 9000001 and words[0].freq == 3
    assert [w.freq for w in words] == sorted((w.freq for w in words), reverse=True)


def test_examples_list_each_line_once(lines, mini_dict, tokenizer):
    words = words_by_id(build_words(lines[:2], tokenizer, mini_dict))
    assert words[9000001].examples == ["08000001", "08000002"]  # こと twice in l2, listed once
    assert words[9000001].freq == 3


def test_examples_are_capped_but_frequency_is_not(mini_dict):
    many = [line(n, "x") for n in range(1, 6)]
    t = FakeTokenizer({"x": [KOTO]})
    word = build_words(many, t, mini_dict, max_examples=2)[0]
    assert (word.freq, len(word.examples)) == (5, 2)


def test_the_name_placeholder_is_replaced_before_tokenizing(lines, mini_dict, tokenizer):
    build_words(lines, tokenizer, mini_dict)
    assert "　が来た" in tokenizer.calls
    assert not any("〇〇" in c for c in tokenizer.calls)


def test_word_details(lines, mini_dict, tokenizer):
    words = words_by_id(build_words([lines[0], lines[1], lines[2]], tokenizer, mini_dict))
    koto = words[9000001]
    assert (koto.written, koto.kana, koto.kanji, koto.pos, koto.common) == (
        "事",
        "こと",
        "事",
        "名詞",
        True,
    )
    assert koto.meanings == ["thing (abstract); matter"]
    assert koto.sentence_safe is True
    assert words[9000004].written == "依頼"  # the kanji guess was trusted


def test_homophones_become_separate_words_by_part_of_speech(lines, mini_dict, tokenizer):
    words = words_by_id(build_words(lines[:2], tokenizer, mini_dict))
    assert words[9000008].written == "帰る"
    frog = words[9000010]
    assert (frog.written, frog.kanji, frog.common) == ("かえる", "蛙", False)


def test_kana_only_and_katakana_words(lines, mini_dict, tokenizer):
    words = words_by_id(build_words([lines[2]], tokenizer, mini_dict))
    sugoi = words[9000011]
    assert (sugoi.written, sugoi.kanji, sugoi.meanings) == ("すごい", "", ["amazing; great"])
    button = words[9000012]
    assert (button.written, button.kana, button.kanji) == ("ボタン", "ボタン", "釦")


def test_names_symbols_and_unknown_words_are_skipped(lines, mini_dict, tokenizer):
    ids = {w.jmdict_id for w in build_words([lines[2]], tokenizer, mini_dict)}
    assert ids == {9000011, 9000012}


def test_ties_keep_the_order_first_seen(mini_dict):
    t = FakeTokenizer({"a": [IRAI, KOTO]})
    words = build_words([line(1, "a")], t, mini_dict)
    assert [w.jmdict_id for w in words] == [9000004, 9000001]


def test_the_same_token_is_only_looked_up_once(mini_dict, monkeypatch):
    import yomineko.analyze.vocabulary as vocabulary

    calls = []
    real = vocabulary.candidates
    monkeypatch.setattr(vocabulary, "candidates", lambda d, t: calls.append(t) or real(d, t))
    t = FakeTokenizer({"x": [KOTO, KOTO]})
    build_words([line(n, "x") for n in range(1, 4)], t, mini_dict)
    assert len(calls) == 1


# -------------------------------------------------------------------- analyze


def test_analyze_returns_a_new_script_with_words_and_the_credit(lines, mini_dict, tokenizer):
    script = Script(generator="t", game=_game(), lines=lines)
    source = DictionarySource(date="2026-10-03", source="https://x", credit="CREDIT")
    result = analyze(script, tokenizer, mini_dict, source)
    assert script.words == [] and script.dictionary is None, "the input is not modified"
    assert len(result.words) > 0
    assert result.dictionary == source
    assert [x.id for x in result.lines] == [x.id for x in script.lines]
    assert result.schema_version == 4


def test_analyze_is_repeatable(lines, mini_dict, tokenizer):
    script = Script(generator="t", game=_game(), lines=lines)
    source = DictionarySource(date="d", source="s", credit="c")
    first = analyze(script, tokenizer, mini_dict, source)
    assert analyze(first, tokenizer, mini_dict, source) == first


def test_token_kana_detection():
    assert Token("ねこ", "猫", "ねこ", "名詞").is_kana
    assert Token("ボタン", "ボタン", "ぼたん", "名詞").is_kana
    assert Token("のー", "x", "x", "感動詞").is_kana
    assert not Token("猫", "猫", "ねこ", "名詞").is_kana
    assert not Token("お茶", "お茶", "おちゃ", "名詞").is_kana


# ------------------------------------------------------- words per line, terms


def test_each_line_lists_its_words_once_in_order(lines, mini_dict, tokenizer):
    vocabulary = build_vocabulary(lines[:3], tokenizer, mini_dict)
    assert vocabulary.line_words["08000001"] == [9000001, 9000004]
    assert vocabulary.line_words["08000002"] == [9000001, 9000008, 9000010]
    assert vocabulary.line_words["08000003"] == [9000011, 9000012]


def test_line_words_are_not_capped_like_examples(mini_dict):
    many = [line(n, "x") for n in range(1, 6)]
    vocabulary = build_vocabulary(many, FakeTokenizer({"x": [KOTO]}), mini_dict, max_examples=2)
    assert all(ids == [9000001] for ids in vocabulary.line_words.values())
    assert len(vocabulary.line_words) == 5


def test_analyze_stores_word_ids_on_lines_and_clears_old_ones(lines, mini_dict, tokenizer):
    script = Script(generator="t", game=_game(), lines=lines)
    source = DictionarySource(date="d", source="s", credit="c")
    result = analyze(script, tokenizer, mini_dict, source)
    by_id = {x.id: x for x in result.lines}
    assert by_id["08000001"].word_ids == [9000001, 9000004]
    assert by_id["08000005"].word_ids == [], "repeats and terms have no words of their own"
    assert by_id["08000004"].word_ids == []


def test_unsafe_corrections_stay_off_the_line_words(mini_dict):
    from yomineko.analyze.review import ReviewApplier, parse_review

    review = parse_review(
        {"words": [{"from": 9000001, "to": 9000002, "sentence_safe": False}]}, "r"
    )
    t = FakeTokenizer({"x": [KOTO, IRAI]})
    vocabulary = build_vocabulary(
        [line(1, "x")], t, mini_dict, review=ReviewApplier(review, mini_dict)
    )
    assert vocabulary.line_words["08000001"] == [9000004]
    assert {w.jmdict_id for w in vocabulary.words} == {9000002, 9000004}


def _terms_script(*terms, lines=()):
    return Script(generator="t", game=_game(), lines=list(lines), terms=list(terms))


def test_a_term_matching_exactly_one_entry_is_tagged(mini_dict):
    script = _terms_script(
        Term(jp="ボタン", category="item", index=0),  # one entry, by reading
        Term(jp="雲", category="item", index=1),  # one entry, by kanji
    )
    matched = match_terms(script, mini_dict)
    assert [t.jmdict_id for t in matched] == [9000012, 9000013]
    assert matched[0].literal == "button"


def test_ambiguous_and_unknown_terms_are_left_untagged(mini_dict):
    script = _terms_script(
        Term(jp="くも", category="move", index=0),  # 雲 and 蜘蛛
        Term(jp="ぴかぴか", category="move", index=1),  # not in the dictionary
    )
    assert [t.jmdict_id for t in match_terms(script, mini_dict)] == [None, None]


def test_a_term_on_a_dialogue_line_is_not_matched(mini_dict):
    script = _terms_script(
        Term(jp="ボタン", category="item_desc", index=0, line_id="08000001"),
        lines=[line(1, "ボタン")],
    )
    assert match_terms(script, mini_dict)[0].jmdict_id is None


def test_analyze_tags_terms_and_a_second_run_changes_nothing(lines, mini_dict, tokenizer):
    script = Script(
        generator="t",
        game=_game(),
        lines=lines,
        terms=[Term(jp="ボタン", category="item", index=0)],
    )
    source = DictionarySource(date="d", source="s", credit="c")
    first = analyze(script, tokenizer, mini_dict, source)
    assert first.terms[0].jmdict_id == 9000012
    assert analyze(first, tokenizer, mini_dict, source) == first
