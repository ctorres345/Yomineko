"""``yomineko known``: the words you marked "I know this", which get no card in any game."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yomineko.analyze.dictionary.install import dictionary_info
from yomineko.analyze.worklist import describe_entry
from yomineko.cli.common import handle_errors
from yomineko.errors import YominekoError
from yomineko.pipeline.analysis import open_dictionary
from yomineko.pipeline.known import known_path, load_known, mark_known, save_known, unmark_known
from yomineko.pipeline.workspace import Workspace, app_workspace, cli_workspace

known_app = typer.Typer(
    help='Words you marked "I know this": no card for them in any game.', no_args_is_help=True
)

WorkspaceOpt = Annotated[
    Path | None,
    typer.Option(help="Folder that holds your games. Default: ./yomineko-out"),
]
AppOpt = Annotated[
    bool, typer.Option("--app", help="Use the list of the desktop app instead (its own folder).")
]
IdsArg = Annotated[list[int], typer.Argument(metavar="JMDICT_ID...", help="JMdict entry ids.")]


def _workspace(workspace: Path | None, use_app: bool) -> Workspace:
    if workspace and use_app:
        raise YominekoError("--workspace and --app name two folders: choose one")
    if use_app:
        return app_workspace()
    return Workspace(workspace) if workspace else cli_workspace()


def _check_ids(ids: list[int]) -> None:
    bad = [i for i in ids if i <= 0]
    if bad:
        raise YominekoError(f"{bad[0]} is not a JMdict entry id")


@known_app.command("list")
@handle_errors
def known_list(workspace: WorkspaceOpt = None, use_app: AppOpt = False) -> None:
    """List the known words: their JMdict ids, and their first English meaning when the dictionary
    is installed. (The words are not printed: a Windows console may not show Japanese.)"""
    folder = _workspace(workspace, use_app)
    known = sorted(load_known(folder))
    if not known:
        typer.echo(f"No words are marked as known ({known_path(folder)}).")
        return
    if dictionary_info() is None:
        for entry_id in known:
            typer.echo(str(entry_id))
    else:
        with open_dictionary() as dictionary:
            for entry_id in known:
                c = describe_entry(dictionary, entry_id)
                typer.echo(f"{entry_id}\t{c.meaning}")
    typer.echo(f"{len(known):,} known word{'' if len(known) == 1 else 's'} in {known_path(folder)}")


@known_app.command("add")
@handle_errors
def known_add(ids: IdsArg, workspace: WorkspaceOpt = None, use_app: AppOpt = False) -> None:
    """Mark words as known by their JMdict ids."""
    _check_ids(ids)
    known = mark_known(_workspace(workspace, use_app), ids)
    typer.echo(f"{len(known):,} known word{'' if len(known) == 1 else 's'}.")


@known_app.command("remove")
@handle_errors
def known_remove(ids: IdsArg, workspace: WorkspaceOpt = None, use_app: AppOpt = False) -> None:
    """Take words off the known list (they get cards again)."""
    known = unmark_known(_workspace(workspace, use_app), ids)
    typer.echo(f"{len(known):,} known word{'' if len(known) == 1 else 's'}.")


@known_app.command("clear")
@handle_errors
def known_clear(
    workspace: WorkspaceOpt = None,
    use_app: AppOpt = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask first.")] = False,
) -> None:
    """Forget every known word."""
    folder = _workspace(workspace, use_app)
    count = len(load_known(folder))
    if not count:
        typer.echo("No words are marked as known.")
        return
    if not yes:
        typer.confirm(f"Forget all {count:,} known words?", abort=True)
    save_known(folder, [])
    typer.echo(f"Forgot {count:,} known word{'' if count == 1 else 's'}.")
