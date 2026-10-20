"""Detector 10: what the control codes of a draft profile do.

Writing a profile for a byte-stream or glyph-id game means deciding, for every command, how many
parameters it takes and whether it ends a line or sits in the middle of a sentence. That is done
here from counts: what comes before each command, what comes after it, and (for glyph ids) how
often the token right after it is a lone glyph between commands. A parameter that happens to be a
glyph id is read as a one-character line of text; a real text run is longer. Counts and codes
only, never text.

Needs a draft profile (the character table and the text regions or compressed blocks), because
what counts as text is what the table can decode.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from yomineko.core.containers import Block
from yomineko.core.discover.compressed import read_profile_blocks
from yomineko.core.encodings.table8 import UNTIL_PREFIX, Table8Codec
from yomineko.core.encodings.table16 import Table16Codec
from yomineko.errors import YominekoError
from yomineko.profile.loader import LoadedProfile

PROBES = 4  # table8: positions after an unknown command that are looked at
MIN_COUNT = 20  # a command seen fewer times than this gets no suggestion
ISOLATED_LIKELY = 0.5  # share of lone glyphs after a command that makes a skip very likely
ISOLATED_POSSIBLE = 0.2


class CommandsError(YominekoError):
    """The profile has no commands to measure."""


@dataclass
class CommandStat:
    code: int
    count: int = 0
    declared: int | None = None  # parameters the profile says it takes
    before_text: int = 0  # occurrences right after text
    after_text: int = 0  # occurrences followed (after the declared parameters) by text
    after_command: int = 0
    probes: list[int] = field(default_factory=lambda: [0] * PROBES)  # table8: text or command at +k
    isolated: int = 0  # table16: followed by one glyph and then a command (a text-like parameter)
    line_break: bool = False

    @property
    def share_isolated(self) -> float:
        return self.isolated / self.count

    @property
    def share_before(self) -> float:
        return self.before_text / self.count

    @property
    def share_after(self) -> float:
        return self.after_text / self.count


@dataclass(frozen=True)
class CommandReport:
    profile_id: str
    kind: str  # "table8" or "table16"
    stats: list[CommandStat]  # most frequent first


def measure_commands(data: bytes, loaded: LoadedProfile) -> CommandReport:
    codec = loaded.codec(data)
    if isinstance(codec, Table8Codec):
        if codec.prefix is None:
            raise CommandsError("the profile has no command_prefix: there are no commands to read")
        stats = _table8(data, codec, [(r.start, r.end) for r in loaded.profile.text.regions])
        return CommandReport(loaded.profile.id, "table8", _ranked(stats))
    if isinstance(codec, Table16Codec):
        blocks = read_profile_blocks(data, loaded.profile)
        skip = loaded.profile.encoding.skip
        stats = _table16(blocks, codec)
        for code, stat in stats.items():
            stat.declared = skip.get(code)
        return CommandReport(loaded.profile.id, "table16", _ranked(stats))
    raise CommandsError("only table8 (byte stream) and table16 (glyph id) profiles have commands")


def _ranked(stats: dict[int, CommandStat]) -> list[CommandStat]:
    return sorted(stats.values(), key=lambda s: (-s.count, s.code))


def _class_at(data: bytes, p: int, end: int, codec: Table8Codec) -> str:
    if p >= end:
        return "other"
    b = data[p]
    if b == codec.prefix:
        return "command"
    return "text" if codec.starts_text(b) else "other"


def _table8(
    data: bytes, codec: Table8Codec, regions: list[tuple[int, int]]
) -> dict[int, CommandStat]:
    stats: dict[int, CommandStat] = {}
    for start, end in regions:
        end = min(end, len(data))
        i, prev = start, "other"
        while i < end:
            b = data[i]
            if b == codec.prefix and i + 1 < end:
                code = data[i + 1]
                declared = codec.commands.get(code)
                stat = stats.setdefault(code, CommandStat(code, declared=declared))
                stat.line_break = code in codec.breaks
                stat.count += 1
                stat.before_text += prev == "text"
                if declared == UNTIL_PREFIX:
                    nxt = data.find(bytes([codec.prefix]), i + 2, end)
                    after = end if nxt == -1 else nxt
                else:
                    after = i + 2 + (declared or 0)
                kind = _class_at(data, after, end, codec)
                stat.after_text += kind == "text"
                stat.after_command += kind == "command"
                if declared is None:
                    for k in range(PROBES):
                        stat.probes[k] += _class_at(data, i + 2 + k, end, codec) != "other"
                i, prev = max(after, i + 2), "command"
            elif _class_at(data, i, end, codec) == "text":
                i += codec.skip_len(data, i)
                prev = "text"
            else:
                i, prev = i + 1, "other"
    return stats


def _table16(blocks: list[Block], codec: Table16Codec) -> dict[int, CommandStat]:
    stats: dict[int, CommandStat] = {}
    for block in blocks:
        for start, end in block.entries:
            tokens = [
                block.data[p] | block.data[p + 1] << 8
                for p in range(start + (start & 1), end - 1, 2)
            ]
            prev_text = False
            for i, token in enumerate(tokens):
                if codec.knows(token):
                    prev_text = True
                    continue
                stat = stats.setdefault(token, CommandStat(token))
                stat.count += 1
                stat.before_text += prev_text
                prev_text = False
                if i + 2 < len(tokens) and codec.knows(tokens[i + 1]):
                    stat.isolated += not codec.knows(tokens[i + 2])
                if i + 1 < len(tokens):
                    stat.after_text += codec.knows(tokens[i + 1])
                    stat.after_command += not codec.knows(tokens[i + 1])
    return stats


def suggest(stat: CommandStat, kind: str) -> str:
    """A plain-language guess about the command, or an empty string when there is too little."""
    if stat.count < MIN_COUNT:
        return "too few to tell"
    if kind == "table16":
        share = stat.share_isolated
        if share >= ISOLATED_LIKELY:
            return "skip likely: its parameters look like glyphs"
        if share >= ISOLATED_POSSIBLE:
            return "skip possible: some parameters look like glyphs"
        return ""
    parts = []
    if stat.declared is None:
        best = max(range(PROBES), key=lambda k: (stat.probes[k], -k))
        if stat.probes[best] >= 0.8 * stat.count:
            parts.append(f"probably {best} parameter bytes")
    before, after = stat.share_before, stat.share_after
    if before >= 0.6 and after >= 0.6:
        parts.append("inside a sentence")
    elif before >= 0.6 and after < 0.4:
        parts.append("ends a line")
    elif before < 0.4 and after >= 0.6:
        parts.append("starts a text")
    return "; ".join(parts)
