"""Opt-in test against a real dump. Set YOMINEKO_ROM_POKEMON_CRYSTAL_JP to the ROM (.gbc or
.zip) and run ``pytest -m realrom``. Compares counts and checksums only: no game text.

A Game Boy Color ROM: framed messages in 20 banks, one line per row of the text box, and three
name tables. The numbers are what this port found on the owner's dump.
"""

import os
import re
from collections import Counter

import pytest

from yomineko.core.rom.base import load_rom
from yomineko.core.roundtrip import verify
from yomineko.extract import extract
from yomineko.profile.loader import resolve_profile

ROM_PATH = os.environ.get("YOMINEKO_ROM_POKEMON_CRYSTAL_JP")
BANK = 0x4000

pytestmark = [
    pytest.mark.realrom,
    pytest.mark.skipif(not ROM_PATH, reason="set YOMINEKO_ROM_POKEMON_CRYSTAL_JP to run"),
]


@pytest.fixture(scope="module")
def run():
    rom = load_rom(ROM_PATH)
    loaded = resolve_profile("pokemon-crystal-jp")
    return rom, loaded, extract(rom, loaded)


def test_rom_is_the_expected_dump(run):
    rom, loaded, _ = run
    assert rom.sha1 == loaded.profile.rom.sha1 == "95127b901bbce2407daf43cce9f45d4c27ef635d"
    assert (rom.platform, rom.game_code, rom.japanese, len(rom)) == ("gbc", "BXTJ", True, 0x200000)


def test_string_counts(run):
    _, loaded, result = run
    assert len(result.strings) == 14184
    assert result.unstable == []
    assert sum(1 for s in result.strings if s.referenced) == 12304
    regions = [(r.start, r.end) for r in loaded.profile.text.regions]
    assert len(regions) == 20
    assert all(any(a <= s.start and s.end <= b for a, b in regions) for s in result.strings)


def test_every_text_bank_has_lines(run):
    _, _, result = run
    per_bank = Counter(x.address // BANK for x in result.script.lines)
    assert len(per_bank) == 20
    assert (per_bank[0x05], per_bank[0x11], per_bank[0x20], per_bank[0x5D]) == (250, 366, 268, 1186)
    assert min(per_bank.values()) == 250


def test_unique_readable_line_counts(run):
    _, _, result = run
    unique = [x for x in result.script.lines if x.text and x.duplicate_of is None]
    assert len(unique) == 12793
    assert sum(1 for x in unique if x.kind == "dialogue") == 12632
    assert sum(1 for x in unique if x.kind == "term") == 161


def test_readable_text_has_no_marks_and_shows_the_shared_glyphs_as_katakana(run):
    _, _, result = run
    lines = result.script.lines
    assert not any(re.search(r"[<>{}]", x.text) for x in lines)
    # bytes that draw a fixed string, and names read from memory
    assert sum(len(re.findall(r"<[^n][^>]*>", x.raw)) for x in lines) == 12156
    assert sum(x.text.count("〇〇") for x in lines) == 461
    # he, ri, be and pe of katakana words, stored with the hiragana codes
    assert sum(len(re.findall("[ヘリベペ]", x.text)) for x in lines) == 421


def test_name_tables(run):
    _, _, result = run
    terms = result.script.terms
    assert Counter(t.category for t in terms) == {"pokemon": 251, "move": 251, "item": 256}
    assert len({t.jp for t in terms}) == 726  # unused item slots repeat a filler name
    assert all(1 <= len(t.jp) <= 8 for t in terms)


def test_every_line_re_encodes_to_the_original_bytes(run):
    rom, loaded, result = run
    check = verify(rom.data, result.script.lines, loaded.codec(rom.data))
    assert check.ok
    assert check.sha1 == rom.sha1
