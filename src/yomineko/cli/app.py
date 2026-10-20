"""The yomineko command line.

This module only parses arguments, calls the layers below and prints. The work itself lives in
``pipeline``, ``extract``, ``export`` and ``core``. Expected failures (``YominekoError``) are
shown as one line and exit with code 1; anything else is a bug and keeps its traceback.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from yomineko import __version__
from yomineko.cli.analyze_cmd import analyze_command
from yomineko.cli.app_cmd import app_command
from yomineko.cli.common import handle_errors
from yomineko.cli.dict_cmd import dict_app
from yomineko.cli.known_cmd import known_app
from yomineko.cli.review_cmd import ReviewOpt, review_app
from yomineko.cli.serve_cmd import serve_command
from yomineko.cli.survey_cmd import survey_command
from yomineko.core.rom.base import Rom, load_rom
from yomineko.core.roundtrip import verify as verify_rom
from yomineko.errors import YominekoError
from yomineko.export.level import LEVELS, parse_level
from yomineko.export.select import select_lines
from yomineko.export.sentences import DEFAULT_COUNT, DEFAULT_MIN_FREQ
from yomineko.export.study import DEFAULT_PLAYER_NAME
from yomineko.extract import ExtractResult, is_japanese
from yomineko.extract import extract as run_extract
from yomineko.model import LineKind
from yomineko.pipeline.exporting import EXTENSIONS, ExportRequest, build_export
from yomineko.pipeline.extraction import find_loaded_profile
from yomineko.pipeline.known import load_known
from yomineko.pipeline.study import parse_decks
from yomineko.pipeline.workspace import Workspace, cli_workspace
from yomineko.profile.loader import (
    LoadedProfile,
    ProfileError,
    find_profile,
    load_profile,
    packaged_profiles,
    resolve_profile,
)
from yomineko.profile.schema import PROFILE_ID
from yomineko.profile.template import render_skeleton
from yomineko.script_io import read_script, write_script

app = typer.Typer(
    help="Extract the Japanese script from game ROMs you own and turn it into study material.",
    no_args_is_help=True,
    add_completion=False,
)
profile_app = typer.Typer(help="Work with game profiles.", no_args_is_help=True)
app.add_typer(profile_app, name="profile")
app.add_typer(dict_app, name="dict")
app.add_typer(review_app, name="review")
app.add_typer(known_app, name="known")
app.command("analyze")(analyze_command)
app.command("serve")(serve_command)
app.command("app")(app_command)
app.command("survey")(survey_command)

OUT_DIR = Path("yomineko-out")

RomArg = Annotated[
    Path, typer.Argument(metavar="ROM", help="A ROM file (.gba, .gbc), or a .zip with one.")
]
ProfileOpt = Annotated[
    str | None,
    typer.Option(
        "--profile", "-p", help="Profile id or path to a profile file. Default: match by checksum."
    ),
]


class ExportFormat(str, Enum):
    json = "json"
    csv = "csv"
    anki = "anki"
    xlsx = "xlsx"


class Content(str, Enum):
    lines = "lines"
    words = "words"
    sentences = "sentences"


class OrderOpt(str, Enum):
    frequency = "frequency"
    rom = "rom"


class LevelOpt(str, Enum):
    starting = "starting"
    basics = "basics"
    intermediate = "intermediate"
    advanced = "advanced"


LEVEL_HELP = (
    "Words you already know get no card: "
    + "; ".join(f"{k}: {v.description.lower()}" for k, v in LEVELS.items())
    + ". How common a word is comes from the dictionary's newspaper word counts."
)


class KindFilter(str, Enum):
    dialogue = "dialogue"
    term = "term"


KIND_FILTERS: dict[KindFilter, LineKind] = {
    KindFilter.dialogue: "dialogue",
    KindFilter.term: "term",
}


def _version(value: bool) -> None:
    if value:
        typer.echo(f"yomineko {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version, is_eager=True, help="Show the version."),
    ] = False,
) -> None:
    """Extract the Japanese script from game ROMs you own and turn it into study material.

    yomineko does not include ROMs, game scripts or decks, and nothing leaves your machine.
    """


# ------------------------------------------------------------------ helpers


def _extract(rom_path: Path, spec: str | None) -> tuple[Rom, LoadedProfile, ExtractResult]:
    rom = load_rom(rom_path)
    loaded = find_loaded_profile(rom, spec)
    return rom, loaded, run_extract(rom, loaded)


# ----------------------------------------------------------------- commands


@app.command()
@handle_errors
def info(rom_path: RomArg, profile: ProfileOpt = None) -> None:
    """Show a ROM's header, checksum and the profile that matches it."""
    rom = load_rom(rom_path)
    matched = resolve_profile(profile) if profile else find_profile(rom.sha1)
    typer.echo(f"File:       {rom.source}")
    typer.echo(f"Title:      {rom.title}")
    typer.echo(f"Game code:  {rom.game_code}")
    typer.echo(f"Revision:   {rom.revision}")
    typer.echo(f"Platform:   {rom.platform}")
    typer.echo(f"Size:       {len(rom):,} bytes")
    typer.echo(f"SHA-1:      {rom.sha1}")
    if not is_japanese(rom):
        typer.echo("Profile:    none (not a Japanese release: yomineko reads Japanese games)")
    elif matched is None:
        typer.echo("Profile:    none (this ROM is not supported yet)")
    else:
        typer.echo(f"Profile:    {matched.profile.id} ({matched.profile.title})")


