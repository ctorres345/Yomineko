"""Helpers shared by the web tests: a client, a fake dictionary install, jobs and small scripts."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from support.dictionary import fake_urlopen, mini_gz_bytes
from support.tokens import FakeTokenizer, tok
from yomineko.analyze.dictionary.install import install_dictionary
from yomineko.model import GameInfo, Line, Script
from yomineko.web.app import create_app

ORIGIN = {"Origin": "http://localhost"}
HEADERS = {"Last-Modified": "Sat, 03 Oct 2026 03:30:23 GMT"}
SHA1 = "0123456789abcdef0123456789abcdef01234567"
KOTO = 9000001  # 事, the pick for こと
KOTO_ZITHER = 9000002  # 琴
KOTO_CAPITAL = 9000003  # 古都


def fake_install(folder):
    urlopen, _ = fake_urlopen(mini_gz_bytes(), HEADERS)

    def install():
        return install_dictionary(url="https://example.test/j.gz", folder=folder, urlopen=urlopen)

    return install


def make_client(workspace, **kw):
    client = TestClient(create_app(workspace, **kw), base_url="http://localhost")
    client.get("/")  # picks up the cookie
    return client


def post(client, url, **data):
    return client.post(url, data=data or None, headers=ORIGIN, follow_redirects=False)


def finish(client, response, timeout=5):
    """Follow the redirect to a job and wait until it stops running; return the status HTML."""
    assert response.status_code == 303, response.text
    job_url = response.headers["location"]
    assert job_url.startswith("/jobs/")
    deadline = time.time() + timeout
    while time.time() < deadline:
        html = client.get(job_url + "/status").text
        if "aria-busy" not in html:
            return html
        time.sleep(0.02)
    raise AssertionError("the job did not finish")


def raw_script(lines: int = 2) -> Script:
    """Lines "l1", "l2" ... that the fake tokenizer reads as the ambiguous word こと."""
    made = [
        Line(
            id=f"{0x08000000 + n:08X}",
            address=n,
            bank="b",
            raw=f"l{n}",
            text=f"l{n}",
            kind="dialogue",
        )
        for n in range(1, lines + 1)
    ]
    game = GameInfo(profile_id="demo", title="Demo", platform="gba", rom_sha1=SHA1)
    return Script(generator="t", game=game, lines=made)


def tokenizer(lines: int = 2) -> FakeTokenizer:
    return FakeTokenizer({f"l{n}": [tok("こと")] for n in range(1, lines + 1)})
