import pytest
from support.dictionary import fake_urlopen, mini_gz_bytes
from support.tokens import FakeTokenizer, tok
from typer.testing import CliRunner

from yomineko.analyze.dictionary.install import install_dictionary
from yomineko.analyze.dictionary.paths import ENV_VAR
from yomineko.analyze.review import parse_review
from yomineko.cli.app import app
from yomineko.model import GameInfo, Line, Script
from yomineko.script_io import read_script, write_script

runner = CliRunner()
SHA1 = "0123456789abcdef0123456789abcdef01234567"
KOTO, KOTO_ZITHER = 9000001, 9000002


def run(*args):
    return runner.invoke(app, [str(a) for a in args])


def line(n, text):
    return Line(
        id=f"{0x08000000 + n:08X}", address=n, bank="b", raw=text, text=text, kind="dialogue"
    )


@pytest.fixture
def installed(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv(ENV_VAR, str(folder))
    urlopen, _ = fake_urlopen(mini_gz_bytes(), {"Last-Modified": "Sat, 03 Oct 2026 03:30:23 GMT"})
    install_dictionary(url="https://example.test/j.gz", folder=folder, urlopen=urlopen)
    return folder


@pytest.fixture
def fake_tokenizer(monkeypatch):
    tokenizer = FakeTokenizer({f"l{n}": [tok("こと"), tok("かえる")] for n in range(1, 6)})
    for module in ("analyze_cmd", "review_cmd"):
        monkeypatch.setattr(f"yomineko.cli.{module}.make_tokenizer", lambda: tokenizer)
    return tokenizer


@pytest.fixture
def script_file(tmp_path):
    script = Script(
        generator="t",
        game=GameInfo(profile_id="demo", title="t", platform="gba", rom_sha1=SHA1),
        lines=[line(n, f"l{n}") for n in range(1, 6)],
    )
    return write_script(script, tmp_path / "out" / "script.json")


def write_review(tmp_path, text, name="review.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


RULE = f"words:\n  - {{from: {KOTO}, to: {KOTO_ZITHER}}}\n"


# --------------------------------------------------------------------- validate


def test_validate_good_and_bad_files(tmp_path):
    good = write_review(tmp_path, RULE + "lines:\n  - {line: '0810ABCD', from: 1, drop: true}\n")
    bad = write_review(tmp_path, "words:\n  - {from: 1}\n", "bad.yaml")
    ok = run("review", "validate", good)
    assert ok.exit_code == 0 and "1 word rules, 1 line rules, 0 excluded and 0 pinned" in ok.output
    result = run("review", "validate", good, bad)
    assert result.exit_code == 1 and "FAIL" in result.output and "bad.yaml" in result.output


def test_validate_needs_a_file():
    result = run("review", "validate")
    assert result.exit_code == 1 and "name at least one review file" in result.output


# ---------------------------------------------------------------------- analyze


def test_analyze_applies_a_review_and_reports_it(installed, fake_tokenizer, script_file, tmp_path):
    review = write_review(tmp_path, RULE)
    result = run("analyze", script_file, "--review", review)
    assert result.exit_code == 0, result.output
    assert "Review: 1 of 1 rules applied, 5 word occurrences corrected." in result.output
    ids = {w.jmdict_id for w in read_script(script_file).words}
    assert KOTO_ZITHER in ids and KOTO not in ids


def test_analyze_reports_stale_rules(installed, fake_tokenizer, script_file, tmp_path):
    review = write_review(tmp_path, RULE + "  - {from: 9000011, drop: true}\n")
    result = run("analyze", script_file, "-r", review)
    assert result.exit_code == 0
    assert "1 rules matched nothing (stale?): word 9000011" in result.output


def test_a_review_for_another_rom_is_refused_before_anything_happens(
    installed, fake_tokenizer, script_file, tmp_path
):
    review = write_review(tmp_path, f'rom_sha1: "{"f" * 40}"\n' + RULE)
    result = run("analyze", script_file, "--review", review)
    assert result.exit_code == 1 and "is for ROM" in result.output
    assert read_script(script_file).words == []


def test_a_packaged_review_is_applied_automatically_and_can_be_turned_off(
    installed, fake_tokenizer, script_file, monkeypatch
):
    monkeypatch.setattr(
        "yomineko.pipeline.reviews.packaged_review",
        lambda profile_id: (
            parse_review({"words": [{"from": KOTO, "drop": True}]})
            if profile_id == "demo"
            else None
        ),
    )
    assert run("analyze", script_file).exit_code == 0
    assert KOTO not in {w.jmdict_id for w in read_script(script_file).words}
    assert run("analyze", script_file, "--no-packaged-review").exit_code == 0
    assert KOTO in {w.jmdict_id for w in read_script(script_file).words}


def test_your_review_wins_over_the_packaged_one(
    installed, fake_tokenizer, script_file, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yomineko.pipeline.reviews.packaged_review",
        lambda profile_id: parse_review({"words": [{"from": KOTO, "drop": True}]}),
    )
    mine = write_review(tmp_path, RULE)
    assert run("analyze", script_file, "-r", mine).exit_code == 0
    ids = {w.jmdict_id for w in read_script(script_file).words}
    assert KOTO_ZITHER in ids and KOTO not in ids


# ------------------------------------------------------------------------ check


def test_check_reports_without_changing_the_script(
    installed, fake_tokenizer, script_file, tmp_path
):
    before = script_file.read_bytes()
    result = run("review", "check", script_file, "-r", write_review(tmp_path, RULE))
    assert result.exit_code == 0, result.output
    assert "1 of 1 rules applied" in result.output
    assert script_file.read_bytes() == before


def test_check_fails_on_ids_the_dictionary_does_not_have(
    installed, fake_tokenizer, script_file, tmp_path
):
    review = write_review(tmp_path, "words:\n  - {from: 1, to: 2}\n")
    result = run("review", "check", script_file, "-r", review)
    assert result.exit_code == 1
    assert "2 dictionary ids are not in your dictionary: 1, 2" in result.output


def test_check_fails_on_sentence_ids_that_are_not_in_the_script(
    installed, fake_tokenizer, script_file, tmp_path
):
    review = write_review(tmp_path, RULE + 'sentences:\n  exclude: ["0899AAAA"]\n')
    result = run("review", "check", script_file, "-r", review)
    assert result.exit_code == 1
    assert "1 sentence line ids are not in this script: 0899AAAA" in result.output


def test_check_without_any_review(installed, fake_tokenizer, script_file):
    result = run("review", "check", script_file)
    assert result.exit_code == 1 and "no review to check" in result.output


# --------------------------------------------------------------------- worklist


def test_worklist_is_written_next_to_the_script_with_a_warning(
    installed, fake_tokenizer, script_file
):
    result = run("review", "worklist", script_file)
    assert result.exit_code == 0, result.output
    out = script_file.with_name("worklist.txt")
    text = out.read_text(encoding="utf-8")
    assert "2 words to look at (seen 4+ times; 0 look like names)" in result.output
    assert "do not share or commit" in result.output
    assert f"id {KOTO}" in text and "08000001  l1" in text


def test_worklist_options_and_review_filtering(installed, fake_tokenizer, script_file, tmp_path):
    out = tmp_path / "w" / "list.txt"
    assert run("review", "worklist", script_file, "--min-freq", "99", "-o", out).exit_code == 0
    assert "0 words to look at" in out.read_text(encoding="utf-8")
    covered = write_review(tmp_path, RULE)
    result = run("review", "worklist", script_file, "-r", covered)
    assert "1 words to look at" in result.output


def test_worklist_needs_the_dictionary(tmp_path, monkeypatch, fake_tokenizer, script_file):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "empty"))
    result = run("review", "worklist", script_file)
    assert result.exit_code == 1 and "yomineko dict download" in result.output
