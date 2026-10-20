"""Run every detector over one ROM and collect the results."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from yomineko.core.rom.base import Rom
from yomineko.profile.loader import LoadedProfile
from yomineko.survey import (
    bios,
    commands,
    compare,
    extent,
    fonts,
    plaintext,
    relative,
    state,
    tables,
    tokens,
)
from yomineko.survey.bios import OtherStreams, Stream
from yomineko.survey.commands import CommandReport
from yomineko.survey.compare import Comparison
from yomineko.survey.extent import Extent
from yomineko.survey.fonts import FontCandidate, Geometry
from yomineko.survey.plaintext import PlainText
from yomineko.survey.relative import RelativeHits
from yomineko.survey.state import StateReport
from yomineko.survey.tables import OffsetRun, PointerRun
from yomineko.survey.tokens import TokenRange


@dataclass
class Survey:
    game_code: str
    title: str
    sha1: str
    extent: Extent
    lz77: list[Stream]
    other_streams: list[OtherStreams]
    plain: PlainText
    pointer_runs: list[PointerRun]
    offset_runs: list[OffsetRun]
    fonts: list[FontCandidate]
    geometry: dict[int, Geometry | None]  # by candidate start
    tokens: list[TokenRange]
    relative: RelativeHits | None = None
    state: StateReport | None = None
    comparison: Comparison | None = None
    commands: CommandReport | None = None
    sheets: dict[str, bytes] = field(default_factory=dict)  # PNG file name -> bytes


def run_survey(
    rom: Rom,
    *,
    word: str | None = None,
    state_file: bytes | None = None,
    other: Rom | None = None,
    command_profile: LoadedProfile | None = None,
    sheets: bool = False,
    progress: Callable[[str], None] | None = None,
) -> Survey:
    """Survey ``rom``. The word and the state file are optional extra checks."""
    data = rom.data

    def step(name: str) -> None:
        if progress:
            progress(name)

    step("extent and fill")
    layout = extent.measure_extent(data)
    step("BIOS compression")
    lz77 = bios.find_lz77(data)
    others = bios.check_pointer_targets(data, bios.pointer_targets(data))
    step("plain text")
    plain = plaintext.find_plain_text(data)
    step("pointer and offset tables")
    pointer_runs = tables.find_pointer_runs(data)
    offset_runs = tables.find_offset_runs(data)
    step("font candidates")
    candidates = fonts.find_font_candidates(data)
    geometry = {c.start: fonts.estimate_geometry(data, c.start, c.end) for c in candidates}
    step("token streams")
    token_ranges = tokens.find_token_streams(data, lz77)
    found = Survey(
        rom.game_code,
        rom.title,
        rom.sha1,
        layout,
        lz77,
        others,
        plain,
        pointer_runs,
        offset_runs,
        candidates,
        geometry,
        token_ranges,
    )
    if word:
        step("relative search")
        found.relative = relative.relative_search(data, word)
    if state_file is not None:
        step("save state")
        found.state = state.analyze_state(state_file, data)
    if other is not None:
        step("comparison with the other ROM")
        found.comparison = compare.compare_roms(data, other.data)
    if command_profile is not None:
        step("commands of the profile")
        found.commands = commands.measure_commands(data, command_profile)
    if sheets:
        found.sheets = fonts.candidate_sheets(data, candidates)
    return found
