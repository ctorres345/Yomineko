"""The extraction pipeline: ROM + profile -> Script.

discover strings -> bank them -> readable text -> kind -> duplicates -> terms.
Ported from ``extract_text.py`` and ``export_text.py`` in the first prototype.
"""

from __future__ import annotations

import re
import struct
from collections.abc import Iterator
from dataclasses import dataclass, field

from yomineko import __version__
from yomineko.core.containers import Block, is_virtual, split_virtual
from yomineko.core.discover.banks import bank_name, group_banks
from yomineko.core.discover.compressed import find_compressed_strings, read_profile_blocks
from yomineko.core.discover.stream import find_stream_strings
from yomineko.core.discover.strings import DiscoverResult, FoundString, find_strings
from yomineko.core.encodings.table8 import Table8Codec
from yomineko.core.rom.base import Rom
from yomineko.errors import YominekoError
from yomineko.model import GameInfo, Line, LineKind, Script, Term
from yomineko.profile.loader import LoadedProfile
from yomineko.profile.schema import TableSpec

_DIALOGUE_PUNCT = re.compile(r"[。！？…、]")


class ProfileMismatch(YominekoError):
    """The ROM's checksum is not the one the profile was written for."""


class NotJapaneseError(YominekoError):
    """The ROM is not a Japanese release, going by its header."""


def is_japanese(rom: Rom) -> bool:
    """A Japanese release has a game code ending in ``J``; an older Game Boy cartridge has
    no code and says it in its destination byte (see ``core/rom``)."""
    return rom.japanese


def require_japanese(rom: Rom) -> None:
    if is_japanese(rom):
        return
    if rom.game_code:
        why = f"this ROM's game code is {rom.game_code!r} (a Japanese release ends in J)"
    else:
        why = "this ROM's header says it was sold outside Japan"
    raise NotJapaneseError(f"yomineko reads Japanese games: {why}")


@dataclass
class ExtractResult:
    script: Script
    strings: list[FoundString]
    banks: list[list[FoundString]]
    unstable: list[int] = field(default_factory=list)  # strings left out: not round-trippable
    blocks: list[Block] = field(default_factory=list)  # decompressed blocks, if the game has any


def line_kind(text: str, dialogue_min_length: int) -> LineKind:
    if len(text) > dialogue_min_length or "\n" in text or _DIALOGUE_PUNCT.search(text):
        return "dialogue"
    return "term"


def extract(rom: Rom, loaded: LoadedProfile, *, check_checksum: bool = True) -> ExtractResult:
    profile = loaded.profile
    require_japanese(rom)
    if check_checksum and rom.sha1 != profile.rom.sha1:
        raise ProfileMismatch(
            f"profile {profile.id!r} is for ROM {profile.rom.sha1}, but this ROM is {rom.sha1}"
        )
    codec = loaded.codec(rom.data)
    plain = loaded.plain()
    base = profile.text.pointer_base

    if isinstance(codec, Table8Codec):
        found = find_stream_strings(rom.data, codec, profile)
    elif profile.text.regions:
        found = find_strings(rom.data, codec, profile)
    else:
        found = DiscoverResult([])
    banks = group_banks(found.strings, profile.text.bank_gap)
    blocks = read_profile_blocks(rom.data, profile)
    if blocks:
        in_blocks = find_compressed_strings(blocks, codec, profile)
        found.strings.extend(in_blocks.strings)
        found.unstable.extend(in_blocks.unstable)
        banks.extend(_block_banks(in_blocks.strings))

    lines: list[Line] = []
    first_seen: dict[str, str] = {}  # readable text -> id of the first line with it
    by_address: dict[int, Line] = {}
    for bank in banks:
        name = _bank_name(bank)
        for s in bank:
            text = plain(s.raw)
            # text in a compressed block has a virtual address: no pointer base to add
            line_id = f"{s.start if is_virtual(s.start) else base + s.start:08X}"
            line = Line(
                id=line_id,
                address=s.start,
                bank=name,
                raw=s.raw,
                text=text,
                kind=line_kind(text, profile.kinds.dialogue_min_length),
                referenced=s.referenced,
                duplicate_of=first_seen.get(text) if text else None,
                scene=s.scene,
            )
            if text:
                first_seen.setdefault(text, line_id)
            lines.append(line)
            by_address[s.start] = line

    terms = _read_terms(rom.data, loaded, by_address)
    script = Script(
        generator=f"yomineko {__version__}",
        game=GameInfo(
            profile_id=profile.id,
            title=profile.title,
            platform=profile.platform,
            rom_sha1=rom.sha1,
        ),
        lines=lines,
        terms=terms,
    )
    return ExtractResult(script, found.strings, banks, found.unstable, blocks)


def _block_banks(strings: list[FoundString]) -> list[list[FoundString]]:
    """One bank per compressed block, in block order."""
    banks: dict[int, list[FoundString]] = {}
    for s in strings:
        banks.setdefault(split_virtual(s.start)[0], []).append(s)
    return [banks[index] for index in sorted(banks)]


def _bank_name(bank: list[FoundString]) -> str:
    first = bank[0].start
    if is_virtual(first):
        return f"block_{split_virtual(first)[0]:02d}"
    return bank_name(bank)


def _read_terms(data: bytes, loaded: LoadedProfile, by_address: dict[int, Line]) -> list[Term]:
    """The names in each profile table. A ``pointers`` table is followed: entry ``i`` has a
    text pointer at ``base + i*stride + field``. The other kinds hold the names themselves."""
    profile = loaded.profile
    codec = loaded.codec(data)
    plain = loaded.plain()
    pointer_base = profile.text.pointer_base
    end_byte = bytes([profile.encoding.terminator])
    terms: list[Term] = []
    for table in profile.tables:
        if table.kind != "pointers":
            for i, name in enumerate(_inline_names(data, table, end_byte)):
                # read on its own, so a name that fills its record cannot run into the next
                parsed = codec.parse(name + end_byte, 0)
                jp = plain(parsed[1]) if parsed and parsed[0] == len(name) else ""
                if jp:
                    terms.append(Term(jp=jp, category=table.category, index=i))
            continue
        for i in range(table.count):
            at = table.base + i * table.stride + table.field
            if at + 4 > len(data):
                break
            target = struct.unpack_from("<I", data, at)[0] - pointer_base
            if not 0 <= target < len(data):
                continue
            line = by_address.get(target)
            if line is not None:
                jp, line_id = line.text, line.id
            else:
                parsed = codec.parse(data, target)
                if parsed is None:
                    continue
                jp, line_id = plain(parsed[1]), None
            if jp:
                terms.append(Term(jp=jp, category=table.category, index=i, line_id=line_id))
    return terms


def _inline_names(data: bytes, table: TableSpec, end_byte: bytes) -> Iterator[bytes]:
    """The bytes of each name of a ``records`` or ``strings`` table, without padding or the
    end byte. Stops early where the table leaves the ROM."""
    at = table.base
    for _ in range(table.count):
        if table.kind == "records":
            record = data[at : at + table.stride]
            if len(record) < table.stride:
                return
            yield record.split(end_byte, 1)[0]
            at += table.stride
        else:
            end = data.find(end_byte, at)
            if end == -1:
                return
            yield data[at:end]
            at = end + 1
