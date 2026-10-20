import pytest
from pydantic import ValidationError

from yomineko.analyze.review import (
    LineRule,
    Review,
    ReviewError,
    WordRule,
    load_review,
    merge_reviews,
    packaged_review,
    parse_review,
)

SHA1 = "0123456789abcdef0123456789abcdef01234567"


def write(tmp_path, text, name="review.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------ word rules


def test_a_review_with_every_kind_of_rule(tmp_path):
    path = write(
        tmp_path,
        f"""
schema_version: 1
profile: some-game
rom_sha1: "{SHA1}"
words:
  - {{from: 1, to: 2}}
  - {{from: 3, to: 4, sentence_safe: false}}
  - {{from: 5, drop: true}}
  - {{from: 6, gloss: "amazing; great"}}
lines:
  - {{line: "0810ABCD", from: 1, to: 7}}
  - {{line: "0810ABCE", from: 1, drop: true}}
""",
    )
    review = load_review(path)
    assert [(r.from_, r.to, r.drop, r.sentence_safe) for r in review.words] == [
        (1, 2, False, True),
        (3, 4, False, False),
        (5, None, True, True),
        (6, None, False, True),
    ]
    assert review.words[3].gloss == "amazing; great"
    assert [(r.line, r.to, r.drop) for r in review.lines] == [
        ("0810ABCD", 7, False),
        ("0810ABCE", None, True),
    ]


def test_an_empty_review_is_valid(tmp_path):
    assert load_review(write(tmp_path, "")).words == []
    assert parse_review(None).lines == []


@pytest.mark.parametrize(
    "rule",
    [
        {"from": 1},  # does nothing
        {"from": 1, "drop": True, "to": 2},
        {"from": 1, "drop": True, "gloss": "x"},
        {"from": 1, "to": 1},  # to itself
        {"from": 0, "to": 2},
        {"from": 1, "to": -2},
        {"from": 1, "gloss": "   "},
        {"from": 1, "gloss": "日本語の意味"},  # game text does not belong in a review
        {"from": 1, "to": 2, "surprise": True},
        {"to": 2},
    ],
)
def test_bad_word_rules_are_rejected(rule):
    with pytest.raises(ValidationError):
        WordRule.model_validate(rule)


def test_a_rule_can_be_built_in_code_with_the_python_friendly_name():
    assert WordRule(from_=1, to=2).from_ == 1


def test_a_gloss_is_trimmed():
    assert WordRule.model_validate({"from": 1, "gloss": "  hello  "}).gloss == "hello"


# ------------------------------------------------------------------ line rules


@pytest.mark.parametrize(
    "rule",
    [
        {"line": "0810ABCD", "from": 1},  # neither to nor drop
        {"line": "0810ABCD", "from": 1, "to": 2, "drop": True},
        {"line": "0810abcd", "from": 1, "to": 2},  # lower case
        {"line": "810ABCD", "from": 1, "to": 2},  # too short
        {"line": "0810ABCD", "from": 3, "to": 3},
    ],
)
def test_bad_line_rules_are_rejected(rule):
    with pytest.raises(ValidationError):
        LineRule.model_validate(rule)


def test_an_unquoted_numeric_line_id_is_caught_instead_of_silently_misread(tmp_path):
    """YAML reads 01001000 as an octal number; the error says to quote it."""
    path = write(tmp_path, "lines:\n  - {line: 01001000, from: 1, to: 2}\n")
    with pytest.raises(ReviewError, match="quote the line id"):
        load_review(path)


def test_an_unquoted_hex_line_id_that_is_not_a_number_is_fine(tmp_path):
    path = write(tmp_path, "lines:\n  - {line: 0810ABCD, from: 1, to: 2}\n")
    assert load_review(path).lines[0].line == "0810ABCD"


# ----------------------------------------------------------------- whole file


def test_duplicate_rules_are_rejected():
    with pytest.raises(ReviewError, match="more than one word rule for entry 1"):
        parse_review({"words": [{"from": 1, "to": 2}, {"from": 1, "drop": True}]})
    with pytest.raises(ReviewError, match="more than one line rule"):
        parse_review(
            {
                "lines": [
                    {"line": "0810ABCD", "from": 1, "to": 2},
                    {"line": "0810ABCD", "from": 1, "drop": True},
                ]
            }
        )


def test_the_same_word_may_have_rules_for_different_lines():
    review = parse_review(
        {
            "lines": [
                {"line": "0810ABCD", "from": 1, "to": 2},
                {"line": "0810ABCE", "from": 1, "to": 3},
            ]
        }
    )
    assert len(review.lines) == 2


@pytest.mark.parametrize("data", [{"schema_version": 2}, {"rom_sha1": "XYZ"}, {"surprise": 1}, [1]])
def test_bad_files_are_rejected(data):
    with pytest.raises(ReviewError, match="invalid review"):
        parse_review(data)


def test_unreadable_and_unparseable_files(tmp_path):
    with pytest.raises(ReviewError, match="cannot read review file"):
        load_review(tmp_path / "nope.yaml")
    with pytest.raises(ReviewError, match="not valid YAML"):
        load_review(write(tmp_path, "words: [unclosed"))
    with pytest.raises(ReviewError, match="invalid review"):
        load_review(write(tmp_path, "- just\n- a list\n"))


def test_errors_name_the_file_and_the_field(tmp_path):
    path = write(tmp_path, "words:\n  - {from: 1, gloss: ''}\n", "mine.yaml")
    with pytest.raises(ReviewError) as error:
        load_review(path)
    assert "mine.yaml" in str(error.value) and "words.0.gloss" in str(error.value)


# ------------------------------------------------------------------ check_for


def test_a_review_for_another_rom_or_game_is_refused():
    review = Review(rom_sha1=SHA1, profile="game-a")
    review.check_for(SHA1, "game-a")
    with pytest.raises(ReviewError, match="is for ROM"):
        review.check_for("f" * 40, "game-a")
    with pytest.raises(ReviewError, match="not 'game-b'"):
        review.check_for(SHA1, "game-b")


def test_a_review_without_a_rom_or_profile_fits_anything():
    Review().check_for("f" * 40, "anything")


# ----------------------------------------------------------------------- merge


def test_a_later_review_replaces_an_earlier_rule_for_the_same_word():
    base = parse_review({"words": [{"from": 1, "to": 2}, {"from": 3, "drop": True}]})
    mine = parse_review({"words": [{"from": 1, "to": 9}]})
    merged = merge_reviews([base, mine])
    assert {r.from_: r.to for r in merged.words} == {1: 9, 3: None}


def test_line_rules_merge_by_line_and_entry():
    a = parse_review({"lines": [{"line": "0810ABCD", "from": 1, "to": 2}]})
    b = parse_review(
        {
            "lines": [
                {"line": "0810ABCD", "from": 1, "to": 5},
                {"line": "0810ABCE", "from": 1, "to": 6},
            ]
        }
    )
    merged = merge_reviews([a, b])
    assert {(r.line, r.to) for r in merged.lines} == {("0810ABCD", 5), ("0810ABCE", 6)}


def test_merging_nothing_gives_an_empty_review():
    assert merge_reviews([]).words == []


# -------------------------------------------------------------------- packaged


def test_a_game_without_a_packaged_review_gets_none():
    assert packaged_review("no-such-game") is None


# ------------------------------------------------------------ sentence rules


def test_sentence_rules_are_line_ids():
    review = parse_review({"sentences": {"exclude": ["0810ABCD", "0810ABCE"], "pin": ["0810ABCF"]}})
    assert review.sentences.exclude == ["0810ABCD", "0810ABCE"]
    assert review.sentences.pin == ["0810ABCF"]
    assert parse_review({}).sentences.exclude == []


@pytest.mark.parametrize(
    "bad",
    [
        {"exclude": [810123]},  # unquoted: YAML read it as a number
        {"exclude": ["0810abcd"]},  # lower case
        {"pin": ["abc"]},
        {"exclude": ["0810ABCD"], "pin": ["0810ABCD"]},  # both
        {"surprise": []},
    ],
)
def test_bad_sentence_rules_are_rejected(bad):
    with pytest.raises(ReviewError):
        parse_review({"sentences": bad})


def test_sentence_rules_load_from_yaml_and_merge_with_later_files_winning(tmp_path):
    first = load_review(
        write(tmp_path, 'sentences:\n  exclude: ["0810ABCD", "0810ABCE"]\n  pin: ["0810ABCF"]\n')
    )
    second = load_review(
        write(tmp_path, 'sentences:\n  exclude: ["0810ABCF"]\n  pin: ["0810ABCD"]\n', "b.yaml")
    )
    merged = merge_reviews([first, second])
    assert merged.sentences.exclude == ["0810ABCE", "0810ABCF"]
    assert merged.sentences.pin == ["0810ABCD"]
