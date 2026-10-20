"""Correct a game's word list: the user's own review file and the worklist behind it.

The user's review lives in the game's folder as ``review.yaml`` (dictionary ids and the user's own
English only). Rules are added and removed one at a time; there is at most one rule per word.
Words the user confirmed are right as picked are remembered in ``review-state.json`` so they leave
the worklist: a review file has no way to say "this pick is fine".
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from yomineko.analyze.review import (
    Review,
    ReviewApplier,
    WordRule,
    load_review,
    save_review,
)
from yomineko.analyze.tokenizer import Tokenizer
from yomineko.analyze.vocabulary import analysable_lines
from yomineko.analyze.worklist import DEFAULT_MIN_FREQ, WorkItem, build_worklist
from yomineko.errors import YominekoError
from yomineko.model import Script
from yomineko.pipeline.analysis import open_dictionary
from yomineko.pipeline.reviews import resolve_review
from yomineko.pipeline.workspace import Workspace

STATE_NAME = "review-state.json"


class RuleError(YominekoError):
    """A correction that cannot be made."""


def user_review(workspace: Workspace, game_id: str) -> Review:
    """The user's own review (empty if they have none yet)."""
    path = workspace.review_path(game_id)
    return load_review(path) if path.is_file() else Review()


def _stamp(review: Review, script: Script) -> Review:
    """Tie a new review file to its game, so a review for another ROM is never applied."""
    return review.model_copy(
        update={"profile": script.game.profile_id, "rom_sha1": script.game.rom_sha1}
    )


def set_word_rule(workspace: Workspace, game_id: str, script: Script, rule: WordRule) -> None:
    """Add ``rule`` to the user's review, replacing any earlier rule for the same word."""
    review = user_review(workspace, game_id)
    words = [w for w in review.words if w.from_ != rule.from_] + [rule]
    stamped = _stamp(review.model_copy(update={"words": words}), script)
    save_review(stamped, workspace.review_path(game_id))


def remove_word_rule(workspace: Workspace, game_id: str, entry_id: int) -> bool:
    """Take the user's rule for ``entry_id`` out. Returns whether there was one."""
    review = user_review(workspace, game_id)
    words = [w for w in review.words if w.from_ != entry_id]
    if len(words) == len(review.words):
        return False
    save_review(review.model_copy(update={"words": words}), workspace.review_path(game_id))
    return True


def _state_path(workspace: Workspace, game_id: str) -> Path:
    return workspace.game_dir(game_id) / STATE_NAME


def confirmed(workspace: Workspace, game_id: str) -> set[int]:
    """Words the user said are right as picked."""
    try:
        data = json.loads(_state_path(workspace, game_id).read_text(encoding="utf-8"))
        return {int(i) for i in data.get("confirmed", [])}
    except (OSError, ValueError, TypeError, AttributeError):
        return set()


def confirm(workspace: Workspace, game_id: str, entry_id: int) -> None:
    ids = sorted(confirmed(workspace, game_id) | {entry_id})
    path = _state_path(workspace, game_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"confirmed": ids}) + "\n", encoding="utf-8", newline="\n")


def prepare_worklist(
    workspace: Workspace,
    game_id: str,
    script: Script,
    make_tokenizer: Callable[[], Tokenizer],
    *,
    min_freq: int = DEFAULT_MIN_FREQ,
) -> list[WorkItem]:
    """The ambiguous words still to look at: not covered by any review rule, not confirmed."""
    review_path = workspace.review_path(game_id)
    merged = resolve_review(script, [review_path] if review_path.is_file() else None)
    tokenizer = make_tokenizer()
    with open_dictionary() as dictionary:
        applier = ReviewApplier(merged, dictionary) if merged else None
        items = build_worklist(
            analysable_lines(script), tokenizer, dictionary, review=applier, min_freq=min_freq
        )
    done = confirmed(workspace, game_id)
    return [i for i in items if i.pick.entry_id not in done]
