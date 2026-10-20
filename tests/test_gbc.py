"""Game Boy Color: framed messages in banks, pointers inside a bank, and name tables that hold
their text, on the synthetic ROM from ``build_gbc_rom``."""

import copy
import re

import pytest
from pydantic import ValidationError
from support.synthrom import (
    F_END,
    F_LINE,
    F_NOT_TEXT,
    F_NUMBER,
    F_RESUME,
    F_SOUND,
    F_START,
    FAKE_FRAME_TBL,
    GBC_BANK,
    GBC_WORDS,
    lcg_bytes,
    load_tbl,
    tbl_encode,
)

from yomineko.core.discover import stream
from yomineko.core.discover.pointers import pointed_at_in_bank
from yomineko.core.discover.stream import find_stream_strings
from yomineko.core.encodings.tbl import TableError
from yomineko.core.rom import gb
from yomineko.core.rom.base import rom_from_bytes
from yomineko.core.roundtrip import verify
from yomineko.extract import extract
from yomineko.profile.loader import LoadedProfile, ProfileError, load_profile
from yomineko.profile.schema import Profile

KANA = re.compile("[ぁ-ヿ一-鿿]")
MARKED = re.compile("<[^>]*>")  # the synthetic profile's discover.ignore


@pytest.fixture(scope="module")
def loaded(gbc_rom):
    return load_profile(gbc_rom.profile_path)


@pytest.fixture(scope="module")
def found(gbc_rom, loaded):
    return find_stream_strings(gbc_rom.rom, loaded.codec(gbc_rom.rom), loaded.profile)


@pytest.fixture(scope="module")
def result(gbc_rom, loaded):
    return extract(rom_from_bytes(gbc_rom.rom, "t.gbc"), loaded)


def t(text: str) -> bytes:
    return tbl_encode(text, load_tbl(FAKE_FRAME_TBL))


# ---------------------------------------------------------------- addresses


@pytest.mark.parametrize(
    ("offset", "address"),
    [(0x0000, 0x0000), (0x3FFF, 0x3FFF), (0x4000, 0x4000), (0x7FFF, 0x7FFF), (0x54123, 0x4123)],
)
def test_the_address_of_a_file_offset(offset, address):
    assert gb.bank_address(offset) == address


def test_a_pointer_counts_only_inside_the_bank_of_its_target():
    data = bytearray(3 * GBC_BANK)
    data[0x4010:0x4012] = (0x4120).to_bytes(2, "little")  # in bank 1
    data[0x0020:0x0022] = (0x0300).to_bytes(2, "little")  # in bank 0, where offsets are addresses
    assert pointed_at_in_bank(bytes(data), 0x4120)
    assert not pointed_at_in_bank(bytes(data), 0x8120)  # the same address, in bank 2
    assert pointed_at_in_bank(bytes(data), 0x0300)
    assert not pointed_at_in_bank(bytes(data), 0x4300)


# ---------------------------------------------------------------- discovery


def test_every_expected_line_is_found_and_nothing_else(gbc_rom, found):
    got = [(s.start, s.end, s.raw, s.referenced) for s in found.strings]
    want = [(s.offset, s.end, s.raw, s.referenced) for s in gbc_rom.manifest.strings]
    assert got == want
    assert found.unstable == []
    assert len(want) == 11


def test_bytes_that_only_read_as_text_are_not_lines(gbc_rom, found):
    rejected = gbc_rom.manifest.rejected
    assert sorted(rejected.values()) == sorted(
        [
            "too little text and no pointer",
            "no start command",
            "a byte that is not text",
            "an unknown command between two texts",
            "its kana are all inside marked entries",
            "no end byte",
            "runs into the next bank",
            "the pointer to its address is in another bank",
            "outside the regions",
        ]
    )
    for offset, why in rejected.items():
        inside = [s.start for s in found.strings if offset <= s.start < offset + 0x40]
        assert not inside, why


