"""``python -m glyph_render``: render, sheets, table."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from glyph_render import render as rendering
from glyph_render import sheets, table
from glyph_render.libretro import read_rom


def _window(text: str) -> tuple[int, int, int, int]:
    x0, x1, y0, y1 = (int(v) for v in text.split(","))
    return x0, x1, y0, y1


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="glyph_render", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    r = sub.add_parser("render", help="render every code in an emulator")
    r.add_argument("--core", type=Path, required=True, help="the libretro mGBA core")
    r.add_argument("--rom", type=Path, required=True)
    r.add_argument("--state", type=Path, required=True, help="a state with a message on screen")
    r.add_argument("--pointer", type=lambda v: int(v, 0), required=True, help="ROM offset of it")
    r.add_argument(
        "--template", required=True, help="hex bytes with {code}, e.g. FF03FF35{code}FF0C"
    )
    r.add_argument("--window", type=_window, required=True, help="x0,x1,y0,y1 of the glyph")
    r.add_argument("--codes", default="00-F9,FA00-FEFF", help="ranges of hex codes")
    r.add_argument("--frames", type=int, default=rendering.DEFAULT_FRAMES)
    r.add_argument("--threshold", type=int, default=rendering.DEFAULT_THRESHOLD)
    r.add_argument("--out", type=Path, required=True, help="glyphs.json to write")

    s = sub.add_parser("sheets", help="labelled PNG sheets from glyphs.json (needs Pillow)")
    s.add_argument("glyphs", type=Path)
    s.add_argument("--out", type=Path, required=True, help="folder for the PNG files")

    t = sub.add_parser("table", help="a .tbl from a transcription (code<TAB>character)")
    t.add_argument("transcription", type=Path)
    t.add_argument("--out", type=Path, required=True)
    t.add_argument("--header", default="", help="comment lines at the top of the table")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "render":
        from yomineko.survey.state import unwrap_state

        glyphs: dict[str, list[str]] = {}
        for code, rows in rendering.render_codes(
            args.core,
            read_rom(args.rom),
            unwrap_state(args.state.read_bytes()),
            rendering.parse_codes(args.codes),
            pointer=args.pointer,
            template=args.template,
            window=args.window,
            frames=args.frames,
            threshold=args.threshold,
            progress=lambda n, total, secs: print(f"{n}/{total} {secs:.0f}s", file=sys.stderr),
        ):
            glyphs[code] = rows
        rendering.save_glyphs(glyphs, args.out)
        blank = sum(1 for v in glyphs.values() if not v)
        print(f"{len(glyphs)} codes, {blank} blank: {args.out}")
    elif args.command == "sheets":
        paths = sheets.write_sheets(args.glyphs, args.out)
        print(f"{len(paths)} sheets in {args.out}")
    else:
        aliases = table.write_table(
            table.read_transcription(args.transcription), args.out, args.header
        )
        print(f"wrote {args.out}; {len(aliases)} codes draw a character that has another code")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
