"""Dictionary download, analysis and browsing in the web interface."""

import threading

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from support.study import make_line, make_script
from support.web import fake_install, finish, make_client, post, raw_script, tokenizer

from yomineko.analyze.dictionary.paths import ENV_VAR
from yomineko.errors import MissingExtraError
from yomineko.pipeline.workspace import Workspace
from yomineko.script_io import read_script, write_script


@pytest.fixture
def data_folder(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv(ENV_VAR, str(folder))
    return folder


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "games")


# ------------------------------------------------------------------ dictionary


def test_the_start_page_offers_the_download_until_it_is_installed(workspace, data_folder):
    client = make_client(workspace, install=fake_install(data_folder))
    home = client.get("/")
    assert "Download the dictionary" in home.text and "edrdg.org" in home.text
    status = finish(client, post(client, "/dictionary/download"))
    assert "Done" in status and "14 entries" in status
    after = client.get("/")
    assert "Installed" in after.text and "Download the dictionary" not in after.text


def test_a_failed_download_explains_itself(workspace, data_folder):
    def broken():
        raise MissingExtraError("no network today")

    client = make_client(workspace, install=broken)
    status = finish(client, post(client, "/dictionary/download"))
    assert "did not work" in status and "no network today" in status


def test_the_job_page_polls_while_it_runs(workspace, data_folder):
    gate = threading.Event()

    def slow():
        gate.wait(5)
        return fake_install(data_folder)()

    client = make_client(workspace, install=slow)
    response = post(client, "/dictionary/download")
    page = client.get(response.headers["location"])
    assert 'hx-trigger="every 1s"' in page.text and "aria-busy" in page.text
    gate.set()
    finish(client, response)


def test_a_second_task_shows_the_one_already_running(workspace, data_folder):
    gate = threading.Event()
    client = make_client(workspace, install=lambda: (gate.wait(5), fake_install(data_folder)())[1])
    first = post(client, "/dictionary/download")
    second = post(client, "/dictionary/download")
    assert second.headers["location"] == first.headers["location"]
    gate.set()
    finish(client, first)


def test_an_unknown_job_is_a_404(workspace):
    client = make_client(workspace)
    assert client.get("/jobs/nope").status_code == 404
    assert client.get("/jobs/nope/status").status_code == 404


# -------------------------------------------------------------------- analyse


def test_analysing_a_game_finds_its_words(workspace, data_folder):
    write_script(raw_script(), workspace.script_path("demo"))
    fake_install(data_folder)()
    client = make_client(workspace, make_tokenizer=tokenizer)
    assert "Find the words" in client.get("/games/demo").text
    status = finish(client, post(client, "/games/demo/analyze"))
    assert "Done" in status and "1 distinct word found" in status
    assert [w.jmdict_id for w in read_script(workspace.script_path("demo")).words] == [9000001]
    page = client.get("/games/demo")
    assert "1 distinct word found" in page.text and "Find the words again" in page.text


def test_the_review_the_user_wrote_is_applied(workspace, data_folder):
    write_script(raw_script(), workspace.script_path("demo"))
    workspace.review_path("demo").write_text(
        "words:\n  - {from: 9000001, to: 9000002}\n", encoding="utf-8"
    )
    fake_install(data_folder)()
    client = make_client(workspace, make_tokenizer=tokenizer)
    status = finish(client, post(client, "/games/demo/analyze"))
    assert "Review: 1 of 1 rules applied" in status
    assert [w.jmdict_id for w in read_script(workspace.script_path("demo")).words] == [9000002]


def test_analysing_needs_the_dictionary(workspace, data_folder):
    write_script(raw_script(), workspace.script_path("demo"))
    client = make_client(workspace, make_tokenizer=tokenizer)
    response = post(client, "/games/demo/analyze")
    assert response.status_code == 400 and "Download the dictionary first" in response.text
    assert "The dictionary is needed first" in client.get("/games/demo").text


def test_analysing_a_game_that_was_not_extracted(workspace, data_folder):
    fake_install(data_folder)()
    client = make_client(workspace, make_tokenizer=tokenizer)
    response = post(client, "/games/demo/analyze")
    assert response.status_code == 400 and "not been extracted" in response.text


def test_a_missing_tokenizer_extra_is_shown_as_a_failed_task(workspace, data_folder):
    def missing():
        raise MissingExtraError('install it with: pip install "yomineko[analyze]"')

    write_script(raw_script(), workspace.script_path("demo"))
    fake_install(data_folder)()
    client = make_client(workspace, make_tokenizer=missing)
    status = finish(client, post(client, "/games/demo/analyze"))
    assert "did not work" in status and "yomineko[analyze]" in status
    assert read_script(workspace.script_path("demo")).words == []


# --------------------------------------------------------------------- browse


@pytest.fixture
def analysed(workspace):
    write_script(make_script(), workspace.script_path("demo"))
    return make_client(workspace)


