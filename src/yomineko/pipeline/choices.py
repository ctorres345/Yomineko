"""The learner's word choices, remembered on this computer: their level and, per game, how often
a word must be seen to get a card.

    <root>/choices.json             {"level": ...}: the level a new game starts with
    <root>/<game id>/choices.json   {"level": ..., "min_freq": ...} for that game

Only these settings are stored, never game text. A missing or damaged file means the defaults.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from yomineko.errors import YominekoError
from yomineko.export.level import DEFAULT_LEVEL, Level, parse_level
from yomineko.export.sentences import DEFAULT_MIN_FREQ
from yomineko.pipeline.workspace import Workspace

CHOICES_NAME = "choices.json"
MAX_MIN_FREQ = 1000


@dataclass(frozen=True)
class Choices:
    level: Level = DEFAULT_LEVEL
    min_freq: int = DEFAULT_MIN_FREQ


def _read(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _level(value: object) -> Level | None:
    try:
        return parse_level(value) if isinstance(value, str) else None
    except YominekoError:
        return None


def load_choices(workspace: Workspace, game_id: str) -> Choices:
    """The game's saved choices; a game with none starts at the last level picked."""
    mine = _read(workspace.game_dir(game_id) / CHOICES_NAME)
    shared = _read(workspace.root / CHOICES_NAME)
    level = _level(mine.get("level")) or _level(shared.get("level")) or DEFAULT_LEVEL
    min_freq = mine.get("min_freq")
    if not isinstance(min_freq, int) or isinstance(min_freq, bool):
        min_freq = DEFAULT_MIN_FREQ
    return Choices(level, min(max(min_freq, 1), MAX_MIN_FREQ))


def save_choices(workspace: Workspace, game_id: str, choices: Choices) -> None:
    """Remember ``choices`` for the game, and its level for the next game."""
    folder = workspace.game_dir(game_id)
    folder.mkdir(parents=True, exist_ok=True)
    game = {"level": choices.level, "min_freq": choices.min_freq}
    (folder / CHOICES_NAME).write_text(json.dumps(game) + "\n", encoding="utf-8")
    (workspace.root / CHOICES_NAME).write_text(
        json.dumps({"level": choices.level}) + "\n", encoding="utf-8"
    )
