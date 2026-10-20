"""Load a ROM dump into memory. This module never unpacks or writes it to disk.

One exception outside this module: the web interface's server keeps an upload larger than
1 MB in a temporary file while the request is read, and deletes it when the answer is sent.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from yomineko.core.rom import gb, gba
from yomineko.errors import YominekoError

MAX_ROM_SIZE = 32 * 1024 * 1024  # the largest GBA cartridge; Game Boy ones are smaller
ROM_SUFFIXES = (".gba", ".agb", ".gbc", ".gb", ".bin")


class RomError(YominekoError):
    """The file is not a usable ROM dump."""


@dataclass(frozen=True)
class Rom:
    data: bytes
    sha1: str
    platform: str  # "gba", "gbc", or "gb" for a cartridge without Game Boy Color support
    title: str
    game_code: str  # empty on older Game Boy cartridges
    revision: int
    japanese: bool  # the header says it is a Japanese release
    source: str  # file name it came from (for messages)

    def __len__(self) -> int:
        return len(self.data)


def _read_header(data: bytes) -> tuple[str, gba.GbaHeader | gb.GbHeader] | None:
    """The platform and header of a dump. Each header can match the other console's ROM by
    chance (one fixed byte for GBA, a one-byte checksum for Game Boy). Where both match, it
    is GBA when the GBA checksum is right or the ROM begins the way a GBA ROM must, so a
    damaged checksum on either side does not change the console."""
    if gba.looks_like_gba(data):
        header = gba.parse_header(data)
        if header.checksum_ok or gba.starts_with_a_branch(data) or not gb.looks_like_gb(data):
            return "gba", header
    if gb.looks_like_gb(data):
        gb_header = gb.parse_header(data)
        return ("gbc" if gb_header.color else "gb"), gb_header
    return None


def rom_from_bytes(data: bytes, source: str = "<memory>") -> Rom:
    if len(data) > MAX_ROM_SIZE:
        raise RomError(f"{source}: larger than the {MAX_ROM_SIZE >> 20} MiB a ROM can be")
    found = _read_header(data)
    if found is None:
        raise RomError(
            f"{source}: not a GBA or Game Boy ROM: the cartridge header is missing or damaged"
        )
    platform, header = found
    return Rom(
        data=data,
        sha1=hashlib.sha1(data).hexdigest(),
        platform=platform,
        title=header.title,
        game_code=header.game_code,
        revision=header.revision,
        japanese=header.japanese,
        source=source,
    )


def _read_zip(source: str | Path | BinaryIO, name: str) -> tuple[bytes, str]:
    try:
        with zipfile.ZipFile(source) as zf:
            members = [
                i
                for i in zf.infolist()
                if not i.is_dir() and i.filename.lower().endswith(ROM_SUFFIXES)
            ]
            if len(members) != 1:
                raise RomError(
                    f"{name}: expected exactly one ROM inside the zip, found {len(members)}"
                )
            info = members[0]
            with zf.open(info) as f:  # bounded read: never trust the declared size
                data = f.read(MAX_ROM_SIZE + 1)
            return data, f"{name}:{info.filename}"
    except (zipfile.BadZipFile, zlib.error, EOFError) as e:
        raise RomError(f"{name}: not a valid zip file") from e
    except (RuntimeError, NotImplementedError) as e:  # a password, or an unknown compression
        raise RomError(
            f"{name}: the zip is password-protected or packed in a way yomineko cannot read. "
            "Unzip it and pick the ROM inside."
        ) from e


def load_rom(path: str | Path) -> Rom:
    """Read a ROM file (``.gba``, ``.gbc``, ``.gb``), or a ``.zip`` holding exactly one ROM."""
    path = Path(path)
    if not path.is_file():
        raise RomError(f"{path}: no such file")
    if path.suffix.lower() == ".zip":
        data, source = _read_zip(path, path.name)
    else:
        if path.stat().st_size > MAX_ROM_SIZE:
            raise RomError(f"{path.name}: larger than {MAX_ROM_SIZE >> 20} MiB, not a ROM")
        data, source = path.read_bytes(), path.name
    return rom_from_bytes(data, source)


def load_rom_bytes(data: bytes, name: str) -> Rom:
    """A ROM already in memory (an upload): the raw dump, or a zip holding exactly one ROM.
    ``name`` is the file name, used in messages."""
    if data[:4] == b"PK\x03\x04":  # a zip file starts with this signature
        data, name = _read_zip(io.BytesIO(data), name)
    return rom_from_bytes(data, name)