def test_a_message_with_a_pointer_is_kept_however_short(gbc_rom, found):
    referenced = [s.raw for s in found.strings if s.referenced]
    assert referenced == ["おはよう！", "またね！"]


def test_without_a_frame_the_same_table_reads_data_as_text(gbc_rom, loaded):
    data = copy.deepcopy(gbc_rom.profile_data)
    del data["discover"]["frame"]
    unframed = find_stream_strings(
        gbc_rom.rom, loaded.codec(gbc_rom.rom), Profile.model_validate(data)
    )
    starts = {s.start for s in unframed.strings}
    assert {0x4620, 0x4921, 0x8121} <= starts  # no start command, marked entries, no pointer


def test_a_frame_without_commands_ends_a_message_at_its_first_end_byte(gbc_rom, loaded):
    data = copy.deepcopy(gbc_rom.profile_data)
    data["discover"]["frame"] = {"start": F_START, "breaks": [F_LINE], "ends": [F_END]}
    data["text"]["regions"] = [{"start": 0, "end": 0x40}]
    data["discover"]["unreferenced"] = {"min_japanese": 2}
    profile = Profile.model_validate(data)
    blob = bytes([F_START]) + t("ねこ") + bytes([F_LINE]) + t("つき") + bytes([F_END])
    resumed = bytes([F_START]) + t("そら") + bytes([F_RESUME, F_START]) + t("あめ") + bytes([F_END])
    rom = blob + resumed
    strings = find_stream_strings(rom, loaded.codec(gbc_rom.rom), profile).strings
    # with no resume byte in the frame, the byte that would hand back to the commands is not
    # text, so the first text of the second message is dropped and the second stands alone
    assert [s.raw for s in strings] == ["ねこ", "つき", "あめ"]


def scan(gbc_rom, loaded, rom: bytes, **discover):
    data = copy.deepcopy(gbc_rom.profile_data)
    data["text"]["regions"] = [{"bank": 0}]
    data["discover"].update(discover)
    return find_stream_strings(rom, loaded.codec(gbc_rom.rom), Profile.model_validate(data))


def test_a_message_is_found_behind_bytes_that_only_look_like_its_beginning(gbc_rom, loaded):
    # a start command in front of a real message makes a longer candidate that is no message
    # (the second start is not text); the real one is still found
    rom = bytes([F_START, F_START]) + t("きょうは　いい　てんきですね。") + bytes([F_END])
    strings = scan(gbc_rom, loaded, rom).strings
    assert [(s.start, s.raw) for s in strings] == [(2, "きょうは　いい　てんきですね。")]


def test_the_rest_of_a_message_is_kept_when_only_its_later_text_has_a_pointer(gbc_rom, loaded):
    # too little text as a whole and no pointer to its start; a pointer leads to its second text
    first = bytes([F_START]) + t("ねこ") + bytes([F_RESUME])
    second = bytes([F_START]) + t("つき") + bytes([F_END])
    rom = bytearray(0x40)
    rom[0x10 : 0x10 + len(first + second)] = first + second
    assert scan(gbc_rom, loaded, bytes(rom)).strings == []
    rom[0x30:0x32] = (0x10 + len(first)).to_bytes(2, "little")
    strings = scan(gbc_rom, loaded, bytes(rom)).strings
    assert [(s.raw, s.referenced) for s in strings] == [("つき", True)]


TEXT_THEN_COMMANDS = bytes([F_START, 0x80, F_RESUME])  # start, one character, hand back
START_AS_A_PARAMETER = bytes([F_NUMBER, F_START, F_RESUME])  # a command and its two parameters