@app.command()
@handle_errors
def extract(
    rom_path: RomArg,
    profile: ProfileOpt = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output", "-o", help="Script file to write. Default: yomineko-out/<id>/script.json"
        ),
    ] = None,
) -> None:
    """Extract the script from a ROM into a JSON file."""
    _, loaded, result = _extract(rom_path, profile)
    dest = output or OUT_DIR / loaded.profile.id / "script.json"
    write_script(result.script, dest)
    unique = select_lines(result.script)
    dialogue = sum(1 for x in unique if x.kind == "dialogue")
    typer.echo(
        f"Extracted {len(result.strings):,} strings in {len(result.banks):,} banks "
        f"({len(unique):,} unique readable lines: {dialogue:,} dialogue, "
        f"{len(unique) - dialogue:,} terms)."
    )
    if result.unstable:
        typer.echo(
            f"{len(result.unstable)} strings were left out: they do not rebuild identically.",
            err=True,
        )
    typer.echo(f"Wrote {dest}")


@app.command()
@handle_errors
def verify(rom_path: RomArg, profile: ProfileOpt = None) -> None:
    """Rebuild the ROM from the extracted text and compare it with the original."""
    rom, loaded, result = _extract(rom_path, profile)
    check = verify_rom(rom.data, result.script.lines, loaded.codec(rom.data), result.blocks)
    if check.ok:
        typer.echo(f"OK: the rebuilt ROM matches the original (sha1 {check.sha1}).")
        if check.decompressed_checked:
            typer.echo(
                f"{check.decompressed_checked:,} lines in {len(result.blocks)} compressed blocks "
                "re-encode to the exact bytes of the decompressed data (the compressed stream "
                "itself is not rebuilt)."
            )
        if result.unstable:
            typer.echo(f"({len(result.unstable)} strings were left out and are untouched.)")
        return
    typer.echo(
        f"MISMATCH: rebuilt sha1 {check.sha1}, original {check.expected_sha1}; "
        f"{len(check.mismatches)} lines re-encode differently, "
        f"{len(check.length_changes)} changed length.",
        err=True,
    )
    raise typer.Exit(1)


