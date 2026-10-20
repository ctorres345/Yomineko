"""Open the dictionary and analyse a script: the steps behind ``yomineko analyze``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from yomineko.analyze.dictionary.install import (
    DictionaryInfo,
    dictionary_info,
    install_dictionary,
)
from yomineko.analyze.dictionary.store import Dictionary
from yomineko.analyze.dictionary.xml_parser import DictionaryError
from yomineko.analyze.review import ReviewApplier, ReviewReport
from yomineko.analyze.tokenizer import Tokenizer
from yomineko.analyze.vocabulary import MAX_EXAMPLES, analyze
from yomineko.model import DictionarySource, Script
from yomineko.pipeline.reviews import resolve_review

NO_DICTIONARY = "no dictionary installed. Download it once with: yomineko dict download"


def open_dictionary() -> Dictionary:
    """The installed dictionary, open for lookups (close it, or use ``with``)."""
    info = dictionary_info()
    if info is None:
        raise DictionaryError(NO_DICTIONARY)
    return Dictionary(info.path)


@dataclass(frozen=True)
class Analysis:
    script: Script
    dictionary: DictionaryInfo
    report: ReviewReport | None  # None when no review applied


def run_analysis(
    script: Script,
    make_tokenizer: Callable[[], Tokenizer],
    *,
    review_files: list[Path] | None = None,
    use_packaged_review: bool = True,
    download: bool = False,
    examples: int = MAX_EXAMPLES,
    say: Callable[[str], None] = lambda _: None,
) -> Analysis:
    """Find the words in ``script``. Checks the review and the tokenizer before anything is
    downloaded, so a mistake costs no network. ``say`` receives progress messages."""
    merged = resolve_review(script, review_files, use_packaged=use_packaged_review)
    tokenizer = make_tokenizer()  # fail on a missing extra before downloading anything
    info = dictionary_info()
    if info is None:
        if not download:
            raise DictionaryError(f"{NO_DICTIONARY} (or add --download to this command)")
        say("Downloading the dictionary ...")
        info = install_dictionary()
    source = DictionarySource(date=info.date, source=info.source, credit=info.credit)
    with Dictionary(info.path) as dictionary:
        applier = ReviewApplier(merged, dictionary) if merged else None
        result = analyze(
            script, tokenizer, dictionary, source, max_examples=examples, review=applier
        )
    return Analysis(result, info, applier.report() if applier else None)
