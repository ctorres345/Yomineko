"""Which lines an export contains."""

from __future__ import annotations

from yomineko.model import Line, LineKind, Script


def select_lines(
    script: Script, *, include_all: bool = False, kind: LineKind | None = None
) -> list[Line]:
    """Lines to export, in ROM order.

    By default: lines with readable text, each distinct text once (the first occurrence).
    ``include_all`` keeps repeats and lines with no readable text (control codes only).
    ``kind`` keeps only dialogue or only terms.
    """
    lines = script.lines
    if not include_all:
        lines = [x for x in lines if x.text and x.duplicate_of is None]
    if kind is not None:
        lines = [x for x in lines if x.kind == kind]
    return sorted(lines, key=lambda x: x.address)
