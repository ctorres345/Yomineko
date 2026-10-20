"""Opt-in test against a real dump. Set YOMINEKO_ROM_MARIO_LUIGI_RPG_JP to the ROM (.gba or
.zip) and run ``pytest -m realrom``. Compares counts and checksums only: no game text.

The script is two byte-stream regions with FF commands; the numbers are what this port found on
the owner's dump.
"""

import os

import pytest

from yomineko.core.rom.base import load_rom
from yomineko.core.roundtrip import verify
from yomineko.extract import extract
from yomineko.profile.loader import resolve_profile

ROM_PATH = os.environ.get("YOMINEKO_ROM_MARIO_LUIGI_RPG_JP")

pytestmark = [
    pytest.mark.realrom,
    pytest.mark.skipif(not ROM_PATH, reason="set YOMINEKO_ROM_MARIO_LUIGI_RPG_JP to run"),
]


@pytest.fixture(scope="module")
def run():
    rom = load_rom(ROM_PATH)
    loaded = resolve_profile("mario-luigi-rpg-jp")
    return rom, loaded, extract(rom, loaded)


def test_rom_is_the_expected_dump(run):
    rom, loaded, _ = run
    assert rom.sha1 == loaded.profile.rom.sha1 == "edc538ac505bfcd337abdd03b3a6f2744d81eaab"
    assert rom.game_code == "A88J"


def test_string_counts(run):
    _, _, result = run
    assert len(result.strings) == 5962
    assert result.unstable == []
    regions = loaded_regions(run)
    assert all(any(a <= s.start and s.end <= b for a, b in regions) for s in result.strings)


def test_unique_readable_line_counts(run):
    _, _, result = run
    unique = [x for x in result.script.lines if x.text and x.duplicate_of is None]
    assert len(unique) == 5152
    assert sum(1 for x in unique if x.kind == "dialogue") == 3913
    assert sum(1 for x in unique if x.kind == "term") == 1239


def test_every_line_re_encodes_to_the_original_bytes(run):
    rom, loaded, result = run
    check = verify(rom.data, result.script.lines, loaded.codec())
    assert check.ok
    assert check.sha1 == rom.sha1


def loaded_regions(run):
    return [(r.start, r.end) for r in run[1].profile.text.regions]
