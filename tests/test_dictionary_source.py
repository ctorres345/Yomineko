import re
import ssl
import urllib.error
import urllib.request

import pytest
from support.dictionary import MINI_ENTRY_COUNT, FakeResponse, fake_urlopen, mini_gz_bytes

from yomineko import __version__
from yomineko.analyze.dictionary.install import dictionary_info, install_dictionary
from yomineko.analyze.dictionary.paths import ENV_VAR, INDEX_NAME, data_dir, index_path
from yomineko.analyze.dictionary.source import DEFAULT_URL, download_jmdict, ssl_context
from yomineko.analyze.dictionary.store import CREDIT, Dictionary
from yomineko.analyze.dictionary.xml_parser import DictionaryError

URL = "https://example.test/JMdict_e.gz"
LAST_MODIFIED = {"Last-Modified": "Sat, 03 Oct 2026 03:30:23 GMT"}


def leftovers(folder):
    return sorted(p.name for p in folder.iterdir())


# ------------------------------------------------------------------- download


def test_download_writes_the_file_and_reads_the_date(tmp_path):
    urlopen, calls = fake_urlopen(b"payload", LAST_MODIFIED)
    result = download_jmdict(tmp_path / "j.gz", url=URL, urlopen=urlopen)
    assert result.path.read_bytes() == b"payload"
    assert (result.size, result.date) == (7, "2026-10-03")
    assert leftovers(tmp_path) == ["j.gz"]
    request, timeout = calls[0]
    assert request.full_url == URL
    assert request.get_header("User-agent") == f"yomineko/{__version__}"
    assert timeout > 0


def test_a_missing_date_header_falls_back_to_today(tmp_path):
    urlopen, _ = fake_urlopen(b"x")
    result = download_jmdict(tmp_path / "j.gz", url=URL, urlopen=urlopen)
    assert re.fullmatch(r"\d{4}-\d\d-\d\d", result.date)


def test_a_garbled_date_header_falls_back_to_today(tmp_path):
    urlopen, _ = fake_urlopen(b"x", {"Last-Modified": "not a date"})
    result = download_jmdict(tmp_path / "j.gz", url=URL, urlopen=urlopen)
    assert re.fullmatch(r"\d{4}-\d\d-\d\d", result.date)


def test_the_default_url_is_the_official_https_one():
    assert DEFAULT_URL == "https://www.edrdg.org/pub/Nihongo/JMdict_e.gz"


@pytest.mark.parametrize(
    "url", ["http://example.test/j.gz", "ftp://example.test/j.gz", "file:///x"]
)
def test_only_https_is_allowed(tmp_path, url):
    urlopen, calls = fake_urlopen(b"x")
    with pytest.raises(DictionaryError, match="insecure"):
        download_jmdict(tmp_path / "j.gz", url=url, urlopen=urlopen)
    assert calls == [] and leftovers(tmp_path) == []


def test_http_errors_are_reported_with_the_status(tmp_path):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(URL, 404, "Not Found", {}, None)

    with pytest.raises(DictionaryError, match="HTTP 404"):
        download_jmdict(tmp_path / "j.gz", url=URL, urlopen=urlopen)


@pytest.mark.parametrize(
    "error",
    [urllib.error.URLError("name not resolved"), TimeoutError("timed out"), OSError("no route")],
)
def test_network_failures_are_reported(tmp_path, error):
    def urlopen(request, timeout):
        raise error

    with pytest.raises(DictionaryError, match="could not download"):
        download_jmdict(tmp_path / "j.gz", url=URL, urlopen=urlopen)
    assert leftovers(tmp_path) == []


def test_a_declared_size_over_the_cap_is_refused_before_reading(tmp_path):
    urlopen, _ = fake_urlopen(b"x" * 10, {"Content-Length": "1000000"})
    with pytest.raises(DictionaryError, match="larger than"):
        download_jmdict(tmp_path / "j.gz", url=URL, urlopen=urlopen, max_bytes=1000)
    assert leftovers(tmp_path) == []


def test_a_stream_that_outgrows_the_cap_is_stopped_and_cleaned_up(tmp_path):
    urlopen, _ = fake_urlopen(b"x" * 5000)  # no Content-Length: only the stream can tell
    with pytest.raises(DictionaryError, match="exceeded"):
        download_jmdict(tmp_path / "j.gz", url=URL, urlopen=urlopen, max_bytes=1000)
    assert leftovers(tmp_path) == []


