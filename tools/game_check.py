#!/usr/bin/env python3
"""Check a game end to end, the way a user would use it, and write a scorecard.

    python tools/game_check.py "Some Game (Japan).zip"
    python tools/game_check.py game.gba --profile my-game --out yomineko-out/my-game

It extracts the script and rebuilds the ROM, finds the words (with the game's packaged review),
builds the Anki deck, opens the deck file and reads it back, and measures what a learner would
meet: cards per deck, empty fields, raw escape codes, sentences that stop mid-sentence, repeated
sentences, words that look like character names, review rules that no longer match anything.
It ends with a verdict: *ready*, *works, with limits* (the limits are named) or *broken*.

``check.md`` holds counts only and is safe to share. ``samples.txt`` holds game text (the top
words, 100 sentences, the probable names) for you to read; keep it under ``yomineko-out/``.
Needs the analysis extra and the dictionary (``yomineko dict download``).
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import statistics
import sys
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from yomineko.analyze.review import ReviewApplier
from yomineko.analyze.tokenizer import SudachiTokenizer, Tokenizer
from yomineko.analyze.vocabulary import analysable_lines
from yomineko.analyze.worklist import build_worklist
from yomineko.core.rom.base import load_rom
from yomineko.export.sentences import Sentence
from yomineko.model import Script
from yomineko.pipeline.analysis import open_dictionary, run_analysis
from yomineko.pipeline.exporting import ExportRequest, build_export
from yomineko.pipeline.extraction import extract_rom
from yomineko.pipeline.reviews import resolve_review
from yomineko.pipeline.study import choose_sentences

ESCAPE = re.compile(r"\{[0-9A-Fa-f]{2,4}\}")
CLOSERS = frozenset("。！？…）」』”♪〜ー")  # how a finished sentence can end
MAX_UNCLOSED = 0.10  # share of sentence cards that may stop mid-sentence
MAX_NAMES = 5  # probable names left in the worklist (words seen 8+ times)
MIN_WORDS = 300
NAME_MIN_FREQ = 8
SAMPLE_WORDS = 60
SAMPLE_SENTENCES = 100


@dataclass
class Scorecard:
    profile_id: str = ""
    title: str = ""
    verified: bool = False
    verify_note: str = ""
    strings: int = 0
    lines: int = 0
    dialogue: int = 0
    terms: int = 0
    words: int = 0
    frequent_words: int = 0
    review_rules: int = 0
    rules_applied: int = 0
    rules_unused: int = 0
    cards: dict[str, int] = field(default_factory=dict)
    empty_fields: dict[str, int] = field(default_factory=dict)
    cards_with_escapes: int = 0
    credit_on_cards: bool = False
    sentences: int = 0
    median_length: float = 0.0
    unclosed: int = 0
    repeated: int = 0
    sentences_with_escapes: int = 0
    probable_names: int = 0
    ambiguous: int = 0
    problems: list[str] = field(default_factory=list)  # what makes it "works, with limits"
    broken: list[str] = field(default_factory=list)  # what makes it unusable

    @property
    def verdict(self) -> str:
        if self.broken:
            return "broken"
        return "works, with limits" if self.problems else "ready"


@dataclass(frozen=True)
class DeckReading:
    cards: dict[str, int]
    empty_fields: dict[str, int]
    cards_with_escapes: int
    credit_on_cards: bool


def read_deck(data: bytes) -> DeckReading:
    """Open an .apkg (a zip with a SQLite collection) and count what a learner would see."""
    with tempfile.TemporaryDirectory() as folder:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extract("collection.anki2", folder)
        db = sqlite3.connect(Path(folder) / "collection.anki2")
        try:
            decks = {int(k): v["name"] for k, v in json.loads(_one(db, "decks")).items()}
            models = {int(k): v for k, v in json.loads(_one(db, "models")).items()}
            rows = db.execute(
                "SELECT n.mid, n.flds, c.did FROM notes n JOIN cards c ON c.nid = n.id"
            ).fetchall()
        finally:
            db.close()
    cards: dict[str, int] = {}
    empty: dict[str, int] = {}
    escapes = 0
    for model_id, flds, deck_id in rows:
        deck = decks[deck_id].split("::")[-1]
        cards[deck] = cards.get(deck, 0) + 1
        names = [f["name"] for f in models[model_id]["flds"]]
        values = flds.split("\x1f")
        for name, value in zip(names, values, strict=False):
            if not value.strip():
                empty[f"{deck}/{name}"] = empty.get(f"{deck}/{name}", 0) + 1
        escapes += any(ESCAPE.search(v) for v in values)
    credit = all(
        "JMdict" in t["afmt"] or "EDRDG" in t["afmt"] for m in models.values() for t in m["tmpls"]
    )
    return DeckReading(cards, empty, escapes, credit)


def _one(db: sqlite3.Connection, column: str) -> str:
    row = db.execute(f"SELECT {column} FROM col").fetchone()
    return str(row[0])


def sentence_figures(picked: list[Sentence]) -> tuple[float, int, int, int]:
    """(median length, cards not ending like a sentence, repeated texts, cards with escapes)."""
    texts = [s.text for s in picked]
    if not texts:
        return 0.0, 0, 0, 0
    return (
        statistics.median(len(t) for t in texts),
        sum(1 for t in texts if t[-1] not in CLOSERS),
        len(texts) - len(set(texts)),
        sum(1 for t in texts if ESCAPE.search(t)),
    )


def judge(card: Scorecard) -> Scorecard:
    """Fill ``broken`` and ``problems`` from the numbers."""
    if not card.verified:
        card.broken.append("the text does not rebuild the ROM")
    if card.cards_with_escapes or card.sentences_with_escapes:
        card.broken.append("raw escape codes reach the cards")
    if any("Words/Meanings" in k or "/Meaning" in k for k in card.empty_fields):
        card.broken.append("word cards without a meaning")
    if card.words < MIN_WORDS:
        card.problems.append(f"only {card.words} words")
    if card.rules_unused:
        card.problems.append(f"{card.rules_unused} review rules match nothing")
    if card.sentences and card.unclosed / card.sentences > MAX_UNCLOSED:
        card.problems.append(
            f"{card.unclosed} of {card.sentences} sentence cards do not end like a sentence"
        )
    if card.sentences and card.repeated:
        card.problems.append(f"{card.repeated} repeated sentences")
    if card.probable_names > MAX_NAMES:
        card.problems.append(f"{card.probable_names} words that look like character names")
    if not card.cards.get("3 Terms"):
        card.problems.append("no name or term cards")
    if not card.credit_on_cards:
        card.broken.append("the dictionary credit is missing from the cards")
    return card


def check_game(
    rom_path: Path,
    *,
    spec: str | None = None,
    make_tokenizer: Callable[[], Tokenizer] = SudachiTokenizer,
    samples: Path | None = None,
) -> Scorecard:
    rom = load_rom(rom_path)
    extraction = extract_rom(rom, spec)
    return check_script(
        extraction.script,
        make_tokenizer=make_tokenizer,
        samples=samples,
        verified=extraction.status.rebuild_ok,
        strings=extraction.status.strings,
    )


def check_script(
    script: Script,
    *,
    make_tokenizer: Callable[[], Tokenizer],
    samples: Path | None = None,
    verified: bool = True,
    verify_note: str = "",
    strings: int = 0,
) -> Scorecard:
    card = Scorecard(
        profile_id=script.game.profile_id,
        title=script.game.title,
        verified=verified,
        verify_note=verify_note,
        strings=strings,
    )
    unique = [x for x in script.lines if x.text and x.duplicate_of is None]
    card.lines = len(unique)
    card.dialogue = sum(1 for x in unique if x.kind == "dialogue")
    card.terms = card.lines - card.dialogue
    analysis = run_analysis(script, make_tokenizer)
    done = analysis.script
    card.words = len(done.words)
    card.frequent_words = sum(1 for w in done.words if w.freq >= 3)
    if analysis.report is not None:
        card.review_rules = analysis.report.rules
        card.rules_applied = analysis.report.applied
        card.rules_unused = len(analysis.report.unused)
    deck = build_export(done, ExportRequest(format="anki"))
    reading = read_deck(deck.data)
    card.cards = reading.cards
    card.empty_fields = reading.empty_fields
    card.cards_with_escapes = reading.cards_with_escapes
    card.credit_on_cards = reading.credit_on_cards
    picked = choose_sentences(done, count=1000, min_freq=4)
    card.sentences = len(picked)
    card.median_length, card.unclosed, card.repeated, card.sentences_with_escapes = (
        sentence_figures(picked)
    )
    review = resolve_review(done, None)
    with open_dictionary() as dictionary:
        # what is left to look at: a word the review decides (a dropped name, a corrected pick)
        # no longer reaches the learner as it was picked
        items = build_worklist(
            analysable_lines(done),
            make_tokenizer(),
            dictionary,
            review=ReviewApplier(review, dictionary) if review else None,
            min_freq=NAME_MIN_FREQ,
        )
    card.probable_names = sum(1 for i in items if i.reason)
    card.ambiguous = sum(1 for i in items if not i.reason)
    if samples is not None:
        _write_samples(samples, done, picked, items)
    return judge(card)


def _write_samples(path: Path, script: Script, picked: list[Sentence], items: list) -> None:  # type: ignore[type-arg]
    lines = ["TOP WORDS (rank, written, reading, seen, meaning)"]
    for rank, w in enumerate(script.words[:SAMPLE_WORDS], start=1):
        lines.append(f"{rank}\t{w.written}\t{w.kana}\t{w.freq}\t{w.meanings[0][:50]}")
    lines += ["", "SENTENCES (spread over the deck)"]
    step = max(1, len(picked) // SAMPLE_SENTENCES)
    lines += [f"{s.line.id}\t{s.text}" for s in picked[::step][:SAMPLE_SENTENCES]]
    lines += ["", "PROBABLE NAMES"]
    for item in items:
        if item.reason:
            lines.append(f"{item.pick.written}\t{item.pick.kana}\t{item.freq}\t{item.reason}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def render(card: Scorecard) -> str:
    """The scorecard as Markdown: counts only, no game text."""
    empty = ", ".join(f"{k}: {v}" for k, v in sorted(card.empty_fields.items())) or "none"
    cards = ", ".join(f"{k}: {v}" for k, v in sorted(card.cards.items())) or "none"
    out = [
        f"# Game check: {card.title} ({card.profile_id})",
        "",
        f"**Verdict: {card.verdict}**",
        "",
    ]
    out += [f"- broken: {b}" for b in card.broken]
    out += [f"- limit: {p}" for p in card.problems]
    out += [
        "",
        "## Numbers",
        "",
        f"- rebuild: {'ok' if card.verified else 'FAILED'} ({card.verify_note or 'byte for byte'})",
        f"- strings {card.strings:,}; distinct lines {card.lines:,} "
        f"({card.dialogue:,} dialogue, {card.terms:,} terms)",
        f"- words {card.words:,} ({card.frequent_words:,} seen 3 or more times)",
        f"- review: {card.rules_applied} of {card.review_rules} rules applied, "
        f"{card.rules_unused} unused",
        f"- cards per deck: {cards}",
        f"- empty card fields: {empty}",
        f"- cards with a raw escape: {card.cards_with_escapes}; dictionary credit on cards: "
        f"{'yes' if card.credit_on_cards else 'NO'}",
        f"- sentences {card.sentences:,}, median length {card.median_length:g}, "
        f"not ending like a sentence {card.unclosed}, repeated {card.repeated}, "
        f"with escapes {card.sentences_with_escapes}",
        f"- worklist (words seen {NAME_MIN_FREQ}+ times): {card.ambiguous} ambiguous, "
        f"{card.probable_names} probable names",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    ap.add_argument("rom", type=Path, help="a ROM file (.gba, .gbc) or a .zip with one")
    ap.add_argument("--profile", help="profile id or path (default: match by checksum)")
    ap.add_argument("--out", type=Path, help="folder for check.md and samples.txt")
    args = ap.parse_args(argv)
    rom = load_rom(args.rom)
    folder = args.out or Path("yomineko-out") / (rom.game_code.lower() or "rom")
    card = check_game(args.rom, spec=args.profile, samples=folder / "samples.txt")
    text = render(card)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "check.md").write_text(text, encoding="utf-8", newline="\n")
    sys.stdout.write(text)
    sys.stdout.write(
        f"\nWrote {folder / 'check.md'} and {folder / 'samples.txt'} (game text: private)\n"
    )
    return 0 if card.verdict != "broken" else 1


if __name__ == "__main__":
    raise SystemExit(main())
