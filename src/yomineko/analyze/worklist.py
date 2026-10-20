"""A worklist of ambiguous words, for writing review rules.

A word is *ambiguous* when the matcher's pick has at least one common alternative: こと could be
事 or 琴, so someone should look at it in context. Words with only rare alternatives are not
listed. Each item shows the pick, the alternatives, and example lines.

The list also holds *probable names*: nouns that a game's characters are called by and that the
tokenizer split into ordinary words (a surname of two kanji, a nickname spelled like a noun).
Two signs give them away, both about grammar and not about any game: the noun is often followed
by a title or an honorific (さん, 先生, 検事), or it is almost always followed by the same other
noun, both a single kanji (a surname split in two), and the two do not make a dictionary word.
They are only suggestions: a person decides.

The worklist contains game text (the example lines). It is for the person reviewing the game,
written under ``yomineko-out/``; it is never meant to be shared or committed.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from yomineko.analyze.dictionary.store import Dictionary
from yomineko.analyze.matcher import candidates
from yomineko.analyze.review import ReviewApplier
from yomineko.analyze.tokenizer import Tokenizer
from yomineko.analyze.vocabulary import meanings, tokens_with_candidates, usable, written_form
from yomineko.model import NAME_PLACEHOLDER, Line

DEFAULT_MIN_FREQ = 4  # the prototype's review covered words seen 4 or more times
MAX_EXAMPLES = 3
MAX_ALTERNATIVES = 5

# what follows a person's name: honorifics and titles (Japanese, not any game's)
HONORIFICS = frozenset(
    {
        "さん",
        "君",
        "くん",
        "ちゃん",
        "様",
        "さま",
        "殿",
        "どの",
        "氏",
        "先生",
        "先輩",
        "検事",
        "刑事",
    }
    | {"弁護士", "警部", "警官", "王子", "姫", "王", "女王", "博士", "部長", "署長", "隊長", "長官"}
)
NAME_HONORIFIC_SHARE = 0.4  # of a noun's uses followed by an honorific
NAME_HONORIFIC_MIN = 3
NAME_PAIR_SHARE = 0.8  # of a noun's uses followed by the same other noun
NAME_PAIR_MIN = 4
NAME_PARTNER_SHARE = 0.6  # of the other noun's uses preceded by it


@dataclass(frozen=True)
class Candidate:
    entry_id: int
    written: str
    kana: str
    meaning: str
    common: bool
    kanji: str = ""  # the kanji form, shown when the word is usually written in kana


@dataclass
class WorkItem:
    pick: Candidate
    freq: int = 0
    alternatives: list[Candidate] = field(default_factory=list)
    examples: list[tuple[str, str]] = field(default_factory=list)  # (line id, text)
    reason: str = ""  # why it is listed when it is not only ambiguous: "probably a name: ..."


def _one_kanji(surface: str) -> bool:
    return len(surface) == 1 and "一" <= surface <= "鿿"


def describe_entry(dictionary: Dictionary, entry_id: int, reading: str = "") -> Candidate:
    """How a reviewer sees an entry: written form, reading and first meaning."""
    entry = dictionary.entry(entry_id)
    if entry is None:  # an index that lost an entry: show the id only
        return Candidate(entry_id, "?", "?", "", False)
    written, kanji = written_form(entry, reading)
    meaning = meanings(entry, limit=1)[0]
    return Candidate(
        entry_id, written, entry.kana[0][0], meaning, dictionary.common(entry_id), kanji
    )


def _label(c: Candidate) -> str:
    kanji = f" (kanji {c.kanji})" if c.kanji and c.kanji != c.written else ""
    return f"{c.written} [{c.kana}]{kanji}"


def build_worklist(
    lines: Iterable[Line],
    tokenizer: Tokenizer,
    dictionary: Dictionary,
    *,
    review: ReviewApplier | None = None,
    min_freq: int = DEFAULT_MIN_FREQ,
    max_examples: int = MAX_EXAMPLES,
) -> list[WorkItem]:
    """Ambiguous words seen at least ``min_freq`` times, most frequent first. Words a review
    already has a rule for are left out."""
    items: dict[int, WorkItem] = {}
    ambiguity: dict[tuple[int, ...], bool] = {}
    for line, token, ranked in tokens_with_candidates(lines, tokenizer, dictionary):
        key = tuple(ranked)
        if key not in ambiguity:
            ambiguity[key] = len(ranked) > 1 and any(dictionary.common(a) for a in ranked[1:])
        if not ambiguity[key]:
            continue
        pick = ranked[0]
        if review is not None and review.has_rule(pick):
            continue
        item = items.get(pick)
        if item is None:
            item = items[pick] = WorkItem(
                pick=describe_entry(dictionary, pick, token.reading),
                alternatives=[
                    describe_entry(dictionary, a, token.reading)
                    for a in ranked[1 : 1 + MAX_ALTERNATIVES]
                ],
            )
        item.freq += 1
        if len(item.examples) < max_examples and all(line.id != i for i, _ in item.examples):
            item.examples.append((line.id, line.text))
    for entry_id, named in _probable_names(
        lines, tokenizer, dictionary, review, min_freq, max_examples
    ).items():
        if entry_id in items:
            items[entry_id].reason = named.reason
        else:
            items[entry_id] = named
    chosen = [i for i in items.values() if i.freq >= min_freq]
    return sorted(chosen, key=lambda i: (-i.freq, i.pick.entry_id))


def _probable_names(
    lines: Iterable[Line],
    tokenizer: Tokenizer,
    dictionary: Dictionary,
    review: ReviewApplier | None,
    min_freq: int,
    max_examples: int,
) -> dict[int, WorkItem]:
    """Nouns that look like names (see the module docstring), as work items without alternatives."""
    ranked_by_key: dict[tuple[str, str, str, bool], list[int]] = {}
    uses: Counter[int] = Counter()
    honorific: Counter[int] = Counter()
    pairs: Counter[tuple[int, int]] = Counter()
    joined: dict[tuple[int, int], str] = {}
    reading: dict[int, str] = {}
    examples: dict[int, list[tuple[str, str]]] = {}
    for line in lines:
        tokens = tokenizer.tokenize(line.text.replace(NAME_PLACEHOLDER, "　"))
        picks: list[int | None] = []
        for token in tokens:
            pick = None
            if usable(token) and token.pos == "名詞" and token.surface not in HONORIFICS:
                key = (token.normalized, token.reading, token.pos, token.is_kana)
                if key not in ranked_by_key:
                    ranked_by_key[key] = candidates(dictionary, token)
                pick = ranked_by_key[key][0] if ranked_by_key[key] else None
            picks.append(pick)
        for i, pick in enumerate(picks):
            if pick is None:
                continue
            uses[pick] += 1
            reading.setdefault(pick, tokens[i].reading)
            shown = examples.setdefault(pick, [])
            if len(shown) < max_examples and all(line.id != n for n, _ in shown):
                shown.append((line.id, line.text))
            if i + 1 == len(tokens):
                continue
            if tokens[i + 1].surface in HONORIFICS:
                honorific[pick] += 1
            else:
                after = picks[i + 1]
                if (
                    after is not None
                    and after != pick
                    and _one_kanji(tokens[i].surface)
                    and _one_kanji(tokens[i + 1].surface)
                ):
                    pairs[(pick, after)] += 1
                    joined[(pick, after)] = tokens[i].surface + tokens[i + 1].surface
    why: dict[int, str] = {}
    for entry_id, n in uses.items():
        h = honorific[entry_id]
        if n >= min_freq and h >= NAME_HONORIFIC_MIN and h / n >= NAME_HONORIFIC_SHARE:
            why[entry_id] = f"followed by a title or honorific in {h} of {n} uses"
    for (first, second), c in pairs.items():
        if c < NAME_PAIR_MIN or dictionary.ids_by_kanji(joined[(first, second)]):
            continue  # too rare to tell, or the two make a real compound word
        if uses[first] >= min_freq and c / uses[first] >= NAME_PAIR_SHARE:
            why.setdefault(first, f"followed by the same word in {c} of {uses[first]} uses")
        if uses[second] >= min_freq and c / uses[second] >= NAME_PARTNER_SHARE:
            why.setdefault(second, f"preceded by the same word in {c} of {uses[second]} uses")
    return {
        entry_id: WorkItem(
            pick=describe_entry(dictionary, entry_id, reading[entry_id]),
            freq=uses[entry_id],
            examples=examples[entry_id],
            reason=f"probably a name: {reason}",
        )
        for entry_id, reason in why.items()
        if review is None or not review.has_rule(entry_id)
    }


def render_worklist(items: list[WorkItem]) -> str:
    out = [
        "yomineko review worklist",
        "Contains game text (the example lines): for your own review, do not share or commit.",
        f"{len(items)} words to look at, most frequent first ({sum(1 for i in items if i.reason)} "
        "look like names). If a pick is wrong, or a word is only a name, add a rule to your "
        "review file:",
        "  - {from: <picked id>, to: <right id>}      or      - {from: <picked id>, drop: true}",
        "",
    ]
    for n, item in enumerate(items, start=1):
        p = item.pick
        out.append(f"[{n}] seen {item.freq}x   picked: {_label(p)} id {p.entry_id}")
        out.append(f"      meaning: {p.meaning}")
        if item.reason:
            out.append(f"      {item.reason}")
        out.append("      alternatives:")
        for a in item.alternatives:
            tag = "common" if a.common else "rare"
            out.append(f"        - {_label(a)} id {a.entry_id} ({tag}): {a.meaning}")
        out.append("      lines:")
        for line_id, text in item.examples:
            out.append(f"        {line_id}  {text.replace(chr(10), ' ')}")
        out.append("")
    return "\n".join(out)