def test_the_words_page_lists_ranked_words(analysed):
    page = analysed.get("/games/demo/words")
    assert page.status_code == 200 and "60 words" in page.text
    assert "meaning 1; extra 1 | second 1" in page.text and "Page 1 of 2" in page.text
    assert "min_freq=1&amp;p=2" in page.text


def test_the_words_page_searches_and_filters(analysed):
    found = analysed.get("/games/demo/words", params={"q": "meaning 5"})
    assert "11 words" in found.text  # 5 and 50 to 59
    assert "9 words" not in found.text
    frequent = analysed.get("/games/demo/words", params={"min_freq": 951})
    assert "49 words" in frequent.text
    assert "0 words" in analysed.get("/games/demo/words", params={"q": "zzz"}).text


def test_the_second_page_of_words(analysed):
    page = analysed.get("/games/demo/words", params={"p": 2})
    assert "Page 2 of 2" in page.text and "ことば60" in page.text and "ことば1<" not in page.text


def test_words_of_a_game_that_is_not_analysed(workspace):
    write_script(raw_script(), workspace.script_path("demo"))
    page = make_client(workspace).get("/games/demo/words")
    assert page.status_code == 200 and "has not been analysed yet" in page.text


def test_the_lines_page_searches_and_filters_by_kind(workspace):
    lines = [
        make_line(1, "ようこそ　あたらしいまちへ。", [1, 2]),
        make_line(2, "ボタン", [], kind="term"),
        make_line(3, "<b>きょう</b>", [], kind="term"),
    ]
    write_script(make_script(lines=lines), workspace.script_path("demo"))
    client = make_client(workspace)
    everything = client.get("/games/demo/lines")
    assert "3 lines" in everything.text and "&lt;b&gt;きょう" in everything.text
    assert "<b>きょう" not in everything.text, "game text is escaped"
    assert "2 lines" in client.get("/games/demo/lines", params={"kind": "term"}).text
    assert "1 line<" in client.get("/games/demo/lines", params={"q": "あたらしい"}).text
    assert "1 line<" in client.get("/games/demo/lines", params={"kind": "dialogue"}).text


def test_the_sentences_page_shows_the_picks(analysed):
    page = analysed.get("/games/demo/sentences")
    assert page.status_code == 200 and "5 sentences" in page.text
    assert "ようこそ　あたらしいまちへ。" in page.text
    assert "3 sentences" in analysed.get("/games/demo/sentences", params={"count": 3}).text


def test_sentences_of_a_game_analysed_by_an_older_version_say_so(workspace):
    lines = [make_line(1, "ようこそ　あたらしいまちへ。")]  # no word ids
    write_script(make_script(lines=lines), workspace.script_path("demo"))
    page = make_client(workspace).get("/games/demo/sentences")
    assert page.status_code == 400 and "analyze" in page.text


def test_the_sentences_use_the_users_review(workspace):
    write_script(make_script(), workspace.script_path("demo"))
    workspace.review_path("demo").write_text(
        'sentences:\n  exclude: ["08000001"]\n', encoding="utf-8"
    )
    page = make_client(workspace).get("/games/demo/sentences")
    assert "4 sentences" in page.text and "ようこそ" not in page.text


def test_paging_the_sentences_reuses_the_selection_until_an_input_changes(workspace, monkeypatch):
    import os

    from yomineko.web import app as web_app

    calls = []
    real = web_app.choose_sentences

    def counted(*args, **kwargs):
        calls.append(kwargs["count"])
        return real(*args, **kwargs)

    monkeypatch.setattr(web_app, "choose_sentences", counted)
    write_script(make_script(), workspace.script_path("demo"))
    client = make_client(workspace)
    for p in (1, 2, 1):
        assert client.get("/games/demo/sentences", params={"p": p}).status_code == 200
    assert calls == [1000]
    client.get("/games/demo/sentences", params={"count": 3})
    assert calls == [1000, 3]
    review = workspace.review_path("demo")
    review.write_text('sentences:\n  exclude: ["08000001"]\n', encoding="utf-8")
    page = client.get("/games/demo/sentences", params={"count": 3})
    assert calls == [1000, 3, 3] and "ようこそ" not in page.text
    review.write_text("sentences:\n  exclude: []\n", encoding="utf-8")
    stat = review.stat()
    os.utime(review, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    client.get("/games/demo/sentences", params={"count": 3})
    assert calls == [1000, 3, 3, 3]


def test_browse_pages_of_a_missing_game_are_clean_errors(workspace):
    client = make_client(workspace)
    for part in ("words", "lines", "sentences"):
        page = client.get(f"/games/demo/{part}")
        assert page.status_code == 400 and "not been extracted" in page.text


def test_the_script_is_read_again_when_the_file_changes(workspace):
    write_script(make_script(), workspace.script_path("demo"))
    client = make_client(workspace)
    assert "60 words" in client.get("/games/demo/words").text
    write_script(make_script(words=make_script().words[:10]), workspace.script_path("demo"))
    assert "10 words" in client.get("/games/demo/words").text
