"""Opt-in analysis test on a real dump. Needs the ROM (YOMINEKO_ROM_PMD_RED_JP), the analysis
extra, and the downloaded dictionary (`yomineko dict download`). Checks counts and structure
only: no game text. Run with ``pytest -m realrom``.

The numbers are bands, not exact values: they move a little with each JMdict and Sudachi
dictionary release. Measured on 2026-10-03: 3,214 words, 1,403 seen 4+ times.
"""

import os

import pytest

from yomineko.analyze.dictionary.install import dictionary_info
from yomineko.analyze.dictionary.store import Dictionary
from yomineko.analyze.review import ReviewApplier, packaged_review, parse_review
from yomineko.analyze.tokenizer import SudachiTokenizer
from yomineko.analyze.vocabulary import analysable_lines, analyze
from yomineko.analyze.worklist import build_worklist
from yomineko.core.rom.base import load_rom
from yomineko.extract import extract
from yomineko.model import DictionarySource
from yomineko.profile.loader import resolve_profile

ROM_PATH = os.environ.get("YOMINEKO_ROM_PMD_RED_JP")

pytestmark = [
    pytest.mark.realrom,
    pytest.mark.skipif(not ROM_PATH, reason="set YOMINEKO_ROM_PMD_RED_JP to run"),
]


@pytest.fixture(scope="module")
def analysed():
    pytest.importorskip("sudachipy")
    pytest.importorskip("sudachidict_core")
    info = dictionary_info()
    if info is None:
        pytest.skip("download the dictionary first: yomineko dict download")
    script = extract(load_rom(ROM_PATH), resolve_profile("pmd-red-jp")).script
    source = DictionarySource(date=info.date, source=info.source, credit=info.credit)
    tokenizer = SudachiTokenizer()
    with Dictionary(info.path) as dictionary:
        first = analyze(script, tokenizer, dictionary, source)
        second = analyze(script, tokenizer, dictionary, source)
    return script, first, second


def test_the_word_counts_are_in_the_expected_bands(analysed):
    _, result, _ = analysed
    assert 2500 <= len(result.words) <= 4000
    assert 1200 <= sum(1 for w in result.words if w.freq >= 4) <= 1700
    assert sum(1 for w in result.words if w.common) > len(result.words) // 2


def test_the_analysis_is_deterministic(analysed):
    _, first, second = analysed
    assert first == second


def test_every_word_is_well_formed(analysed):
    script, result, _ = analysed
    line_ids = {x.id for x in script.lines}
    freqs = [w.freq for w in result.words]
    assert freqs == sorted(freqs, reverse=True)
    for w in result.words:
        assert w.meanings and w.kana and w.written
        assert 1 <= len(w.examples) <= 20 and set(w.examples) <= line_ids
        assert w.freq >= len(w.examples)


def test_the_dictionary_is_credited(analysed):
    _, result, _ = analysed
    assert result.dictionary is not None and "CC BY-SA" in result.dictionary.credit


def test_a_correction_changes_exactly_the_occurrences_it_names(analysed):
    script, result, _ = analysed
    top = result.words[0]
    info = dictionary_info()
    review = parse_review({"words": [{"from": top.jmdict_id, "drop": True}]})
    with Dictionary(info.path) as dictionary:
        applier = ReviewApplier(review, dictionary)
        corrected = analyze(
            script,
            SudachiTokenizer(),
            dictionary,
            DictionarySource(date=info.date, source=info.source, credit=info.credit),
            review=applier,
        )
    report = applier.report()
    assert top.jmdict_id not in {w.jmdict_id for w in corrected.words}
    assert len(corrected.words) == len(result.words) - 1
    assert (report.rules, report.applied, report.unknown_ids) == (1, 1, [])
    assert report.changed_occurrences == top.freq


def test_the_worklist_lists_ambiguous_words_most_frequent_first(analysed):
    script, _, _ = analysed
    info = dictionary_info()
    with Dictionary(info.path) as dictionary:
        items = build_worklist(analysable_lines(script), SudachiTokenizer(), dictionary)
    assert 200 <= len(items) <= 900  # measured: 454 words seen 4+ times
    assert [i.freq for i in items] == sorted((i.freq for i in items), reverse=True)
    assert all(i.freq >= 4 and i.examples for i in items)
    assert all(i.alternatives for i in items if not i.reason)  # a probable name needs none


def test_the_packaged_review_applies_in_full(analysed):
    """All of the shipped review's rules fire on the real ROM, and the reviewed word list lands
    near the prototype's hand-reviewed one (1,106 words seen 4+ times)."""
    script, raw, _ = analysed
    info = dictionary_info()
    review = packaged_review("pmd-red-jp")
    assert review is not None
    with Dictionary(info.path) as dictionary:
        applier = ReviewApplier(review, dictionary)
        reviewed = analyze(
            script,
            SudachiTokenizer(),
            dictionary,
            DictionarySource(date=info.date, source=info.source, credit=info.credit),
            review=applier,
        )
    report = applier.report()
    assert report.rules == len(review.words) and report.applied == report.rules
    assert report.unknown_ids == [] and report.unused == []
    assert len(reviewed.words) < len(raw.words)
    assert 1000 <= sum(1 for w in reviewed.words if w.freq >= 4) <= 1300
    assert any(not w.sentence_safe for w in reviewed.words)


def test_lines_know_their_words_and_terms_are_matched(analysed):
    """Measured 2026-10-04: 9,349 lines with words, 636 of 2,843 terms matched."""
    script, result, _ = analysed
    word_ids = {w.jmdict_id for w in result.words}
    with_words = [x for x in result.lines if x.word_ids]
    assert 8000 <= len(with_words) <= 10500
    for x in with_words:
        assert x.kind == "dialogue" and x.duplicate_of is None
        assert len(set(x.word_ids)) == len(x.word_ids) and set(x.word_ids) <= word_ids
    matched = [t for t in result.terms if t.jmdict_id is not None]
    assert 400 <= len(matched) <= 900
    assert len(result.terms) == len(script.terms)
