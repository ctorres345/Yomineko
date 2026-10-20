"""GBA cartridge header (the first 0xC0 bytes of a ROM)."""

from __future__ import annotations

from dataclasses import dataclass

HEADER_SIZE = 0xC0
FIXED_BYTE = 0x96  # constant at 0xB2 in every GBA header
BRANCH = 0xEA  # the ARM "branch always" instruction


@dataclass(frozen=True)
class GbaHeader:
    title: str
    game_code: str
    maker_code: str
    revision: int
    checksum_ok: bool

    @property
    def japanese(self) -> bool:
        """The last letter of the game code says the region."""
        return self.game_code.endswith("J")


def looks_like_gba(data: bytes) -> bool:
    return len(data) >= HEADER_SIZE and data[0xB2] == FIXED_BYTE


def starts_with_a_branch(data: bytes) -> bool:
    """A GBA ROM begins with an ARM branch to its start-up code (the top byte of the word)."""
    return len(data) >= 4 and data[3] == BRANCH


def parse_header(data: bytes) -> GbaHeader:
    if not looks_like_gba(data):
        raise ValueError("not a GBA ROM: header is missing or damaged")

    def ascii_field(raw: bytes) -> str:
        return raw.split(b"\0", 1)[0].decode("ascii", errors="replace").strip()

    expected = (-(sum(data[0xA0:0xBD]) + 0x19)) & 0xFF
    return GbaHeader(
        title=ascii_field(data[0xA0:0xAC]),
        game_code=ascii_field(data[0xAC:0xB0]),
        maker_code=ascii_field(data[0xB0:0xB2]),
        revision=data[0xBC],
        checksum_ok=data[0xBD] == expected,
    )