def test_an_empty_response_is_an_error(tmp_path):
    urlopen, _ = fake_urlopen(b"")
    with pytest.raises(DictionaryError, match="empty"):
        download_jmdict(tmp_path / "j.gz", url=URL, urlopen=urlopen)
    assert leftovers(tmp_path) == []


def test_a_connection_that_drops_midway_leaves_no_half_file(tmp_path):
    urlopen, _ = fake_urlopen(b"x" * 200_000, fail_after=70_000)
    with pytest.raises(DictionaryError, match="connection reset"):
        download_jmdict(tmp_path / "j.gz", url=URL, urlopen=urlopen)
    assert leftovers(tmp_path) == []


def test_a_failed_download_does_not_touch_an_existing_file(tmp_path):
    dest = tmp_path / "j.gz"
    dest.write_bytes(b"the previous download")
    urlopen, _ = fake_urlopen(b"x" * 5000)
    with pytest.raises(DictionaryError):
        download_jmdict(dest, url=URL, urlopen=urlopen, max_bytes=100)
    assert dest.read_bytes() == b"the previous download"


def test_fake_response_context_manager_contract():
    with FakeResponse(b"abc") as r:
        assert r.read(2) == b"ab"


# --------------------------------------------------------------------- install


def test_install_downloads_indexes_and_removes_the_archive(tmp_path):
    urlopen, _ = fake_urlopen(mini_gz_bytes(), LAST_MODIFIED)
    info = install_dictionary(url=URL, folder=tmp_path, urlopen=urlopen)
    assert info.entries == MINI_ENTRY_COUNT
    assert (info.date, info.source, info.credit) == ("2026-10-03", URL, CREDIT)
    assert info.path == tmp_path / INDEX_NAME
    assert leftovers(tmp_path) == [INDEX_NAME]
    with Dictionary(info.path) as d:
        assert d.ids_by_reading("こと")


def test_a_damaged_download_leaves_no_index_and_no_archive(tmp_path):
    urlopen, _ = fake_urlopen(mini_gz_bytes()[:-30])
    with pytest.raises(DictionaryError, match="damaged"):
        install_dictionary(url=URL, folder=tmp_path, urlopen=urlopen)
    assert leftovers(tmp_path) == []


def test_a_failed_reinstall_keeps_the_working_index(tmp_path):
    good, _ = fake_urlopen(mini_gz_bytes(), LAST_MODIFIED)
    install_dictionary(url=URL, folder=tmp_path, urlopen=good)
    bad, _ = fake_urlopen(b"not gzip")
    with pytest.raises(DictionaryError):
        install_dictionary(url=URL, folder=tmp_path, urlopen=bad)
    info = dictionary_info(tmp_path)
    assert info is not None and info.entries == MINI_ENTRY_COUNT
    assert leftovers(tmp_path) == [INDEX_NAME]


def test_dictionary_info_when_nothing_is_installed(tmp_path):
    assert dictionary_info(tmp_path) is None


# ----------------------------------------------------------------------- paths


def test_the_data_folder_can_be_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "custom"))
    assert data_dir() == tmp_path / "custom"
    assert index_path() == tmp_path / "custom" / INDEX_NAME


def test_the_default_data_folder_is_per_user(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert data_dir().name.lower() == "yomineko"
    assert index_path(data_dir()) == data_dir() / INDEX_NAME


def test_the_download_trusts_certifi_when_the_system_has_no_certificates(monkeypatch):
    # what a packaged app sees on a Mac: the build machine's certificate paths, which are empty
    def no_system_certificates():
        return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    monkeypatch.setattr(ssl, "create_default_context", no_system_certificates)
    assert no_system_certificates().cert_store_stats()["x509_ca"] == 0
    assert ssl_context().cert_store_stats()["x509_ca"] > 100


def test_the_default_opener_uses_that_context(tmp_path, monkeypatch):
    seen = {}

    def urlopen(request, timeout, context):
        seen["context"] = context
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(DictionaryError, match="offline"):
        download_jmdict(tmp_path / "j.gz", url=URL)
    assert isinstance(seen["context"], ssl.SSLContext)
