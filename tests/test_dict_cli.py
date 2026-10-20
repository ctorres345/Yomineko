import pytest
from support.dictionary import MINI_ENTRY_COUNT, fake_urlopen, mini_gz_bytes
from typer.testing import CliRunner

from yomineko.analyze.dictionary.install import install_dictionary
from yomineko.analyze.dictionary.paths import ENV_VAR
from yomineko.analyze.dictionary.store import CREDIT
from yomineko.cli.app import app

runner = CliRunner()
LAST_MODIFIED = {"Last-Modified": "Sat, 03 Oct 2026 03:30:23 GMT"}


def run(*args):
    return runner.invoke(app, [str(a) for a in args])


@pytest.fixture
def data_folder(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv(ENV_VAR, str(folder))
    return folder


def test_status_when_nothing_is_installed(data_folder):
    result = run("dict", "status")
    assert result.exit_code == 0
    assert "No dictionary installed" in result.output
    assert "yomineko dict download" in result.output
    assert ENV_VAR in result.output


def test_status_after_installing(data_folder):
    urlopen, _ = fake_urlopen(mini_gz_bytes(), LAST_MODIFIED)
    install_dictionary(url="https://example.test/j.gz", folder=data_folder, urlopen=urlopen)
    result = run("dict", "status")
    assert result.exit_code == 0
    assert f"Entries:  {MINI_ENTRY_COUNT}" in result.output
    assert "2026-10-03" in result.output
    assert CREDIT in result.output


def test_download_installs_and_prints_the_credit(data_folder, monkeypatch):
    urlopen, calls = fake_urlopen(mini_gz_bytes(), LAST_MODIFIED)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    result = run("dict", "download")
    assert result.exit_code == 0, result.output
    assert f"Indexed {MINI_ENTRY_COUNT} entries (dictionary date 2026-10-03)" in result.output
    assert CREDIT in result.output
    assert calls[0][0].full_url == "https://www.edrdg.org/pub/Nihongo/JMdict_e.gz"
    assert (data_folder / "jmdict.sqlite").is_file()


def test_download_from_another_url(data_folder, monkeypatch):
    urlopen, calls = fake_urlopen(mini_gz_bytes())
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    assert run("dict", "download", "--url", "https://mirror.test/j.gz").exit_code == 0
    assert calls[0][0].full_url == "https://mirror.test/j.gz"


def test_download_refuses_http(data_folder):
    result = run("dict", "download", "--url", "http://mirror.test/j.gz")
    assert result.exit_code == 1
    assert "error:" in result.output and "insecure" in result.output
    assert "Traceback" not in result.output


def test_download_failure_is_a_clean_error(data_folder, monkeypatch):
    def broken(request, timeout, context=None):
        raise OSError("network is unreachable")

    monkeypatch.setattr("urllib.request.urlopen", broken)
    result = run("dict", "download")
    assert result.exit_code == 1
    assert "could not download" in result.output and "Traceback" not in result.output
    assert not (data_folder / "jmdict.sqlite").exists()
