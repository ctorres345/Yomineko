"""Where a user's games live on disk: one folder per game.

    <root>/<profile id>/script.json     the extracted (and analysed) script
    <root>/<profile id>/review.yaml     the user's own review (ids and their English only)

The command line uses ``./yomineko-out``; the app uses a folder in the user's data directory.
Everything here can hold game text, so it is never part of the repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from yomineko.analyze.dictionary.paths import data_dir
from yomineko.errors import YominekoError
from yomineko.profile.schema import PROFILE_ID

SCRIPT_NAME = "script.json"
REVIEW_NAME = "review.yaml"


class WorkspaceError(YominekoError):
    """A game id that is not safe to use as a folder name."""


@dataclass(frozen=True)
class Workspace:
    root: Path

    def game_dir(self, profile_id: str) -> Path:
        # ids come from profiles and from a web request: never let one climb out of the root
        if not PROFILE_ID.match(profile_id):
            raise WorkspaceError(f"{profile_id!r} is not a valid game id")
        return self.root / profile_id

    def script_path(self, profile_id: str) -> Path:
        return self.game_dir(profile_id) / SCRIPT_NAME

    def review_path(self, profile_id: str) -> Path:
        return self.game_dir(profile_id) / REVIEW_NAME

    def games(self) -> list[str]:
        """Ids of the games that have an extracted script, sorted."""
        if not self.root.is_dir():
            return []
        return sorted(
            d.name
            for d in self.root.iterdir()
            if PROFILE_ID.match(d.name) and (d / SCRIPT_NAME).is_file()
        )


def cli_workspace() -> Workspace:
    return Workspace(Path("yomineko-out"))


def app_workspace() -> Workspace:
    return Workspace(data_dir() / "games")
