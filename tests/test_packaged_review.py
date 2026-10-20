"""The review shipped for PMD Red JP: ids only, valid, for the right ROM."""

import re
from importlib import resources
from pathlib import Path

import pytest
import repo_guard

from yomineko.analyze.review import packaged_review
from yomineko.profile.loader import find_profile

PMD_SHA1 = "4bc9370edebb3da5bdf768eeced689fda3f8b77b"
JAPANESE = re.compile("[ぁ-んァ-ヶ" + chr(0x4E00) + "-" + chr(0x9FFF) + "]")


@pytest.fixture(scope="module")
def review():
    loaded = packaged_review("pmd-red-jp")
    assert loaded is not None, "the review is missing from the package"
    return loaded


@pytest.fixture(scope="module")
def text():
    return Path(str(resources.files("yomineko.reviews").joinpath("pmd-red-jp.yaml"))).read_text(
        encoding="utf-8"
    )


def test_it_is_for_the_pmd_rom_and_profile(review):
    review.check_for(PMD_SHA1, "pmd-red-jp")
    assert (review.profile, review.rom_sha1) == ("pmd-red-jp", PMD_SHA1)
    assert find_profile(PMD_SHA1).profile.id == review.profile


def test_it_holds_the_converted_rules(review):
    kinds = {
        "drop": sum(r.drop for r in review.words),
        "gloss": sum(r.gloss is not None for r in review.words),
        "remap": sum(r.to is not None for r in review.words),
    }
    assert kinds["drop"] > 200 and kinds["remap"] > 30 and kinds["gloss"] >= 10
    assert 300 <= len(review.words) <= 330 and review.lines == []
    assert any(not r.sentence_safe for r in review.words), "unsafe remaps were kept"
    assert all(r.from_ > 0 and (r.to is None or r.to > 0) for r in review.words)


def test_it_contains_no_game_text(text):
    assert not JAPANESE.search(text)
    assert repo_guard.check_text("src/yomineko/reviews/pmd-red-jp.yaml", text) is None
    assert repo_guard.check_path("src/yomineko/reviews/pmd-red-jp.yaml") is None


def test_it_is_a_packaged_resource():
    folder = resources.files("yomineko.reviews")
    assert folder.joinpath("pmd-red-jp.yaml").is_file()
