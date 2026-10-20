"""``yomineko serve``: the web interface in your browser."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yomineko.cli.common import handle_errors
from yomineko.pipeline.workspace import Workspace, cli_workspace
from yomineko.web.extra import require_web_extra

DEFAULT_PORT = 8765


@handle_errors
def serve_command(
    port: Annotated[
        int, typer.Option(min=1, max=65535, help="Port on this computer.")
    ] = DEFAULT_PORT,
    workspace: Annotated[
        Path | None,
        typer.Option(help="Folder that holds your games. Default: ./yomineko-out"),
    ] = None,
    no_browser: Annotated[
        bool, typer.Option("--no-browser", help="Do not open the browser.")
    ] = False,
) -> None:
    """Open the yomineko web interface. It only listens on this computer (127.0.0.1)."""
    require_web_extra()
    from yomineko.web.app import create_app  # imported late: needs the web extra
    from yomineko.web.server import run

    folder = Workspace(workspace) if workspace else cli_workspace()
    typer.echo(f"yomineko is running at http://localhost:{port}/  (Ctrl+C to stop)")
    run(create_app(folder), port, open_browser=not no_browser)