@pytest.mark.parametrize(
    "rom",
    [
        TEXT_THEN_COMMANDS * 4000 + bytes([F_NOT_TEXT]),  # no candidate is a message
        START_AS_A_PARAMETER * 4000 + bytes([F_NOT_TEXT]),
        START_AS_A_PARAMETER * 4000 + bytes([F_RESUME]),  # each is one, with nothing to keep
    ],
    ids=["texts that never end", "starts inside parameters", "messages too short to keep"],
)
def test_every_place_is_walked_once_however_many_candidates_pass_it(
    gbc_rom, loaded, monkeypatch, rom
):
    # each candidate's walk is the tail of an earlier one: reading it again for every
    # candidate would take time that grows with the square of the region
    steps = 0
    step = stream._step

    def counting(*args):
        nonlocal steps
        steps += 1
        return step(*args)

    monkeypatch.setattr(stream, "_step", counting)
    assert scan(gbc_rom, loaded, rom).strings == []
    assert steps <= len(rom)


def plain_scan(rom: bytes, codec, profile: Profile) -> list:
    """The scan with nothing remembered: every start command in turn, walked to its end."""
    frame = profile.discover.frame
    out = []
    pos = 0
    while pos < len(rom):
        rows = []
        after = None
        at, in_text = pos, False
        while rom[pos] == frame.start and at < len(rom):
            b = rom[at]
            if not in_text:
                if b == frame.start:
                    in_text = True
                elif b == frame.resume:
                    after = at + 1
                    break
                elif b in frame.commands:
                    at += frame.commands[b]
                else:
                    break
                at += 1
            elif b in frame.ends:
                after = at + 1
                break
            elif b == frame.resume:
                in_text = False
                at += 1
            elif b in frame.breaks:
                at += 1
            else:
                run = codec.parse(rom, at)
                if run is None or run[0] > len(rom):
                    break
                rows.append((at, run[0], run[1]))
                at = run[0]
        if after is None:
            pos += 1
            continue
        kana = sum(len(KANA.findall(MARKED.sub("", raw))) for _, _, raw in rows)
        referenced = pointed_at_in_bank(rom, pos)
        if referenced or kana >= profile.discover.unreferenced.min_japanese:
            out += [(a, b, raw, referenced) for a, b, raw in rows]
            pos = after
        else:
            pos += 1
    return out


def soup(seed: int, size: int = 0x600) -> bytes:
    """Random pieces of messages and of things that are not: starts, text, hand-backs, ends,
    commands whose parameters are any byte, marked entries, bytes that are nothing, and
    two-byte words that point somewhere into the soup."""
    noise = lcg_bytes(seed)
    any_byte = bytes([F_START, F_RESUME, F_END, F_LINE, F_NUMBER, F_NOT_TEXT, 0x80, 0x81])
    out = bytearray()
    while len(out) < size:
        kind = next(noise) % 26
        if kind < 5:
            out.append(F_START)
        elif kind < 14:
            out += bytes(0x80 + next(noise) % 10 for _ in range(1 + next(noise) % 4))
        elif kind < 17:
            out.append(F_RESUME)
        elif kind < 19:
            out.append(F_END if kind == 17 else 0x04)
        elif kind < 21:
            out.append(F_LINE if kind == 19 else 0x0D)
        elif kind == 21:
            out += bytes([F_NUMBER, any_byte[next(noise) % 8], any_byte[next(noise) % 8]])
        elif kind == 22:
            out.append(F_SOUND)
        elif kind == 23:
            out.append(F_NOT_TEXT)
        elif kind == 24:
            out.append(0x40 if next(noise) % 2 else 0x48)
        else:
            out += bytes([next(noise), next(noise) % (size >> 8)])
    return bytes(out[:size])


def test_the_scan_finds_what_the_plain_one_finds_in_bytes_of_every_kind(gbc_rom, loaded):
    data = copy.deepcopy(gbc_rom.profile_data)
    data["text"]["regions"] = [{"bank": 0}]
    profile = Profile.model_validate(data)
    codec = loaded.codec(gbc_rom.rom)
    kept = pointed = 0
    for seed in range(1, 101):
        rom = soup(seed)
        got = list(stream._framed_runs(rom, codec, profile, 0, len(rom)))
        assert got == plain_scan(rom, codec, profile), seed
        kept += len(got)
        pointed += sum(1 for row in got if row[3])
    assert kept > 300 and pointed > 60, (kept, pointed)  # the soups hold both kinds


