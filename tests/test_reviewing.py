"""The user's own review file, the confirmed words and the worklist behind the review screen."""

from pathlib import Path

import pytest
import yaml
from support.dictionary import fake_urlopen, mini_gz_bytes
from support.tokens import FakeTokenizer, tok
from support.web import KOTO, KOTO_CAPITAL, KOTO_ZITHER, SHA1, raw_script

from yomineko.analyze.dictionary.install import install_dictionary
from yomineko.analyze.dictionary.paths import ENV_VAR
from yomineko.analyze.review import (
    LineRule,
    Review,
    SentenceRules,
    WordRule,
    load_review,
    parse_review,
    review_data,
    save_review,
)
from yomineko.pipeline.reviewing import (
    confirm,
    confirmed,
    prepare_worklist,
    remove_word_rule,
    set_word_rule,
    user_review,
)
from yomineko.pipeline.workspace import Workspace


def rule(**kw):
    return WordRule.model_validate(kw)


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "games")


@pytest.fixture
def installed(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv(ENV_VAR, str(folder))
    urlopen, _ = fake_urlopen(mini_gz_bytes(), {"Last-Modified": "Sat, 03 Oct 2026 03:30:23 GMT"})
    install_dictionary(url="https://example.test/j.gz", folder=folder, urlopen=urlopen)
    return folder


# -------------------------------------------------------------- saving a review


def test_a_review_survives_a_save_and_a_load(tmp_path):
    review = Review(
        profile="demo",
        rom_sha1=SHA1,
        words=[
            rule(**{"from": 1, "to": 2, "sentence_safe": False}),
            rule(**{"from": 3, "drop": True}),
            rule(**{"from": 4, "gloss": "amazing; great"}),
        ],
        lines=[
            LineRule.model_validate({"line": "0810ABCD", "from": 1, "to": 5}),
            LineRule.model_validate({"line": "08000001", "from": 6, "drop": True}),
        ],
        sentences=SentenceRules(exclude=["08000009"], pin=["0810ABCE"]),
    )
    path = save_review(review, tmp_path / "out" / "review.yaml")
    assert load_review(path) == review


def test_the_saved_file_uses_the_documented_spelling_and_quotes_line_ids(tmp_path):
    review = Review(
        words=[rule(**{"from": 1, "to": 2})],
        lines=[LineRule.model_validate({"line": "08000001", "from": 1, "drop": True})],
    )
    text = save_review(review, tmp_path / "r.yaml").read_text(encoding="utf-8")
    assert text.startswith("# Your corrections") and "from: 1" in text and "from_" not in text
    # a string, not the number 8000001
    assert yaml.safe_load(text)["lines"][0]["line"] == "08000001"


def test_a_failed_save_leaves_the_old_review_whole(tmp_path, monkeypatch):
    path = save_review(Review(), tmp_path / "r.yaml")
    before = path.read_bytes()

    def interrupted(self, *args, **kwargs):
        Path.write_bytes(self, b"words:\n  - id")  # half a file, then the app stops
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "write_text", interrupted)
    with pytest.raises(KeyboardInterrupt):
        save_review(Review(), path)
    monkeypatch.undo()
    assert path.read_bytes() == before


def test_an_empty_review_saves_and_loads(tmp_path):
    path = save_review(Review(), tmp_path / "r.yaml")
    assert load_review(path) == Review() and review_data(Review()) == {"schema_version": 1}


# ------------------------------------------------------------------ user rules


def test_a_new_rule_creates_the_users_review_for_this_game(workspace):
    script = raw_script()
    assert user_review(workspace, "demo") == Review()
    set_word_rule(workspace, "demo", script, rule(**{"from": KOTO, "to": KOTO_ZITHER}))
    review = user_review(workspace, "demo")
    assert [(w.from_, w.to) for w in review.words] == [(KOTO, KOTO_ZITHER)]
    assert (review.profile, review.rom_sha1) == ("demo", SHA1)


