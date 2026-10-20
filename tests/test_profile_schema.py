import copy

import pytest
from pydantic import ValidationError

from yomineko.profile.schema import Profile

GOOD = {
    "schema_version": 1,
    "id": "demo-game",
    "title": "Demo Game",
    "platform": "gba",
    "rom": {"sha1": "0123456789abcdef0123456789abcdef01234567", "game_code": "TSTJ"},
    "encoding": {"type": "shift_jis", "custom_leads": [[0x84, 0x87]]},
    "text": {"regions": [{"start": 0, "end": 0x10000}]},
    "discover": {"ignore": [r"#C."]},
    "plain": [{"pattern": r"#P", "replace": "\n"}],
    "tables": [{"category": "item", "base": 0x100, "stride": 8, "count": 4}],
}


def variant(**changes):
    data = copy.deepcopy(GOOD)
    for dotted, value in changes.items():
        *path, last = dotted.split("__")
        node = data
        for key in path:
            node = node[key]
        node[last] = value
    return data


@pytest.mark.parametrize("code", ["ABCE", "ABCP", "ABC", "ABCDJ", ""])
def test_a_game_code_must_be_four_characters_ending_in_j(code):
    with pytest.raises(ValidationError):
        Profile.model_validate(variant(rom__game_code=code))
    assert Profile.model_validate(variant(rom__game_code="ABCJ")).rom.game_code == "ABCJ"


def test_good_profile_validates_and_fills_defaults():
    p = Profile.model_validate(GOOD)
    assert p.text.pointer_base == 0x08000000
    assert p.text.bank_gap == 0x40
    assert p.discover.min_score == 0.7
    assert p.kinds.dialogue_min_length == 12
    assert p.encoding.terminator == 0


@pytest.mark.parametrize(
    "bad",
    [
        variant(id="Bad_Id"),
        variant(platform="nds"),
        variant(rom__sha1="NOTAHASH"),
        variant(schema_version=2),
        variant(text__regions=[]),
        variant(text__regions=[{"start": 10, "end": 10}]),
        variant(discover__ignore=["(unclosed"]),
        variant(plain=[{"pattern": "[bad", "replace": ""}]),
        variant(encoding={"type": "table"}),
        variant(tables=[{"category": "x", "base": 0, "stride": 0, "count": 1}]),
        variant(surprise=True),
    ],
)
def test_bad_profiles_are_rejected(bad):
    with pytest.raises(ValidationError):
        Profile.model_validate(bad)


def test_table_encoding_with_a_table_path_is_valid():
    p = Profile.model_validate(variant(encoding={"type": "table", "table": "fake.tbl"}))
    assert p.encoding.table == "fake.tbl"


@pytest.mark.parametrize("fixture", ["sjis_rom", "tbl_rom", "table8_rom", "gbc_rom"])
def test_fixture_profiles_validate(fixture, request):
    synth = request.getfixturevalue(fixture)
    p = Profile.model_validate(synth.profile_data)
    assert p.rom.sha1 == synth.sha1
    assert p.text.regions[0].end > p.text.regions[0].start


# ------------------------------------------------------- Game Boy Color


def test_game_boy_color_is_a_platform():
    assert Profile.model_validate(variant(platform="gbc")).platform == "gbc"


def test_a_banked_region_is_read_as_the_file_offsets_of_the_whole_bank():
    p = Profile.model_validate(variant(text__regions=[{"bank": 0}, {"bank": 0x15}]))
    assert [(r.start, r.end, r.bank) for r in p.text.regions] == [
        (0, 0x4000, None),
        (0x54000, 0x58000, None),
    ]
    again = Profile.model_validate(p.model_dump())  # what was read validates to the same
    assert again.text.regions == p.text.regions


@pytest.mark.parametrize(
    "region",
    [
        {"bank": 5, "start": 0x4000, "end": 0x5000},  # a bank is taken whole
        {"bank": -1},
        {"bank": "five"},
        {"bank": True},
        {},
        {"start": 0x100},
    ],
)
def test_bad_regions_are_rejected(region):
    with pytest.raises(ValidationError):
        Profile.model_validate(variant(text__regions=[region]))


