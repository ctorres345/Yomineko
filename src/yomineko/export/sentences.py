"""Pick the sentences for a study deck.

Ported from ``curate.py`` in the first prototype. Each pick should teach frequent words that
earlier picks have not covered: a candidate's gain is the sum over its words of
``1 / (1 + times covered) * 1 / log(rank + 3)``, scaled by 0.7 when the line is shorter than
10 or longer than 40 characters, and by 0.5 when it does not end like a sentence (a text box row
that stops at a comma). Whole sentences come first and fragments only fill the gaps. Structural
kinds of line (the player talking in a battle, the adventure log) can be capped, and address
ranges can be left out; both come from the profile.

With a level (``export.level``) or words marked known, words the learner already knows still
count toward a line's length and ``difficulty`` but teach nothing: the gain and a sentence's
``word_ids`` hold only the words being studied, and a line with none of them is not picked.

Nothing here knows any game's words. Phrases a game needs filtered out (debug strings, system
text) are line ids in the review file (``sentences.exclude``); ``sentences.pin`` forces a line in.
"""

from __future__ import annotations

import heapq
import math
import re
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from yomineko.errors import YominekoError
from yomineko.export.level import DEFAULT_LEVEL, Level, check_ranked, is_known
from yomineko.export.words_export import NotAnalysedError
from yomineko.model import NAME_PLACEHOLDER, Line, Script

Order = Literal["frequency", "rom"]

DEFAULT_COUNT: Final = 1000
DEFAULT_MIN_FREQ: Final = 4
TIER_SIZE: Final = 150  # sentences are grouped by the rarest word they use, 150 ranks per tier

# generic "this is not a sentence" markers: format codes, Latin words, brackets, colons, and
# texts of two characters or fewer
_NOT_TEXT = re.compile(r"%[sd]|[A-Za-z]{3,}|\d+[a-z]|\[|\]|[:：]|^[\s\S]{0,2}$")
_FRAGMENT_END = frozenset("てしやとをにがでのへもはり")
_CLOSERS = frozenset("。！？…）」』”♪〜ー！？")  # how a finished sentence can end
FRAGMENT_PENALTY: Final = 0.5
_FILLER = re.compile(r"[" + NAME_PLACEHOLDER + r"…ー！？。、「」　〜♪（）・]")
_SHAPE_END = re.compile(r"(ね|な|よ|ぜ|の|さ|わ|だ|んだ|もん|もンね|もンな)+$")
# the partner and the player may be called by any of these; lines that differ only in the
# pronoun count as one
_PRONOUN = re.compile(r"ボク|ワタシ|オイラ|わたし|ぼく|おいら|オレ|おれ")
_NAME_SUBJECT = re.compile(NAME_PLACEHOLDER + r"(は|の|に|には|を)　")

MAX_NAME_PLACEHOLDERS = 2
BODY_LENGTH = (6, 60)
MAX_PER_OPENING = 3
MIN_WORDS = 2
OPENING_LENGTH = 7


class NotReanalysedError(YominekoError):
    """The script has words but its lines do not know theirs (analysed before schema 3)."""


@dataclass(frozen=True)
class Sentence:
    line: Line
    text: str  # cleaned for a card
    word_ids: tuple[int, ...]  # JMdict ids of the words studied, in order of appearance
    difficulty: int  # rank (0 = most frequent) of the rarest word in it


def clean_for_card(text: str) -> str:
    """One line of text: breaks and runs of spaces become one full-width space, long runs of
    the same mark are shortened."""
    t = re.sub(r"[ 　]+", "　", text.replace("\n", "　")).strip("　")
    t = re.sub(r"〜{2,}", "〜", t)
    t = re.sub(r"ー{3,}", "ーー", t)
    t = re.sub(r"(…){3,}", "……", t)
    return re.sub(r"！{3,}", "！！", t)


def _kind_of(raw: str, text: str) -> str | None:
    if raw.startswith(NAME_PLACEHOLDER + "「"):
        return "name_quote"
    if _NAME_SUBJECT.match(text):
        return "name_subject"
    return None


def _shape(body: str) -> str:
    """What is left of a line once names, pronouns and sentence-final particles are removed:
    two lines with the same shape say the same thing."""
    return _SHAPE_END.sub("", _PRONOUN.sub("", body.replace(NAME_PLACEHOLDER, "")))


def sentence_ready(script: Script) -> None:
    """Raise unless ``analyze`` has run in a way that stored words on lines."""
    if not script.words:
        raise NotAnalysedError(
            "this script has no words yet. Run `yomineko analyze` on it first "
            "(it needs the dictionary: `yomineko dict download`)."
        )
    if not any(x.word_ids for x in script.lines):
        raise NotReanalysedError(
            "this script was analysed before lines kept their words. "
            "Run `yomineko analyze` on it again to export sentences."
        )


