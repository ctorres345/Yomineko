"""The "I know this" button on the Choose and words pages: the card count follows at once."""

import csv
import io
import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from support.study import make_script
from support.web import ORIGIN, make_client, post

from yomineko.pipeline.known import known_path, load_known
from yomineko.pipeline.workspace import Workspace
from yomineko.script_io import write_script

LIVE = {**ORIGIN, "HX-Request": "true"}


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "games")


def ranked(script):
    """Words 1-10 in the dictionary's commonest band, the rest far rarer."""
    words = [
        w.model_copy(update={"jmdict_rank": 1 if w.jmdict_id <= 10 else 40}) for w in script.words
    ]
    return script.model_copy(update={"words": words})


def as_game(script, game_id):
    return script.model_copy(
        update={"game": script.game.model_copy(update={"profile_id": game_id})}
    )


@pytest.fixture
def client(workspace):
    write_script(ranked(make_script()), workspace.script_path("demo"))
    return make_client(workspace)


def live(client, url, **data):
    return client.post(url, data=data, headers=LIVE, follow_redirects=False)


def test_the_choose_page_lists_the_words_with_i_know_this(client):
    page = client.get("/games/demo/choose").text
    assert "The words" in page and page.count(">I know this</button>") == 50  # one page
    assert "Top 1,000" in page and "Top 24,000" in page  # how common, from the rank
    assert "Page 1 of 2" in page


def test_i_know_this_updates_the_card_count_at_once(client, workspace):
    answer = live(client, "/games/demo/known", word="12", action="know", back="choose")
    assert answer.status_code == 200 and 'id="choose"' in answer.text
    assert "59 word cards" in answer.text and "1 you know." in answer.text
    assert "You know it" in answer.text and ">Undo</button>" in answer.text
    assert load_known(workspace) == {12}
    undone = live(client, "/games/demo/known", word="12", action="undo", back="choose")
    assert "60 word cards" in undone.text and "you know" not in undone.text
    assert load_known(workspace) == frozenset()


def test_known_and_skipped_words_are_counted_apart(client):
    post(client, "/games/demo/choose", level="basics", min_freq="1")
    page = live(client, "/games/demo/known", word="20", action="know").text
    assert "49 word cards" in page and "10 skipped for your level, 1 you know." in page
    # a word the level already skips has no button: there is nothing to mark
    assert page.count(">I know this</button>") == 39


def test_the_file_holds_ids_only_and_serves_every_game(client, workspace):
    live(client, "/games/demo/known", word="15", action="know")
    assert json.loads(known_path(workspace).read_text(encoding="utf-8")) == {"jmdict_ids": [15]}
    write_script(as_game(ranked(make_script()), "other"), workspace.script_path("other"))
    page = client.get("/games/other/choose").text
    assert "59 word cards" in page and "1 you know." in page


def test_a_plain_post_goes_back_to_the_page_it_came_from(client):
    answer = post(client, "/games/demo/known", word="51", action="know", p="2")
    assert answer.status_code == 303 and answer.headers["location"] == "/games/demo/choose?p=2"
    back = post(
        client, "/games/demo/known", word="51", action="undo", back="words", q="w", min_freq="3"
    )
    assert back.headers["location"] == "/games/demo/words?q=w&min_freq=3&p=1"


def test_a_word_not_in_the_game_or_an_unknown_action_is_refused(client, workspace):
    assert post(client, "/games/demo/known", word="999999", action="know").status_code == 400
    assert post(client, "/games/demo/known", word="12", action="forget").status_code == 400
    assert load_known(workspace) == frozenset()


def test_the_words_page_marks_known_words_and_has_the_buttons(client):
    page = client.get("/games/demo/words").text
    assert page.count(">I know this</button>") == 50
    answer = live(client, "/games/demo/known", word="3", action="know", back="words", q="")
    assert answer.status_code == 200 and 'id="results"' in answer.text
    assert answer.text.count("You know it") == 1 and ">Undo</button>" in answer.text


def test_the_export_and_the_sentences_leave_out_known_words(client):
    post(client, "/games/demo/choose", level="starting", min_freq="1")
    live(client, "/games/demo/known", word="1", action="know")
    live(client, "/games/demo/known", word="2", action="know")
    form = client.get("/games/demo/export").text
    assert "leaving out the 2 words you marked as known" in form
    assert "58 cards" in form  # the count the deck will have
    made = post(client, "/games/demo/export", kind="csv", content="words")
    rows = list(csv.reader(io.StringIO(client.get(made.headers["location"]).text)))
    ids = {int(r[7]) for r in rows[1:] if r and not r[0].startswith("#")}
    assert len(ids) == 58 and not ids & {1, 2}
    # line 1 holds words 1 and 2 only: it teaches nothing now
    assert "08000001" not in client.get("/games/demo/sentences").text
