"""Load and look up game profiles (data-only YAML, validated by the schema)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from yomineko.core.encodings.base import Codec
from yomineko.core.encodings.plain import make_plain
from yomineko.core.encodings.sjis import ShiftJISCodec
from yomineko.core.encodings.table8 import Table8Codec
from yomineko.core.encodings.table16 import Table16Codec
from yomineko.core.encodings.tbl import TableCodec
from yomineko.errors import YominekoError
from yomineko.profile.schema import Profile

ROM_STRING_MARKS = ("<", ">")  # around the text of a byte in encoding.rom_strings
ROM_STRING_LIMIT = 32  # longest such string, in bytes
# libyaml's loader when PyYAML was built with it: about ten times faster than the Python one
_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def load_yaml(text: str) -> Any:
    """``yaml.safe_load``, with libyaml when it is there. Raises ``yaml.YAMLError``."""
    return yaml.load(text, Loader=_YAML_LOADER)  # a safe loader either way


class ProfileError(YominekoError):
    """A profile file is missing, malformed or fails validation."""


@dataclass(frozen=True)
class LoadedProfile:
    profile: Profile
    path: Path | None  # table paths in the profile are relative to this file's folder

    def codec(self, rom: bytes | None = None) -> Codec:
        """The codec for this game. ``rom`` is needed by a profile that keeps part of its
        character table in the ROM (``encoding.rom_strings``)."""
        enc = self.profile.encoding
        if enc.type == "shift_jis":
            return ShiftJISCodec(enc.custom_leads, enc.terminator)
        base = self.path.parent if self.path else Path.cwd()
        if enc.type == "table16":
            return Table16Codec(base / str(enc.table))
        if enc.type == "table8":
            if enc.rom_strings and rom is None:
                raise ProfileError(
                    f"profile {self.profile.id!r} reads part of its character table from the "
                    "ROM: its codec cannot be built without one"
                )
            return self._table8(rom)
        return TableCodec(base / str(enc.table), enc.terminator)

    def check_table(self) -> None:
        """Load what can be checked without a ROM: the table file and the roles of its bytes."""
        if self.profile.encoding.type == "table8":
            self._table8(None)
        else:
            self.codec()

    def _table8(self, rom: bytes | None) -> Table8Codec:
        enc = self.profile.encoding
        base = self.path.parent if self.path else Path.cwd()
        args = (base / str(enc.table), enc.command_prefix, enc.commands, set(enc.line_breaks))
        codec = Table8Codec(*args)
        self._check_table8(codec)
        if rom is not None and enc.rom_strings:
            codec = Table8Codec(*args, self._rom_strings(codec, rom))
        return codec

    def _rom_strings(self, characters: Table8Codec, rom: bytes) -> dict[int, str]:
        """The text of each byte in ``encoding.rom_strings``: the string at its offset in
        ``rom``, read with the table's characters, between the marks."""
        enc = self.profile.encoding
        end = bytes([enc.terminator])
        texts: dict[int, str] = {}
        for byte, offset in enc.rom_strings.items():
            stop = rom.find(end, offset, offset + ROM_STRING_LIMIT)
            parsed = characters.parse(rom[offset:stop] + end, 0) if stop > offset else None
            # an escape in the text (a brace, a backslash, an unknown code) would not encode back
            if parsed is None or parsed[0] != stop - offset or set(parsed[1]) & set("{}" + chr(92)):
                raise ProfileError(
                    f"profile {self.profile.id!r}: no string of table characters at "
                    f"{offset:#x} for byte {byte:02X}. Is this the ROM the profile is for?"
                )
            texts[byte] = f"{ROM_STRING_MARKS[0]}{parsed[1]}{ROM_STRING_MARKS[1]}"
        return texts

    def _check_table8(self, codec: Table8Codec) -> None:
        """A byte that ends text must not also be a character of the table: the codec would
        read it as text, and nothing would ever end. Nor may the start command: every such
        character inside a text would be tried as the start of another. (The commands between
        two texts are not read as text, so they may share a value with a character.)"""
        roles: dict[int, str] = {}
        frame = self.profile.discover.frame
        if frame is not None:
            marks = [frame.start, *frame.breaks, *frame.ends]
            roles.update(dict.fromkeys(marks, "discover.frame"))
            if frame.resume is not None:
                roles[frame.resume] = "discover.frame"
        if self.profile.encoding.rom_strings or any(
            t.kind != "pointers" for t in self.profile.tables
        ):
            roles[self.profile.encoding.terminator] = "encoding.terminator"
        strings = self.profile.encoding.rom_strings  # these bytes are characters as well
        for byte in strings:
            if codec.starts_text(byte):
                raise ProfileError(
                    f"profile {self.profile.id!r}: byte {byte:02X} is in the table file and in "
                    "encoding.rom_strings; it can be one or the other"
                )
        for byte, where in roles.items():
            if byte in strings or codec.starts_text(byte):
                raise ProfileError(
                    f"profile {self.profile.id!r}: byte {byte:02X} is in the character table "
                    f"and in {where}; it can be one or the other"
                )

    def plain(self) -> Callable[[str], str]:
        return make_plain(self.profile)


def load_profile(path: str | Path) -> LoadedProfile:
    path = Path(path)
    try:
        data = load_yaml(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ProfileError(f"{path}: cannot read profile: {e}") from e
    except yaml.YAMLError as e:
        raise ProfileError(f"{path}: not valid YAML: {e}") from e
    try:
        profile = Profile.model_validate(data)
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
        )
        raise ProfileError(f"{path}: invalid profile: {problems}") from e
    return LoadedProfile(profile, path)


def packaged_profiles() -> list[LoadedProfile]:
    """The profiles shipped inside the package, sorted by id."""
    return list(_packaged_profiles())


@cache
def _packaged_profiles() -> tuple[LoadedProfile, ...]:
    """Read once: the packaged files do not change while the program runs."""
    folder = resources.files("yomineko.profiles")
    found = [
        load_profile(Path(str(item)))
        for item in folder.iterdir()
        if item.name.endswith((".yaml", ".yml"))
    ]
    return tuple(sorted(found, key=lambda p: p.profile.id))


def find_profile(sha1: str, extra: Iterable[LoadedProfile] = ()) -> LoadedProfile | None:
    """The profile whose ROM checksum is ``sha1``; ``extra`` (user-supplied) wins."""
    for loaded in [*extra, *packaged_profiles()]:
        if loaded.profile.rom.sha1 == sha1:
            return loaded
    return None


def resolve_profile(spec: str) -> LoadedProfile:
    """``spec`` is a path to a YAML file, or the id of a packaged profile."""
    if spec.lower().endswith((".yaml", ".yml")) or Path(spec).is_file():
        return load_profile(spec)
    for loaded in packaged_profiles():
        if loaded.profile.id == spec:
            return loaded
    ids = ", ".join(p.profile.id for p in packaged_profiles()) or "none"
    raise ProfileError(f"no profile named {spec!r} (packaged profiles: {ids})")
