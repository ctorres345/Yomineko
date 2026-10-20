import io

import pytest
from support.dictionary import MINI_ENTRY_COUNT, mini_xml_bytes

from yomineko.analyze.dictionary.text import kata_to_hira
from yomineko.analyze.dictionary.xml_parser import (
    COMMON_RANK,
    UNCOMMON_RANK,
    DictionaryError,
    parse_entries,
    rank_of,
)


def entries():
    return {e.id: e for e in parse_entries(io.BytesIO(mini_xml_bytes()))}


# ----------------------------------------------------------------------- rank


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"nf05", "news1"}, 5),
        ({"nf48"}, 48),
        ({"nf02", "nf30"}, 2),  # the smallest nf wins
        ({"news1"}, COMMON_RANK),
        ({"ichi1"}, COMMON_RANK),
        ({"gai1"}, COMMON_RANK),
        ({"news2"}, UNCOMMON_RANK),  # news2 is not in the common set
        (set(), UNCOMMON_RANK),
        ({"nfxx"}, UNCOMMON_RANK),  # not a number: ignored
    ],
)
def test_rank_of(tags, expected):
    assert rank_of(tags) == expected


# -------------------------------------------------------------------- parsing


def test_every_entry_is_read():
    assert len(entries()) == MINI_ENTRY_COUNT


def test_entry_fields():
    koto = entries()[9000001]
    assert koto.kanji == (("事", 2),)
    assert koto.kana == (("こと", 2),)
    assert koto.senses[0].gloss == ("thing (abstract)", "matter")


def test_entities_are_expanded_to_their_text():
    senses = entries()[9000008].senses
    assert senses[0].pos == ("Godan verb with 'ru' ending", "intransitive verb")


def test_misc_tags_are_kept_per_sense():
    sugoi = entries()[9000011]
    assert [s.misc for s in sugoi.senses] == [
        ("archaism",),
        ("word usually written using kana alone",),
    ]
    assert sugoi.senses[1].gloss == ("amazing", "great")


def test_a_kana_only_entry_has_no_written_form():
    sugoi = entries()[9000011]
    assert sugoi.kanji == ()
    assert sugoi.kana == (("すごい", COMMON_RANK),)


def test_unprioritised_forms_are_uncommon():
    assert entries()[9000003].kanji == (("古都", UNCOMMON_RANK),)


def test_katakana_reading_is_kept_as_written():
    assert entries()[9000012].kana == (("ボタン", COMMON_RANK),)


# --------------------------------------------------------------------- errors


def test_damaged_xml_is_a_dictionary_error():
    with pytest.raises(DictionaryError, match="not valid XML"):
        list(parse_entries(io.BytesIO(b"<JMdict><entry><ent_seq>1</ent_seq>")))


def test_entry_without_a_numeric_id_is_rejected():
    with pytest.raises(DictionaryError, match="ent_seq"):
        list(parse_entries(io.BytesIO(b"<JMdict><entry><ent_seq>abc</ent_seq></entry></JMdict>")))


def test_external_entities_are_never_read(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT", encoding="utf-8")
    xml = (
        f'<?xml version="1.0"?><!DOCTYPE JMdict [<!ENTITY leak SYSTEM "{secret.as_uri()}">]>'
        "<JMdict><entry><ent_seq>1</ent_seq>"
        "<r_ele><reb>あ</reb></r_ele><sense><gloss>&leak;</gloss></sense></entry></JMdict>"
    ).encode()
    try:
        parsed = list(parse_entries(io.BytesIO(xml)))
    except DictionaryError:
        return  # refusing is fine too
    assert "TOP-SECRET" not in repr(parsed)


# ---------------------------------------------------------------------- kana


def test_kata_to_hira():
    assert kata_to_hira("ボタン") == "ぼたん"
    assert kata_to_hira("こと") == "こと"
    assert kata_to_hira("ーA") == "ーA"  # the long-vowel mark and ASCII are untouched
