"""Export the word list (CSV or JSON), most frequent first.

CSV columns: rank, written, kana, kanji, pos, freq, common, jmdict_id, meanings, examples,
jmdict_rank. ``rank`` is the word's place in the full frequency list, so it does not change with
``min_freq``, the level or the words marked known; ``jmdict_rank`` is how common the word is in
general (see ``Word``, empty for a script analysed before schema 4). ``meanings`` are separated
by " | " and ``examples`` (line ids) by spaces. The file ends with a ``#`` comment line crediting
the dictionary; Anki's importer skips such lines.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Collection

from yomineko.errors import YominekoError
from yomineko.export.level import DEFAULT_LEVEL, Level, check_ranked, is_known
from yomineko.model import Script, Word

COLUMNS = (
    "rank",
    "written",
    "kana",
    "kanji",
    "pos",
    "freq",
    "common",
    "jmdict_id",
    "meanings",
    "examples",
    "jmdict_rank",
)


class NotAnalysedError(YominekoError):
    """The script has no words yet."""


def select_words(
    script: Script,
    min_freq: int = 1,
    level: Level = DEFAULT_LEVEL,
    known: Collection[int] = frozenset(),
) -> list[tuple[int, Word]]:
    """(rank, word) pairs with at least ``min_freq`` occurrences that ``level`` does not skip
    and the learner has not marked ``known``."""
    if not script.words:
        raise NotAnalysedError(
            "this script has no words yet. Run `yomineko analyze` on it first "
            "(it needs the dictionary: `yomineko dict download`)."
        )
    check_ranked(script, level)
    return [
        (rank, w)
        for rank, w in enumerate(script.words, start=1)
        if w.freq >= min_freq and not is_known(w, level, known)
    ]


def render_words_csv(
    script: Script,
    *,
    min_freq: int = 1,
    level: Level = DEFAULT_LEVEL,
    known: Collection[int] = frozenset(),
) -> tuple[str, int]:
    selected = select_words(script, min_freq, level, known)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for rank, w in selected:
        writer.writerow(
            [
                rank,
                w.written,
                w.kana,
                w.kanji,
                w.pos,
                w.freq,
                "yes" if w.common else "no",
                w.jmdict_id,
                " | ".join(w.meanings),
                " ".join(w.examples),
                "" if w.jmdict_rank is None else w.jmdict_rank,
            ]
        )
    if script.dictionary:
        out.write(f"# {script.dictionary.credit}\n")
    return out.getvalue(), len(selected)


def render_words_json(
    script: Script,
    *,
    min_freq: int = 1,
    level: Level = DEFAULT_LEVEL,
    known: Collection[int] = frozenset(),
) -> tuple[str, int]:
    """A valid script file holding only the selected words (lines and terms are left out)."""
    selected = select_words(script, min_freq, level, known)
    narrowed = script.model_copy(
        update={"words": [w for _, w in selected], "lines": [], "terms": []}
    )
    return narrowed.model_dump_json(indent=2) + "\n", len(selected)
