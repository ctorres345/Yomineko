"""Opt-in test: the packaged reviews of Gyakuten Saiban, Mario & Luigi and Crystal apply in full to
the real dumps. Needs the ROM variables, the analysis extra and the downloaded dictionary. Counts
only: no game text. Run with ``pytest -m realrom``.

Bands, not exact values: they move a little with each JMdict and Sudachi dictionary release.
Measured on 2026-10-05: Gyakuten Saiban 4,182 words (1,795 seen 3+ times) with 34 rules;
Mario & Luigi 2,238 words (755 seen 3+ times) with 10 rules. On 2026-10-09: Crystal 3,229 words
(1,531 seen 3+ times) with 64 rules.
"""

import os

import pytest

from yomineko.analyze.dictionary.install import dictionary_info
from yomineko.analyze.dictionary.store import Dictionary
from yomineko.analyze.review import ReviewApplier, packaged_review
from yomineko.analyze.tokenizer import SudachiTokenizer
from yomineko.analyze.vocabulary import analyze
from yomineko.core.rom.base import load_rom
from yomineko.extract import extract
from yomineko.model import DictionarySource
from yomineko.profile.loader import resolve_profile

GAMES = {
    "gyakuten-saiban-jp": ("YOMINEKO_ROM_GYAKUTEN_SAIBAN_JP", (3500, 5000), (1500, 2100)),
    "mario-luigi-rpg-jp": ("YOMINEKO_ROM_MARIO_LUIGI_RPG_JP", (1800, 2700), (600, 950)),
    "pokemon-crystal-jp": ("YOMINEKO_ROM_POKEMON_CRYSTAL_JP", (2700, 3900), (1250, 1850)),
}

pytestmark = pytest.mark.realrom


@pytest.mark.parametrize("profile_id", GAMES)
def test_the_packaged_review_applies_in_full(profile_id):
    env, words_band, frequent_band = GAMES[profile_id]
    path = os.environ.get(env)
    if not path:
        pytest.skip(f"set {env} to run")
    pytest.importorskip("sudachipy")
    pytest.importorskip("sudachidict_core")
    info = dictionary_info()
    if info is None:
        pytest.skip("download the dictionary first: yomineko dict download")
    script = extract(load_rom(path), resolve_profile(profile_id)).script
    review = packaged_review(profile_id)
    assert review is not None
    source = DictionarySource(date=info.date, source=info.source, credit=info.credit)
    with Dictionary(info.path) as dictionary:
        applier = ReviewApplier(review, dictionary)
        reviewed = analyze(script, SudachiTokenizer(), dictionary, source, review=applier)
    report = applier.report()
    assert report.rules == len(review.words) and report.applied == report.rules
    assert report.unknown_ids == [] and report.unused == []
    assert words_band[0] <= len(reviewed.words) <= words_band[1]
    assert frequent_band[0] <= sum(1 for w in reviewed.words if w.freq >= 3) <= frequent_band[1]
