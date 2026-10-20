"""Build an export file in memory: the choices behind ``yomineko export`` and the web download.

The CLI writes the bytes to the path it was given; the web app sends them as a download.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from yomineko.errors import YominekoError
from yomineko.export import csv_export
from yomineko.export.anki import write_apkg
from yomineko.export.json_export import render_json
from yomineko.export.level import DEFAULT_LEVEL, Level
from yomineko.export.sentences import DEFAULT_COUNT, DEFAULT_MIN_FREQ, Order, order_sentences
from yomineko.export.sentences_export import render_sentences_csv, render_sentences_json
from yomineko.export.study import ALL_DECKS, Deck, build_study
from yomineko.export.words_export import render_words_csv, render_words_json
from yomineko.export.xlsx_export import write_xlsx
from yomineko.model import LineKind, Script
from yomineko.pipeline.study import choose_sentences

Format = Literal["json", "csv", "anki", "xlsx"]
Content = Literal["lines", "words", "sentences"]
STUDY_FORMATS = ("anki", "xlsx")
EXTENSIONS: dict[str, str] = {"json": "json", "csv": "csv", "anki": "apkg", "xlsx": "xlsx"}
MEDIA_TYPES: dict[str, str] = {
    "json": "application/json",
    "csv": "text/csv; charset=utf-8",
    "anki": "application/octet-stream",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass(frozen=True)
class ExportRequest:
    format: Format
    content: Content = "lines"  # csv and json only: anki and xlsx hold the whole study set
    min_freq: int | None = None  # default: 1 for a word list, DEFAULT_MIN_FREQ otherwise
    level: Level = DEFAULT_LEVEL  # words, sentences and decks: the words the learner knows
    known: frozenset[int] = frozenset()  # and the words they marked "I know this" (JMdict ids)
    sentences: int = DEFAULT_COUNT
    order: Order = "frequency"
    decks: list[Deck] = field(default_factory=lambda: list(ALL_DECKS))
    deck_name: str | None = None
    player_name: str = "ハル"
    include_all: bool = False  # lines only
    kind: LineKind | None = None  # lines only
    profile_spec: str | None = None
    review_files: list[Path] | None = None
    use_packaged_review: bool = True


@dataclass(frozen=True)
class ExportFile:
    data: bytes
    extension: str
    media_type: str
    summary: str  # for example "Exported 5 sentences"; the caller adds where it went

    def filename(self, game_id: str, what: str = "") -> str:
        return f"{game_id}{'-' + what if what else ''}.{self.extension}"


def build_export(script: Script, request: ExportRequest) -> ExportFile:
    """The file for ``request``. Raises ``YominekoError`` if the script is not ready for it
    (not analysed, say)."""
    fmt, content = request.format, request.content
    study = fmt in STUDY_FORMATS
    extension, media = EXTENSIONS[fmt], MEDIA_TYPES[fmt]
    if study or content == "sentences":
        count = request.min_freq or DEFAULT_MIN_FREQ
        picked = choose_sentences(
            script,
            count=request.sentences,
            min_freq=count,
            profile_spec=request.profile_spec,
            review_files=request.review_files,
            use_packaged_review=request.use_packaged_review,
            level=request.level,
            known=request.known,
        )
        if study:
            deck = build_study(
                script,
                picked,
                min_freq=count,
                order=request.order,
                decks=request.decks,
                player_name=request.player_name,
                level=request.level,
                known=request.known,
            )
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / f"export.{extension}"
                if fmt == "anki":
                    cards = write_apkg(deck, path, deck_name=request.deck_name)
                else:
                    cards = write_xlsx(deck, path)
                data = path.read_bytes()
            summary = (
                f"Wrote {cards:,} cards ({len(deck.words):,} words, {len(deck.sentences):,} "
                f"sentences, {len(deck.terms):,} terms)"
            )
            return ExportFile(data, extension, media, summary)
        ordered = order_sentences(picked, request.order)
        text, n = (
            render_sentences_csv(script, ordered)
            if fmt == "csv"
            else render_sentences_json(script, ordered)
        )
    elif content == "words":
        freq = request.min_freq or 1
        text, n = (
            render_words_csv(script, min_freq=freq, level=request.level, known=request.known)
            if fmt == "csv"
            else render_words_json(script, min_freq=freq, level=request.level, known=request.known)
        )
    elif content == "lines":
        text, n = (
            csv_export.render_csv(script, include_all=request.include_all, kind=request.kind)
            if fmt == "csv"
            else render_json(script, include_all=request.include_all, kind=request.kind)
        )
    else:
        raise YominekoError(f"unknown content {content!r}")
    encoding = csv_export.ENCODING if fmt == "csv" else "utf-8"
    return ExportFile(text.encode(encoding), extension, media, f"Exported {n:,} {content}")
