"""Words marked "I know this": kept as JMdict ids for every game, and left out of every deck."""

import csv
import io
import json
import threading
import time

import pytest
from support.dictionary import fake_urlopen, mini_gz_bytes
from support.study import make_script
from typer.testing import CliRunner

from yomineko.analyze.dictionary.install import install_dictionary
from yomineko.analyze.dictionary.paths import ENV_VAR
from yomineko.cli.app import app
from yomineko.errors import YominekoError
from yomineko.export.level import choose_words, word_status
from yomineko.export.sentences import select_sentences
from yomineko.export.study import build_study
from yomineko.export.words_export import select_words
from yomineko.model import Word
from yomineko.pipeline import known as known_module
from yomineko.pipeline.exporting import ExportRequest, build_export
from yomineko.pipeline.known import (
    known_path,
    load_known,
    mark_known,
    save_known,
    unmark_known,
)
from yomineko.pipeline.workspace import Workspace
from yomineko.script_io import write_script


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "games")


def word(entry_id, rank, freq=10):
    return Word(jmdict_id=entry_id, written=f"w{entry_id}", kana="k", freq=freq, jmdict_rank=rank)


# ---------------------------------------------------------------------- the file


def test_marking_and_unmarking_round_trip(workspace):
    assert load_known(workspace) == frozenset()
    assert mark_known(workspace, [30, 7]) == {7, 30}
    assert mark_known(workspace, [7]) == {7, 30}
    assert load_known(workspace) == {7, 30}
    assert unmark_known(workspace, [30]) == {7}
    assert unmark_known(workspace, [7]) == frozenset()
    assert not known_path(workspace).exists()  # nothing left: no file


def test_the_file_holds_jmdict_ids_only(workspace):
    mark_known(workspace, [1578850, 1000220])
    data = json.loads(known_path(workspace).read_text(encoding="utf-8"))
    assert data == {"jmdict_ids": [1000220, 1578850]}
    assert all(type(i) is int for i in data["jmdict_ids"])


def test_the_file_sits_in_the_workspace_not_in_a_game(workspace):
    mark_known(workspace, [5])
    assert known_path(workspace) == workspace.root / "known.json"


@pytest.mark.parametrize(
    "text",
    ["not json", "[1, 2]", '{"jmdict_ids": "12"}', '{"other": [1]}'],
)
def test_a_damaged_file_means_no_known_words(workspace, text):
    workspace.root.mkdir(parents=True)
    known_path(workspace).write_text(text, encoding="utf-8")
    assert load_known(workspace) == frozenset()


@pytest.mark.parametrize("change", [mark_known, unmark_known])
def test_a_damaged_file_is_left_as_it_is_not_written_over(workspace, change):
    workspace.root.mkdir(parents=True)
    damaged = '{"jmdict_ids": [1, 2, 3,]}'
    known_path(workspace).write_text(damaged, encoding="utf-8")
    with pytest.raises(YominekoError, match="damaged"):
        change(workspace, [99])
    assert known_path(workspace).read_text(encoding="utf-8") == damaged


