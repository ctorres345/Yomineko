"""JSON export: the script itself, narrowed to the selected lines."""

from __future__ import annotations

from yomineko.export.select import select_lines
from yomineko.model import LineKind, Script


def render_json(
    script: Script, *, include_all: bool = False, kind: LineKind | None = None
) -> tuple[str, int]:
    """JSON text and the number of lines in it. The result is a valid script file: words and
    terms are kept as they are, only ``lines`` is narrowed."""
    lines = select_lines(script, include_all=include_all, kind=kind)
    narrowed = script.model_copy(update={"lines": lines})
    return narrowed.model_dump_json(indent=2) + "\n", len(lines)
