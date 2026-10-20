"""Start the desktop app: the server, then a window (or the browser) showing it."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import threading
import webbrowser

from yomineko.errors import YominekoError
from yomineko.pipeline.workspace import app_workspace
from yomineko.web.extra import require_web_extra


def _open_window(url: str) -> bool:
    """Show ``url`` in a native window until it is closed. Returns False if there is no way to
    make a window here, so the caller can use the browser instead."""
    try:
        import webview  # the app extra; imported late so the CLI never needs it

        webview.settings["ALLOW_DOWNLOADS"] = True  # exports are file downloads
        webview.create_window("yomineko", url, width=1100, height=800, min_size=(360, 500))
        webview.start()
    except Exception as e:  # no GUI toolkit, no WebView2 runtime ...
        print(f"No window ({type(e).__name__}); using the browser instead.", file=sys.stderr)
        return False
    return True


def run(*, smoke: bool = False, browser: bool = False, port: int = 0) -> int:
    """Run the app. Returns the exit code."""
    require_web_extra()
    if smoke:
        from yomineko.app.smoke import run_smoke

        try:
            for line in run_smoke():
                print(f"ok  {line}")
        except YominekoError as e:
            print(f"FAILED: {e}", file=sys.stderr)
            return 1
        print("smoke test passed")
        return 0

    from yomineko.web.app import create_app
    from yomineko.web.server import start

    stop = threading.Event()
    running = start(create_app(app_workspace(), on_quit=stop.set), port)
    try:
        if browser or not _open_window(running.url):
            webbrowser.open(running.url)
            print(f"yomineko is running at {running.url} (Quit from the page, or Ctrl+C)")
            with contextlib.suppress(KeyboardInterrupt):
                stop.wait()
    finally:
        running.stop()
    return 0


def _give_streams() -> None:
    """A windowed program (the packaged ``yomineko-app.exe`` on Windows) has no console, so
    ``sys.stdout`` and ``sys.stderr`` are None. The web server's logging setup then fails before
    any window opens; point them at the null device instead."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115


def main(argv: list[str] | None = None) -> int:
    """The ``yomineko-app`` program."""
    _give_streams()
    parser = argparse.ArgumentParser(prog="yomineko-app", description="The yomineko desktop app.")
    parser.add_argument("--smoke", action="store_true", help="check the install and exit")
    parser.add_argument("--browser", action="store_true", help="use the browser, not a window")
    parser.add_argument("--port", type=int, default=0, help="port on this computer (default: any)")
    args = parser.parse_args(argv)
    try:
        return run(smoke=args.smoke, browser=args.browser, port=args.port)
    except YominekoError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
