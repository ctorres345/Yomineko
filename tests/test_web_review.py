"""The review screen: look at ambiguous words and correct them."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from support.web import (
    KOTO,
    KOTO_CAPITAL,
    KOTO_ZITHER,
    fake_install,
    finish,
    make_client,
    post,
    raw_script,
    tokenizer,
)

from yomineko.analyze.dictionary.paths import ENV_VAR
from yomineko.analyze.review import load_review
from yomineko.pipeline.reviewing import confirmed
from yomineko.pipeline.workspace import Workspace
from yomineko.script_io import read_script, write_script


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "games")


@pytest.fixture
def data_folder(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv(ENV_VAR, str(folder))
    fake_install(folder)()
    return folder


@pytest.fixture
def client(workspace, data_folder):
    """A game that has been analysed, with the dictionary installed."""
    write_script(raw_script(5), workspace.script_path("demo"))
    client = make_client(workspace, make_tokenizer=lambda: tokenizer(5))
    finish(client, post(client, "/games/demo/analyze"))
    return client


@pytest.fixture
def prepared(client):
    finish(client, post(client, "/games/demo/review/prepare"))
    return client


def rule(client, **data):
    data.setdefault("pick", KOTO)
    return post(client, "/games/demo/review/rule", **data)


# ---------------------------------------------------------------------- page


def test_the_review_page_asks_for_the_list_to_be_prepared(client):
    page = client.get("/games/demo/review")
    assert page.status_code == 200 and "Prepare the words to check" in page.text


def test_a_game_that_is_not_analysed_is_sent_back(workspace, data_folder):
    write_script(raw_script(5), workspace.script_path("demo"))
    page = make_client(workspace).get("/games/demo/review")
    assert "Find the words first" in page.text


def test_preparing_lists_the_ambiguous_word_with_alternatives_and_lines(prepared):
    page = prepared.get("/games/demo/review")
    assert "1 word left to check" in page.text and "seen 5 times" in page.text
    assert page.text.count('name="to"') == 2  # the two alternatives
    assert "l1" in page.text and "(rare)" in page.text  # example line; 古都 is rare


def test_preparing_needs_the_dictionary(workspace, tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "empty"))
    write_script(raw_script(5), workspace.script_path("demo"))
    response = post(make_client(workspace), "/games/demo/review/prepare")
    assert response.status_code == 400 and "Download the dictionary first" in response.text


# --------------------------------------------------------------------- rules


def test_choosing_an_alternative_saves_a_rule_and_clears_the_word(prepared, workspace):
    response = rule(prepared, action="use", to=KOTO_ZITHER)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/games/demo/review")
    saved = load_review(workspace.review_path("demo"))
    assert [(w.from_, w.to, w.sentence_safe) for w in saved.words] == [(KOTO, KOTO_ZITHER, True)]
    page = prepared.get("/games/demo/review")
    assert "0 words left" in page.text
    assert "Your corrections" in page.text
    assert "corrections the word list does not show" in page.text


def test_not_all_lines_keeps_the_correction_off_sentence_cards(prepared, workspace):
    rule(prepared, action="use", to=KOTO_CAPITAL, partial="1")
    assert load_review(workspace.review_path("demo")).words[0].sentence_safe is False


def test_a_word_can_be_dropped(prepared, workspace):
    rule(prepared, action="drop")
    assert load_review(workspace.review_path("demo")).words[0].drop is True


def test_a_meaning_can_be_replaced_with_english(prepared, workspace):
    rule(prepared, action="gloss", gloss="thing; matter")
    assert load_review(workspace.review_path("demo")).words[0].gloss == "thing; matter"


def test_a_meaning_with_japanese_is_refused_with_the_reason(prepared, workspace):
    response = rule(prepared, action="gloss", gloss="こと")
    assert response.status_code == 400 and "never hold game text" in response.text
    assert not workspace.review_path("demo").exists()


def test_confirming_a_pick_is_remembered_without_a_rule(prepared, workspace):
    rule(prepared, action="confirm")
    assert confirmed(workspace, "demo") == {KOTO} and not workspace.review_path("demo").exists()
    assert "0 words left" in prepared.get("/games/demo/review").text


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"pick": 5, "action": "drop"}, "not on the list"),
        ({"action": "use", "to": 12345}, "not one of the alternatives"),
        ({"action": "use"}, "not one of the alternatives"),
        ({"action": "explode"}, "Unknown action"),
    ],
)
def test_wrong_requests_are_explained(prepared, data, message):
    response = rule(prepared, **data)
    assert response.status_code == 400 and message in response.text


def test_a_rule_without_a_prepared_list_is_refused(client):
    response = rule(client, action="drop")
    assert response.status_code == 400 and "not on the list" in response.text


def test_undoing_a_rule_removes_it_and_asks_for_the_list_again(prepared, workspace):
    rule(prepared, action="drop")
    response = post(prepared, "/games/demo/review/remove", pick=KOTO)
    assert response.status_code == 303
    assert load_review(workspace.review_path("demo")).words == []
    page = prepared.get("/games/demo/review")
    assert "Prepare the words to check" in page.text and "Your corrections" not in page.text


def test_applying_the_corrections_changes_the_word_list(prepared, workspace):
    rule(prepared, action="use", to=KOTO_ZITHER)
    finish(prepared, post(prepared, "/games/demo/analyze"))
    assert [w.jmdict_id for w in read_script(workspace.script_path("demo")).words] == [KOTO_ZITHER]
    assert "corrections the word list does not show" not in prepared.get("/games/demo/review").text


def test_the_game_page_links_to_the_review(client):
    assert "/games/demo/review" in client.get("/games/demo").text
