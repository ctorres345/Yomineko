"""Pieces shared by the CLI command modules."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import typer

from yomineko.errors import YominekoError

P = ParamSpec("P")
R = TypeVar("R")


def handle_errors(fn: Callable[P, R]) -> Callable[P, R]:
    """Show a ``YominekoError`` as ``error: ...`` and exit 1, without a traceback."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except YominekoError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(1) from e

    return wrapper
