"""A dictionary of a few invented entries, with just the lookups the analysis uses."""

from __future__ import annotations

from yomineko.analyze.dictionary.xml_parser import Entry, Sense


class TinyDictionary:
    """Just the lookups the matcher uses, over a few invented entries."""

    def __init__(self, entries: list[Entry], common: set[int]):
        self.entries = {e.id: e for e in entries}
        self._common = common

    def entry(self, entry_id):
        return self.entries.get(entry_id)

    def ids_by_kanji(self, text):
        return sorted(i for i, e in self.entries.items() if any(k == text for k, _ in e.kanji))

    def ids_by_reading(self, reading):
        return sorted(i for i, e in self.entries.items() if any(k == reading for k, _ in e.kana))

    def common(self, entry_id):
        return entry_id in self._common

    def rank(self, entry_id, reading=None):
        return 10 if entry_id in self._common else 100


def verb(entry_id, kanji, kana):
    return Entry(entry_id, ((kanji, 10),), ((kana, 10),), (Sense(("Godan verb",), (), ("x",)),))


def noun(entry_id, kanji, kana):
    return Entry(entry_id, ((kanji, 10),), ((kana, 10),), (Sense(("noun",), (), ("x",)),))
