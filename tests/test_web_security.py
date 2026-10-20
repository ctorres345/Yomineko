"""The rules that keep other pages and other computers away from the local server."""

import importlib.util
import inspect

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from yomineko.cli.app import app as cli_app
from yomineko.pipeline.workspace import Workspace
from yomineko.web import security, server
from yomineko.web.app import create_app

ORIGIN = {"Origin": "http://localhost"}
TOKEN = "fixed-test-token"


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "games")


@pytest.fixture
def client(workspace):
    return TestClient(create_app(workspace, token=TOKEN), base_url="http://localhost")


def post(client, **kw):
    return client.post("/notice", follow_redirects=False, **kw)


# ----------------------------------------------------------------------- host


@pytest.mark.parametrize("host", ["localhost", "localhost:8765", "127.0.0.1:8765"])
def test_loopback_hosts_are_served(workspace, host):
    c = TestClient(create_app(workspace), base_url=f"http://{host}")
    assert c.get("/").status_code == 200


@pytest.mark.parametrize(
    "host", ["evil.example", "localhost.evil.example", "192.168.1.5:8765", "[::1]:8765"]
)
def test_other_host_names_are_refused(workspace, host):
    """A hostile site pointing its own name at 127.0.0.1 (DNS rebinding) sends its own Host."""
    c = TestClient(create_app(workspace), base_url=f"http://{host}")
    assert c.get("/").status_code == 400


# ------------------------------------------------------------- origin and token


def test_a_post_from_the_page_goes_through(client):
    client.get("/")
    assert post(client, headers=ORIGIN).status_code == 303


def test_a_post_without_an_origin_is_refused(client):
    client.get("/")
    response = post(client)
    assert response.status_code == 403 and "Origin" in response.text


@pytest.mark.parametrize("origin", ["http://evil.example", "http://localhost:9999", "null", "x"])
def test_a_post_from_another_origin_is_refused(client, origin):
    client.get("/")
    assert post(client, headers={"Origin": origin}).status_code == 403


def test_a_post_without_the_cookie_is_refused(workspace):
    fresh = TestClient(create_app(workspace, token=TOKEN), base_url="http://localhost")
    response = post(fresh, headers=ORIGIN)  # never loaded a page, so it has no cookie
    assert response.status_code == 403 and "token" in response.text


def test_a_post_with_the_wrong_token_is_refused(workspace):
    c = TestClient(create_app(workspace, token=TOKEN), base_url="http://localhost")
    c.cookies.set(security.COOKIE, "guess")
    assert post(c, headers=ORIGIN).status_code == 403


def test_the_token_is_random_per_run_and_the_cookie_is_strict(workspace):
    first = create_app(workspace)
    second = create_app(workspace)
    cookie = TestClient(first, base_url="http://localhost").get("/").headers["set-cookie"]
    other = TestClient(second, base_url="http://localhost").get("/").headers["set-cookie"]
    assert cookie != other
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie


def test_a_stale_cookie_from_an_earlier_run_is_replaced(workspace):
    c = TestClient(create_app(workspace, token=TOKEN), base_url="http://localhost")
    c.cookies.set(security.COOKIE, "from-an-earlier-run")
    assert f"{security.COOKIE}={TOKEN}" in c.get("/").headers["set-cookie"]


def test_an_oversized_upload_is_refused_before_it_is_read(client):
    client.get("/")
    headers = {**ORIGIN, "content-length": str(security.MAX_UPLOAD + 1)}
    response = client.post("/extract", content=b"x", headers=headers)
    assert response.status_code == 403 and "larger than" in response.text


def test_get_requests_do_not_need_a_token(workspace):
    c = TestClient(create_app(workspace, token=TOKEN), base_url="http://localhost")
    assert c.get("/").status_code == 200 and c.get("/static/app.css").status_code == 200


# -------------------------------------------------------------------- headers


def test_security_headers_are_on_every_response(client):
    for response in (client.get("/"), client.get("/nope"), client.get("/static/app.css")):
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
        assert "img-src 'self' data:;" in response.headers["Content-Security-Policy"]  # spinner
        assert response.headers["Referrer-Policy"] == "same-origin"


def test_pages_are_never_stored_but_static_files_are_revalidated(client):
    assert client.get("/").headers["Cache-Control"] == "no-store"
    css = client.get("/static/app.css")
    assert css.headers["Cache-Control"] == "no-cache" and css.headers["ETag"]
    again = client.get("/static/app.css", headers={"If-None-Match": css.headers["ETag"]})
    assert again.status_code == 304 and again.content == b""


def test_the_generated_api_docs_are_not_exposed(client):
    assert all(client.get(p).status_code == 404 for p in ("/docs", "/redoc", "/openapi.json"))


# --------------------------------------------------------------------- listener


def test_the_server_only_binds_to_loopback(monkeypatch):
    seen = {}
    monkeypatch.setattr(server.uvicorn, "run", lambda app, **kw: seen.update(kw))
    server.run(object(), 8123)  # type: ignore[arg-type]
    assert seen["host"] == "127.0.0.1" and seen["port"] == 8123
    assert "host" not in inspect.signature(server.run).parameters, "no way to change the address"


def test_the_browser_opens_only_when_asked(monkeypatch):
    started = []

    class Timer:
        def __init__(self, delay, fn, args=()):
            started.append((fn, args))

        def start(self):
            pass

    monkeypatch.setattr(server.uvicorn, "run", lambda app, **kw: None)
    monkeypatch.setattr(server.threading, "Timer", Timer)
    server.run(object(), 8123)  # type: ignore[arg-type]
    assert started == []
    server.run(object(), 8123, open_browser=True)  # type: ignore[arg-type]
    assert started == [(server.webbrowser.open, ("http://localhost:8123/",))]


# ------------------------------------------------------------------ serve command


def test_the_serve_command_starts_the_server_on_this_computer(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("yomineko.web.server.run", lambda app, port, **kw: calls.append((port, kw)))
    result = CliRunner().invoke(
        cli_app, ["serve", "--port", "9001", "--no-browser", "--workspace", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "http://localhost:9001/" in result.output
    assert calls == [(9001, {"open_browser": False})]


def test_the_serve_command_opens_the_browser_by_default(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("yomineko.web.server.run", lambda app, port, **kw: calls.append(kw))
    CliRunner().invoke(cli_app, ["serve", "--workspace", str(tmp_path)])
    assert calls == [{"open_browser": True}]


def test_serve_without_the_web_extra_says_how_to_install_it(monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *a: None if name == "fastapi" else real(name, *a)
    )
    result = CliRunner().invoke(cli_app, ["serve"])
    assert result.exit_code == 1
    assert 'pip install "yomineko[web]"' in result.output and "fastapi" in result.output
