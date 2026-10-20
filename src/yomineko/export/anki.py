"""Write an Anki deck (.apkg) from a ``StudySet``.

Ported from ``make_study_deck.py`` in the first prototype. Three note types (Word, Sentence,
Term) and up to three decks under one root: ``<game>::1 Words``, ``::2 Sentences``, ``::3 Terms``.

Ids are stable so that importing a newer deck updates cards in place and keeps review history:
- note types are shared by every game and versioned (``MODEL_VERSION``); change a template or a
  field list and the version must go up, so Anki never sees one id with two shapes;
- decks are per game, from the profile id;
- note GUIDs come from the JMdict id (words), the ROM line id (sentences) and the category plus
  text (terms).

Every card footer credits JMdict; the deck descriptions carry the full credit line.
"""

from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path
from typing import Final

import genanki

from yomineko.export.study import StudySet

MODEL_VERSION: Final = 1
FOOTER_CREDIT: Final = "JMdict (EDRDG, CC BY-SA 4.0)"

CSS: Final = """
.card { font-family: "Hiragino Kaku Gothic ProN", "Noto Sans JP", "Yu Gothic", sans-serif;
        font-size: 20px; line-height: 1.5; text-align: center; color: #1f2328;
        background: #fbfaf7; }
.night_mode .card, .nightMode .card { color: #e8e6e1; background: #1e1f22; }
.jp { font-size: 40px; }
.jp.sentence { font-size: 26px; text-align: left; display: inline-block; max-width: 30em; }
.kanji { font-size: 30px; margin-top: 6px; }
.reading { font-size: 18px; opacity: .65; }
.mean { margin: 12px auto 0; max-width: 30em; text-align: left; display: inline-block; }
.mean ol { margin: 0; padding-left: 1.4em; }
.en { font-size: 21px; margin-top: 10px; max-width: 30em; display: inline-block; text-align: left; }
.ex { margin-top: 18px; padding-top: 10px; border-top: 1px solid rgba(127,127,127,.25);
      font-size: 18px; text-align: left; display: inline-block; max-width: 30em; }
.ex .ex-en { opacity: .7; font-size: 16px; margin-top: 2px; }
.words { margin-top: 16px; font-size: 16px; text-align: left; display: inline-block;
         max-width: 30em; }
.words div { margin: 2px 0; }
.words b { font-weight: 600; }
.foot { margin-top: 16px; font-size: 12px; opacity: .45; }
.foot a { color: inherit; }
"""

FOOT: Final = '<div class="foot">{{Lookup}} · ' + FOOTER_CREDIT + "</div>"


def stable_id(*parts: str) -> int:
    """A 31-bit id (at least 2**30) derived from the parts: the same input, the same id."""
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).digest()
    return (1 << 30) + int.from_bytes(digest[:4], "big") % (1 << 30)


def _model(kind: str, name: str, fields: list[str], qfmt: str, afmt: str) -> genanki.Model:
    return genanki.Model(
        stable_id("yomineko", "model", kind, str(MODEL_VERSION)),
        f"yomineko {name}",
        fields=[{"name": n} for n in fields],
        templates=[{"name": name, "qfmt": qfmt, "afmt": afmt}],
        css=CSS,
    )


WORD_MODEL: Final = _model(
    "word",
    "Word",
    ["Word", "Kanji", "Reading", "Meaning", "Example", "ExampleEnglish", "Lookup", "Rank"],
    '<div class="jp">{{Word}}</div>',
    '{{FrontSide}}{{#Kanji}}<div class="kanji">{{Kanji}}</div>{{/Kanji}}'
    '<div class="reading">{{Reading}}</div><hr id="answer">'
    '<div class="mean">{{Meaning}}</div><div>{{tts ja_JP:Reading}}</div>'
    '{{#Example}}<div class="ex"><div>{{Example}}</div>'
    '<div class="ex-en">{{ExampleEnglish}}</div></div>{{/Example}}' + FOOT,
)
SENTENCE_MODEL: Final = _model(
    "sentence",
    "Sentence",
    ["Japanese", "English", "Words", "Lookup", "Source"],
    '<div class="jp sentence">{{Japanese}}</div>',
    '{{FrontSide}}<hr id="answer">{{#English}}<div class="en">{{English}}</div>{{/English}}'
    "<div>{{tts ja_JP:Japanese}}</div>"
    '{{#Words}}<div class="words">{{Words}}</div>{{/Words}}' + FOOT,
)
TERM_MODEL: Final = _model(
    "term",
    "Term",
    ["Japanese", "Meaning", "Category", "Lookup"],
    '<div class="jp">{{Japanese}}</div>',
    '{{FrontSide}}<hr id="answer"><div class="en">{{Meaning}}</div>'
    '<div class="reading">{{Category}}</div><div>{{tts ja_JP:Japanese}}</div>' + FOOT,
)