def select_sentences(
    script: Script,
    *,
    count: int = DEFAULT_COUNT,
    min_freq: int = DEFAULT_MIN_FREQ,
    exclude_ids: Collection[str] = (),
    pin_ids: Collection[str] = (),
    exclude_ranges: Sequence[tuple[int, int]] = (),
    caps: Mapping[str, int] = {},
    level: Level = DEFAULT_LEVEL,
    known: Collection[int] = frozenset(),
) -> list[Sentence]:
    """Up to ``count`` sentences in ROM order, chosen greedily for the words they teach.

    ``min_freq`` decides which words count (those seen at least that often, ranked by
    frequency). ``exclude_ids`` are never chosen; ``pin_ids`` are chosen first and skip the
    filters. ``exclude_ranges`` are (start, end) file offsets; lines in them are skipped by the
    greedy pass. ``caps`` limits the structural kinds ``name_quote`` and ``name_subject``.
    ``level`` leaves the words it skips out of each sentence's ``word_ids`` and gain, and so
    does ``known`` (JMdict ids the learner marked as known)."""
    sentence_ready(script)
    check_ranked(script, level)
    counted = [w for w in script.words if w.freq >= min_freq]
    rank = {w.jmdict_id: i for i, w in enumerate(counted)}
    no_help = {w.jmdict_id for w in counted if is_known(w, level, known)}
    excluded, pinned_ids = set(exclude_ids), set(pin_ids)
    pinned: list[tuple[Sentence, str | None]] = []
    pool: list[tuple[Sentence, str | None]] = []
    seen_shape: set[str] = set()
    opening_count: Counter[str] = Counter()
    for line in script.lines:
        if line.kind != "dialogue" or not line.text or line.duplicate_of or line.id in excluded:
            continue
        force = line.id in pinned_ids
        raw = line.text
        if not force and (
            _NOT_TEXT.search(raw) or raw.count(NAME_PLACEHOLDER) > MAX_NAME_PLACEHOLDERS
        ):
            continue
        text = clean_for_card(raw)
        if not text:
            continue
        if not force:
            if text[-1] in _FRAGMENT_END or ("（" in text and not text.startswith("（")):
                continue
            body = _FILLER.sub("", text)
            if not BODY_LENGTH[0] <= len(body) <= BODY_LENGTH[1]:
                continue
            opening = body[:OPENING_LENGTH]
            if opening_count[opening] >= MAX_PER_OPENING:
                continue
            opening_count[opening] += 1
            shape = _shape(body)
            if shape in seen_shape:
                continue
            seen_shape.add(shape)
        ids = tuple(dict.fromkeys(i for i in line.word_ids if i in rank))
        studied = tuple(i for i in ids if i not in no_help)
        if not force and (len(ids) < MIN_WORDS or not studied):
            continue
        sentence = Sentence(line, text, studied, max((rank[i] for i in ids), default=0))
        entry = (sentence, _kind_of(raw, text))
        if force:
            pinned.append(entry)
        elif not any(a <= line.address < b for a, b in exclude_ranges):
            pool.append(entry)

    chosen = [s for s, _ in pinned[:count]]
    covered: Counter[int] = Counter()
    for s in chosen:
        covered.update(s.word_ids)
    left = {kind: limit - sum(1 for _, k in pinned if k == kind) for kind, limit in caps.items()}

    def gain(s: Sentence) -> float:
        g = sum(1.0 / (1 + covered[i]) * (1.0 / math.log(rank[i] + 3)) for i in s.word_ids)
        g *= 1.0 if 10 <= len(s.text) <= 40 else 0.7
        return g * (1.0 if s.text[-1] in _CLOSERS else FRAGMENT_PENALTY)

    # Greedy with lazy re-scoring: gains only fall as words get covered, so a stale score that
    # is still the best after re-scoring is the true best. Ties go to the earlier line, as in
    # a plain "max over the pool".
    heap = [(-gain(s), i) for i, (s, _) in enumerate(pool)]
    heapq.heapify(heap)
    while heap and len(chosen) < count:
        stale, i = heapq.heappop(heap)
        sentence, kind = pool[i]
        fresh = gain(sentence)
        if fresh < -stale:
            heapq.heappush(heap, (-fresh, i))
            continue
        if kind in left:
            if left[kind] <= 0:
                continue
            left[kind] -= 1
        chosen.append(sentence)
        covered.update(sentence.word_ids)
    return sorted(chosen, key=lambda s: s.line.address)


def order_sentences(sentences: Sequence[Sentence], order: Order) -> list[Sentence]:
    """``rom``: as stored. ``frequency``: easiest first. Sentences whose rarest word is within the
    same 150 ranks form a tier; inside a tier the shorter ones come first."""
    if order == "rom":
        return sorted(sentences, key=lambda s: s.line.address)
    return sorted(sentences, key=lambda s: (s.difficulty // TIER_SIZE, len(s.text), s.line.address))
