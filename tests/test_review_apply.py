import pytest
from support.tokens import FakeTokenizer, tok

from yomineko.analyze.review import ReviewApplier, parse_review
from yomineko.analyze.vocabulary import analysable_lines, analyze, build_words
from yomineko.model import DictionarySource, GameInfo, Line, Script

SHA1 = "0123456789abcdef0123456789abcdef01234567"
KOTO, KOTO_ZITHER, KOTO_CAPITAL = 9000001, 9000002, 9000003
KAERU_RETURN, KAERU_CHANGE, KAERU_FROG, SUGOI = 9000008, 9000009, 9000010, 9000011


def line(n, text):
    return Line(
        id=f"{0x08000000 + n:08X}", address=n, bank="b", raw=text, text=text, kind="dialogue"
    )


L1, L2, L3 = "08000001", "08000002", "08000003"
KOTO_TOKEN = tok("こと")
KAERU = tok("かえる", pos="動詞", sub_pos="一般")
SUGOI_TOKEN = tok("すごい", pos="形容詞", sub_pos="一般")


@pytest.fixture
def lines():
    return [line(1, "l1"), line(2, "l2"), line(3, "l3")]


@pytest.fixture
def tokenizer():
    return FakeTokenizer(
        {
            "l1": [KOTO_TOKEN, KAERU],
            "l2": [KOTO_TOKEN, KOTO_TOKEN, SUGOI_TOKEN],
            "l3": [KOTO_TOKEN, tok("かえる", pos="動詞", sub_pos="一般")],
        }
    )


def run(lines, tokenizer, mini_dict, rules):
    applier = ReviewApplier(parse_review(rules), mini_dict)
    words = build_words(lines, tokenizer, mini_dict, review=applier)
    return {w.jmdict_id: w for w in words}, applier


def test_without_rules_nothing_changes(lines, tokenizer, mini_dict):
    plain = build_words(lines, tokenizer, mini_dict)
    reviewed, applier = run(lines, tokenizer, mini_dict, {})
    assert list(reviewed.values()) == plain
    assert applier.report().rules == 0


# ----------------------------------------------------------------------- words


def test_a_remap_moves_every_occurrence_to_the_other_entry(lines, tokenizer, mini_dict):
    rules = {"words": [{"from": KOTO, "to": KOTO_ZITHER}]}
    words, applier = run(lines, tokenizer, mini_dict, rules)
    assert KOTO not in words
    assert words[KOTO_ZITHER].freq == 4
    assert words[KOTO_ZITHER].written == "琴"
    assert applier.report().changed_occurrences == 4


def test_remapping_onto_an_existing_word_merges_counts_and_examples(lines, tokenizer, mini_dict):
    words, _ = run(
        lines, tokenizer, mini_dict, {"words": [{"from": KAERU_RETURN, "to": KAERU_CHANGE}]}
    )
    merged = words[KAERU_CHANGE]
    assert merged.freq == 2 and merged.examples == [L1, L3]
    assert KAERU_RETURN not in words


def test_remapping_onto_a_word_that_also_occurs_directly_adds_up(lines, mini_dict):
    t = FakeTokenizer({"l1": [KOTO_TOKEN], "l2": [tok("こと", pos="名詞")]})
    # make the second token resolve to the zither via a different (kanji) surface
    t.table["l2"] = [tok("琴", reading="こと", normalized="琴")]
    words, _ = run(lines[:2], t, mini_dict, {"words": [{"from": KOTO, "to": KOTO_ZITHER}]})
    assert words[KOTO_ZITHER].freq == 2
    assert words[KOTO_ZITHER].examples == [L1, L2]


def test_drop_removes_the_word(lines, tokenizer, mini_dict):
    words, applier = run(lines, tokenizer, mini_dict, {"words": [{"from": KOTO, "drop": True}]})
    assert KOTO not in words
    assert applier.report().changed_occurrences == 4


def test_a_gloss_replaces_the_meanings(lines, tokenizer, mini_dict):
    words, _ = run(lines, tokenizer, mini_dict, {"words": [{"from": SUGOI, "gloss": "wow"}]})
    assert words[SUGOI].meanings == ["wow"]
    assert words[KOTO].meanings != ["wow"]


def test_a_gloss_with_a_remap_applies_to_the_target(lines, tokenizer, mini_dict):
    words, _ = run(
        lines, tokenizer, mini_dict, {"words": [{"from": KOTO, "to": KOTO_ZITHER, "gloss": "harp"}]}
    )
    assert words[KOTO_ZITHER].meanings == ["harp"]


# ------------------------------------------------------------- sentence safety


