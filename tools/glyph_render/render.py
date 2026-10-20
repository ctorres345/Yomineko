"""Render every code of a byte-stream text through an emulator and keep the glyph pictures.

The ROM is patched so the message that a save state is reading says ``template`` with one code
in it; the emulator runs a few dozen frames; a fixed window of the screen holds the glyph. The
picture is kept as rows of ``#`` and ``.`` (all rows: the vertical position is information, and so
is the width).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path

DEFAULT_THRESHOLD = 140
DEFAULT_FRAMES = 70


def parse_codes(spec: str) -> list[bytes]:
    """Codes from ``"00-F9,FA00-FEFF"``: two hex digits are a byte, four a lead and an index."""
    codes: list[bytes] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        first, _, last = part.partition("-")
        last = last or first
        if len(first) != len(last) or len(first) not in (2, 4):
            raise ValueError(f"{part!r}: a range is two or four hex digits on each side")
        width = len(first) // 2
        for value in range(int(first, 16), int(last, 16) + 1):
            codes.append(value.to_bytes(width, "big"))
    return codes


def patch_message(rom: bytes, pointer: int, template: str, code: bytes) -> bytes:
    """``rom`` with the message at ``pointer`` replaced by the template (hex, ``{code}`` inside)."""
    payload = bytes.fromhex(template.replace("{code}", code.hex()))
    if pointer + len(payload) > len(rom):
        raise ValueError("the message does not fit in the ROM at that offset")
    out = bytearray(rom)
    out[pointer : pointer + len(payload)] = payload
    return bytes(out)


def to_bitmap(window: list[list[int]], threshold: int = DEFAULT_THRESHOLD) -> list[str]:
    """Rows of ``#`` (ink) and ``.``, cropped to the columns that have ink; ``[]`` if blank."""
    rows = [[v > threshold for v in line] for line in window]
    columns = [x for x in range(len(rows[0])) if any(r[x] for r in rows)] if rows else []
    if not columns:
        return []
    first, last = columns[0], columns[-1]
    return ["".join("#" if v else "." for v in r[first : last + 1]) for r in rows]


def render_codes(
    core_path: Path,
    rom: bytes,
    state: bytes,
    codes: list[bytes],
    *,
    pointer: int,
    template: str,
    window: tuple[int, int, int, int],
    frames: int = DEFAULT_FRAMES,
    threshold: int = DEFAULT_THRESHOLD,
    progress: Callable[[int, int, float], None] | None = None,
) -> Iterator[tuple[str, list[str]]]:
    """Yield ``(code as hex, glyph rows)`` for each code. A fresh core per code: slow, but nothing
    from the previous glyph can leak into the next picture."""
    from glyph_render.libretro import Core  # imported here: it needs the core library

    x0, x1, y0, y1 = window
    started = time.time()
    for n, code in enumerate(codes):
        core = Core(core_path, patch_message(rom, pointer, template, code))
        try:
            core.load_state(state)
            core.run(frames)
            rows = to_bitmap(core.gray_window(x0, x1, y0, y1), threshold)
        except Exception:  # a code that crashes the core is blank, not fatal
            rows = []
        finally:
            core.close()
        yield code.hex(), rows
        if progress and n % 100 == 0:
            progress(n, len(codes), time.time() - started)


def save_glyphs(glyphs: dict[str, list[str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(glyphs), encoding="utf-8", newline="\n")
