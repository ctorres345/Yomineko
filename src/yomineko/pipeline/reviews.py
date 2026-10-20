"""Which review applies to a script: the game's packaged one plus the user's files."""

from __future__ import annotations

from pathlib import Path

from yomineko.analyze.review import (
    Review,
    ReviewReport,
    load_review,
    merge_reviews,
    packaged_review,
)
from yomineko.model import Script


def resolve_review(
    script: Script, files: list[Path] | None, use_packaged: bool = True
) -> Review | None:
    """The packaged review for the script's game (if any) plus the user's files, merged. Later
    files win. A review written for another ROM or game is refused."""
    reviews: list[Review] = []
    if use_packaged:
        packaged = packaged_review(script.game.profile_id)
        if packaged is not None:
            reviews.append(packaged)
    reviews.extend(load_review(f) for f in files or [])
    for review in reviews:
        review.check_for(script.game.rom_sha1, script.game.profile_id)
    return merge_reviews(reviews) if reviews else None


def describe_report(report: ReviewReport) -> list[str]:
    """The report as plain sentences, for a terminal or a page."""
    lines = [
        f"Review: {report.applied} of {report.rules} rules applied, "
        f"{report.changed_occurrences:,} word occurrences corrected."
    ]
    if report.unused:
        shown = ", ".join(report.unused[:8])
        lines.append(f"{len(report.unused)} rules matched nothing (stale?): {shown}")
    if report.unknown_ids:
        lines.append(
            f"{len(report.unknown_ids)} dictionary ids are not in your dictionary: "
            + ", ".join(str(i) for i in report.unknown_ids[:8])
        )
    return lines
