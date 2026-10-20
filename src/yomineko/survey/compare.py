"""Detector 9: where two versions of a game differ (a Japanese ROM against another region).

Another release of the same game holds the same code and data, moved by constant amounts where
the Japanese version has more or less of something. Matching 32-byte chunks finds the runs that
agree up to a shift; what is left over in one image and not the other is where that version keeps
its own data (the script, for instance). Counts and offsets only.

The first image is probed every 4 bytes, the second is indexed every 16: a run of 48 bytes or more
always contains a probe that lines up with an indexed chunk.
"""

from __future__ import annotations

from dataclasses import dataclass

CHUNK = 32
PROBE_STEP = 4
INDEX_STEP = 16
MIN_RUN = 128  # bytes a run needs to be reported
MIN_ONLY = 4096  # bytes a range present in one image only needs to be reported
MIN_DISTINCT = 6  # distinct byte values a chunk needs: fill and padding match everything


@dataclass(frozen=True)
class Run:
    start: int  # in the first image
    end: int
    shift: int  # offset in the second image minus offset in the first


@dataclass(frozen=True)
class Comparison:
    size_a: int
    size_b: int
    runs: list[Run]  # sorted by start
    matched: int  # bytes of the first image inside a run
    only_a: list[tuple[int, int]]  # ranges of the first image with no match
    only_b: list[tuple[int, int]]  # ranges of the second image with no match


def _distinct(chunk: bytes) -> bool:
    return len(set(chunk)) >= MIN_DISTINCT


def _index(b: bytes) -> dict[bytes, int]:
    index: dict[bytes, int] = {}
    for off in range(0, len(b) - CHUNK + 1, INDEX_STEP):
        chunk = b[off : off + CHUNK]
        if _distinct(chunk):
            index.setdefault(chunk, off)
    return index


def _runs(hits: list[tuple[int, int]]) -> list[Run]:
    """Join probe hits ``(offset, shift)`` that follow each other with the same shift."""
    runs: list[Run] = []
    for off, shift in hits:
        last = runs[-1] if runs else None
        if last and last.shift == shift and off <= last.end:
            runs[-1] = Run(last.start, max(last.end, off + CHUNK), shift)
        else:
            runs.append(Run(off, off + CHUNK, shift))
    return [r for r in runs if r.end - r.start >= MIN_RUN]


def _gaps(covered: list[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    gaps: list[tuple[int, int]] = []
    cursor = 0
    for start, end in sorted(covered):
        if start - cursor >= MIN_ONLY:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if size - cursor >= MIN_ONLY:
        gaps.append((cursor, size))
    return gaps


def compare_roms(a: bytes, b: bytes) -> Comparison:
    index = _index(b)
    hits: list[tuple[int, int]] = []
    for off in range(0, len(a) - CHUNK + 1, PROBE_STEP):
        chunk = a[off : off + CHUNK]
        other = index.get(chunk)
        if other is not None:
            hits.append((off, other - off))
    runs = _runs(hits)
    matched = sum(r.end - r.start for r in runs)
    only_a = _gaps([(r.start, r.end) for r in runs], len(a))
    only_b = _gaps([(r.start + r.shift, r.end + r.shift) for r in runs], len(b))
    return Comparison(len(a), len(b), runs, matched, only_a, only_b)