@app.command()
@handle_errors
def export(
    script_path: Annotated[
        Path, typer.Argument(metavar="SCRIPT", help="A script.json from `extract`.")
    ],
    fmt: Annotated[ExportFormat, typer.Option("--format", "-f", help="Output format.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="File to write. Default: next to the script."),
    ] = None,
    include_all: Annotated[
        bool,
        typer.Option("--all", help="Include repeated lines and lines with no readable text."),
    ] = False,
    kind: Annotated[KindFilter | None, typer.Option(help="Only this kind of line.")] = None,
    content: Annotated[
        Content | None,
        typer.Option(help="For csv and json: the text lines, the word list or the sentences."),
    ] = None,
    min_freq: Annotated[
        int | None,
        typer.Option(
            min=1,
            help="Words only count if seen this often (default 1 for a word list, "
            f"{DEFAULT_MIN_FREQ} for sentences and decks).",
        ),
    ] = None,
    level: Annotated[LevelOpt, typer.Option(help=LEVEL_HELP)] = LevelOpt.starting,
    no_known: Annotated[
        bool,
        typer.Option(
            "--no-known",
            help='Make cards for the words marked "I know this" too (see `yomineko known`).',
        ),
    ] = False,
    workspace: Annotated[
        Path | None,
        typer.Option(help="Folder whose known words to leave out. Default: ./yomineko-out"),
    ] = None,
    sentences: Annotated[
        int, typer.Option(min=1, help="Sentences to pick (sentence list, Anki, XLSX).")
    ] = DEFAULT_COUNT,
    order: Annotated[
        OrderOpt, typer.Option(help="Sentence order: easiest first, or as in the ROM.")
    ] = OrderOpt.frequency,
    decks: Annotated[
        str | None,
        typer.Option(help="Anki and XLSX: which of words,sentences,terms (default: all)."),
    ] = None,
    deck_name: Annotated[
        str | None, typer.Option(help="Anki: the root deck name (default: the game's title).")
    ] = None,
    player_name: Annotated[
        str,
        typer.Option(
            help="Anki and XLSX: the name shown where the game puts the player's name "
            "(a placeholder reads badly and is spelled out by text-to-speech). "
            "Default: a Japanese stand-in name.",
            show_default=False,  # the default is Japanese; a cp1252 console cannot print it
        ),
    ] = DEFAULT_PLAYER_NAME,
    profile: ProfileOpt = None,
    review: ReviewOpt = None,
    no_packaged_review: Annotated[
        bool,
        typer.Option(
            "--no-packaged-review", help="Sentences: ignore the review shipped for this game."
        ),
    ] = False,
) -> None:
    """Export a script: lines, words or sentences as JSON or CSV; a study deck as Anki or XLSX.

    By default each distinct line appears once. Sentences, Anki and XLSX need `analyze` first.
    Words, sentences and decks leave out the words marked "I know this" (`yomineko known`).
    """
    study_format = fmt in (ExportFormat.anki, ExportFormat.xlsx)
    if study_format and content is not None:
        raise YominekoError(
            f"--content does not apply to {fmt.value}: it holds the whole study set "
            "(choose parts with --decks)"
        )
    chosen = content or Content.lines
    if chosen is not Content.lines and (include_all or kind):
        raise YominekoError("--all and --kind apply to lines; they cannot be used with words")
    if decks and not study_format:
        raise YominekoError("--decks applies to anki and xlsx")
    script = read_script(script_path)
    dest = output or script_path.with_name(f"{script_path.stem}.export.{EXTENSIONS[fmt.value]}")
    if dest.resolve() == script_path.resolve():
        raise YominekoError(f"{dest}: the output would overwrite the script it reads")
    done = build_export(
        script,
        ExportRequest(
            format=fmt.value,
            content=chosen.value,
            min_freq=min_freq,
            level=parse_level(level.value),
            known=frozenset()
            if no_known
            else load_known(Workspace(workspace) if workspace else cli_workspace()),
            sentences=sentences,
            order=order.value,
            decks=parse_decks(decks),
            deck_name=deck_name,
            player_name=player_name,
            include_all=include_all,
            kind=KIND_FILTERS[kind] if kind else None,
            profile_spec=profile,
            review_files=review,
            use_packaged_review=not no_packaged_review,
        ),
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(done.data)
    typer.echo(f"{done.summary} to {dest}")


# ------------------------------------------------------------ profile group


@profile_app.command("list")
@handle_errors
def profile_list() -> None:
    """List the profiles that ship with yomineko."""
    profiles = packaged_profiles()
    if not profiles:
        typer.echo("No packaged profiles.")
        return
    for p in profiles:
        rom = p.profile.rom
        typer.echo(f"{p.profile.id}  {rom.game_code}  {rom.sha1[:12]}  {p.profile.title}")


@profile_app.command("validate")
@handle_errors
def profile_validate(
    paths: Annotated[
        list[Path] | None,
        typer.Argument(help="Profile files to check. Default: every packaged profile."),
    ] = None,
) -> None:
    """Check profiles against the schema, and that their encoding table loads."""
    failed = 0
    if paths:
        for path in paths:
            try:
                loaded = load_profile(path)
                loaded.check_table()  # a table encoding must load too
                loaded.plain()
            except YominekoError as e:
                failed += 1
                typer.echo(f"FAIL {e}", err=True)
            else:
                typer.echo(f"ok   {path}")
    else:
        for loaded in packaged_profiles():
            loaded.check_table()
            loaded.plain()
            typer.echo(f"ok   {loaded.profile.id}")
    if failed:
        raise typer.Exit(1)


@profile_app.command("new")
@handle_errors
def profile_new(
    profile_id: Annotated[
        str, typer.Argument(metavar="ID", help="Lowercase letters, digits, dashes.")
    ],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Default: ./<id>.yaml")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,
) -> None:
    """Write a commented, valid profile skeleton to fill in for a new game."""
    if not PROFILE_ID.match(profile_id):
        raise ProfileError(
            f"{profile_id!r} is not a valid id: use lowercase letters, digits, dashes"
        )
    dest = output or Path(f"{profile_id}.yaml")
    if dest.exists() and not force:
        raise ProfileError(f"{dest} already exists (use --force to overwrite)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_skeleton(profile_id), encoding="utf-8", newline="\n")
    typer.echo(f"Wrote {dest}. Fill in the TODO values, then run: yomineko profile validate {dest}")
