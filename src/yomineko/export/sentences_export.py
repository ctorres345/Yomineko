"""Export the chosen sentences as CSV or JSON.

CSV columns: id, text, english, tier, words. ``id`` is the line's ROM address (8 hex digits),
``words`` are JMdict ids separated by spaces, ``english`` is filled from the line's translation.
The file ends with a ``#`` comment crediting the dictionary.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

from yomineko.export.sentences import TIER_SIZE, Sentence
from yomineko.model import Script

COLUMNS = ("id", "text", "english", "tier", "words")


def render_sentences_csv(script: Script, sentences: Sequence[Sentence]) -> tuple[str, int]:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for s in sentences:
        translation = s.line.translation
        writer.writerow(
            [
                s.line.id,
                s.text,
                translation.text if translation else "",
                s.difficulty // TIER_SIZE,
                " ".join(str(i) for i in s.word_ids),
            ]
        )
    if script.dictionary:
        out.write(f"# {script.dictionary.credit}\n")
    return out.getvalue(), len(sentences)


def render_sentences_json(script: Script, sentences: Sequence[Sentence]) -> tuple[str, int]:
    """A valid script file holding only the chosen lines (words stay, for lookups)."""
    narrowed = script.model_copy(update={"lines": [s.line for s in sentences], "terms": []})
    return narrowed.model_dump_json(indent=2) + "\n", len(sentences)
