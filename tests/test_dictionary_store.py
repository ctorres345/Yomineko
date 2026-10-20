import sqlite3

import pytest
from support.dictionary import KOTO_IDS, MINI_ENTRY_COUNT, MINI_XML

from yomineko.analyze.dictionary.store import (
    CREDIT,
    INDEX_FORMAT,
    Dictionary,
    build_index,
    build_index_from_gzip,
)
from yomineko.analyze.dictionary.xml_parser import (
    COMMON_RANK,
    UNCOMMON_RANK,
    DictionaryError,
    Entry,
    parse_entries,
)


def mini_entries():
    with open(MINI_XML, "rb") as f:
        return list(parse_entries(f))


# -------------------------------------------------------------------- lookups


def test_size_and_meta(mini_dict):
    assert len(mini_dict) == MINI_ENTRY_COUNT
    assert mini_dict.meta["dictionary_date"] == "2026-01-02"
    assert mini_dict.meta["format_version"] == str(INDEX_FORMAT)


def test_homophones_share_a_reading(mini_dict):
    assert mini_dict.ids_by_reading("こと") == KOTO_IDS


def test_reading_lookup_treats_katakana_and_hiragana_alike(mini_dict):
    assert mini_dict.ids_by_reading("コト") == KOTO_IDS
    assert mini_dict.ids_by_reading("ぼたん") == [9000012]
    assert mini_dict.ids_by_reading("ボタン") == [9000012]


def test_kanji_lookup(mini_dict):
    assert mini_dict.ids_by_kanji("事") == [9000001]
    assert mini_dict.ids_by_kanji("釦") == [9000012]
    assert mini_dict.ids_by_kanji("存在しない") == []
    assert mini_dict.ids_by_reading("そんざいしない") == []


def test_entry_roundtrips_through_the_index(mini_dict):
    originals = {e.id: e for e in mini_entries()}
    for entry_id, original in originals.items():
        assert mini_dict.entry(entry_id) == original


def test_unknown_entry_is_none(mini_dict):
    assert mini_dict.entry(1) is None


def test_entries_are_cached(mini_dict):
    assert mini_dict.entry(9000001) is mini_dict.entry(9000001)


# ----------------------------------------------------------------------- rank


def test_rank_is_the_best_of_readings_and_written_forms(mini_dict):
    assert mini_dict.rank(9000001) == 2
    assert mini_dict.rank(9000002) == 40
    assert mini_dict.rank(9000003) == UNCOMMON_RANK
    assert mini_dict.rank(9000011) == COMMON_RANK  # kana-only entry


def test_rank_can_be_limited_to_one_reading(mini_dict):
    # ボタン: the reading is common (60) but the written form 釦 is not (100)
    assert mini_dict.rank(9000012) == COMMON_RANK
    assert mini_dict.rank(9000012, "ぼたん") == COMMON_RANK
    assert mini_dict.rank(9000012, "ボタン") == COMMON_RANK
    # a reading the entry does not have: only the written form competes
    assert mini_dict.rank(9000012, "べつ") == UNCOMMON_RANK


def test_unknown_entry_ranks_as_uncommon(mini_dict):
    assert mini_dict.rank(1) == UNCOMMON_RANK


def test_common(mini_dict):
    assert mini_dict.common(9000001)
    assert not mini_dict.common(9000003)


def test_the_prototype_homophone_cases_resolve_by_rank(mini_dict):
    """こと: 事 (rank 2) beats 琴 (40) beats 古都 (uncommon); いらい: 以来 (5) beats 依頼 (10)."""
    by_rank = sorted(mini_dict.ids_by_reading("こと"), key=mini_dict.rank)
    assert by_rank == [9000001, 9000002, 9000003]
    assert min(mini_dict.ids_by_reading("いらい"), key=mini_dict.rank) == 9000005


# ------------------------------------------------------------- building/errors


def test_missing_index_tells_the_user_what_to_do(tmp_path):
    with pytest.raises(DictionaryError, match="yomineko dict download"):
        Dictionary(tmp_path / "nope.sqlite")


def test_garbage_file_is_not_a_dictionary(tmp_path):
    path = tmp_path / "garbage.sqlite"
    path.write_bytes(b"this is not a database" * 100)
    with pytest.raises(DictionaryError, match="not a usable dictionary"):
        Dictionary(path)


