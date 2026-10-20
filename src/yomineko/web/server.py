"""Run the application: the only module that opens a listening socket.

The address is fixed to 127.0.0.1 on purpose. There is no ``host`` parameter, so nothing (an option,
a setting, a bug in a caller) can make the server reachable from another computer.
"""

from __future__ import annotations

import threading
import time
import webbrowser
from dataclasses import dataclass
from typing import Final

import uvicorn
from fastapi import FastAPI

from yomineko.errors import YominekoError

LOCALHOST: Final = "127.0.0.1"
START_TIMEOUT: Final = 15.0


class ServerError(YominekoError):
    """The server did not start."""


def run(app: FastAPI, port: int, *, open_browser: bool = False) -> None:
    """Serve ``app`` on 127.0.0.1:``port`` until interrupted."""
    if open_browser:
        threading.Timer(0.8, webbrowser.open, args=(f"http://localhost:{port}/",)).start()
    uvicorn.run(app, host=LOCALHOST, port=port, log_level="warning")


@dataclass
class Running:
    """A server running in a background thread."""

    port: int
    _server: uvicorn.Server
    _thread: threading.Thread

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}/"

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)


def start(app: FastAPI, port: int = 0) -> Running:
    """Serve ``app`` on 127.0.0.1 in a background thread. ``port`` 0 picks a free port, which is
    returned. Raises ``ServerError`` if it does not come up."""
    config = uvicorn.Config(app, host=LOCALHOST, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="yomineko-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + START_TIMEOUT
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise ServerError(f"the server could not start on port {port or 'any'}")
        time.sleep(0.02)
    chosen = server.servers[0].sockets[0].getsockname()[1]
    return Running(chosen, server, thread)
