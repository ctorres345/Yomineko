"""Stream-parse JMdict's XML into ``Entry`` objects.

Only the standard library is used. JMdict declares its tags as entities in an internal DTD
(``<!ENTITY n "noun (common) (futsuumeishi)">``); the parser expands them, so a part of speech
reads as its full English description. External entities are never fetched.

Frequency rank (ported from the first prototype's ``_rank``): the smallest ``nfNN``
(1 is most frequent, 48 least), else 60 for words tagged news1/ichi1/spec1/spec2/gai1, else
100 (uncommon).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

from yomineko.errors import YominekoError

COMMON_TAGS = frozenset({"news1", "ichi1", "spec1", "spec2", "gai1"})
COMMON_RANK = 60
UNCOMMON_RANK = 100


class DictionaryError(YominekoError):
    """The dictionary is missing, damaged, or could not be downloaded."""


@dataclass(frozen=True)
class Sense:
    pos: tuple[str, ...]
    misc: tuple[str, ...]
    gloss: tuple[str, ...]


@dataclass(frozen=True)
class Entry:
    id: int
    kanji: tuple[tuple[str, int], ...]  # (written form, rank)
    kana: tuple[tuple[str, int], ...]  # (reading, rank)
    senses: tuple[Sense, ...] = field(default_factory=tuple)


def rank_of(tags: set[str]) -> int:
    nf = [int(t[2:]) for t in tags if t.startswith("nf") and t[2:].isdigit()]
    if nf:
        return min(nf)
    return COMMON_RANK if tags & COMMON_TAGS else UNCOMMON_RANK


def _texts(elem: ET.Element, tag: str) -> tuple[str, ...]:
    return tuple((e.text or "").strip() for e in elem.findall(tag) if (e.text or "").strip())


def _parse_entry(elem: ET.Element) -> Entry:
    seq = elem.findtext("ent_seq")
    if not seq or not seq.strip().isdigit():
        raise DictionaryError("JMdict entry without a numeric ent_seq")
    kanji = []
    for k in elem.findall("k_ele"):
        text = (k.findtext("keb") or "").strip()
        if text:
            kanji.append((text, rank_of(set(_texts(k, "ke_pri")))))
    kana = []
    for r in elem.findall("r_ele"):
        text = (r.findtext("reb") or "").strip()
        if text:
            kana.append((text, rank_of(set(_texts(r, "re_pri")))))
    senses = tuple(
        Sense(pos=_texts(s, "pos"), misc=_texts(s, "misc"), gloss=_texts(s, "gloss"))
        for s in elem.findall("sense")
    )
    return Entry(int(seq), tuple(kanji), tuple(kana), senses)


class Readable(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


def parse_entries(stream: Readable) -> Iterator[Entry]:
    """Yield every entry in a JMdict XML stream, using constant memory."""
    try:
        for _event, elem in ET.iterparse(stream, events=("end",)):
            if elem.tag == "entry":
                yield _parse_entry(elem)
                elem.clear()
    except ET.ParseError as e:
        raise DictionaryError(f"the dictionary file is damaged (not valid XML): {e}") from e
