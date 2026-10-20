"""The step bar on a game's pages, the one Next button on each and the start page's setup list."""

import re

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from support.study import make_script
from support.web import fake_install, finish, make_client, post, raw_script, tokenizer

from yomineko.analyze.dictionary.paths import ENV_VAR
from yomineko.pipeline.workspace import Workspace
from yomineko.script_io import write_script

STEP = re.compile(r'<a href="([^"]*)" class="step (done|current|later)"')
PRIMARY = re.compile(r'<button type="submit">|<a role="button" href="[^"]*">([^<]*)<')


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "games")


@pytest.fixture
def no_dictionary(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "no-dictionary"))


@pytest.fixture
def dictionary(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv(ENV_VAR, str(folder))
    fake_install(folder)()


@pytest.fixture
def client(workspace, no_dictionary):
    write_script(make_script(), workspace.script_path("demo"))
    return make_client(workspace)


def states(html):
    return [state for _, state in STEP.findall(html)]


def primaries(html):
    """Every filled button on the page: an unclassed submit button or link button."""
    return PRIMARY.findall(html)


# -------------------------------------------------------------------- the bar


@pytest.mark.parametrize(
    ("path", "current"),
    [
        ("/games/demo", 2),
        ("/games/demo/lines", 2),
        ("/games/demo/sentences", 2),
        ("/games/demo/words", 3),
        ("/games/demo/choose", 3),
        ("/games/demo/review", 4),
        ("/games/demo/export", 5),
    ],
)
def test_each_page_marks_its_step_current_the_ones_before_done(client, path, current):
    html = client.get(path).text
    expected = ["done"] * (current - 1) + ["current"] + ["later"] * (5 - current)
    assert states(html) == expected
    assert html.count('aria-current="step"') == 1


def test_the_steps_link_to_their_pages(client):
    links = [href for href, _ in STEP.findall(client.get("/games/demo").text)]
    assert links == [
        "/",
        "/games/demo",
        "/games/demo/choose",
        "/games/demo/review",
        "/games/demo/export",
    ]
    for href in links:
        assert client.get(href).status_code == 200


def test_steps_that_need_the_words_are_not_done_before_they_are_found(workspace, no_dictionary):
    write_script(make_script(words=[]), workspace.script_path("demo"))
    html = make_client(workspace).get("/games/demo/export").text
    assert states(html) == ["done", "later", "later", "later", "current"]


def test_a_done_step_shows_a_check_and_says_so(client):
    html = client.get("/games/demo/export").text
    assert html.count("<svg") >= 4 and html.count('<span class="sr-only">Done:</span>') == 4


def test_the_start_and_job_pages_have_no_step_bar(client):
    assert 'class="steps"' not in client.get("/").text


def test_step_four_is_optional_and_counts_the_words_left(workspace, dictionary):
    write_script(raw_script(5), workspace.script_path("demo"))
    client = make_client(workspace, make_tokenizer=lambda: tokenizer(5))
    finish(client, post(client, "/games/demo/analyze"))
    assert '<small class="note">optional</small>' in client.get("/games/demo").text
    finish(client, post(client, "/games/demo/review/prepare"))
    assert '<small class="note">optional, 1 left</small>' in client.get("/games/demo").text


# ---------------------------------------------------------------- next button


@pytest.mark.parametrize(
    ("path", "label"),
    [
        ("/games/demo", "Next: Choose your words"),
        ("/games/demo/choose", "Next: Check the meanings"),
        ("/games/demo/review", "Next: Export"),
    ],
)
def test_each_step_has_one_filled_next_button(client, path, label):
    assert primaries(client.get(path).text) == [label]


def test_the_review_step_can_be_skipped(client):
    html = client.get("/games/demo/review").text
    assert '<a href="/games/demo/export">Skip this step</a>' in html


def test_before_the_words_are_found_finding_them_is_the_one_filled_button(workspace, dictionary):
    write_script(raw_script(), workspace.script_path("demo"))
    html = make_client(workspace).get("/games/demo").text
    assert primaries(html) == [""] and "Find the words</button>" in html


def test_without_the_dictionary_the_game_page_sends_the_user_to_get_it(workspace, no_dictionary):
    write_script(raw_script(), workspace.script_path("demo"))
    html = make_client(workspace).get("/games/demo").text
    assert primaries(html) == ["Next: Get the dictionary"]


def test_the_game_page_offers_a_look_inside(client):
    html = client.get("/games/demo").text
    assert "Look inside" in html
    for page in ("lines", "words", "sentences"):
        assert f'href="/games/demo/{page}"' in html


# --------------------------------------------------------------------- export


def test_export_has_one_download_button_with_the_card_count_next_to_it(client):
    html = client.get("/games/demo/export").text
    assert primaries(html) == [""] and "Download</button>" in html
    summary = html[html.index('class="summary"') :]
    assert "60 word cards" in summary and summary.index("60 word cards") < summary.index(
        "Download</button>"
    )


def test_export_options_are_marked_with_the_formats_they_belong_to(client):
    html = client.get("/games/demo/export").text
    assert '<fieldset class="for-deck">' in html and 'name="decks"' in html
    assert '<fieldset class="for-file">' in html and 'name="content"' in html
    assert '<label class="for-anki">' in html and 'name="deck_name"' in html


# ------------------------------------------------------------------ sentences


def test_the_sentences_hide_the_rom_address_until_asked(client):
    assert "<th>Address</th>" not in client.get("/games/demo/sentences").text
    shown = client.get("/games/demo/sentences?addresses=1").text
    assert "<th>Address</th>" in shown and "Hide the ROM addresses" in shown


# ------------------------------------------------------------------ the start


def test_the_first_run_lists_the_dictionary_then_a_game(workspace, no_dictionary):
    html = make_client(workspace).get("/").text
    assert "Two things to get started" in html
    assert html.index("Get the dictionary") < html.index("Add a game")
    assert '<span class="dot current">1</span>' in html
    assert '<span class="dot later">2</span>' in html
    assert primaries(html) == [""] and "Download the dictionary</button>" in html


def test_with_the_dictionary_adding_a_game_is_next(workspace, dictionary):
    html = make_client(workspace).get("/").text
    assert "Two things to get started" in html and "Installed." in html
    assert '<span class="dot current">2</span>' in html
    assert primaries(html) == [""] and "Read the game's text</button>" in html


def test_once_set_up_the_start_page_just_adds_games(workspace, dictionary):
    write_script(make_script(), workspace.script_path("demo"))
    html = make_client(workspace).get("/").text
    assert "Two things to get started" not in html and "Dictionary installed" in html
    assert '<a href="/games/demo">Demo Game</a>' in html or 'href="/games/demo"' in html