def test_a_database_that_is_not_an_index_is_refused_and_closed(tmp_path, monkeypatch):
    from yomineko.analyze.dictionary import store

    path = tmp_path / "other.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE notes (text TEXT)")
    conn.close()
    opened = []

    class Tracked(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    real = sqlite3.connect

    def connect(*args, **kwargs):
        opened.append(real(*args, factory=Tracked, **kwargs))
        return opened[-1]

    monkeypatch.setattr(store.sqlite3, "connect", connect)
    with pytest.raises(DictionaryError, match="not a usable dictionary"):
        Dictionary(path)
    assert len(opened) == 1 and opened[0].closed


def test_an_index_from_another_format_asks_for_a_new_download(mini_index):
    conn = sqlite3.connect(mini_index)
    conn.execute("UPDATE meta SET value = '999' WHERE key = 'format_version'")
    conn.commit()
    conn.close()
    with pytest.raises(DictionaryError, match=r"different yomineko.*dict download"):
        Dictionary(mini_index)


def test_duplicate_ids_are_rejected_and_leave_nothing_behind(tmp_path):
    entry = Entry(1, (), (("あ", 100),))
    dest = tmp_path / "x.sqlite"
    with pytest.raises(DictionaryError, match="duplicate"):
        build_index([entry, entry], dest, {})
    assert list(tmp_path.iterdir()) == []


def test_a_failed_build_keeps_the_previous_index(mini_index):
    def broken():
        yield mini_entries()[0]
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        build_index(broken(), mini_index, {})
    with Dictionary(mini_index) as d:
        assert len(d) == MINI_ENTRY_COUNT
    assert [p.name for p in mini_index.parent.iterdir()] == [mini_index.name]


def test_rebuilding_replaces_the_index(mini_index):
    build_index(mini_entries()[:2], mini_index, {"dictionary_date": "2030-01-01"})
    with Dictionary(mini_index) as d:
        assert len(d) == 2 and d.meta["dictionary_date"] == "2030-01-01"


def test_index_from_a_gzip_file(tmp_path):
    from support.dictionary import write_gz

    gz = write_gz(tmp_path / "j.gz", MINI_XML.read_bytes())
    dest = tmp_path / "out" / "idx.sqlite"
    count = build_index_from_gzip(gz, dest, {"credit": CREDIT}, max_xml=10_000_000)
    assert count == MINI_ENTRY_COUNT
    with Dictionary(dest) as d:
        assert d.meta["credit"] == CREDIT


def test_a_file_that_expands_too_much_is_refused(tmp_path):
    from support.dictionary import write_gz

    gz = write_gz(tmp_path / "bomb.gz", MINI_XML.read_bytes())
    with pytest.raises(DictionaryError, match="unreasonable size"):
        build_index_from_gzip(gz, tmp_path / "i.sqlite", {}, max_xml=200)
    assert not (tmp_path / "i.sqlite").exists()
    assert not (tmp_path / "i.sqlite.part").exists()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"not gzip at all", "damaged"),
        (b"", "damaged"),
    ],
)
def test_damaged_gzip_files(tmp_path, content, message):
    gz = tmp_path / "bad.gz"
    gz.write_bytes(content)
    with pytest.raises(DictionaryError, match=message):
        build_index_from_gzip(gz, tmp_path / "i.sqlite", {}, max_xml=10_000_000)


def test_a_truncated_gzip_file(tmp_path):
    from support.dictionary import mini_gz_bytes

    gz = tmp_path / "cut.gz"
    gz.write_bytes(mini_gz_bytes()[:-40])
    with pytest.raises(DictionaryError, match="damaged"):
        build_index_from_gzip(gz, tmp_path / "i.sqlite", {}, max_xml=10_000_000)
    assert not (tmp_path / "i.sqlite").exists()


def test_gzip_of_something_that_is_not_xml(tmp_path):
    from support.dictionary import write_gz

    gz = write_gz(tmp_path / "text.gz", b"hello, this is not XML")
    with pytest.raises(DictionaryError, match="not valid XML"):
        build_index_from_gzip(gz, tmp_path / "i.sqlite", {}, max_xml=10_000_000)


def test_missing_gzip_file(tmp_path):
    with pytest.raises(DictionaryError, match="cannot read"):
        build_index_from_gzip(tmp_path / "none.gz", tmp_path / "i.sqlite", {}, max_xml=1000)