def test_unsafe_corrections_count_but_are_kept_out_of_the_examples(lines, tokenizer, mini_dict):
    rules = {"words": [{"from": KOTO, "to": KOTO_ZITHER, "sentence_safe": False}]}
    words, _ = run(lines, tokenizer, mini_dict, rules)
    word = words[KOTO_ZITHER]
    assert word.freq == 4 and word.examples == [] and word.sentence_safe is False


def test_safe_corrections_leave_the_flag_alone(lines, tokenizer, mini_dict):
    words, _ = run(lines, tokenizer, mini_dict, {"words": [{"from": KOTO, "to": KOTO_ZITHER}]})
    assert words[KOTO_ZITHER].sentence_safe is True and words[KOTO_ZITHER].examples


def test_an_unsafe_word_keeps_examples_from_its_direct_occurrences(lines, mini_dict):
    t = FakeTokenizer(
        {"l1": [KOTO_TOKEN], "l2": [tok("琴", reading="こと", normalized="琴")], "l3": []}
    )
    rules = {"words": [{"from": KOTO, "to": KOTO_ZITHER, "sentence_safe": False}]}
    words, _ = run(lines, t, mini_dict, rules)
    word = words[KOTO_ZITHER]
    assert word.freq == 2 and word.examples == [L2] and word.sentence_safe is False


# ------------------------------------------------------------------ line rules


def test_a_line_rule_beats_a_word_rule(lines, tokenizer, mini_dict):
    rules = {
        "words": [{"from": KOTO, "to": KOTO_ZITHER}],
        "lines": [{"line": L2, "from": KOTO, "to": KOTO_CAPITAL}],
    }
    words, applier = run(lines, tokenizer, mini_dict, rules)
    assert words[KOTO_CAPITAL].freq == 2  # both occurrences in l2
    assert words[KOTO_ZITHER].freq == 2  # l1 and l3
    assert applier.report().applied == 2


def test_a_line_rule_alone_changes_only_that_line(lines, tokenizer, mini_dict):
    words, _ = run(
        lines, tokenizer, mini_dict, {"lines": [{"line": L1, "from": KOTO, "to": KOTO_ZITHER}]}
    )
    assert words[KOTO].freq == 3 and words[KOTO_ZITHER].freq == 1


def test_a_line_rule_can_drop_one_occurrence_line(lines, tokenizer, mini_dict):
    rules = {"lines": [{"line": L2, "from": KOTO, "drop": True}]}
    words, _ = run(lines, tokenizer, mini_dict, rules)
    assert words[KOTO].freq == 2 and L2 not in words[KOTO].examples


# -------------------------------------------------------------------- the report


def test_the_report_counts_rules_and_lists_stale_ones(lines, tokenizer, mini_dict):
    rules = {
        "words": [{"from": KOTO, "to": KOTO_ZITHER}, {"from": KAERU_FROG, "drop": True}],
        "lines": [{"line": "08000099", "from": KOTO, "to": KOTO_CAPITAL}],
    }
    _, applier = run(lines, tokenizer, mini_dict, rules)
    report = applier.report()
    assert (report.rules, report.applied) == (3, 1)
    assert report.unused == [f"word {KAERU_FROG}", f"line 08000099 word {KOTO}"]
    assert report.unknown_ids == []


def test_ids_that_are_not_in_the_dictionary_are_reported_and_the_rule_is_ignored(
    lines, tokenizer, mini_dict
):
    rules = {"words": [{"from": KOTO, "to": 123}, {"from": 456, "drop": True}]}
    words, applier = run(lines, tokenizer, mini_dict, rules)
    assert words[KOTO].freq == 4, "a rule pointing at an unknown entry must not delete the word"
    assert applier.report().unknown_ids == [123, 456]
    assert applier.report().unused == ["word 456"]


def test_has_rule(mini_dict):
    applier = ReviewApplier(
        parse_review(
            {
                "words": [{"from": KOTO, "to": KOTO_ZITHER}],
                "lines": [{"line": L1, "from": KAERU_RETURN, "drop": True}],
            }
        ),
        mini_dict,
    )
    assert applier.has_rule(KOTO) and applier.has_rule(KAERU_RETURN)
    assert not applier.has_rule(SUGOI)


# ---------------------------------------------------------------------- analyze


def test_analyze_applies_a_review_and_leaves_the_input_alone(lines, tokenizer, mini_dict):
    script = Script(
        generator="t",
        game=GameInfo(profile_id="p", title="t", platform="gba", rom_sha1=SHA1),
        lines=lines,
    )
    applier = ReviewApplier(parse_review({"words": [{"from": KOTO, "drop": True}]}), mini_dict)
    source = DictionarySource(date="d", source="s", credit="c")
    result = analyze(script, tokenizer, mini_dict, source, review=applier)
    assert KOTO not in {w.jmdict_id for w in result.words}
    assert script.words == []
    assert len(analysable_lines(script)) == 3
