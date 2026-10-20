"""The shared steps behind the CLI and the web app."""

import pytest
from support.dictionary import fake_urlopen, mini_gz_bytes
from support.study import line_id, make_line, make_script
from support.tokens import FakeTokenizer, tok

from yomineko.analyze.dictionary.install import install_dictionary
from yomineko.analyze.dictionary.paths import ENV_VAR
from yomineko.analyze.dictionary.xml_parser import DictionaryError
from yomineko.analyze.review import ReviewReport, parse_review
from yomineko.errors import MissingExtraError, YominekoError
from yomineko.model import GameInfo, Line, Script
from yomineko.pipeline.analysis import open_dictionary, run_analysis
from yomineko.pipeline.reviews import describe_report, resolve_review
from yomineko.pipeline.study import choose_sentences, parse_decks
from yomineko.pipeline.workspace import (
    Workspace,
    WorkspaceError,
    app_workspace,
    cli_workspace,
)
from yomineko.script_io import write_script

SHA1 = "0123456789abcdef0123456789abcdef01234567"
KOTO = 9000001


def small_script():
    lines = [
        Line(
            id=f"{0x08000000 + n:08X}",
            address=n,
            bank="b",
            raw=f"l{n}",
            text=f"l{n}",
            kind="dialogue",
        )
        for n in (1, 2)
    ]
    game = GameInfo(profile_id="demo", title="t", platform="gba", rom_sha1=SHA1)
    return Script(generator="t", game=game, lines=lines)


