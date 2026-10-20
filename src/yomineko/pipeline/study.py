"""Pick sentences and decks the way a game's profile and review ask for."""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from yomineko.analyze.review import SentenceRules
from yomineko.errors import YominekoError
from yomineko.export.level import DEFAULT_LEVEL, Level
from yomineko.export.sentences import Sentence, select_sentences
from yomineko.export.study import ALL_DECKS, Deck
from yomineko.model import Script
from yomineko.pipeline.reviews import resolve_review
from yomineko.profile.loader import ProfileError, resolve_profile


def parse_decks(spec: str | None) -> list[Deck]:
    """``words,sentences`` -> the deck names, in the usual order."""
    if not spec:
        return list(ALL_DECKS)
    asked = {x.strip().lower() for x in spec.split(",") if x.strip()}
    unknown = sorted(asked - set(ALL_DECKS))
    if unknown or not asked:
        raise YominekoError(
            f"unknown deck {unknown[0]!r}: choose from {', '.join(ALL_DECKS)}"
            if unknown
            else "--decks needs at least one of: " + ", ".join(ALL_DECKS)
        )
    return [d for d in ALL_DECKS if d in asked]


def choose_sentences(
    script: Script,
    *,
    count: int,
    min_freq: int,
    profile_spec: str | None = None,
    review_files: list[Path] | None = None,
    use_packaged_review: bool = True,
    level: Level = DEFAULT_LEVEL,
    known: Collection[int] = frozenset(),
) -> list[Sentence]:
    """Sentences for ``script`` under its game's profile rules and review.

    The profile is the one named by ``profile_spec``, else the packaged profile with the script's
    id; a game with no profile at hand simply has no address ranges or caps."""
    exclude_ranges: list[tuple[int, int]] = []
    caps: dict[str, int] = {}
    try:
        profile = resolve_profile(profile_spec or script.game.profile_id).profile
    except ProfileError:
        if profile_spec:
            raise
    else:
        exclude_ranges = [(r.start, r.end) for r in profile.sentences.exclude_ranges]
        caps = {k: v for k, v in profile.sentences.caps.model_dump().items() if v is not None}
    review = resolve_review(script, review_files, use_packaged=use_packaged_review)
    rules = review.sentences if review else SentenceRules()
    return select_sentences(
        script,
        count=count,
        min_freq=min_freq,
        exclude_ids=rules.exclude,
        pin_ids=rules.pin,
        exclude_ranges=exclude_ranges,
        caps=caps,
        level=level,
        known=known,
    )
