"""Everything a deck or spreadsheet shows, worked out once: words, sentences and terms.

The Anki and XLSX writers both read a ``StudySet`` and only format it. The choices live here:
which words get a card (seen at least ``min_freq`` times and not skipped by the learner's level,
most frequent first), which sentences
(already picked by ``select_sentences``), what each sentence card lists as help, which sentence
is a word's example, and which game terms are real dictionary words.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

from yomineko.export.level import DEFAULT_LEVEL, Level
from yomineko.export.sentences import TIER_SIZE, Order, Sentence, order_sentences
from yomineko.export.words_export import select_words
from yomineko.model import NAME_PLACEHOLDER, Script, Word

Deck = Literal["words", "sentences", "terms"]
ALL_DECKS: Final[tuple[Deck, ...]] = ("words", "sentences", "terms")
# sentence cards do not list the commonest words (する, いる, もう ...): learners know them
HELP_MIN_RANK: Final = 40
HELP_MAX_WORDS: Final = 6
_KANA = re.compile("[ぁ-んァ-ヶ]")
# The game writes the player's name as a placeholder, which reads badly on a card and which
# text-to-speech spells out. Cards show this ordinary name instead (``--player-name`` changes it).
DEFAULT_PLAYER_NAME: Final = "ハル"


@dataclass(frozen=True)
class WordGloss:
    """One word as listed under a sentence."""

    kana: str
    kanji: str
    meaning: str


@dataclass(frozen=True)
class StudyWord:
    rank: int  # 1 = most frequent word of the game
    front: str  # what the card asks about
    kanji: str  # empty for words usually written in kana
    kana: str
    meanings: tuple[str, ...]
    pos: str
    jmdict_id: int
    freq: int
    example: str = ""
    example_english: str = ""


@dataclass(frozen=True)
class StudySentence:
    line_id: str
    text: str  # as shown, with the stand-in name
    english: str
    words: tuple[WordGloss, ...]
    tier: int  # 0 = easiest
    lookup: str = ""  # the text without the stand-in, for the dictionary link


@dataclass(frozen=True)
class StudyTerm:
    jp: str
    category: str
    meaning: str
    jmdict_id: int


@dataclass(frozen=True)
class StudySet:
    title: str
    profile_id: str
    credit: str
    min_freq: int
    words: list[StudyWord] = field(default_factory=list)
    sentences: list[StudySentence] = field(default_factory=list)
    terms: list[StudyTerm] = field(default_factory=list)


def _kanji_shown(word: Word) -> str:
    """Words usually written in kana keep no kanji line (their kanji add nothing)."""
    return word.kanji if word.kanji and word.written != word.kana else ""


def _first_gloss(word: Word) -> str:
    return word.meanings[0].split(";")[0].strip() if word.meanings else ""


def _english(sentence: Sentence) -> str:
    translation = sentence.line.translation
    return translation.text if translation else ""


def build_study(
    script: Script,
    sentences: Sequence[Sentence],
    *,
    min_freq: int,
    order: Order = "frequency",
    decks: Collection[Deck] = ALL_DECKS,
    player_name: str = DEFAULT_PLAYER_NAME,
    level: Level = DEFAULT_LEVEL,
    known: Collection[int] = frozenset(),
) -> StudySet:
    """The cards for ``decks``. ``sentences`` are the picks from ``select_sentences`` (with the
    same ``min_freq``, ``level`` and ``known``). The player-name placeholder in sentence text is
    replaced by ``player_name``."""

    def shown(text: str) -> str:
        return text.replace(NAME_PLACEHOLDER, player_name)

    study = StudySet(
        title=script.game.title,
        profile_id=script.game.profile_id,
        credit=script.dictionary.credit if script.dictionary else "",
        min_freq=min_freq,
    )
    ranked = {w.jmdict_id: (rank, w) for rank, w in select_words(script, min_freq, level, known)}

    if "words" in decks:
        # a word's example: the shortest chosen sentence that uses it
        example: dict[int, Sentence] = {}
        for s in sorted(sentences, key=lambda s: (len(s.text), s.line.address)):
            for word_id in s.word_ids:
                example.setdefault(word_id, s)
        for rank, w in ranked.values():
            ex = example.get(w.jmdict_id)
            study.words.append(
                StudyWord(
                    rank=rank,
                    front=w.kana if _KANA.search(w.kana) else w.written,
                    kanji=_kanji_shown(w),
                    kana=w.kana,
                    meanings=tuple(w.meanings),
                    pos=w.pos,
                    jmdict_id=w.jmdict_id,
                    freq=w.freq,
                    example=shown(ex.text) if ex else "",
                    example_english=_english(ex) if ex else "",
                )
            )

    if "sentences" in decks:
        for s in order_sentences(sentences, order):
            help_words = []
            for word_id in s.word_ids:
                rank, w = ranked[word_id]
                if rank > HELP_MIN_RANK:
                    help_words.append(WordGloss(w.kana, _kanji_shown(w), _first_gloss(w)))
            study.sentences.append(
                StudySentence(
                    line_id=s.line.id,
                    text=shown(s.text),
                    english=_english(s),
                    words=tuple(help_words[:HELP_MAX_WORDS]),
                    tier=s.difficulty // TIER_SIZE,
                    lookup=s.text,
                )
            )

    if "terms" in decks:
        seen: set[str] = set()
        for t in script.terms:
            if t.jmdict_id is None or t.jp in seen:
                continue
            seen.add(t.jp)
            study.terms.append(StudyTerm(t.jp, t.category, t.literal or "", t.jmdict_id))
    return study
