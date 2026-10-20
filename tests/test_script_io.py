import json
from pathlib import Path

import pytest

from yomineko.model import GameInfo, Script
from yomineko.script_io import ScriptError, read_script, write_script

SHA1 = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def script():
    return Script(
        generator="test",
        game=GameInfo(profile_id="demo", title="Demo", platform="gba", rom_sha1=SHA1),
    )


def test_write_then_read_roundtrips_and_creates_folders(script, tmp_path):
    path = write_script(script, tmp_path / "a" / "b" / "script.json")
    assert path.is_file()
    assert read_script(path) == script


def test_a_current_script_is_parsed_once_straight_from_the_bytes(script, tmp_path, monkeypatch):
    path = write_script(script, tmp_path / "s.json")

    def no_second_parse(*args, **kwargs):
        raise AssertionError("parsed the JSON a second time")

    monkeypatch.setattr(json, "loads", no_second_parse)
    assert read_script(path) == script


def test_written_file_is_utf8_json_with_unix_endings(script, tmp_path):
    path = write_script(script, tmp_path / "s.json")
    raw = path.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert json.loads(raw)["schema_version"] == 4


def test_a_failed_write_leaves_the_old_script_whole(script, tmp_path, monkeypatch):
    path = write_script(script, tmp_path / "s.json")
    before = path.read_bytes()

    def interrupted(self, *args, **kwargs):
        Path.write_bytes(self, b'{"schema_ver')  # half a file, then the app stops
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "write_text", interrupted)
    with pytest.raises(KeyboardInterrupt):
        write_script(script, path)
    monkeypatch.undo()
    assert path.read_bytes() == before and read_script(path) == script


def test_missing_file(tmp_path):
    with pytest.raises(ScriptError, match="cannot read"):
        read_script(tmp_path / "nope.json")


@pytest.mark.parametrize("content", [b"not json", b"\xff\xfe\x00", b""])
def test_not_json(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_bytes(content)
    with pytest.raises(ScriptError, match="not a valid script file"):
        read_script(path)


@pytest.mark.parametrize("content", ["[]", "42", '{"lines": []}'])
def test_json_that_is_not_a_script(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ScriptError, match="schema version"):
        read_script(path)


def test_other_schema_version_says_how_to_fix_it(tmp_path):
    path = tmp_path / "old.json"
    path.write_text('{"schema_version": 7}', encoding="utf-8")
    with pytest.raises(ScriptError, match=r"version is 7.*reads versions 1 to 4.*extract"):
        read_script(path)


def test_a_version_1_script_is_upgraded_in_memory(script, tmp_path):
    """Version 1 scripts have no words, so they read as the current version with nothing lost."""
    path = write_script(script, tmp_path / "s.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["dictionary"]
    data["schema_version"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")
    upgraded = read_script(path)
    assert upgraded.schema_version == 4
    assert upgraded.words == [] and upgraded.dictionary is None


def test_a_version_2_script_is_upgraded_with_empty_line_words(script, tmp_path):
    path = write_script(script, tmp_path / "s.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["lines"] = [
        {"id": "08000001", "address": 1, "bank": "b", "raw": "r", "text": "t", "kind": "term"}
    ]
    data["schema_version"] = 2
    path.write_text(json.dumps(data), encoding="utf-8")
    upgraded = read_script(path)
    assert upgraded.schema_version == 4
    assert upgraded.lines[0].word_ids == []


def test_a_version_3_script_is_upgraded_with_words_that_have_no_rank(script, tmp_path):
    path = write_script(script, tmp_path / "s.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["words"] = [{"jmdict_id": 1, "written": "w", "kana": "k", "freq": 2}]
    data["schema_version"] = 3
    path.write_text(json.dumps(data), encoding="utf-8")
    upgraded = read_script(path)
    assert upgraded.schema_version == 4
    assert upgraded.words[0].jmdict_rank is None


def test_right_version_but_damaged_content_names_the_field(tmp_path):
    path = tmp_path / "damaged.json"
    path.write_text('{"schema_version": 4, "generator": "x"}', encoding="utf-8")
    with pytest.raises(ScriptError, match="game"):
        read_script(path)
