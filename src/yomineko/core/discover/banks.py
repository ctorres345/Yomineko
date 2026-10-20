"""Group nearby strings into banks (one text block of the ROM)."""

from __future__ import annotations

from yomineko.core.discover.strings import FoundString


def group_banks(strings: list[FoundString], gap: int) -> list[list[FoundString]]:
    """Strings no further apart than ``gap`` bytes (end of one to start of the next) share a
    bank. ``strings`` must be sorted by address."""
    banks: list[list[FoundString]] = []
    for s in strings:
        if banks and s.start - banks[-1][-1].end <= gap:
            banks[-1].append(s)
        else:
            banks.append([s])
    return banks


def bank_name(bank: list[FoundString]) -> str:
    return f"bank_{bank[0].start:06X}"
