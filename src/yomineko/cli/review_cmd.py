"""``yomineko review``: validate review files, check them against a script, build a worklist."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yomineko.analyze.dictionary.install import dictionary_info
from yomineko.analyze.review import ReviewApplier, ReviewError, load_review
from yomineko.analyze.tokenizer import SudachiTokenizer, Tokenizer
from yomineko.analyze.vocabulary import analysable_lines, analyze
from yomineko.analyze.worklist import DEFAULT_MIN_FREQ, build_worklist, render_worklist
from yomineko.cli.common import handle_errors
from yomineko.errors import YominekoError
from yomineko.model import DictionarySource
from yomineko.pipeline.analysis import open_dictionary
from yomineko.pipeline.reviews import describe_report, resolve_review
from yomineko.script_io import read_script

review_app = typer.Typer(help="Corrections for wrong dictionary picks.", no_args_is_help=True)

# A function so tests can replace the real tokenizer with a fake one.
make_tokenizer = SudachiTokenizer

ReviewOpt = Annotated[
    list[Path] | None,
    typer.Option("--review", "-r", help="A review file to apply (repeatable; later ones win)."),
]


def _tokenizer() -> Tokenizer:
    return make_tokenizer()


@review_app.command("validate")
@handle_errors
def review_validate(
    paths: Annotated[
        list[Path] | None, typer.Argument(help="Review files. Default: none (name the files).")
    ] = None,
) -> None:
    """Check review files for format errors (no dictionary or ROM needed)."""
    if not paths:
        raise ReviewError("name at least one review file to validate")
    failed = 0
    for path in paths:
        try:
            review = load_review(path)
        except YominekoError as e:
            failed += 1
            typer.echo(f"FAIL {e}", err=True)
        else:
            counts = (
                f"{len(review.words)} word rules, {len(review.lines)} line rules, "
                f"{len(review.sentences.exclude)} excluded and {len(review.sentences.pin)} "
                "pinned sentence lines"
            )
            typer.echo(f"ok   {path} ({counts})")
    if failed:
        raise typer.Exit(1)


@review_app.command("check")
@handle_errors
def review_check(
    script_path: Annotated[Path, typer.Argument(metavar="SCRIPT", help="A script.json.")],
    review: ReviewOpt = None,
    no_packaged_review: Annotated[
        bool, typer.Option("--no-packaged-review", help="Do not include the packaged review.")
    ] = False,
) -> None:
    """Apply the review to a script and report rules that matched nothing or use unknown ids."""
    script = read_script(script_path)
    merged = resolve_review(script, review, use_packaged=not no_packaged_review)
    if merged is None:
        raise ReviewError(
            "no review to check: pass --review FILE (this game has no packaged review)"
        )
    tokenizer = _tokenizer()
    with open_dictionary() as dictionary:
        applier = ReviewApplier(merged, dictionary)
        info = dictionary_info()
        source = DictionarySource(date=info.date if info else "", source="", credit="")
        analyze(script, tokenizer, dictionary, source, review=applier)
    report = applier.report()
    for text in describe_report(report):
        typer.echo(text)
    known = {x.id for x in script.lines}
    missing = [i for i in (*merged.sentences.exclude, *merged.sentences.pin) if i not in known]
    if missing:
        typer.echo(
            f"{len(missing)} sentence line ids are not in this script: {', '.join(missing[:8])}"
        )
    if report.unknown_ids or missing:
        raise typer.Exit(1)


@review_app.command("worklist")
@handle_errors
def review_worklist(
    script_path: Annotated[Path, typer.Argument(metavar="SCRIPT", help="A script.json.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Default: worklist.txt next to the script."),
    ] = None,
    min_freq: Annotated[
        int, typer.Option(min=1, help="Skip words seen fewer times than this.")
    ] = DEFAULT_MIN_FREQ,
    review: ReviewOpt = None,
    no_packaged_review: Annotated[
        bool,
        typer.Option("--no-packaged-review", help="Do not skip words the packaged review covers."),
    ] = False,
) -> None:
    """List ambiguous words (a common alternative exists) with example lines, to review.

    The file contains game text: keep it for yourself.
    """
    script = read_script(script_path)
    merged = resolve_review(script, review, use_packaged=not no_packaged_review)
    tokenizer = _tokenizer()
    with open_dictionary() as dictionary:
        applier = ReviewApplier(merged, dictionary) if merged else None
        items = build_worklist(
            analysable_lines(script), tokenizer, dictionary, review=applier, min_freq=min_freq
        )
    dest = output or script_path.with_name("worklist.txt")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_worklist(items), encoding="utf-8", newline="\n")
    names = sum(1 for i in items if i.reason)
    typer.echo(
        f"{len(items):,} words to look at (seen {min_freq}+ times; {names:,} look like names) "
        f"written to {dest}"
    )
    typer.echo("It contains game text: keep it for your own review, do not share or commit it.")
