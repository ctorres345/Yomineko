"""The learner's level: which words are common enough that they already know them.

A level skips the words among the dictionary's most frequent ones (JMdict's ``nf01`` to ``nf48``
bands of 500 words each, counted in newspaper text), so a deck has no cards for words the
learner would skip anyway. Levels are named by word counts, not JLPT levels: the bands are not
the JLPT lists. Skipped words still appear in sentences; they only get no card of their own and
no help line under a sentence.

Words the learner marked "I know this" (``known``: JMdict ids, see ``pipeline.known``) are left
out the same way, in every game, whatever the level.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Final, Literal

from yomineko.errors import YominekoError
from yomineko.model import Script, Word

Level = Literal["starting", "basics", "intermediate", "advanced"]
Status = Literal["card", "known", "skipped", "rare"]
DEFAULT_LEVEL: Final[Level] = "starting"
BAND_SIZE: Final = 500  # words per JMdict nf band
SAMPLE_SIZE: Final = 10


@dataclass(frozen=True)
class LevelInfo:
    name: str
    skips: int  # how many of the dictionary's most frequent words are skipped

    @property
    def description(self) -> str:
        if not self.skips:
            return "Make cards for every word"
        return f"Skip the {self.skips:,} most common words"

    @property
    def max_rank(self) -> int:
        """Words whose ``jmdict_rank`` is at most this are skipped (0: none are)."""
        return self.skips // BAND_SIZE


LEVELS: Final[dict[Level, LevelInfo]] = {
    "starting": LevelInfo("Just starting", 0),
    "basics": LevelInfo("The basics", 1000),
    "intermediate": LevelInfo("Intermediate", 5000),
    "advanced": LevelInfo("Advanced", 10000),
}


class NotRankedError(YominekoError):
    """The script's words do not know their dictionary rank (analysed before schema 4)."""


def parse_level(text: str) -> Level:
    for level in LEVELS:
        if text == level:
            return level
    raise YominekoError(f"unknown level {text!r}: choose from {', '.join(LEVELS)}")


def is_skipped(word: Word, level: Level) -> bool:
    """True when ``level`` counts ``word`` as already known."""
    return word.jmdict_rank is not None and word.jmdict_rank <= LEVELS[level].max_rank


def is_known(word: Word, level: Level, known: Collection[int] = frozenset()) -> bool:
    """True when the learner marked ``word`` as known or ``level`` skips it: no card, no help."""
    return word.jmdict_id in known or is_skipped(word, level)


def word_status(
    word: Word, *, level: Level, min_freq: int, known: Collection[int] = frozenset()
) -> Status:
    """Whether ``word`` gets a card and, if not, why. A word marked known says so first."""
    if word.jmdict_id in known:
        return "known"
    if is_skipped(word, level):
        return "skipped"
    return "card" if word.freq >= min_freq else "rare"


def check_ranked(script: Script, level: Level) -> None:
    """Raise unless the script's words carry the rank ``level`` needs."""
    if LEVELS[level].max_rank and any(w.jmdict_rank is None for w in script.words):
        raise NotRankedError(
            "this script was analysed before words kept how common they are, so a level cannot "
            "skip any yet. Run `yomineko analyze` on it again (in the app: Analyse again)."
        )


@dataclass(frozen=True)
class Choice:
    """What a level and a minimum count leave for the word cards."""

    cards: int  # words that get a card
    skipped: int  # seen often enough, but known at this level
    rare: int  # not known, but seen fewer than ``min_freq`` times
    sample: list[Word]  # the skipped words seen most often in the game, up to SAMPLE_SIZE
    known: int = 0  # seen often enough, but marked "I know this"


def choose_words(
    script: Script, *, level: Level, min_freq: int, known: Collection[int] = frozenset()
) -> Choice:
    """Count the word cards for ``level``, ``min_freq`` and the words marked ``known`` (the
    words page and the deck agree: a word gets a card when it is seen at least ``min_freq``
    times, is not skipped and is not marked known)."""
    check_ranked(script, level)
    cards = skipped = rare = mine = 0
    sample: list[Word] = []
    for w in script.words:
        status = word_status(w, level=level, min_freq=min_freq, known=known)
        if status == "card":
            cards += 1
        elif status == "rare":
            rare += 1
        elif w.freq >= min_freq:
            if status == "known":
                mine += 1
            else:
                skipped += 1
        if status == "skipped" and len(sample) < SAMPLE_SIZE:
            sample.append(w)
    return Choice(cards, skipped, rare, sample, mine)
