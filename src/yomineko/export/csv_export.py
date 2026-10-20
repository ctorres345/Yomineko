"""CSV export for spreadsheets.

Columns: id, address (0x...), bank, kind, text, raw, translation, translation_source.
Write the result with ``utf-8-sig`` (``ENCODING``) so Excel opens the Japanese correctly.
"""

from __future__ import annotations

import csv
import io

from yomineko.export.select import select_lines
from yomineko.model import LineKind, Script

ENCODING = "utf-8-sig"
COLUMNS = (
    "id",
    "address",
    "bank",
    "kind",
    "text",
    "raw",
    "translation",
    "translation_source",
)


def render_csv(
    script: Script, *, include_all: bool = False, kind: LineKind | None = None
) -> tuple[str, int]:
    """CSV text and the number of rows (not counting the header)."""
    lines = select_lines(script, include_all=include_all, kind=kind)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for x in lines:
        t = x.translation
        writer.writerow(
            [
                x.id,
                f"0x{x.address:X}",
                x.bank,
                x.kind,
                x.text,
                x.raw,
                t.text if t else "",
                t.source if t else "",
            ]
        )
    return out.getvalue(), len(lines)