def test_a_line_that_does_not_re_encode_identically_is_set_aside(tmp_path, gbc_rom):
    table = tmp_path / "t.tbl"
    table.write_text("81=あ\n82=い\n83=あい\n84=う\n", encoding="utf-8")
    data = copy.deepcopy(gbc_rom.profile_data)
    data["encoding"]["table"] = "t.tbl"
    del data["encoding"]["rom_strings"]
    data["text"]["regions"] = [{"start": 0, "end": 0x20}]
    data["discover"]["unreferenced"] = {"min_japanese": 2}
    profile = Profile.model_validate(data)
    codec = LoadedProfile(profile, tmp_path / "p.yaml").codec()
    rom = bytes([F_START, 0x81, 0x82, 0x84, F_LINE, 0x83, 0x84, F_END])
    found = find_stream_strings(rom, codec, profile)
    assert [s.start for s in found.strings] == [5]
    assert found.unstable == [1]


# --------------------------------------------------------------- extraction


def test_lines_match_the_manifest(gbc_rom, result):
    lines = result.script.lines
    assert [(x.address, x.raw, x.text, x.kind, x.referenced) for x in lines] == [
        (s.offset, s.raw, s.text, s.kind, s.referenced) for s in gbc_rom.manifest.strings
    ]
    assert lines[0].id == f"{lines[0].address:08X}"  # a file offset: the pointer base is 0
    assert result.script.game.platform == "gbc"


def test_marked_entries_and_shared_glyphs_read_as_plain_text(result):
    by_raw = {x.raw: x.text for x in result.script.lines}
    assert by_raw["<name48><は　><おちゃ>を　のんだ。"] == "〇〇は　おちゃを　のんだ。"
    assert by_raw["クりームを　なめた。"] == "クリームを　なめた。"
    assert by_raw["へンな　ねこが　いる。"] == "ヘンな　ねこが　いる。"
    assert by_raw["へやへ　もどろう。"] == "へやへ　もどろう。"  # a particle stays hiragana


def test_a_word_byte_and_the_same_word_spelled_out_rebuild_to_their_own_bytes(
    gbc_rom, loaded, result
):
    codec = loaded.codec(gbc_rom.rom)
    assert codec.encode("<おちゃ>") == bytes([0x40])
    assert codec.encode("おちゃ") == t("おちゃ") != bytes([0x40])
    check = verify(gbc_rom.rom, result.script.lines, codec)
    assert check.ok and not check.mismatches and not check.length_changes
    assert check.sha1 == gbc_rom.sha1


def test_name_tables_are_read_as_terms(gbc_rom, result):
    terms = [(x.category, x.index, x.jp) for x in result.script.terms]
    assert terms == gbc_rom.manifest.names
    assert all(x.line_id is None for x in result.script.terms)


def test_a_name_table_that_leaves_the_rom_stops_there(gbc_rom, loaded):
    data = copy.deepcopy(gbc_rom.profile_data)
    data["tables"] = [
        {"category": "a", "kind": "records", "base": 0xFFF8, "stride": 5, "count": 3},
        {"category": "b", "kind": "strings", "base": 0xFFFD, "count": 3},
    ]
    rom = bytearray(gbc_rom.rom)
    rom[0xFFF8:0xFFFD] = t("ねこ").ljust(5, bytes([F_RESUME]))
    rom[0xFFFD:0x10000] = t("つき") + bytes([F_NOT_TEXT])  # no end byte before the ROM ends
    changed = LoadedProfile(Profile.model_validate(data), loaded.path)
    out = extract(rom_from_bytes(bytes(rom)), changed, check_checksum=False)
    assert [(x.category, x.index, x.jp) for x in out.script.terms] == [("a", 0, "ねこ")]


# ------------------------------------------------- strings kept in the ROM


