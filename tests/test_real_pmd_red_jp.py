"""Opt-in test against a real dump. Set YOMINEKO_ROM_PMD_RED_JP to the ROM (.gba or .zip)
and run ``pytest -m realrom``. Compares counts and checksums only: no game text.

The numbers are the first prototype's recorded results, reproduced by this port.
"""

import os

import pytest

from yomineko.core.rom.base import load_rom
from yomineko.core.roundtrip import verify
from yomineko.extract import extract
from yomineko.profile.loader import resolve_profile

ROM_PATH = os.environ.get("YOMINEKO_ROM_PMD_RED_JP")

pytestmark = [
    pytest.mark.realrom,
    pytest.mark.skipif(not ROM_PATH, reason="set YOMINEKO_ROM_PMD_RED_JP to run"),
]


@pytest.fixture(scope="module")
def run():
    rom = load_rom(ROM_PATH)
    loaded = resolve_profile("pmd-red-jp")
    return rom, loaded, extract(rom, loaded)


def test_rom_is_the_expected_dump(run):
    rom, loaded, _ = run
    assert rom.sha1 == loaded.profile.rom.sha1 == "4bc9370edebb3da5bdf768eeced689fda3f8b77b"
    assert rom.game_code == "B24J"


def test_string_and_bank_counts(run):
    _, _, result = run
    assert len(result.strings) == 12817
    assert len(result.banks) == 826
    assert result.unstable == []


def test_unique_readable_line_counts(run):
    _, _, result = run
    unique = [x for x in result.script.lines if x.text and x.duplicate_of is None]
    assert len(unique) == 12128
    assert sum(1 for x in unique if x.kind == "dialogue") == 9549
    assert sum(1 for x in unique if x.kind == "term") == 2579


def test_rebuild_is_byte_identical(run):
    rom, loaded, result = run
    check = verify(rom.data, result.script.lines, loaded.codec())
    assert check.ok
    assert check.sha1 == rom.sha1
