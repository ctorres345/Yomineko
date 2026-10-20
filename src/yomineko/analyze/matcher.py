"""Choose the dictionary entry for a token.

Ported from ``JMdict.find`` in the first prototype. Kana-only text is ambiguous (こと may
be 事, 琴 or 古都), so every candidate is ranked, best first, by:

1. does its part of speech agree with the tokenizer's?
2. is it the tokenizer's own kanji guess *and* common?
3. is it common at all?
4. for an inflected verb or adjective, does its reading start like the token's (止め is やめる or
   とめる, not both)?
5. JMdict's frequency rank for the reading,
6. the entry id (so the order is always the same).

The token's reading is that of the *inflected* form (聞い is きい, the entry is きく), so for an
inflected word written with kanji the tokenizer's normalised form alone picks the entries; the
reading only has to start the same way. Without that, the right entry is thrown away and any
word that sounds like the stem (忌諱 きい) takes its place.

``candidates`` returns the whole ranked list: the first is the pick, the rest are the
alternatives a reviewer may want instead (the worklist uses them).
"""

from __future__ import annotations

from yomineko.analyze.dictionary.store import Dictionary
from yomineko.analyze.dictionary.text import kata_to_hira
from yomineko.analyze.dictionary.xml_parser import Entry
from yomineko.analyze.tokenizer import Token

# Sudachi part of speech -> substrings JMdict's part-of-speech descriptions must contain
POS_MAP = {
    "動詞": ["verb"],
    "形容詞": ["adjective (keiyoushi)"],
    "名詞": ["noun"],
    "副詞": ["adverb"],
    "形状詞": ["adjectival noun", "na-adjective", "noun"],
    "感動詞": ["interjection"],
    "代名詞": ["pronoun"],
    "連体詞": ["pre-noun", "prenominal"],
    "接続詞": ["conjunction"],
}


INFLECTING = frozenset({"動詞", "形容詞"})


def is_inflected(token: Token) -> bool:
    """A verb or adjective written with kanji whose form is not its dictionary form."""
    return token.pos in INFLECTING and not token.is_kana and token.surface != token.normalized


def pos_agrees(entry: Entry, sudachi_pos: str) -> bool:
    want = POS_MAP.get(sudachi_pos)
    if not want:
        return True
    tags = " ".join(t for s in entry.senses for t in s.pos).lower()
    return any(w in tags for w in want)


def candidates(dictionary: Dictionary, token: Token) -> list[int]:
    """Entry ids for ``token``, best first; empty if the word is not in the dictionary."""
    reading = kata_to_hira(token.reading)
    inflected = is_inflected(token)
    guess = set()
    for entry_id in dictionary.ids_by_kanji(token.normalized):
        entry = dictionary.entry(entry_id)
        if entry and (inflected or reading in {kata_to_hira(r) for r, _ in entry.kana}):
            guess.add(entry_id)
    if not token.is_kana and guess:
        found = guess
    else:
        found = (
            guess
            | set(dictionary.ids_by_reading(reading))
            | set(dictionary.ids_by_reading(kata_to_hira(token.normalized)))
        )

    def starts_alike(entry: Entry | None) -> bool:
        return entry is not None and any(kata_to_hira(r)[:1] == reading[:1] for r, _ in entry.kana)

    def sort_key(entry_id: int) -> tuple[bool, bool, bool, bool, int, int]:
        entry = dictionary.entry(entry_id)
        agrees = entry is not None and pos_agrees(entry, token.pos)
        common = dictionary.common(entry_id)
        return (
            not agrees,
            not (entry_id in guess and common),
            not common,
            inflected and not starts_alike(entry),
            dictionary.rank(entry_id, reading),
            entry_id,
        )

    return sorted(found, key=sort_key)