def test_a_table_can_hold_its_text_as_records_or_as_strings():
    p = Profile.model_validate(
        variant(
            tables=[
                {"category": "a", "kind": "records", "base": 0x100, "stride": 5, "count": 3},
                {"category": "b", "kind": "strings", "base": 0x200, "count": 3},
                {"category": "c", "base": 0x300, "stride": 4, "count": 3},
            ]
        )
    )
    assert [(t.kind, t.stride) for t in p.tables] == [
        ("records", 5),
        ("strings", 0),
        ("pointers", 4),
    ]


@pytest.mark.parametrize(
    ("table", "message"),
    [
        ({"kind": "records", "base": 0, "count": 1}, "needs a stride"),
        ({"base": 0, "count": 1}, "needs a stride"),
        ({"kind": "strings", "base": 0, "stride": 5, "count": 1}, "takes no stride"),
        ({"kind": "records", "base": 0, "stride": 5, "count": 1, "field": 2}, "only for kind"),
        ({"kind": "strings", "base": 0, "count": 1, "field": 2}, "only for kind"),
        ({"kind": "list", "base": 0, "stride": 5, "count": 1}, "Input should be"),
    ],
)
def test_bad_tables_are_rejected(table, message):
    with pytest.raises(ValidationError, match=message):
        Profile.model_validate(variant(tables=[{"category": "x", **table}]))


COMPRESSED = {"scheme": "lz77", "tables": [{"base": 0x100, "count": 2}]}
TABLE16 = {"type": "table16", "table": "fake16.tbl", "skip": {0x0E: 1}}


def test_compressed_profile_validates_and_fills_defaults(lz16_rom):
    p = Profile.model_validate(lz16_rom.profile_data)
    assert p.rom.sha1 == lz16_rom.sha1
    assert p.text.regions == []
    assert p.compressed.tables[0].stride == 4 and p.compressed.min_chars == 2
    assert p.encoding.skip == {0x0E: 1, 0x0B: 1}


def test_compressed_text_may_sit_next_to_plain_regions():
    p = Profile.model_validate(variant(encoding=TABLE16, compressed=COMPRESSED))
    assert p.text.regions and p.compressed is not None


@pytest.mark.parametrize(
    "bad",
    [
        variant(text__regions=[], compressed=None),  # no text anywhere
        variant(compressed=COMPRESSED),  # compressed text needs the 16-bit encoding
        variant(encoding={**TABLE16, "type": "table"}),  # skip belongs to table16
        variant(encoding={"type": "table16"}),  # no table
        variant(encoding={**TABLE16, "skip": {0x0E: 0}}),
        variant(encoding={**TABLE16, "skip": {0x0E: 17}}),
        variant(encoding={**TABLE16, "skip": {0x10000: 1}}),
        variant(encoding=TABLE16, compressed={**COMPRESSED, "scheme": "rle"}),
        variant(encoding=TABLE16, compressed={**COMPRESSED, "tables": []}),
        variant(encoding=TABLE16, compressed={**COMPRESSED, "min_chars": 0}),
        variant(encoding=TABLE16, compressed={**COMPRESSED, "tables": [{"base": 0, "count": 0}]}),
        variant(encoding=TABLE16, compressed={**COMPRESSED, "surprise": 1}),
    ],
)
def test_bad_compressed_profiles_are_rejected(bad):
    with pytest.raises(ValidationError):
        Profile.model_validate(bad)


def test_sentence_rules_are_optional_and_default_to_none():
    profile = Profile.model_validate(GOOD)
    assert profile.sentences.exclude_ranges == []
    assert profile.sentences.caps.name_quote is None


def test_sentence_rules_read_ranges_and_caps():
    data = copy.deepcopy(GOOD)
    data["sentences"] = {
        "exclude_ranges": [{"start": 0x100, "end": 0x200}],
        "caps": {"name_quote": 5},
    }
    profile = Profile.model_validate(data)
    assert (profile.sentences.exclude_ranges[0].start, profile.sentences.caps.name_quote) == (
        0x100,
        5,
    )
    assert profile.sentences.caps.name_subject is None


@pytest.mark.parametrize(
    "bad",
    [
        {"exclude_ranges": [{"start": 5, "end": 5}]},
        {"caps": {"name_quote": -1}},
        {"caps": {"other": 1}},
        {"surprise": 1},
    ],
)
def test_bad_sentence_rules_are_rejected(bad):
    data = copy.deepcopy(GOOD)
    data["sentences"] = bad
    with pytest.raises(ValidationError):
        Profile.model_validate(data)
