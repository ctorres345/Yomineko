import csv
import json

import pytest
from support.dictionary import fake_urlopen, mini_gz_bytes
from support.tokens import FakeTokenizer, tok
from typer.testing import CliRunner

from yomineko.analyze.dictionary.install import install_dictionary
from yomineko.analyze.dictionary.paths import ENV_VAR
from yomineko.cli.app import app
from yomineko.errors import MissingExtraError
from yomineko.model import GameInfo, Line, Script
from yomineko.script_io import read_script, write_script

runner = CliRunner()
SHA1 = "0123456789abcdef0123456789abcdef01234567"
LAST_MODIFIED = {"Last-Modified": "Sat, 03 Oct 2026 03:30:23 GMT"}


def run(*args):
    return runner.invoke(app, [str(a) for a in args])


def line(n, text):
    return Line(
        id=f"{0x08000000 + n:08X}", address=n, bank="b", raw=text, text=text, kind="dialogue"
    )


@pytest.fixture
def data_folder(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv(ENV_VAR, str(folder))
    return folder


@pytest.fixture
def installed(data_folder):
    urlopen, _ = fake_urlopen(mini_gz_bytes(), LAST_MODIFIED)
    install_dictionary(url="https://example.test/j.gz", folder=data_folder, urlopen=urlopen)
    return data_folder


@pytest.fixture
def fake_tokenizer(monkeypatch):
    tokenizer = FakeTokenizer(
        {
            "l1": [tok("こと"), tok("依頼", reading="いらい", normalized="依頼")],
            "l2": [tok("こと"), tok("こと")],
        }
    )
    monkeypatch.setattr("yomineko.cli.analyze_cmd.make_tokenizer", lambda: tokenizer)
    return tokenizer


@pytest.fixture
def script_file(tmp_path):
    script = Script(
        generator="t",
        game=GameInfo(profile_id="p", title="t", platform="gba", rom_sha1=SHA1),
        lines=[line(1, "l1"), line(2, "l2")],
    )
    return write_script(script, tmp_path / "out" / "script.json")


def test_analyze_updates_the_script_in_place(installed, fake_tokenizer, script_file):
    result = run("analyze", script_file)
    assert result.exit_code == 0, result.output
    assert "Found 2 distinct words (1 appear 3 or more times, 2 are common words)" in result.output
    assert "CC BY-SA" in result.output
    script = read_script(script_file)
    assert [w.freq for w in script.words] == [3, 1]
    assert script.dictionary is not None and script.dictionary.date == "2026-10-03"
    assert script.schema_version == 4


def test_analyze_can_write_somewhere_else(installed, fake_tokenizer, script_file, tmp_path):
    before = script_file.read_bytes()
    out = tmp_path / "elsewhere" / "analysed.json"
    assert run("analyze", script_file, "-o", out).exit_code == 0
    assert script_file.read_bytes() == before
    assert len(read_script(out).words) == 2


def test_the_examples_option(installed, fake_tokenizer, script_file):
    assert run("analyze", script_file, "--examples", "1").exit_code == 0
    assert all(len(w.examples) == 1 for w in read_script(script_file).words)
    assert run("analyze", script_file, "--examples", "0").exit_code == 2


def test_without_a_dictionary_it_says_how_to_get_one(data_folder, fake_tokenizer, script_file):
    result = run("analyze", script_file)
    assert result.exit_code == 1
    assert "yomineko dict download" in result.output and "--download" in result.output
    assert "Traceback" not in result.output
    assert read_script(script_file).words == []


def test_download_flag_installs_the_dictionary_first(
    data_folder, fake_tokenizer, script_file, monkeypatch
):
    urlopen, calls = fake_urlopen(mini_gz_bytes(), LAST_MODIFIED)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    result = run("analyze", script_file, "--download")
    assert result.exit_code == 0, result.output
    assert "Downloading the dictionary" in result.output
    assert len(calls) == 1 and len(read_script(script_file).words) == 2
    assert (data_folder / "jmdict.sqlite").is_file()


def test_a_missing_tokenizer_fails_before_any_download(data_folder, script_file, monkeypatch):
    def missing():
        raise MissingExtraError('SudachiPy is missing: pip install "yomineko[analyze]"')

    urlopen, calls = fake_urlopen(mini_gz_bytes())
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr("yomineko.cli.analyze_cmd.make_tokenizer", missing)
    result = run("analyze", script_file, "--download")
    assert result.exit_code == 1
    assert 'pip install "yomineko[analyze]"' in result.output
    assert calls == [], "nothing may be downloaded when the tokenizer is missing"
    assert not data_folder.exists()


def test_a_damaged_script_is_a_clean_error(installed, fake_tokenizer, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    result = run("analyze", bad)
    assert result.exit_code == 1 and "not a valid script file" in result.output


# ------------------------------------------------------------- export of words


def test_export_words_as_csv(installed, fake_tokenizer, script_file):
    assert run("analyze", script_file).exit_code == 0
    result = run("export", script_file, "--content", "words", "-f", "csv")
    assert result.exit_code == 0, result.output
    assert "Exported 2 words" in result.output
    out = script_file.with_name("script.export.csv")
    text = out.read_text(encoding="utf-8-sig")
    rows = [r for r in csv.reader(text.splitlines()) if r and not r[0].startswith("#")]
    assert [r[1] for r in rows[1:]] == ["事", "依頼"]
    assert text.rstrip().splitlines()[-1].startswith("# JMdict")


def test_min_freq_applies_to_words(installed, fake_tokenizer, script_file):
    run("analyze", script_file)
    result = run("export", script_file, "--content", "words", "-f", "json", "--min-freq", "2")
    assert result.exit_code == 0 and "Exported 1 words" in result.output
    data = json.loads(script_file.with_name("script.export.json").read_text(encoding="utf-8"))
    assert len(data["words"]) == 1


def test_exporting_words_from_an_unanalysed_script(script_file):
    result = run("export", script_file, "--content", "words", "-f", "csv")
    assert result.exit_code == 1
    assert "no words yet" in result.output and "yomineko analyze" in result.output


def test_words_cannot_be_combined_with_line_filters(installed, fake_tokenizer, script_file):
    run("analyze", script_file)
    for extra in (["--all"], ["--kind", "term"]):
        result = run("export", script_file, "--content", "words", "-f", "csv", *extra)
        assert result.exit_code == 1 and "apply to lines" in result.output
