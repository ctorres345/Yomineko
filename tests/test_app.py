"""The desktop app: launcher, smoke test, window fallback, quit button and the real server."""

import sys
import threading
import types

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

import httpx
from support.web import ORIGIN
from typer.testing import CliRunner

from yomineko.app import launch, smoke
from yomineko.cli.app import app as cli_app
from yomineko.pipeline.workspace import Workspace
from yomineko.web import server
from yomineko.web.app import create_app


@pytest.fixture
def fake_webview(monkeypatch):
    """A pywebview stand-in that records what the launcher asks of it."""
    calls = {"windows": [], "started": 0}
    module = types.SimpleNamespace(
        settings={"ALLOW_DOWNLOADS": False},
        create_window=lambda *a, **kw: calls["windows"].append((a, kw)),
        start=lambda: calls.update(started=calls["started"] + 1),
    )
    monkeypatch.setitem(sys.modules, "webview", module)
    return module, calls


# ------------------------------------------------------------------------ smoke


def test_the_smoke_test_passes_on_a_working_install():
    pytest.importorskip("sudachipy")
    pytest.importorskip("sudachidict_core")
    assert smoke.run_smoke() == [
        "page /",
        "page /static/pico.min.css",
        "page /static/htmx.min.js",
        "page /static/app.css",
        "game profiles",
        "packaged review",
        "tokenizer",
        "certificates",
    ]


def test_the_smoke_test_notices_a_missing_page_or_data(monkeypatch):
    monkeypatch.setattr(smoke, "CHECKS", (("/", "text that is not there"),))
    with pytest.raises(smoke.SmokeError, match="status 200, expected text"):
        smoke.run_smoke()
    monkeypatch.undo()
    monkeypatch.setattr(smoke, "packaged_profiles", lambda: [])
    with pytest.raises(smoke.SmokeError, match="no game profiles"):
        smoke.run_smoke()


def test_the_smoke_test_notices_a_missing_review_or_tokenizer(monkeypatch):
    monkeypatch.setattr(smoke, "packaged_review", lambda _: None)
    with pytest.raises(smoke.SmokeError, match="packaged review is missing"):
        smoke.run_smoke()
    monkeypatch.undo()

    class Silent:
        def tokenize(self, text):
            return []

    monkeypatch.setattr(smoke, "SudachiTokenizer", Silent)
    with pytest.raises(smoke.SmokeError, match="tokenizer returned nothing"):
        smoke.run_smoke()


def test_the_app_smoke_flag_reports_and_sets_the_exit_code(monkeypatch, capsys):
    monkeypatch.setattr("yomineko.app.smoke.run_smoke", lambda: ["one", "two"])
    assert launch.main(["--smoke"]) == 0
    assert "ok  one" in capsys.readouterr().out
    monkeypatch.setattr(
        "yomineko.app.smoke.run_smoke", lambda: (_ for _ in ()).throw(smoke.SmokeError("broken"))
    )
    assert launch.main(["--smoke"]) == 1
    assert "FAILED: broken" in capsys.readouterr().err


def test_the_cli_command_runs_the_same_smoke_test(monkeypatch):
    monkeypatch.setattr("yomineko.app.smoke.run_smoke", lambda: ["one"])
    result = CliRunner().invoke(cli_app, ["app", "--smoke"])
    assert result.exit_code == 0 and "smoke test passed" in result.output
    monkeypatch.setattr(
        "yomineko.app.smoke.run_smoke", lambda: (_ for _ in ()).throw(smoke.SmokeError("broken"))
    )
    assert CliRunner().invoke(cli_app, ["app", "--smoke"]).exit_code == 1


# ----------------------------------------------------------------------- window


def test_a_window_is_shown_with_downloads_allowed(fake_webview):
    module, calls = fake_webview
    assert launch._open_window("http://localhost:1/") is True
    assert module.settings["ALLOW_DOWNLOADS"] is True and calls["started"] == 1
    assert calls["windows"][0][0] == ("yomineko", "http://localhost:1/")


def test_without_a_window_system_the_browser_is_used(monkeypatch, capsys):
    def broken_start():
        raise RuntimeError("no GTK")

    module = types.SimpleNamespace(
        settings={}, create_window=lambda *a, **kw: None, start=broken_start
    )
    monkeypatch.setitem(sys.modules, "webview", module)
    assert launch._open_window("http://localhost:1/") is False
    assert "using the browser instead" in capsys.readouterr().err
    monkeypatch.setitem(sys.modules, "webview", None)  # not installed at all
    assert launch._open_window("http://localhost:1/") is False


class FakeRunning:
    port = 4321
    url = "http://localhost:4321/"

    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


@pytest.fixture
def launched(monkeypatch, tmp_path):
    """Stand-ins for the server, the browser and the games folder."""
    monkeypatch.setenv("YOMINEKO_DATA_DIR", str(tmp_path))
    running = FakeRunning()
    seen = {"opened": [], "app": None}

    def fake_create_app(workspace, on_quit=None):
        seen["app"] = (workspace, on_quit)
        return "app"

    monkeypatch.setattr("yomineko.web.app.create_app", fake_create_app)
    monkeypatch.setattr("yomineko.web.server.start", lambda app, port: running)
    monkeypatch.setattr(launch.webbrowser, "open", lambda url: seen["opened"].append(url))
    return running, seen


