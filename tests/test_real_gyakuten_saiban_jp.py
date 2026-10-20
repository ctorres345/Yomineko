"""Opt-in test against a real dump. Set YOMINEKO_ROM_GYAKUTEN_SAIBAN_JP to the ROM (.gba or
.zip) and run ``pytest -m realrom``. Compares counts and checksums only: no game text.

The script is 17 LZ77 blocks and one uncompressed block; the numbers are what this port found
on the owner's dump.
"""

import hashlib
import os

import pytest

from yomineko.core.rom.base import load_rom
from yomineko.core.roundtrip import verify
from yomineko.extract import extract
from yomineko.profile.loader import resolve_profile

ROM_PATH = os.environ.get("YOMINEKO_ROM_GYAKUTEN_SAIBAN_JP")

pytestmark = [
    pytest.mark.realrom,
    pytest.mark.skipif(not ROM_PATH, reason="set YOMINEKO_ROM_GYAKUTEN_SAIBAN_JP to run"),
]


@pytest.fixture(scope="module")
def run():
    rom = load_rom(ROM_PATH)
    loaded = resolve_profile("gyakuten-saiban-jp")
    return rom, loaded, extract(rom, loaded)


def test_rom_is_the_expected_dump(run):
    rom, loaded, _ = run
    assert rom.sha1 == loaded.profile.rom.sha1 == "ea7dabc4f5330c89a341ca38067fb025de73c835"
    assert rom.game_code == "ASBJ"


def test_the_script_blocks_decompress_to_the_known_data(run):
    _, _, result = run
    assert len(result.blocks) == 18
    assert [len(b.entries) for b in result.blocks][17] == 31  # the uncompressed block
    assert sum(len(b.entries) for b in result.blocks) == 2271
    digest = hashlib.sha1()
    for block in result.blocks:
        digest.update(block.data)
    assert digest.hexdigest() == "520722e301024f66867c2d4f379bba0fefa47f25"


def test_string_and_bank_counts(run):
    _, _, result = run
    assert len(result.strings) == 35859
    assert len(result.banks) == 18
    assert result.unstable == []


def test_unique_readable_line_counts(run):
    _, _, result = run
    unique = [x for x in result.script.lines if x.text and x.duplicate_of is None]
    assert len(unique) == 25944
    assert sum(1 for x in unique if x.kind == "dialogue") == 22469
    assert sum(1 for x in unique if x.kind == "term") == 3475


def test_every_line_re_encodes_to_the_decompressed_bytes(run):
    rom, loaded, result = run
    check = verify(rom.data, result.script.lines, loaded.codec(), result.blocks)
    assert check.ok
    assert check.decompressed_checked == 35859
    assert check.sha1 == rom.sha1
