"""Extract a ROM into a script and prove the text rebuilds: the steps behind ``extract`` and
``verify``, for a ROM that is already in memory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from yomineko.core.rom.base import Rom
from yomineko.core.roundtrip import verify as verify_rom
from yomineko.errors import YominekoError
from yomineko.extract import extract as run_extract
from yomineko.extract import require_japanese
from yomineko.model import Script
from yomineko.pipeline.workspace import Workspace
from yomineko.profile.loader import (
    LoadedProfile,
    find_profile,
    packaged_profiles,
    resolve_profile,
)
from yomineko.script_io import write_script

STATUS_NAME = "game.json"


class NoProfileError(YominekoError):
    """No profile is known for this ROM."""


def find_loaded_profile(rom: Rom, spec: str | None = None) -> LoadedProfile:
    """The profile named by ``spec`` (an id or a path), else the one whose checksum matches."""
    require_japanese(rom)
    if spec:
        return resolve_profile(spec)
    found = find_profile(rom.sha1)
    if found is None:
        known = ", ".join(p.profile.id for p in packaged_profiles()) or "none"
        raise NoProfileError(
            f"no profile for this ROM (sha1 {rom.sha1}, game code {rom.game_code}). "
            f"Packaged profiles: {known}. Use --profile PATH, or see CONTRIBUTING.md to add a game."
        )
    return found


@dataclass(frozen=True)
class GameStatus:
    """What extraction found, kept next to the script (``game.json``): counts only."""

    rom_sha1: str
    strings: int
    banks: int
    unstable: int  # strings left out because they do not rebuild identically
    rebuild_ok: bool  # the text rebuilds a ROM with the same checksum


@dataclass(frozen=True)
class Extraction:
    script: Script
    status: GameStatus


def extract_rom(rom: Rom, spec: str | None = None) -> Extraction:
    """Extract the script and check that it rebuilds the ROM byte for byte."""
    loaded = find_loaded_profile(rom, spec)
    result = run_extract(rom, loaded)
    check = verify_rom(rom.data, result.script.lines, loaded.codec(rom.data), result.blocks)
    status = GameStatus(
        rom_sha1=rom.sha1,
        strings=len(result.strings),
        banks=len(result.banks),
        unstable=len(result.unstable),
        rebuild_ok=check.ok,
    )
    return Extraction(result.script, status)


def save_extraction(workspace: Workspace, extraction: Extraction) -> Path:
    """Write the script and its status into the game's folder; returns the script's path."""
    profile_id = extraction.script.game.profile_id
    path = write_script(extraction.script, workspace.script_path(profile_id))
    status = workspace.game_dir(profile_id) / STATUS_NAME
    status.write_text(
        json.dumps(asdict(extraction.status), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return path


def read_status(workspace: Workspace, profile_id: str) -> GameStatus | None:
    """The saved status, or ``None`` if there is none or it cannot be read."""
    try:
        data = json.loads((workspace.game_dir(profile_id) / STATUS_NAME).read_text("utf-8"))
        return GameStatus(**data)
    except (OSError, ValueError, TypeError):
        return None