@pytest.fixture
def data_folder(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv(ENV_VAR, str(folder))
    return folder


@pytest.fixture
def installed(data_folder):
    urlopen, _ = fake_urlopen(mini_gz_bytes(), {"Last-Modified": "Sat, 03 Oct 2026 03:30:23 GMT"})
    install_dictionary(url="https://example.test/j.gz", folder=data_folder, urlopen=urlopen)
    return data_folder


def tokenizer():
    return FakeTokenizer({"l1": [tok("こと")], "l2": [tok("こと")]})


# ------------------------------------------------------------------- reviews


def test_resolve_review_is_none_without_any_review():
    assert resolve_review(small_script(), None) is None


def test_resolve_review_refuses_a_review_for_another_rom(tmp_path):
    path = tmp_path / "r.yaml"
    path.write_text(f'rom_sha1: "{"f" * 40}"\n', encoding="utf-8")
    with pytest.raises(YominekoError, match="is for ROM"):
        resolve_review(small_script(), [path])


def test_resolve_review_uses_the_packaged_review_unless_told_not_to(monkeypatch):
    packaged = parse_review({"words": [{"from": KOTO, "drop": True}]})
    monkeypatch.setattr("yomineko.pipeline.reviews.packaged_review", lambda _: packaged)
    assert resolve_review(small_script(), None) is not None
    assert resolve_review(small_script(), None, use_packaged=False) is None


def test_describe_report_lists_stale_rules_and_unknown_ids():
    report = ReviewReport(rules=3, applied=2, changed_occurrences=1234, unused=["word 5"])
    report.unknown_ids = [7]
    text = describe_report(report)
    assert text[0] == "Review: 2 of 3 rules applied, 1,234 word occurrences corrected."
    assert "1 rules matched nothing (stale?): word 5" in text[1]
    assert "1 dictionary ids are not in your dictionary: 7" in text[2]


# ------------------------------------------------------------------ analysis


def test_run_analysis_returns_the_new_script_and_the_dictionary(installed):
    done = run_analysis(small_script(), tokenizer)
    assert [w.jmdict_id for w in done.script.words] == [KOTO]
    assert done.report is None and "CC BY-SA" in done.dictionary.credit


def test_run_analysis_reports_its_review(installed, tmp_path):
    review = tmp_path / "r.yaml"
    review.write_text(f"words:\n  - {{from: {KOTO}, to: 9000002}}\n", encoding="utf-8")
    done = run_analysis(small_script(), tokenizer, review_files=[review], use_packaged_review=False)
    assert done.report is not None and done.report.applied == 1
    assert [w.jmdict_id for w in done.script.words] == [9000002]


def test_a_missing_dictionary_is_an_error_unless_download_is_allowed(data_folder):
    with pytest.raises(DictionaryError, match="--download"):
        run_analysis(small_script(), tokenizer)
    assert not data_folder.exists()


def test_download_installs_the_dictionary_and_says_so(data_folder, monkeypatch):
    from yomineko.analyze.dictionary.install import install_dictionary as real

    headers = {"Last-Modified": "Sat, 03 Oct 2026 03:30:23 GMT"}
    urlopen, calls = fake_urlopen(mini_gz_bytes(), headers)
    monkeypatch.setattr(
        "yomineko.pipeline.analysis.install_dictionary",
        lambda: real(url="https://example.test/j.gz", urlopen=urlopen),
    )
    said = []
    done = run_analysis(small_script(), tokenizer, download=True, say=said.append)
    assert said == ["Downloading the dictionary ..."] and len(calls) == 1
    assert done.script.words


def test_a_missing_tokenizer_extra_is_reported_before_any_download(data_folder):
    def missing():
        raise MissingExtraError("install the extra")

    with pytest.raises(MissingExtraError):
        run_analysis(small_script(), missing, download=True)
    assert not data_folder.exists()


def test_open_dictionary_needs_an_installed_dictionary(data_folder, installed):
    with open_dictionary() as dictionary:
        assert dictionary.entry(KOTO) is not None


def test_open_dictionary_without_one_says_how_to_get_it(data_folder):
    with pytest.raises(DictionaryError, match="dict download"):
        open_dictionary()


# --------------------------------------------------------------------- study


def test_parse_decks():
    assert parse_decks(None) == ["words", "sentences", "terms"]
    assert parse_decks("terms, words") == ["words", "terms"]
    with pytest.raises(YominekoError, match="unknown deck 'cards'"):
        parse_decks("words,cards")
    with pytest.raises(YominekoError, match="at least one"):
        parse_decks(" , ")


def test_choose_sentences_applies_the_review_files(tmp_path):
    script = make_script()
    review = tmp_path / "r.yaml"
    review.write_text(f'sentences:\n  exclude: ["{line_id(1)}"]\n', encoding="utf-8")
    picked = choose_sentences(
        script, count=10, min_freq=4, review_files=[review], use_packaged_review=False
    )
    assert line_id(1) not in {s.line.id for s in picked} and len(picked) == 4


def test_choose_sentences_uses_the_packaged_profile_rules():
    game = make_script().game.model_copy(update={"profile_id": "pmd-red-jp"})
    lines = [
        make_line(0x30A000 + 4, "ようこそ　あたらしいまちへ。", [1, 2]),
        make_line(0x20, "きょうは　いいてんきですね。", [2, 50]),
    ]
    picked = choose_sentences(
        make_script(game=game, lines=lines), count=10, min_freq=4, use_packaged_review=False
    )
    assert [s.line.address for s in picked] == [0x20]


def test_an_unknown_named_profile_is_an_error():
    with pytest.raises(YominekoError):
        choose_sentences(make_script(), count=1, min_freq=4, profile_spec="nope.yaml")


# ----------------------------------------------------------------- workspace


def test_a_workspace_names_the_files_of_a_game(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.script_path("pmd-red-jp") == tmp_path / "pmd-red-jp" / "script.json"
    assert ws.review_path("pmd-red-jp") == tmp_path / "pmd-red-jp" / "review.yaml"


@pytest.mark.parametrize("bad", ["..", "../x", "a/b", "A", "", "-x", "a b", "a\\b"])
def test_a_game_id_cannot_climb_out_of_the_workspace(tmp_path, bad):
    with pytest.raises(WorkspaceError):
        Workspace(tmp_path).game_dir(bad)


def test_games_lists_only_folders_with_a_script(tmp_path):
    ws = Workspace(tmp_path / "games")
    assert ws.games() == []
    write_script(make_script(), ws.script_path("beta"))
    write_script(make_script(), ws.script_path("alpha"))
    (ws.root / "empty").mkdir()
    (ws.root / "Not-An-Id").mkdir()
    (ws.root / "file.txt").write_text("x", encoding="utf-8")
    assert ws.games() == ["alpha", "beta"]


def test_the_cli_and_the_app_keep_their_games_in_different_places(data_folder):
    assert str(cli_workspace().root) == "yomineko-out"
    assert app_workspace().root == data_folder / "games"
