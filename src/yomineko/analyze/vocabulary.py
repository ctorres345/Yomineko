"""Turn the script's dialogue into a frequency-ordered word list.

Ported from ``vocab.py`` in the first prototype: tokenize each distinct dialogue line, keep
content words, pick a dictionary entry for each, and count. Every word is kept, however rare;
a minimum frequency is a choice at export time, not a loss of data here.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from yomineko.analyze.dictionary.store import Dictionary
from yomineko.analyze.dictionary.text import kata_to_hira
from yomineko.analyze.dictionary.xml_parser import Entry
from yomineko.analyze.matcher import candidates
from yomineko.analyze.review import JAPANESE, ReviewApplier
from yomineko.analyze.tokenizer import Token, Tokenizer
from yomineko.model import NAME_PLACEHOLDER, DictionarySource, Line, Script, Term, Word

KEEP_POS = frozenset(
    {"名詞", "動詞", "形容詞", "副詞", "形状詞", "連体詞", "感動詞", "代名詞", "接続詞"}
)
SKIP_SUB_POS = frozenset({"固有名詞", "数詞"})  # proper nouns and numerals
UK_TAG = "word usually written using kana alone"
# senses that are rarely what a game means; skipped when picking meanings to show
RARE_SENSE_TAGS = ("archaism", "obsolete term", "rare term", "vulgar expression or word")
MAX_EXAMPLES = 20


def usable(token: Token) -> bool:
    """Content words with something Japanese in them: not particles, names, numbers or symbols."""
    return (
        token.pos in KEEP_POS
        and token.sub_pos not in SKIP_SUB_POS
        and bool(JAPANESE.search(token.surface))
    )


def written_form(entry: Entry, reading: str) -> tuple[str, str]:
    """(how to write the word, its kanji form or ""). Words usually written in kana, and words
    whose kanji are all uncommon, are shown by their reading."""
    uk = any(UK_TAG in s.misc for s in entry.senses[:2])
    kanji = [text for text, _ in sorted(entry.kanji, key=lambda k: k[1])]
    uncommon_kanji = all(rank >= 100 for _, rank in entry.kanji)
    if not kanji or uk or (uncommon_kanji and entry.kana[0][1] < 100):
        shown = next(
            (r for r, _ in entry.kana if kata_to_hira(r) == kata_to_hira(reading)), entry.kana[0][0]
        )
        return shown, (kanji[0] if kanji else "")
    return kanji[0], kanji[0]


def meanings(entry: Entry, limit: int = 3) -> list[str]:
    """Up to ``limit`` senses, each as its first three glosses, skipping rare senses."""
    out: list[str] = []
    for sense in entry.senses:
        if any(tag in sense.misc for tag in RARE_SENSE_TAGS):
            continue
        out.append("; ".join(sense.gloss[:3]))
        if len(out) == limit:
            break
    return out or ["; ".join(entry.senses[0].gloss[:3])]


def analysable_lines(script: Script) -> list[Line]:
    """Each distinct dialogue text once: repeats and menu terms say nothing new."""
    return [x for x in script.lines if x.kind == "dialogue" and x.text and x.duplicate_of is None]


def tokens_with_candidates(
    lines: Iterable[Line], tokenizer: Tokenizer, dictionary: Dictionary
) -> Iterator[tuple[Line, Token, list[int]]]:
    """Every usable token in the lines with its ranked dictionary candidates (best first).
    Tokens the dictionary does not know are left out. Rankings are remembered per token, so a
    word seen a thousand times is only looked up once."""
    ranked_by_key: dict[tuple[str, str, str, bool], list[int]] = {}
    for line in lines:
        for token in tokenizer.tokenize(line.text.replace(NAME_PLACEHOLDER, "　")):
            if not usable(token):
                continue
            key = (token.normalized, token.reading, token.pos, token.is_kana)
            if key not in ranked_by_key:
                ranked_by_key[key] = candidates(dictionary, token)
            if ranked_by_key[key]:
                yield line, token, ranked_by_key[key]


def build_words(
    lines: Iterable[Line],
    tokenizer: Tokenizer,
    dictionary: Dictionary,
    *,
    max_examples: int = MAX_EXAMPLES,
    review: ReviewApplier | None = None,
) -> list[Word]:
    """Words in the given lines, most frequent first (ties keep first-seen order).

    With a ``review``, each occurrence is corrected before it is counted. An occurrence reached
    through a correction marked ``sentence_safe: false`` still counts toward ``freq`` but is not
    listed in ``examples``, and the word is flagged ``sentence_safe = False``."""
    return build_vocabulary(
        lines, tokenizer, dictionary, max_examples=max_examples, review=review
    ).words


@dataclass
class Vocabulary:
    words: list[Word]
    # line id -> ids of its words (reviewed, sentence-safe, first-seen order, no repeats)
    line_words: dict[str, list[int]]


def build_vocabulary(
    lines: Iterable[Line],
    tokenizer: Tokenizer,
    dictionary: Dictionary,
    *,
    max_examples: int = MAX_EXAMPLES,
    review: ReviewApplier | None = None,
) -> Vocabulary:
    """``build_words`` plus the words of each line."""
    words: dict[int, Word] = {}
    line_words: dict[str, list[int]] = {}
    current_line = ""
    seen_here: set[int] = set()
    for line, token, ranked in tokens_with_candidates(lines, tokenizer, dictionary):
        if line.id != current_line:
            current_line, seen_here = line.id, set()
        entry_id: int | None = ranked[0]
        safe = True
        if review is not None:
            resolution = review.resolve(ranked[0], line.id)
            entry_id, safe = resolution.entry_id, resolution.safe
        entry = None if entry_id is None else dictionary.entry(entry_id)
        if entry_id is None or entry is None:
            continue
        word = words.get(entry_id)
        if word is None:
            written, kanji = written_form(entry, token.reading)
            kana = next(
                (r for r, _ in entry.kana if kata_to_hira(r) == kata_to_hira(token.reading)),
                entry.kana[0][0],
            )
            word = words[entry_id] = Word(
                jmdict_id=entry_id,
                written=written,
                kana=kana,
                kanji=kanji,
                pos=token.pos,
                common=dictionary.common(entry_id),
                jmdict_rank=dictionary.rank(entry_id),
                meanings=meanings(entry),
            )
        word.freq += 1
        if not safe:
            word.sentence_safe = False
        elif entry_id not in seen_here:
            seen_here.add(entry_id)
            line_words.setdefault(line.id, []).append(entry_id)
            if len(word.examples) < max_examples:
                word.examples.append(line.id)
    if review is not None:
        review.apply_glosses(words.values())
    return Vocabulary(sorted(words.values(), key=lambda w: -w.freq), line_words)


def match_terms(script: Script, dictionary: Dictionary) -> list[Term]:
    """The script's terms, each tagged with its dictionary entry when its text matches exactly
    one (by kanji or by reading). Names that are not real words, and ones that match several
    entries, are left untagged. Dialogue-length terms are never matched."""
    kind = {x.id: x.kind for x in script.lines}
    cache: dict[str, int | None] = {}
    out: list[Term] = []
    for term in script.terms:
        if term.line_id is not None and kind.get(term.line_id) == "dialogue":
            out.append(term.model_copy(update={"jmdict_id": None}))
            continue
        if term.jp not in cache:
            ids = set(dictionary.ids_by_kanji(term.jp)) | set(
                dictionary.ids_by_reading(kata_to_hira(term.jp))
            )
            cache[term.jp] = ids.pop() if len(ids) == 1 else None
        entry_id = cache[term.jp]
        entry = None if entry_id is None else dictionary.entry(entry_id)
        if entry is None:
            out.append(term.model_copy(update={"jmdict_id": None}))
        else:
            out.append(
                term.model_copy(
                    update={"jmdict_id": entry_id, "literal": "; ".join(meanings(entry, 1))}
                )
            )
    return out


def analyze(
    script: Script,
    tokenizer: Tokenizer,
    dictionary: Dictionary,
    source: DictionarySource,
    *,
    max_examples: int = MAX_EXAMPLES,
    review: ReviewApplier | None = None,
) -> Script:
    """A copy of ``script`` with ``words``, each line's ``word_ids`` and the terms' dictionary
    matches filled in, and the dictionary credited. Read the review's report from ``review``
    afterwards."""
    vocabulary = build_vocabulary(
        analysable_lines(script), tokenizer, dictionary, max_examples=max_examples, review=review
    )
    lines = [
        x.model_copy(update={"word_ids": vocabulary.line_words.get(x.id, [])}) for x in script.lines
    ]
    return script.model_copy(
        update={
            "lines": lines,
            "words": vocabulary.words,
            "terms": match_terms(script, dictionary),
            "dictionary": source,
        }
    )
