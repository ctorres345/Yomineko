"""``yomineko app``: the desktop app, from the command line."""

from __future__ import annotations

from typing import Annotated

import typer

from yomineko.cli.common import handle_errors


@handle_errors
def app_command(
    smoke: Annotated[
        bool, typer.Option("--smoke", help="Check that this install works, then exit.")
    ] = False,
    browser: Annotated[
        bool, typer.Option("--browser", help="Use the browser instead of a window.")
    ] = False,
    port: Annotated[
        int, typer.Option(min=0, max=65535, help="Port on this computer (default: any free one).")
    ] = 0,
) -> None:
    """Open yomineko in a window of its own (needs the app extra: pip install "yomineko[app]")."""
    from yomineko.app.launch import run  # imported late: it needs the web extra

    code = run(smoke=smoke, browser=browser, port=port)
    if code:
        raise typer.Exit(code)
