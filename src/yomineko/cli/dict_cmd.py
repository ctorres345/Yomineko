"""``yomineko dict``: download and inspect the JMdict dictionary."""

from __future__ import annotations

from typing import Annotated

import typer

from yomineko.analyze.dictionary.install import dictionary_info, install_dictionary
from yomineko.analyze.dictionary.paths import ENV_VAR, data_dir, index_path
from yomineko.analyze.dictionary.source import DEFAULT_URL
from yomineko.cli.common import handle_errors

dict_app = typer.Typer(help="Download and inspect the JMdict dictionary.", no_args_is_help=True)


@dict_app.command("download")
@handle_errors
def dict_download(
    url: Annotated[
        str, typer.Option("--url", help="Where to download JMdict_e.gz from (HTTPS only).")
    ] = DEFAULT_URL,
) -> None:
    """Download JMdict once and build the local index (about 11 MB download).

    This is the only command that uses the network. JMdict is (c) EDRDG, CC BY-SA 4.0.
    """
    typer.echo(f"Downloading {url} ...")
    info = install_dictionary(url=url)
    typer.echo(f"Indexed {info.entries:,} entries (dictionary date {info.date}).")
    typer.echo(f"Stored in {info.path}")
    typer.echo(info.credit)


@dict_app.command("status")
@handle_errors
def dict_status() -> None:
    """Show whether the dictionary is installed, and where."""
    info = dictionary_info()
    if info is None:
        typer.echo(f"No dictionary installed (it would be stored in {index_path()}).")
        typer.echo("Download it once with: yomineko dict download")
        typer.echo(f"To store it elsewhere, set {ENV_VAR}. Current folder: {data_dir()}")
        return
    typer.echo(f"Path:     {info.path}")
    typer.echo(f"Entries:  {info.entries:,}")
    typer.echo(f"Date:     {info.date}")
    typer.echo(f"Source:   {info.source}")
    typer.echo(info.credit)
