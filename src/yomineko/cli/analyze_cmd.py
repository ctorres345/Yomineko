"""``yomineko analyze``: find the words in an extracted script."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yomineko.analyze.tokenizer import SudachiTokenizer, Tokenizer
from yomineko.analyze.vocabulary import MAX_EXAMPLES
from yomineko.cli.common import handle_errors
from yomineko.cli.review_cmd import ReviewOpt
from yomineko.pipeline.analysis import run_analysis
from yomineko.pipeline.reviews import describe_report
from yomineko.script_io import read_script, write_script

# A function so tests can replace the real tokenizer with a fake one.
make_tokenizer = SudachiTokenizer


def _tokenizer() -> Tokenizer:
    return make_tokenizer()


@handle_errors
def analyze_command(
    script_path: Annotated[
        Path, typer.Argument(metavar="SCRIPT", help="A script.json from `yomineko extract`.")
    ],
    download: Annotated[
        bool, typer.Option("--download", help="Download the dictionary first if it is missing.")
    ] = False,
    review: ReviewOpt = None,
    no_packaged_review: Annotated[
        bool,
        typer.Option("--no-packaged-review", help="Do not apply the review shipped for this game."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Where to write the result. Default: update SCRIPT."),
    ] = None,
    examples: Annotated[
        int, typer.Option(min=1, help="Example lines to keep per word.")
    ] = MAX_EXAMPLES,
) -> None:
    """Find the words in a script, with meanings and how often they occur.

    Needs the analysis extra (pip install "yomineko[analyze]") and the dictionary
    (yomineko dict download).
    """
    script = read_script(script_path)
    done = run_analysis(
        script,
        _tokenizer,
        review_files=review,
        use_packaged_review=not no_packaged_review,
        download=download,
        examples=examples,
        say=typer.echo,
    )
    result = done.script
    dest = output or script_path
    write_script(result, dest)
    common = sum(1 for w in result.words if w.common)
    frequent = sum(1 for w in result.words if w.freq >= 3)
    typer.echo(
        f"Found {len(result.words):,} distinct words ({frequent:,} appear 3 or more times, "
        f"{common:,} are common words)."
    )
    if done.report is not None:
        for text in describe_report(done.report):
            typer.echo(text)
    typer.echo(f"Wrote {dest}")
    typer.echo(f"Meanings: {done.dictionary.credit}")
