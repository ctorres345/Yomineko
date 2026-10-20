"""Labelled sheets of glyph pictures, to read by eye (needs Pillow)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CELL_W, CELL_H = 14, 13  # glyph cell in pixels before scaling


def load_glyphs(path: Path) -> dict[str, list[str]]:
    data: dict[str, list[str]] = json.loads(path.read_text(encoding="utf-8"))
    return data


def sheet_keys(glyphs: dict[str, list[str]], per_sheet: int = 128) -> list[list[str]]:
    """Codes that have ink, in code order, grouped ``per_sheet`` to a sheet."""
    keys = sorted(k for k, rows in glyphs.items() if rows)
    return [keys[i : i + per_sheet] for i in range(0, len(keys), per_sheet)]


def make_sheet(
    glyphs: dict[str, list[str]], keys: list[str], *, per_row: int = 16, scale: int = 4
) -> Any:
    """A greyscale picture with each glyph and its hex code above it."""
    from PIL import Image, ImageDraw  # an optional tool dependency

    cell_w, cell_h = CELL_W * scale + 4, CELL_H * scale + 16
    rows = -(-len(keys) // per_row)
    sheet = Image.new("L", (per_row * cell_w, rows * cell_h), 230)
    draw = ImageDraw.Draw(sheet)
    for i, key in enumerate(keys):
        x, y = (i % per_row) * cell_w, (i // per_row) * cell_h
        draw.text((x + 2, y + 1), key.upper(), fill=0)
        cell = Image.new("L", (CELL_W * scale, CELL_H * scale), 255)
        pixels = cell.load()
        assert pixels is not None
        for gy, line in enumerate(glyphs[key][:CELL_H]):
            for gx, ch in enumerate(line[:CELL_W]):
                if ch == "#":
                    for dy in range(scale):
                        for dx in range(scale):
                            pixels[gx * scale + dx, gy * scale + dy] = 0
        sheet.paste(cell, (x + 2, y + 14))
    return sheet


def write_sheets(glyphs_path: Path, out_dir: Path, per_sheet: int = 128) -> list[Path]:
    glyphs = load_glyphs(glyphs_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for n, keys in enumerate(sheet_keys(glyphs, per_sheet), start=1):
        path = out_dir / f"glyphs-{n:02d}-{keys[0]}-{keys[-1]}.png"
        make_sheet(glyphs, keys).save(path)
        written.append(path)
    return written