def test_marks_made_at_the_same_time_are_all_kept(workspace, monkeypatch):
    save_known(workspace, range(1, 3001))
    read = known_module._read

    def slow_read(path):  # every thread reads before any writes, unless the lock orders them
        ids = read(path)
        time.sleep(0.02)
        return ids

    monkeypatch.setattr(known_module, "_read", slow_read)
    threads = [threading.Thread(target=mark_known, args=(workspace, [5000 + i])) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert load_known(workspace) == set(range(1, 3001)) | {5000 + i for i in range(8)}
    assert [p.name for p in workspace.root.iterdir()] == ["known.json"]


def test_anything_but_an_id_in_the_list_is_ignored(workspace):
    workspace.root.mkdir(parents=True)
    known_path(workspace).write_text(
        '{"jmdict_ids": [4, "事", true, -2, 0, 1.5, 9]}', encoding="utf-8"
    )
    assert load_known(workspace) == {4, 9}


# ----------------------------------------------------------- one rule, every consumer


def test_a_known_word_says_so_before_the_level_or_the_count():
    assert word_status(word(1, 1), level="basics", min_freq=4, known={1}) == "known"
    assert word_status(word(1, 1), level="basics", min_freq=4) == "skipped"
    assert word_status(word(2, 40, 2), level="basics", min_freq=4, known={2}) == "known"
    assert word_status(word(2, 40, 2), level="basics", min_freq=4) == "rare"
    assert word_status(word(3, 40), level="basics", min_freq=4) == "card"


def test_choose_words_counts_the_known_words_seen_often_enough():
    script = make_script(
        words=[word(1, 1, 50), word(2, 30, 40), word(3, 30, 30), word(4, 100, 2), word(5, 2, 9)]
    )
    choice = choose_words(script, level="basics", min_freq=4, known={3, 4, 5})
    assert (choice.cards, choice.skipped, choice.known, choice.rare) == (1, 1, 2, 0)
    # a word marked known is not offered again in the "do you know these?" sample
    assert [w.jmdict_id for w in choice.sample] == [1]
    assert choose_words(script, level="starting", min_freq=4).known == 0


def test_known_words_need_no_rank():
    script = make_script()  # analysed before schema 4
    assert choose_words(script, level="starting", min_freq=1, known={1, 2}).cards == 58
    assert len(select_words(script, 1, "starting", {1, 2})) == 58


def test_the_word_list_leaves_out_known_words_and_keeps_ranks():
    script = make_script()
    picked = select_words(script, 1, known={1, 3})
    assert [rank for rank, _ in picked][:3] == [2, 4, 5] and len(picked) == 58


def test_the_sentence_picker_teaches_no_known_word():
    script = make_script()
    known = set(range(1, 11))
    every = select_sentences(script, min_freq=1)
    fewer = select_sentences(script, min_freq=1, known=known)
    # line 1 holds words 1 and 2 only: nothing left to teach
    assert "08000001" in [s.line.id for s in every]
    assert "08000001" not in [s.line.id for s in fewer]
    assert all(s.word_ids and not known & set(s.word_ids) for s in fewer)


def test_the_deck_has_no_card_for_a_known_word():
    script = make_script()
    picked = select_sentences(script, min_freq=1, known={1, 2})
    study = build_study(script, picked, min_freq=1, known={1, 2})
    assert study.words and not {1, 2} & {w.jmdict_id for w in study.words}


def test_every_export_skips_known_words():
    script = make_script()
    words = build_export(script, ExportRequest(format="csv", content="words", known={1, 2}))
    assert words.summary == "Exported 58 words"
    as_json = build_export(script, ExportRequest(format="json", content="words", known={1}))
    assert as_json.summary == "Exported 59 words"
    deck = build_export(script, ExportRequest(format="xlsx", min_freq=1, known={1, 2}))
    assert "(58 words," in deck.summary
    sentences = build_export(
        script, ExportRequest(format="csv", content="sentences", min_freq=1, known={1, 2})
    )
    assert "08000001" not in sentences.data.decode("utf-8-sig")


# ------------------------------------------------------------------ command line


def test_the_known_command_lists_adds_removes_and_clears(tmp_path, monkeypatch):
    monkeypatch.setattr("yomineko.cli.known_cmd.dictionary_info", lambda: None)
    runner = CliRunner()
    folder = str(tmp_path / "ws")
    empty = runner.invoke(app, ["known", "list", "--workspace", folder])
    assert empty.exit_code == 0 and "No words are marked as known" in empty.output
    added = runner.invoke(app, ["known", "add", "1000220", "1578850", "--workspace", folder])
    assert added.exit_code == 0 and "2 known words" in added.output
    listed = runner.invoke(app, ["known", "list", "--workspace", folder])
    assert listed.output.splitlines()[:2] == ["1000220", "1578850"]
    removed = runner.invoke(app, ["known", "remove", "1000220", "--workspace", folder])
    assert "1 known word." in removed.output
    refused = runner.invoke(app, ["known", "clear", "--workspace", folder], input="n\n")
    assert refused.exit_code != 0
    assert load_known(Workspace(tmp_path / "ws")) == {1578850}
    cleared = runner.invoke(app, ["known", "clear", "--yes", "--workspace", folder])
    assert cleared.exit_code == 0 and "Forgot 1 known word." in cleared.output
    assert load_known(Workspace(tmp_path / "ws")) == frozenset()


def test_the_known_list_shows_meanings_and_no_japanese(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "data"))
    urlopen, _ = fake_urlopen(mini_gz_bytes(), {})
    install_dictionary(url="https://example.test/j.gz", folder=tmp_path / "data", urlopen=urlopen)
    folder = str(tmp_path / "ws")
    CliRunner().invoke(app, ["known", "add", "9000001", "--workspace", folder])
    listed = CliRunner().invoke(app, ["known", "list", "--workspace", folder])
    assert listed.exit_code == 0
    assert listed.output.splitlines()[0] == "9000001\tthing (abstract); matter"
    assert listed.output.isascii()  # a cp1252 console can print every line


def test_the_known_command_refuses_what_is_not_an_id(tmp_path):
    result = CliRunner().invoke(
        app, ["known", "add", "0", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 1 and "not a JMdict entry id" in result.output


def test_export_leaves_out_known_words_unless_told_not_to(tmp_path):
    folder = Workspace(tmp_path / "ws")
    script_path = folder.script_path("demo")
    write_script(make_script(), script_path)
    mark_known(folder, [1, 2])
    runner = CliRunner()
    out = tmp_path / "words.csv"
    args = ["export", str(script_path), "-f", "csv", "--content", "words", "-o", str(out)]
    done = runner.invoke(app, [*args, "--workspace", str(folder.root)])
    assert done.exit_code == 0 and "Exported 58 words" in done.output
    rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8-sig"))))
    assert {"1", "2"}.isdisjoint(r[7] for r in rows[1:] if r and not r[0].startswith("#"))
    every = runner.invoke(app, [*args, "--workspace", str(folder.root), "--no-known"])
    assert "Exported 60 words" in every.output
