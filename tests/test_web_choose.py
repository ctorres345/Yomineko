"""The "Choose your words" page: the level and the minimum count, remembered and used everywhere."""

import csv
import io

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from support.study import make_script
from support.web import ORIGIN, make_client, post

from yomineko.pipeline.choices import Choices, load_choices
from yomineko.pipeline.workspace import Workspace
from yomineko.script_io import write_script


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "games")


def ranked(script, common=10):
    """Words 1..``common`` in the dictionary's commonest band, the rest far rarer."""
    words = [
        w.model_copy(update={"jmdict_rank": 1 if w.jmdict_id <= common else 40})
        for w in script.words
    ]
    return script.model_copy(update={"words": words})


@pytest.fixture
def client(workspace):
    write_script(ranked(make_script()), workspace.script_path("demo"))
    return make_client(workspace)


def test_the_page_starts_at_just_starting_with_every_word_a_card(client):
    page = client.get("/games/demo/choose")
    assert page.status_code == 200
    assert "Which words do you already know?" in page.text
    for name in ("Just starting", "The basics", "Intermediate", "Advanced"):
        assert name in page.text
    assert 'value="starting" id="level-starting" checked' in page.text
    assert "60 word cards" in page.text and "Every word gets a card." in page.text
    assert "Nothing is skipped at this level" in page.text
    assert "newspaper" in page.text and "not JLPT levels" in page.text


def test_picking_a_level_saves_it_and_shows_what_it_skips(client, workspace):
    saved = post(client, "/games/demo/choose", level="basics", min_freq="4")
    assert saved.status_code == 303 and saved.headers["location"] == "/games/demo/choose"
    assert load_choices(workspace, "demo") == Choices("basics", 4)
    page = client.get("/games/demo/choose").text
    assert 'value="basics" id="level-basics" checked' in page
    assert "50 word cards" in page and "10 skipped for your level." in page
    assert "Do you know most of these?" in page
    assert page.count('<li><span lang="ja">') == 10  # the sample


def test_a_live_update_returns_the_page_without_a_redirect(client):
    answer = client.post(
        "/games/demo/choose",
        data={"level": "starting", "min_freq": "995"},
        headers={**ORIGIN, "HX-Request": "true"},
        follow_redirects=False,
    )
    assert answer.status_code == 200 and 'id="choose"' in answer.text
    # word n is seen 1000 - n times
    assert "5 word cards" in answer.text and "55 seen fewer than 995 times" in answer.text


def test_an_unknown_level_is_refused(client):
    assert post(client, "/games/demo/choose", level="N5").status_code == 400


def test_the_level_is_remembered_for_the_next_game(client, workspace):
    post(client, "/games/demo/choose", level="advanced", min_freq="6")
    write_script(
        ranked(make_script()).model_copy(
            update={"game": make_script().game.model_copy(update={"profile_id": "other"})}
        ),
        workspace.script_path("other"),
    )
    page = client.get("/games/other/choose").text
    assert 'value="advanced" id="level-advanced" checked' in page
    assert 'name="min_freq" id="min-freq" value="4"' in page  # the minimum belongs to a game


def test_the_words_page_marks_skipped_words(client):
    post(client, "/games/demo/choose", level="basics", min_freq="4")
    page = client.get("/games/demo/words").text
    assert page.count("Skipped, common") == 10
    assert "level The basics" in page


def test_the_export_uses_the_chosen_level_and_minimum(client):
    post(client, "/games/demo/choose", level="basics", min_freq="985")
    form = client.get("/games/demo/export").text
    assert "level The basics" in form and 'placeholder="985' in form
    made = post(client, "/games/demo/export", kind="csv", content="words")
    rows = list(csv.reader(io.StringIO(client.get(made.headers["location"]).text)))
    ids = [int(r[7]) for r in rows[1:] if r and not r[0].startswith("#")]
    assert ids == [11, 12, 13, 14, 15]  # seen 985 times or more, words 1-10 skipped


def test_the_sentences_page_follows_the_level(client):
    post(client, "/games/demo/choose", level="basics", min_freq="1")
    page = client.get("/games/demo/sentences").text
    assert "08000001" not in page  # only words the learner knows: it teaches nothing


def test_a_script_analysed_before_ranks_asks_to_find_the_words_again(workspace):
    write_script(make_script(), workspace.script_path("demo"))
    client = make_client(workspace)
    page = client.get("/games/demo/choose").text
    assert "analysed with an older yomineko" in page and "Find the words again" in page
    assert 'value="basics" id="level-basics" disabled' in page
    assert "60 word cards" in page


def test_a_level_from_another_game_does_not_break_an_older_script(client, workspace):
    write_script(
        make_script().model_copy(
            update={"game": make_script().game.model_copy(update={"profile_id": "old"})}
        ),
        workspace.script_path("old"),
    )
    post(client, "/games/demo/choose", level="basics", min_freq="1")
    assert client.get("/games/old/sentences").status_code == 200
    form = client.get("/games/old/export").text
    assert "level Just starting" in form
    made = post(client, "/games/old/export", kind="csv", content="words")
    assert made.status_code == 303
    # a new minimum on the older game keeps the level picked for the others
    post(client, "/games/old/choose", level="starting", min_freq="2")
    assert load_choices(workspace, "old") == Choices("basics", 2)
    assert load_choices(workspace, "demo").level == "basics"


@pytest.mark.parametrize("value", ["²", "١٢", "x"])
def test_a_minimum_that_is_not_a_plain_number_is_refused(client, value):
    assert post(client, "/games/demo/choose", level="starting", min_freq=value).status_code == 400


def test_a_game_without_words_says_to_find_them_first(workspace):
    script = make_script(words=[], lines=[])
    write_script(script, workspace.script_path("demo"))
    page = make_client(workspace).get("/games/demo/choose").text
    assert "Find the words first" in page and "word cards" not in page


def test_the_game_page_links_to_the_choice(client):
    assert "/games/demo/choose" in client.get("/games/demo").text
