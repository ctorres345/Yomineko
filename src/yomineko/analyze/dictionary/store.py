"""A SQLite index of JMdict, built once after download and queried read-only.

Why an index: JMdict is about 200,000 entries. Loading it as Python objects takes seconds and
hundreds of MB; SQLite answers "which entries have this reading?" instantly from disk.
"""

from __future__ import annotations

import gzip
import json
import os
import sqlite3
import zlib
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from types import TracebackType

from yomineko.analyze.dictionary.text import kata_to_hira
from yomineko.analyze.dictionary.xml_parser import (
    UNCOMMON_RANK,
    DictionaryError,
    Entry,
    Readable,
    Sense,
    parse_entries,
)

INDEX_FORMAT = 1
CREDIT = (
    "JMdict, (c) the Electronic Dictionary Research and Development Group, CC BY-SA 4.0: "
    "https://www.edrdg.org/edrdg/licence.html"
)
BATCH = 5000

_SCHEMA = """
CREATE TABLE entries (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE kanji (text TEXT NOT NULL, id INTEGER NOT NULL);
CREATE TABLE readings (norm TEXT NOT NULL, id INTEGER NOT NULL);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
_INDEXES = """
CREATE INDEX kanji_text ON kanji (text);
CREATE INDEX readings_norm ON readings (norm);
"""


def _encode(entry: Entry) -> str:
    return json.dumps(
        {
            "k": [list(k) for k in entry.kanji],
            "r": [list(r) for r in entry.kana],
            "s": [{"p": s.pos, "m": s.misc, "g": s.gloss} for s in entry.senses],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _decode(entry_id: int, data: str) -> Entry:
    d = json.loads(data)
    return Entry(
        id=entry_id,
        kanji=tuple((t, int(r)) for t, r in d["k"]),
        kana=tuple((t, int(r)) for t, r in d["r"]),
        senses=tuple(Sense(tuple(s["p"]), tuple(s["m"]), tuple(s["g"])) for s in d["s"]),
    )


def build_index(entries: Iterable[Entry], dest: Path, meta: dict[str, str]) -> int:
    """Write the index to ``dest`` atomically (temp file, then rename). Returns the entry count."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    part.unlink(missing_ok=True)
    conn = sqlite3.connect(part)
    try:
        conn.executescript(_SCHEMA)
        count = 0
        rows_e: list[tuple[int, str]] = []
        rows_k: list[tuple[str, int]] = []
        rows_r: list[tuple[str, int]] = []

        def flush() -> None:
            conn.executemany("INSERT INTO entries VALUES (?, ?)", rows_e)
            conn.executemany("INSERT INTO kanji VALUES (?, ?)", rows_k)
            conn.executemany("INSERT INTO readings VALUES (?, ?)", rows_r)
            rows_e.clear()
            rows_k.clear()
            rows_r.clear()

        for entry in entries:
            rows_e.append((entry.id, _encode(entry)))
            rows_k.extend((text, entry.id) for text, _ in entry.kanji)
            rows_r.extend((kata_to_hira(text), entry.id) for text, _ in entry.kana)
            count += 1
            if len(rows_e) >= BATCH:
                flush()
        flush()
        conn.executescript(_INDEXES)
        full_meta = {**meta, "format_version": str(INDEX_FORMAT), "entry_count": str(count)}
        conn.executemany("INSERT INTO meta VALUES (?, ?)", full_meta.items())
        conn.commit()
        conn.close()
        os.replace(part, dest)
        return count
    except BaseException as e:
        conn.close()  # always release the file, or Windows cannot delete it
        part.unlink(missing_ok=True)
        if isinstance(e, sqlite3.IntegrityError):
            raise DictionaryError(f"the dictionary has a duplicate entry: {e}") from e
        raise


class _CappedReader:
    """Reads from a stream but refuses to produce more than ``limit`` bytes (zip-bomb guard)."""

    def __init__(self, stream: Readable, limit: int):
        self._stream = stream
        self._left = limit

    def read(self, size: int = -1) -> bytes:
        data = self._stream.read(size)
        self._left -= len(data)
        if self._left < 0:
            raise DictionaryError("the dictionary file expands to an unreasonable size")
        return data


def build_index_from_gzip(gz_path: Path, dest: Path, meta: dict[str, str], max_xml: int) -> int:
    """Parse a gzipped JMdict XML file into an index. Damaged files raise DictionaryError."""
    try:
        with gzip.open(gz_path, "rb") as raw:
            return build_index(parse_entries(_CappedReader(raw, max_xml)), dest, meta)
    except (gzip.BadGzipFile, EOFError, zlib.error) as e:
        raise DictionaryError(f"the downloaded file is damaged: {e}") from e
    except OSError as e:
        raise DictionaryError(f"cannot read the dictionary file {gz_path}: {e}") from e


class Dictionary:
    """Read-only access to an index built by ``build_index``."""

    def __init__(self, path: Path):
        if not path.is_file():
            raise DictionaryError(
                f"no dictionary at {path}. Download it once with: yomineko dict download"
            )
        try:
            self._conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        except sqlite3.DatabaseError as e:
            raise DictionaryError(f"{path} is not a usable dictionary index: {e}") from e
        try:
            self.meta: dict[str, str] = dict(self._conn.execute("SELECT key, value FROM meta"))
        except sqlite3.DatabaseError as e:
            self._conn.close()
            raise DictionaryError(f"{path} is not a usable dictionary index: {e}") from e
        if self.meta.get("format_version") != str(INDEX_FORMAT):
            self._conn.close()
            raise DictionaryError(
                f"{path} was built by a different yomineko (index format "
                f"{self.meta.get('format_version')!r}, need {INDEX_FORMAT}). "
                "Run: yomineko dict download"
            )
        self.path = path
        self._entry = lru_cache(maxsize=50_000)(self._load_entry)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Dictionary:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __len__(self) -> int:
        return int(self.meta["entry_count"])

    def _load_entry(self, entry_id: int) -> Entry | None:
        row = self._conn.execute("SELECT data FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return None if row is None else _decode(entry_id, row[0])

    def entry(self, entry_id: int) -> Entry | None:
        result: Entry | None = self._entry(entry_id)
        return result

    def ids_by_kanji(self, text: str) -> list[int]:
        rows = self._conn.execute("SELECT id FROM kanji WHERE text = ? ORDER BY id", (text,))
        return [r[0] for r in rows]

    def ids_by_reading(self, reading: str) -> list[int]:
        """Entries with this reading; katakana and hiragana spellings are treated alike."""
        rows = self._conn.execute(
            "SELECT DISTINCT id FROM readings WHERE norm = ? ORDER BY id", (kata_to_hira(reading),)
        )
        return [r[0] for r in rows]

    def rank(self, entry_id: int, reading: str | None = None) -> int:
        """Best frequency rank of the entry (1 most frequent .. 100 uncommon); with ``reading``,
        only that reading competes with the written forms."""
        entry = self.entry(entry_id)
        if entry is None:
            return UNCOMMON_RANK
        want = kata_to_hira(reading) if reading else None
        ranks = [r for t, r in entry.kana if want is None or kata_to_hira(t) == want]
        ranks += [r for _, r in entry.kanji]
        return min(ranks or [UNCOMMON_RANK])

    def common(self, entry_id: int) -> bool:
        return self.rank(entry_id) < UNCOMMON_RANK
