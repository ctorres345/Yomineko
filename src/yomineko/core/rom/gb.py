"""Game Boy and Game Boy Color cartridge header (0x134-0x14F of a ROM)."""

from __future__ import annotations

from dataclasses import dataclass

HEADER_END = 0x150
BANK_SIZE = 0x4000
CGB_FLAGS = (0x80, 0xC0)  # at 0x143: works on a Game Boy Color, or only on one
DESTINATION_JAPAN = 0x00  # at 0x14A


@dataclass(frozen=True)
class GbHeader:
    title: str
    game_code: str  # four characters on newer cartridges, empty on older ones
    color: bool  # the cartridge declares Game Boy Color support
    destination: int
    revision: int
    checksum_ok: bool  # the checksum over the whole ROM (0x14E); a bad one is not fatal

    @property
    def japanese(self) -> bool:
        """The code's last letter says the region; a cartridge without a code has only the
        destination byte."""
        if self.game_code:
            return self.game_code.endswith("J")
        return self.destination == DESTINATION_JAPAN


def bank_address(offset: int) -> int:
    """The address the console sees a file offset at. The first bank is always at 0x0000; any
    other is switched in at 0x4000, so the bank number is not part of the address:
    ``offset = bank * 0x4000 + (address - 0x4000)`` for bank 1 and up."""
    return offset if offset < BANK_SIZE else BANK_SIZE + offset % BANK_SIZE


def _header_checksum(data: bytes) -> int:
    x = 0
    for b in data[0x134:0x14D]:
        x = (x - b - 1) & 0xFF
    return x


def looks_like_gb(data: bytes) -> bool:
    """The console refuses a cartridge whose header checksum (0x14D) is wrong, so every
    working dump has a right one. An all-zero header also sums right and is not a ROM."""
    return (
        len(data) >= HEADER_END
        and len(data) % BANK_SIZE == 0
        and data[0x14D] == _header_checksum(data)
        and any(data[0x134:0x144])
    )


def _is_code(raw: bytes) -> bool:
    return all(0x30 <= b <= 0x39 or 0x41 <= b <= 0x5A for b in raw)


def parse_header(data: bytes) -> GbHeader:
    if not looks_like_gb(data):
        raise ValueError("not a Game Boy ROM: header is missing or damaged")

    def ascii_field(raw: bytes) -> str:
        return raw.split(b"\0", 1)[0].decode("ascii", errors="replace").strip()

    color = data[0x143] in CGB_FLAGS
    # newer cartridges keep an 11-byte title and a 4-character code; older ones use all
    # 15 or 16 bytes for the title. A 15-character title that ends in four capitals or digits
    # cannot be told from a title and a code, and is read as one
    has_code = color and _is_code(data[0x13F:0x143])
    if has_code:
        title, code = ascii_field(data[0x134:0x13F]), ascii_field(data[0x13F:0x143])
    else:
        title, code = ascii_field(data[0x134 : 0x143 if color else 0x144]), ""
    total = (sum(data) - data[0x14E] - data[0x14F]) & 0xFFFF
    return GbHeader(
        title=title,
        game_code=code,
        color=color,
        destination=data[0x14A],
        revision=data[0x14C],
        checksum_ok=(data[0x14E] << 8 | data[0x14F]) == total,
    )