def test_the_app_shows_a_window_and_stops_the_server_when_it_closes(launched, monkeypatch):
    running, seen = launched
    monkeypatch.setattr(launch, "_open_window", lambda url: True)
    assert launch.run() == 0
    assert running.stopped and seen["opened"] == []
    assert seen["app"][0].root.name == "games"  # the app's own folder, in the user data folder


def test_the_app_falls_back_to_the_browser_and_waits_for_quit(launched, monkeypatch):
    running, seen = launched
    monkeypatch.setattr(launch, "_open_window", lambda url: False)
    threading.Timer(0.2, lambda: seen["app"][1]()).start()  # the Quit button
    assert launch.run() == 0
    assert seen["opened"] == [running.url] and running.stopped


def test_the_browser_flag_skips_the_window(launched, monkeypatch):
    running, seen = launched

    def never(url):
        raise AssertionError("no window wanted")

    monkeypatch.setattr(launch, "_open_window", never)
    threading.Timer(0.2, lambda: seen["app"][1]()).start()
    assert launch.run(browser=True) == 0 and seen["opened"] == [running.url]


def test_the_windowed_app_starts_its_server_with_no_console(monkeypatch, tmp_path):
    """The packaged yomineko-app.exe has no console: sys.stdout and sys.stderr are None."""
    monkeypatch.setenv("YOMINEKO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    shown = []
    monkeypatch.setattr(launch, "_open_window", lambda url: shown.append(url) or True)
    assert launch.main([]) == 0  # the real server, started and stopped
    assert shown and shown[0].startswith("http://localhost:")


def test_the_app_without_the_web_extra_says_how_to_install_it(monkeypatch, capsys):
    from yomineko.errors import MissingExtraError

    def missing():
        raise MissingExtraError('pip install "yomineko[web]"')

    monkeypatch.setattr(launch, "require_web_extra", missing)
    assert launch.main([]) == 1
    assert "yomineko[web]" in capsys.readouterr().err


# ------------------------------------------------------------------ quit button


def test_the_quit_button_only_exists_when_the_app_can_quit(tmp_path):
    from fastapi.testclient import TestClient

    plain = TestClient(create_app(Workspace(tmp_path)), base_url="http://localhost")
    assert "Quit yomineko" not in plain.get("/").text
    plain.get("/")
    refused = plain.post("/quit", headers=ORIGIN, follow_redirects=False)
    assert refused.status_code == 404

    done = threading.Event()
    quitting = TestClient(
        create_app(Workspace(tmp_path), on_quit=done.set), base_url="http://localhost"
    )
    assert "Quit yomineko" in quitting.get("/").text
    response = quitting.post("/quit", headers=ORIGIN)
    assert response.status_code == 200 and "has stopped" in response.text
    assert done.wait(3), "the callback runs after the response"


def test_quitting_needs_the_token_like_any_other_change(tmp_path):
    from fastapi.testclient import TestClient

    done = threading.Event()
    client = TestClient(
        create_app(Workspace(tmp_path), on_quit=done.set), base_url="http://localhost"
    )
    assert client.post("/quit", headers=ORIGIN).status_code == 403  # no cookie yet
    assert not done.wait(0.5)


def test_the_start_page_says_where_the_games_are_kept(tmp_path):
    from fastapi.testclient import TestClient

    client = TestClient(create_app(Workspace(tmp_path / "games")), base_url="http://localhost")
    assert "kept on this computer in" in client.get("/").text


# ------------------------------------------------------------- the real server


def test_the_server_starts_on_a_free_loopback_port_and_stops(tmp_path):
    running = server.start(create_app(Workspace(tmp_path)))
    try:
        assert running.port > 0 and running.url == f"http://localhost:{running.port}/"
        reply = httpx.get(f"http://127.0.0.1:{running.port}/", timeout=5)
        assert reply.status_code == 200 and "Study a game" in reply.text
        wrong = httpx.get(
            f"http://127.0.0.1:{running.port}/", headers={"Host": "evil.example"}, timeout=5
        )
        assert wrong.status_code == 400
    finally:
        running.stop()
    assert not running._thread.is_alive()


def test_start_only_binds_to_loopback(monkeypatch, tmp_path):
    seen = {}

    real = server.uvicorn.Config

    def config(app, **kw):
        seen.update(kw)
        return real(app, **kw)

    monkeypatch.setattr(server.uvicorn, "Config", config)
    monkeypatch.setattr(server, "START_TIMEOUT", 0.2)
    monkeypatch.setattr(server.uvicorn.Server, "run", lambda self, *a, **k: None)
    with pytest.raises(server.ServerError, match="could not start"):
        server.start(create_app(Workspace(tmp_path)), 8123)
    assert seen["host"] == "127.0.0.1" and seen["port"] == 8123
    assert "host" not in __import__("inspect").signature(server.start).parameters