def test_a_second_rule_for_the_same_word_replaces_the_first(workspace):
    script = raw_script()
    set_word_rule(workspace, "demo", script, rule(**{"from": KOTO, "to": KOTO_ZITHER}))
    set_word_rule(workspace, "demo", script, rule(**{"from": 7, "drop": True}))
    set_word_rule(workspace, "demo", script, rule(**{"from": KOTO, "to": KOTO_CAPITAL}))
    words = user_review(workspace, "demo").words
    assert [(w.from_, w.to, w.drop) for w in words] == [
        (7, None, True),
        (KOTO, KOTO_CAPITAL, False),
    ]


def test_removing_a_rule_says_whether_there_was_one(workspace):
    set_word_rule(workspace, "demo", raw_script(), rule(**{"from": KOTO, "drop": True}))
    assert remove_word_rule(workspace, "demo", 5) is False
    assert remove_word_rule(workspace, "demo", KOTO) is True
    assert user_review(workspace, "demo").words == []


def test_other_parts_of_the_users_review_are_kept(workspace):
    path = workspace.review_path("demo")
    path.parent.mkdir(parents=True)
    path.write_text('sentences:\n  exclude: ["08000009"]\n', encoding="utf-8")
    set_word_rule(workspace, "demo", raw_script(), rule(**{"from": KOTO, "drop": True}))
    assert user_review(workspace, "demo").sentences.exclude == ["08000009"]
    remove_word_rule(workspace, "demo", KOTO)
    assert user_review(workspace, "demo").sentences.exclude == ["08000009"]


# ------------------------------------------------------------ confirmed words


def test_confirmed_words_are_remembered(workspace):
    assert confirmed(workspace, "demo") == set()
    confirm(workspace, "demo", 12)
    confirm(workspace, "demo", 5)
    confirm(workspace, "demo", 12)
    assert confirmed(workspace, "demo") == {5, 12}


@pytest.mark.parametrize(
    "content", ["not json", "[1]", '{"confirmed": "x"}', '{"confirmed": ["a"]}']
)
def test_a_damaged_state_file_counts_as_nothing_confirmed(workspace, content):
    path = workspace.game_dir("demo") / "review-state.json"
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    assert confirmed(workspace, "demo") == set()


# ------------------------------------------------------------------- worklist


def tokenizer():
    return FakeTokenizer({f"l{n}": [tok("こと")] for n in range(1, 6)})


def test_the_worklist_has_the_ambiguous_words_with_their_alternatives(workspace, installed):
    items = prepare_worklist(workspace, "demo", raw_script(5), tokenizer)
    assert [i.pick.entry_id for i in items] == [KOTO] and items[0].freq == 5
    assert [a.entry_id for a in items[0].alternatives] == [KOTO_ZITHER, KOTO_CAPITAL]
    assert len(items[0].examples) == 3


def test_a_word_with_a_rule_or_a_confirmation_leaves_the_worklist(workspace, installed):
    script = raw_script(5)
    set_word_rule(workspace, "demo", script, rule(**{"from": KOTO, "to": KOTO_ZITHER}))
    assert prepare_worklist(workspace, "demo", script, tokenizer) == []
    remove_word_rule(workspace, "demo", KOTO)
    assert len(prepare_worklist(workspace, "demo", script, tokenizer)) == 1
    confirm(workspace, "demo", KOTO)
    assert prepare_worklist(workspace, "demo", script, tokenizer) == []


def test_rarely_seen_words_are_not_listed(workspace, installed):
    assert prepare_worklist(workspace, "demo", raw_script(3), tokenizer) == []  # seen 3 times


def test_a_review_made_for_another_rom_is_refused(workspace, installed):
    save_review(
        parse_review({"rom_sha1": "f" * 40, "words": [{"from": 1, "drop": True}]}),
        workspace.review_path("demo"),
    )
    with pytest.raises(Exception, match="is for ROM"):
        prepare_worklist(workspace, "demo", raw_script(5), tokenizer)
