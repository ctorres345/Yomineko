"""Find the text runs in a byte stream of one-byte codes and commands (``table8``).

Unlike the pointer-driven discovery of terminated strings, the script here is a continuous
stream inside the profile's ``text.regions``: text, and commands that either end a line or sit
in the middle of a sentence (the codec knows which). The scan reads a run wherever one starts,
keeps it when it looks like Japanese, and steps over everything else. Graphics data that happens
to decode as text has odd Latin letters between the kana, so among the kana, kanji and Latin
letters of a run most must be Japanese.

Where every byte value is a character, that is not enough: code and data read as kana. A
profile then describes the frame of a message (``discover.frame``) and runs are read from whole
messages only: after the command that starts text, as long as every byte is a character, a line
break or a known command, and only if the message reaches a real end byte.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from yomineko.core.discover.pointers import pointed_at_in_bank
from yomineko.core.discover.strings import DiscoverResult, FoundString
from yomineko.core.encodings.table8 import RUN_LIMIT, Table8Codec
from yomineko.profile.schema import Frame, Profile

_KANA_KANJI = re.compile("[ぁ-ヿ一-鿿]")
_LATIN = re.compile("[Ａ-Ｚａ-ｚ]")  # full-width A-Z and a-z


Run = tuple[int, int, str, bool]  # start, end, extractor text, whether a pointer leads to it
Row = tuple[int, int, str]  # one line of a message: start, end, extractor text


def find_stream_strings(data: bytes, codec: Table8Codec, profile: Profile) -> DiscoverResult:
    disc = profile.discover
    strings: list[FoundString] = []
    unstable: list[int] = []
    for region in profile.text.regions:
        end = min(region.end, len(data))
        if disc.frame is None:
            runs = _runs(data, codec, region.start, end)
        else:
            runs = _framed_runs(data, codec, profile, region.start, end)
        for start, run_end, raw, referenced in runs:
            kana = len(_KANA_KANJI.findall(raw))
            latin = len(_LATIN.findall(raw))
            if kana >= disc.stream_min_chars and kana >= disc.stream_min_jp_ratio * (kana + latin):
                if codec.encode(raw) == data[start:run_end]:
                    strings.append(FoundString(start, run_end, raw, referenced))
                else:
                    unstable.append(start)
    return DiscoverResult(strings, unstable)


def _runs(data: bytes, codec: Table8Codec, start: int, end: int) -> Iterator[Run]:
    """Every run between ``start`` and ``end``, wherever one begins."""
    pos = start
    while pos < end:
        pos = codec.skip_inline(data, pos)  # a line starts at its first character
        if pos >= end:
            break
        run = codec.parse(data, pos, RUN_LIMIT)  # the whole ROM, as `verify` reads it later
        if run is None:
            pos += codec.skip_len(data, pos)
            continue
        run_end, raw, _ = run
        if run_end > end:  # a run that leaves the region is not one the profile vouches for
            break
        yield pos, run_end, raw, False
        pos = run_end


def _framed_runs(
    data: bytes, codec: Table8Codec, profile: Profile, start: int, end: int
) -> Iterator[Run]:
    """The lines of every message between ``start`` and ``end`` that is worth keeping: one a
    pointer leads to, or one with enough kana and kanji of its own (not counting what the
    profile's ``ignore`` patterns remove, such as the text of a placeholder).

    Every text-start command is tried in turn, and a message that is kept is skipped over. A
    message that is not kept is not: a real one can begin inside bytes that only looked like
    the beginning of another. So that this does not read the same bytes again and again,
    ``known`` remembers what a walk found at each place between texts it passed."""
    disc = profile.discover
    frame = disc.frame
    assert frame is not None
    ignore = re.compile("|".join(disc.ignore)) if disc.ignore else None
    banked = profile.platform == "gbc"
    first = bytes([frame.start])
    known: dict[int, tuple[int, int] | None] = {}
    pos = data.find(first, start, end)
    while pos != -1:
        if pos not in known:
            _explore(data, codec, frame, pos, end, ignore, known)
        message = known[pos]
        resume_at = pos + 1
        if message is not None:
            after, kana = message
            referenced = banked and pointed_at_in_bank(data, pos)
            if referenced or kana >= disc.unreferenced.min_japanese:
                for row_start, row_end, raw in _lines_from(data, codec, frame, pos, end):
                    yield row_start, row_end, raw, referenced
                resume_at = after
        pos = data.find(first, resume_at, end)


def _explore(
    data: bytes,
    codec: Table8Codec,
    frame: Frame,
    pos: int,
    end: int,
    ignore: re.Pattern[str] | None,
    known: dict[int, tuple[int, int] | None],
) -> None:
    """Walk the message from the place between texts at ``pos`` and note, for each such place
    passed, what follows from it: ``None`` when the bytes are not a whole message that ends
    before ``end``, else the offset after the message and the kana and kanji of its own from
    that place on. The walk stops at a place already known: the rest is the same from there."""
    path: list[tuple[int, int]] = []  # each place, and the kana of the text read at it
    outcome: tuple[int, int] | None = None
    at = pos
    while at < end:
        if at in known:
            outcome = known[at]
            break
        after, rows, over = _step(data, codec, frame, at, end)
        path.append((at, sum(_own_kana(raw, ignore) for _, _, raw in rows)))
        if after is None:
            break
        if over:
            outcome = (after, 0)
            break
        at = after
    if outcome is None:
        known.update(dict.fromkeys((place for place, _ in path), None))
        return
    after, kana = outcome
    for place, own in reversed(path):
        kana += own
        known[place] = (after, kana)


def _own_kana(raw: str, ignore: re.Pattern[str] | None) -> int:
    return len(_KANA_KANJI.findall(ignore.sub("", raw) if ignore else raw))


def _lines_from(data: bytes, codec: Table8Codec, frame: Frame, pos: int, end: int) -> Iterator[Row]:
    """The lines of the message at ``pos``, which is known to be a whole one."""
    at: int | None = pos
    over = False
    while at is not None and not over:
        at, rows, over = _step(data, codec, frame, at, end)
        yield from rows


def _step(
    data: bytes, codec: Table8Codec, frame: Frame, at: int, end: int
) -> tuple[int | None, list[Row], bool]:
    """One step of a message from the place between texts at ``at``: where the next such place
    is (``None`` when the bytes do not fit a message), the lines of the text read on the way,
    and whether the message is over there."""
    b = data[at]
    if b == frame.resume:
        return at + 1, [], True
    if b in frame.commands:
        return at + 1 + frame.commands[b], [], False
    if b != frame.start:
        return None, [], False
    rows: list[Row] = []
    pos = at + 1
    while pos < end:
        b = data[pos]
        if b in frame.ends:
            return pos + 1, rows, True
        if b == frame.resume:
            return pos + 1, rows, False
        if b in frame.breaks:
            pos += 1
            continue
        run = codec.parse(data, pos, RUN_LIMIT)
        if run is None or run[0] > end:
            break
        rows.append((pos, run[0], run[1]))
        pos = run[0]
    return None, [], False