def test_the_words_two_bytes_stand_for_are_read_from_the_rom_not_from_the_table(gbc_rom, loaded):
    table = FAKE_FRAME_TBL.read_text(encoding="utf-8")
    assert "おちゃ" not in table and "\n40=" not in table and "\n41=" not in table
    codec = loaded.codec(gbc_rom.rom)
    assert codec.parse(bytes([0x40, 0x41, F_END]), 0) == (2, "<おちゃ><は　>", 5)
    assert codec.encode("<おちゃ>おちゃ") == bytes([0x40]) + t("おちゃ")
    assert len(codec) == len(load_tbl(FAKE_FRAME_TBL)["keys"]) + len(GBC_WORDS)


def test_a_codec_that_needs_the_rom_is_not_built_without_it(loaded):
    with pytest.raises(ProfileError, match="cannot be built without one"):
        loaded.codec()
    loaded.check_table()  # what can be checked without a ROM still is


@pytest.mark.parametrize(
    "damage",
    [
        lambda rom: rom.__setitem__(GBC_WORDS[0x40][0], F_NOT_TEXT),  # not a table character
        lambda rom: rom.__setitem__(GBC_WORDS[0x41][0], F_RESUME),  # nothing before the end
        lambda rom: rom.__setitem__(  # no end byte within reach
            slice(GBC_WORDS[0x40][0], GBC_WORDS[0x40][0] + 0x40), bytes([0x80]) * 0x40
        ),
    ],
    ids=["a byte that is not text", "an empty string", "no end"],
)
def test_another_rom_is_refused_when_its_strings_are_not_where_the_profile_says(
    gbc_rom, loaded, damage
):
    rom = bytearray(gbc_rom.rom)
    damage(rom)
    with pytest.raises(ProfileError, match="Is this the ROM the profile is for"):
        loaded.codec(bytes(rom))


def test_a_string_in_the_rom_cannot_repeat_a_table_entry(gbc_rom, profile_data, loaded):
    # both bytes at the same string: the second would encode to the first one's byte
    profile_data["encoding"]["rom_strings"] = {0x40: 0xC300, 0x41: 0xC300}
    changed = LoadedProfile(Profile.model_validate(profile_data), loaded.path)
    with pytest.raises(TableError, match="map back uniquely"):
        changed.codec(gbc_rom.rom)


@pytest.mark.parametrize(
    ("byte", "where"),
    [
        (0x80, "in the table file and in encoding.rom_strings"),  # a character of the file
        (0x02, "in the character table and in discover.frame"),  # the start command
        (0x0A, "in the character table and in discover.frame"),  # a break
        (0x03, "in the character table and in discover.frame"),  # an end
        (0x1F, "in the character table and in encoding.terminator"),  # and the resume byte
    ],
)
def test_a_byte_with_a_string_in_the_rom_is_a_character_like_any_other(
    profile_data, loaded, byte, where
):
    # found without a ROM, so `profile validate` reports it
    profile_data["encoding"]["rom_strings"] = {byte: 0xC300}
    changed = LoadedProfile(Profile.model_validate(profile_data), loaded.path)
    with pytest.raises(ProfileError, match=where):
        changed.check_table()


def test_a_string_in_the_rom_must_be_plain_characters(tmp_path, gbc_rom, profile_data):
    # a brace is a character of this table; text with one cannot be told from an escape
    table = tmp_path / "t.tbl"
    table.write_text(FAKE_FRAME_TBL.read_text(encoding="utf-8") + "70={" + chr(10), "utf-8")
    profile_data["encoding"]["table"] = "t.tbl"
    rom = bytearray(gbc_rom.rom)
    rom[GBC_WORDS[0x40][0] + 1] = 0x70
    changed = LoadedProfile(Profile.model_validate(profile_data), tmp_path / "p.yaml")
    with pytest.raises(ProfileError, match="no string of table characters"):
        changed.codec(bytes(rom))


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d: d["encoding"]["rom_strings"].update({0x100: 0}), "not a byte and an offset"),
        (lambda d: d["encoding"]["rom_strings"].update({0x42: -1}), "not a byte and an offset"),
        (
            lambda d: (
                d["encoding"].update({"type": "table", "table": "x.tbl"}),
                d["discover"].pop("frame"),
            ),
            "only for encoding.type 'table8'",
        ),
    ],
)
def test_bad_rom_strings_are_refused(profile_data, edit, message):
    edit(profile_data)
    with pytest.raises(ValidationError, match=message):
        Profile.model_validate(profile_data)