def esc(text: str) -> str:
    return html.escape(text or "").replace("\n", "<br>")


def _percent_encode(text: str) -> str:
    """URL-encode by hand: this module must not import a networking package, and it only builds
    a link; nothing is fetched."""
    safe = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    return "".join(c if c in safe else "".join(f"%{b:02X}" for b in c.encode()) for c in text)


def jisho(query: str) -> str:
    q = re.sub(r"\s+", " ", query.replace("〇〇", " ")).strip()
    return f'<a href="https://jisho.org/search/{_percent_encode(q)}">Jisho</a>'


def _deck(study: StudySet, root: str, key: str, name: str, about: str) -> genanki.Deck:
    description = esc(f"{about} {study.credit}".strip())
    return genanki.Deck(
        stable_id(study.profile_id, "deck", key), f"{root}::{name}", description=description
    )


def _tags(study: StudySet, *extra: str) -> list[str]:
    return [t.replace(" ", "-") for t in ("yomineko", study.profile_id, *extra) if t]


def build_package(study: StudySet, deck_name: str | None = None) -> genanki.Package:
    root = (deck_name or study.title).replace("::", ":")
    words = _deck(study, root, "words", "1 Words", "Words from the game, most frequent first.")
    sentences = _deck(
        study, root, "sentences", "2 Sentences", "Lines from the game, easiest first."
    )
    terms = _deck(study, root, "terms", "3 Terms", "Game names that are real Japanese words.")
    pid = study.profile_id

    for w in study.words:
        meaning = "<ol>" + "".join(f"<li>{esc(m)}</li>" for m in w.meanings) + "</ol>"
        words.add_note(
            genanki.Note(
                model=WORD_MODEL,
                fields=[
                    esc(w.front),
                    esc(w.kanji),
                    esc(w.kana),
                    meaning,
                    esc(w.example),
                    esc(w.example_english),
                    jisho(w.kanji or w.kana),
                    str(w.rank),
                ],
                guid=genanki.guid_for("yomineko", pid, "word", w.jmdict_id),
                tags=_tags(study, "word", w.pos),
            )
        )
    for s in study.sentences:
        listed = "".join(
            f"<div><b>{esc(g.kana)}</b>{f' ({esc(g.kanji)})' if g.kanji else ''}"
            f" — {esc(g.meaning)}</div>"
            for g in s.words
        )
        sentences.add_note(
            genanki.Note(
                model=SENTENCE_MODEL,
                fields=[esc(s.text), esc(s.english), listed, jisho(s.lookup or s.text), s.line_id],
                guid=genanki.guid_for("yomineko", pid, "sentence", s.line_id),
                tags=_tags(study, "sentence"),
            )
        )
    for t in study.terms:
        terms.add_note(
            genanki.Note(
                model=TERM_MODEL,
                fields=[esc(t.jp), esc(t.meaning), esc(t.category), jisho(t.jp)],
                guid=genanki.guid_for("yomineko", pid, "term", t.category, t.jp),
                tags=_tags(study, "term", t.category),
            )
        )
    return genanki.Package([d for d in (words, sentences, terms) if d.notes])


def write_apkg(
    study: StudySet,
    dest: str | Path,
    *,
    deck_name: str | None = None,
    timestamp: float | None = None,
) -> int:
    """Write the deck; returns the number of notes. ``timestamp`` fixes the note creation time
    (tests use it to compare two builds)."""
    package = build_package(study, deck_name)
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    package.write_to_file(str(path), timestamp=timestamp)
    return sum(len(d.notes) for d in package.decks)
