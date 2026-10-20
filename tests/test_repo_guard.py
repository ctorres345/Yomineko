"""The guard that keeps ROMs and game text out of the repository (tools/repo_guard.py)."""

import json

import pytest
import repo_guard

JAPANESE_LINE = "あいうえおかきくけこさしすせそ"  # 15 characters in a row


@pytest.mark.parametrize(
    "path", ["game.gba", "a/b/game.NDS", "dump.zip", "deck.apkg", "x.7z", "rom.GBC", "d.iso"]
)
def test_rom_archive_and_deck_files_are_refused(path):
    assert "must never be committed" in repo_guard.check_path(path)


@pytest.mark.parametrize("path", ["a.py", "README.md", "src/yomineko/reviews/x.yaml", "t.tbl"])
def test_ordinary_files_pass(path):
    assert repo_guard.check_path(path) is None


def test_a_dump_of_game_text_is_refused_outside_tests():
    text = "\n".join([JAPANESE_LINE] * 8)
    message = repo_guard.check_text("src/yomineko/data.txt", text)
    assert message and "looks like game text" in message


def test_a_review_file_that_contains_game_text_is_refused():
    review = "words:\n" + "\n".join(f"  # {JAPANESE_LINE}" for _ in range(8))
    assert repo_guard.check_text("src/yomineko/reviews/pmd-red-jp.yaml", review)


def test_a_few_japanese_lines_are_fine():
    text = "\n".join([JAPANESE_LINE] * repo_guard.MAX_JP_LINES)
    assert repo_guard.check_text("docs/notes.md", text) is None


def test_short_japanese_words_never_count():
    text = "\n".join(["ねこ と おちゃ"] * 50)
    assert repo_guard.check_text("docs/notes.md", text) is None


@pytest.mark.parametrize("path", ["tests/test_x.py", "C:/p/tests/t.py"])
def test_tests_are_exempt(path):
    assert repo_guard.check_text(path, "\n".join([JAPANESE_LINE] * 20)) is None


def test_hook_mode_blocks_a_rom_write(monkeypatch, capsys):
    import io

    payload = json.dumps({"tool_input": {"file_path": "C:/p/x.gba", "content": "x"}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert repo_guard.main(["--hook"]) == 2
    assert "must never be committed" in capsys.readouterr().err


def test_hook_mode_allows_a_normal_write(monkeypatch):
    import io

    payload = json.dumps({"tool_input": {"file_path": "C:/p/src/a.py", "content": "x = 1"}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert repo_guard.main(["--hook"]) == 0


def test_hook_mode_ignores_garbled_input(monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert repo_guard.main(["--hook"]) == 0