# ------------------------------------------------------------------ schema


@pytest.fixture
def profile_data(gbc_rom):
    return copy.deepcopy(gbc_rom.profile_data)


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d: d["discover"]["frame"].update({"ends": []}), "at least 1 item"),
        (lambda d: d["discover"]["frame"].pop("start"), "Field required"),
        (lambda d: d["discover"]["frame"].update({"start": 0x100}), "less than or equal to 255"),
        (lambda d: d["discover"]["frame"]["breaks"].append(0x100), "is not a byte"),
        (lambda d: d["discover"]["frame"]["commands"].update({0x12: 17}), "parameter count"),
        (lambda d: d["discover"]["frame"].pop("resume"), "needs frame.resume"),
        (lambda d: d["discover"]["frame"]["breaks"].append(0x03), "one role only"),
        (lambda d: d["discover"]["frame"]["commands"].update({0x1F: 0}), "one role only"),
        (
            lambda d: d["encoding"].update({"type": "table", "table": "x.tbl"}),
            "only for encoding.type 'table8'",
        ),
        (
            lambda d: d["encoding"].update({"command_prefix": 0xFF}),
            "cannot be combined with encoding.command_prefix",
        ),
    ],
)
def test_bad_frames_are_refused(profile_data, edit, message):
    edit(profile_data)
    with pytest.raises(ValidationError, match=message):
        Profile.model_validate(profile_data)


def test_tables_that_hold_their_text_need_a_one_byte_encoding(profile_data):
    profile_data["encoding"] = {"type": "table16", "table": "x.tbl"}
    del profile_data["discover"]["frame"]
    with pytest.raises(ValidationError, match="need a one-byte terminator"):
        Profile.model_validate(profile_data)


@pytest.mark.parametrize(
    ("edit", "where"),
    [
        (lambda d: d["discover"]["frame"]["ends"].append(0x60), "discover.frame"),
        (lambda d: d["discover"]["frame"].update({"start": 0x85}), "discover.frame"),
        (lambda d: d["discover"]["frame"]["breaks"].append(0x7F), "discover.frame"),
        (lambda d: d["discover"]["frame"].update({"resume": 0x80}), "discover.frame"),
        (lambda d: d["encoding"].update({"terminator": 0x61}), "encoding.terminator"),
    ],
)
def test_a_byte_cannot_be_a_character_and_start_or_end_text(profile_data, loaded, edit, where):
    # the table decides, so this is found when the codec is built, not when the file is read
    edit(profile_data)
    changed = LoadedProfile(Profile.model_validate(profile_data), loaded.path)
    with pytest.raises(ProfileError, match=f"in the character table and in {where}"):
        changed.check_table()


def test_a_command_between_texts_may_share_its_value_with_a_character(
    profile_data, loaded, gbc_rom
):
    # 0x80 is a character in text and, after the text is handed back, a command with a parameter
    profile_data["discover"]["frame"]["commands"][0x80] = 1
    profile_data["text"]["regions"] = [{"bank": 0}]
    profile = Profile.model_validate(profile_data)
    codec = LoadedProfile(profile, loaded.path).codec(gbc_rom.rom)
    rom = (
        bytes([F_START])
        + t("ぁ　きょうは　いい　てんき")
        + bytes([F_RESUME, 0x80, F_NOT_TEXT, F_START])  # the command, and its parameter
        + t("ですね。")
        + bytes([F_END])
    )
    strings = find_stream_strings(rom, codec, profile).strings
    assert [s.raw for s in strings] == ["ぁ　きょうは　いい　てんき", "ですね。"]
