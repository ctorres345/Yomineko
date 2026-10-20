import pytest
from pydantic import ValidationError

from yomineko.model import SCHEMA_VERSION, GameInfo, Line, Script, Term, Translation, Word

SHA1 = "0123456789abcdef0123456789abcdef01234567"


def make_script(**kw) -> Script:
    return Script(
        generator="yomineko-test",
        game=GameInfo(profile_id="demo", title="Demo", platform="gba", rom_sha1=SHA1),
        **kw,
    )


def make_line(**kw) -> Line:
    base = {
        "id": "08001000",
        "address": 0x1000,
        "bank": "bank_001000",
        "raw": "raw",
        "text": "text",
        "kind": "term",
    }
    base.update(kw)
    return Line(**base)


def test_roundtrip_through_json():
    script = make_script(
        lines=[
            make_line(translation=Translation(text="tea", source="dictionary")),
            make_line(id="08001010", address=0x1010, duplicate_of="08001000"),
        ],
        words=[Word(jmdict_id=1, written="x", kana="x")],
        terms=[Term(jp="x", category="item", index=0, line_id="08001000")],
    )
    assert Script.model_validate_json(script.model_dump_json()) == script


def test_schema_version_defaults_to_current():
    assert make_script().schema_version == SCHEMA_VERSION == 4


def test_other_schema_version_is_rejected():
    data = make_script().model_dump()
    data["schema_version"] = 5
    with pytest.raises(ValidationError):
        Script.model_validate(data)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_line(surprise=1)


@pytest.mark.parametrize("bad_id", ["1000", "0800100g", "08001000A", "0800100"])
def test_line_id_must_be_eight_upper_hex_digits(bad_id):
    with pytest.raises(ValidationError):
        make_line(id=bad_id)


def test_translation_source_is_restricted():
    with pytest.raises(ValidationError):
        Translation(text="x", source="guess")


def test_rom_sha1_must_be_lowercase_hex():
    with pytest.raises(ValidationError):
        GameInfo(profile_id="d", title="D", platform="gba", rom_sha1="ABC")


def test_word_defaults_for_the_fields_added_in_schema_2():
    word = Word(jmdict_id=1, written="x", kana="x")
    assert (word.pos, word.common, word.sentence_safe) == ("", False, True)
    assert word.freq == 0 and word.examples == [] and word.meanings == []


def test_fields_added_in_schema_3_default_to_empty():
    assert make_line().word_ids == []
    term = Term(jp="x", category="item", index=0)
    assert term.jmdict_id is None


def test_a_script_has_no_dictionary_until_it_is_analysed():
    from yomineko.model import DictionarySource

    script = make_script()
    assert script.dictionary is None
    credited = script.model_copy(
        update={"dictionary": DictionarySource(date="2026-10-03", source="https://x", credit="c")}
    )
    assert credited.dictionary is not None and credited.dictionary.name == "JMdict"
    assert Script.model_validate_json(credited.model_dump_json()) == credited
