"""Find the text strings in a ROM.

Ported from ``find_strings`` in the first prototype:

1. every pointer target in a text region that parses as text is a string;
2. unreferenced strings are also kept when they directly follow a terminator and look like
   Japanese prose (enough Japanese characters, and a high kana ratio);
3. strings that start inside another string (shared suffixes) are dropped;
4. strings that do not re-encode to the exact original bytes are set aside, so a rebuild
   is always byte-identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from yomineko.core.discover.filter import kana_ratio, make_looks_like_text
from yomineko.core.discover.pointers import scan_pointers
from yomineko.core.encodings.base import Codec
from yomineko.profile.schema import Profile


@dataclass(frozen=True)
class FoundString:
    start: int
    end: int  # offset of the terminator byte
    raw: str  # extractor text (exact, round-trippable)
    referenced: bool  # some pointer in the ROM points at it
    scene: str | None = None  # compressed text: "block/entry" the run sits in


@dataclass
class DiscoverResult:
    strings: list[FoundString]
    # starts of strings that parsed as text but did not re-encode identically
    unstable: list[int] = field(default_factory=list)


def find_strings(data: bytes, codec: Codec, profile: Profile) -> DiscoverResult:
    cfg = profile.text
    disc = profile.discover
    looks_like_text = make_looks_like_text(disc.ignore, disc.min_score)
    term = codec.terminator
    term_byte = bytes([term])

    found: dict[int, tuple[int, str, bool]] = {}

    # 1) pointer targets
    for a in scan_pointers(data, cfg.pointer_base, cfg.regions, cfg.pointer_align):
        r = codec.parse(data, a)
        if r and r[2] >= 1 and r[0] > a and looks_like_text(r[1]):
            found[a] = (r[0], r[1], True)

    # 2) unreferenced strings that follow a terminator and look like Japanese prose
    for region in cfg.regions:
        lo = max(region.start, 1)
        pos = data.find(term_byte, lo - 1, region.end)
        while pos != -1 and pos + 1 < region.end:
            i = pos + 1
            if data[i] != term and i not in found:
                r = codec.parse(data, i)
                if (
                    r
                    and r[2] >= disc.unreferenced.min_japanese
                    and kana_ratio(r[1]) > disc.unreferenced.min_kana_ratio
                    and looks_like_text(r[1])
                ):
                    found[i] = (r[0], r[1], False)
            pos = data.find(term_byte, pos + 1, region.end)

    # 3) drop strings that start inside another string (shared suffixes)
    kept: list[FoundString] = []
    last_end = -1
    for a in sorted(found):
        end, raw, referenced = found[a]
        if a <= last_end:
            continue
        kept.append(FoundString(a, end, raw, referenced))
        last_end = end

    # 4) the text must re-encode to the exact original bytes
    stable: list[FoundString] = []
    unstable: list[int] = []
    for s in kept:
        try:
            ok = codec.encode(s.raw) == data[s.start : s.end]
        except ValueError:
            ok = False
        if ok:
            stable.append(s)
        else:
            unstable.append(s.start)
    return DiscoverResult(strings=stable, unstable=unstable)
