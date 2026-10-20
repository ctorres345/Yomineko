"""``yomineko survey``: read-only checks that show what is different about a game's ROM."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yomineko.cli.common import handle_errors
from yomineko.core.rom.base import load_rom
from yomineko.profile.loader import find_profile, resolve_profile
from yomineko.survey import render_report, run_survey

OUT_DIR = Path("yomineko-out")


@handle_errors
def survey_command(
    rom_path: Annotated[
        Path, typer.Argument(metavar="ROM", help="A ROM file (.gba, .gbc), or a .zip with one.")
    ],
    state: Annotated[
        Path | None,
        typer.Option(
            "--state",
            help="A save state (RetroArch, mGBA) taken while a message is on screen.",
        ),
    ] = None,
    word: Annotated[
        str | None,
        typer.Option(
            "--word",
            help="A word you know is in the game, in kana (3 or more). It is searched by the "
            "spacing of its kana and is neither stored nor printed.",
        ),
    ] = None,
    compare: Annotated[
        Path | None,
        typer.Option(
            "--compare",
            help="Another version of the same game (a .gba or .zip, for instance the US "
            "release): finds where the two differ. Offsets and sizes only.",
        ),
    ] = None,
    commands: Annotated[
        str | None,
        typer.Option(
            "--commands",
            help="A draft profile (id or path) whose control codes are measured: how often each "
            "occurs, what surrounds it, how many parameters it seems to take.",
        ),
    ] = None,
    report: Annotated[
        bool,
        typer.Option(
            "--report",
            help="Also write yomineko-out/<id>/survey.md and PNG sheets of font candidates.",
        ),
    ] = False,
) -> None:
    """Run the discovery checks over a ROM (a developer tool for adding a game).

    Prints counts and offsets only, never the ROM's text. Use it to see how a game stores its
    script before writing a profile.
    """
    rom = load_rom(rom_path)
    state_bytes = state.read_bytes() if state else None
    found = run_survey(
        rom,
        word=word,
        state_file=state_bytes,
        other=load_rom(compare) if compare else None,
        command_profile=resolve_profile(commands) if commands else None,
        sheets=report,
        progress=lambda name: typer.echo(f"checking {name} ...", err=True),
    )
    text = render_report(found)
    typer.echo(text)
    if not report:
        return
    matched = find_profile(rom.sha1)
    folder = OUT_DIR / (matched.profile.id if matched else rom.game_code.lower() or "rom")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "survey.md").write_text(text, encoding="utf-8", newline="\n")
    for name, png in found.sheets.items():
        (folder / name).write_bytes(png)
    extra = f" and {len(found.sheets)} sheets" if found.sheets else ""
    typer.echo(f"Wrote {folder / 'survey.md'}{extra}")
