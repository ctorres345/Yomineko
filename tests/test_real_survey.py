"""Opt-in survey checks against real dumps. Set the env variable named for each game to its ROM
(.gba or .zip) and run ``pytest -m realrom``. Counts only: no game text.

The numbers are what the survey found on the owner's dumps; a detector change that moves them
should be understood, not just re-pinned.
"""

import os

import pytest

from yomineko.core.rom.base import load_rom
from yomineko.survey import render_report, run_survey

GAMES = {
    "gyakuten-saiban-jp": {
        "env": "YOMINEKO_ROM_GYAKUTEN_SAIBAN_JP",
        "lz77": 1228,
        "large_lz77": 20,
        "other": {"huffman": (2, 1), "rle": (7, 7)},
        "plain": (0, 10),  # hiragana runs, katakana runs
        "pointer_runs": 2,
        "offset_runs": 0,
        "fonts": [0x1D3400, 0x1DB400],
        "token_ranges": 17,
        "token_ranges_in_rom": 0,
    },
    "mario-luigi-rpg-jp": {
        "env": "YOMINEKO_ROM_MARIO_LUIGI_RPG_JP",
        "lz77": 10,
        "large_lz77": 6,
        "other": {"huffman": (32, 7), "rle": (8, 8)},
        "plain": (14, 305),
        "pointer_runs": 62,
        "offset_runs": 15,
        "fonts": [],
        "token_ranges": 0,
        "token_ranges_in_rom": 0,
    },
    "pmd-red-jp": {
        "env": "YOMINEKO_ROM_PMD_RED_JP",
        "lz77": 17,
        "large_lz77": 0,
        "other": {"huffman": (1065, 2), "rle": (14, 14)},
        "plain": (23007, 3115),
        "pointer_runs": 1177,
        "offset_runs": 442,
        "fonts": [0x30F400, 0x508000, 0x50AC00, 0x50EC00],
        "token_ranges": 1,
        "token_ranges_in_rom": 1,
    },
}


@pytest.fixture(scope="module", params=sorted(GAMES))
def survey(request):
    game = GAMES[request.param]
    path = os.environ.get(game["env"])
    if not path:
        pytest.skip(f"set {game['env']} to run")
    return game, run_survey(load_rom(path))


@pytest.mark.realrom
def test_survey_counts_match_the_known_dump(survey):
    game, found = survey
    assert len(found.lz77) == game["lz77"]
    assert sum(s.size >= 8000 for s in found.lz77) == game["large_lz77"]
    assert {o.kind: (o.headers, o.decoded) for o in found.other_streams} == game["other"]
    assert (found.plain.hiragana_runs, found.plain.katakana_runs) == game["plain"]
    assert len(found.pointer_runs) == game["pointer_runs"]
    assert len(found.offset_runs) == game["offset_runs"]
    assert [f.start for f in found.fonts] == game["fonts"]
    assert len(found.tokens) == game["token_ranges"]
    assert sum(t.source == "rom" for t in found.tokens) == game["token_ranges_in_rom"]


@pytest.mark.realrom
def test_survey_report_is_numbers_only(survey):
    _, found = survey
    text = render_report(found)
    assert not any("぀" <= ch <= "鿿" for ch in text)
