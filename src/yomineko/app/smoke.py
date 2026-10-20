"""A quick self-test of an installed or packaged yomineko, with no window and no network.

It asks the web application for its pages in-process, checks that the packaged data (profiles,
reviews, templates, vendored files) is there, and that the tokenizer and its dictionary work. The
build runs it on every system before an executable is offered.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import certifi
from fastapi import FastAPI
from starlette.types import Message, Scope

from yomineko.analyze.review import packaged_review
from yomineko.analyze.tokenizer import SudachiTokenizer
from yomineko.errors import YominekoError
from yomineko.pipeline.workspace import Workspace
from yomineko.profile.loader import packaged_profiles
from yomineko.web.app import create_app

CHECKS = (
    ("/", "Study a game"),
    ("/static/pico.min.css", "Pico CSS"),
    ("/static/htmx.min.js", "htmx"),
    ("/static/app.css", "Pico CSS"),
)


class SmokeError(YominekoError):
    """Something a working install must have is missing or broken."""


async def _get(app: FastAPI, path: str) -> tuple[int, str]:
    """GET ``path`` from the ASGI application itself: no socket, no HTTP client."""
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"host", b"localhost")],
        "client": ("127.0.0.1", 1),
        "server": ("localhost", 80),
    }
    sent: list[Message] = []
    requested = False
    finished = asyncio.Event()

    async def receive() -> Message:
        """The empty request body once, then a disconnect after the response, as a server
        does (Starlette's middleware waits for it and refuses a second request message)."""
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await finished.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            finished.set()

    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body.decode("utf-8", errors="replace")


def run_smoke() -> list[str]:
    """Run every check; returns what passed. Raises ``SmokeError`` at the first failure."""
    passed: list[str] = []
    with tempfile.TemporaryDirectory() as folder:
        app = create_app(Workspace(Path(folder)))
        for path, expected in CHECKS:
            status, body = asyncio.run(_get(app, path))
            if status != 200 or expected not in body:
                raise SmokeError(f"{path}: status {status}, expected text {expected!r}")
            passed.append(f"page {path}")
    if not packaged_profiles():
        raise SmokeError("no game profiles are packaged")
    passed.append("game profiles")
    if packaged_review("pmd-red-jp") is None:
        raise SmokeError("the packaged review is missing")
    passed.append("packaged review")
    tokens = SudachiTokenizer().tokenize("ことばを　さがす")
    if not tokens:
        raise SmokeError("the tokenizer returned nothing")
    passed.append("tokenizer")
    if not Path(certifi.where()).is_file():  # the dictionary download needs them on macOS
        raise SmokeError("the trusted certificates (certifi) are not packaged")
    passed.append("certificates")
    return passed
