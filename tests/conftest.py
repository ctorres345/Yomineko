"""Shared fixtures: synthetic ROMs and their profiles."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from support.synthrom import (
    Manifest,
    build_gbc_rom,
    build_lz16_rom,
    build_sjis_rom,
    build_table8_rom,
    build_tbl_rom,
)

DATA = Path(__file__).parent / "data"
PROFILES = DATA / "profiles"


@dataclass
class Synth:
    rom: bytes
    manifest: Manifest
    profile_path: Path

    @property
    def sha1(self) -> str:
        return hashlib.sha1(self.rom).hexdigest()

    @property
    def profile_data(self) -> dict:
        return yaml.safe_load(self.profile_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def sjis_rom() -> Synth:
    rom, manifest = build_sjis_rom()
    return Synth(rom, manifest, PROFILES / "synth-sjis.yaml")


@pytest.fixture(scope="session")
def tbl_rom() -> Synth:
    rom, manifest = build_tbl_rom()
    return Synth(rom, manifest, PROFILES / "synth-tbl.yaml")


@pytest.fixture(scope="session")
def lz16_rom() -> Synth:
    rom, manifest = build_lz16_rom()
    return Synth(rom, manifest, PROFILES / "synth-lz16.yaml")


@pytest.fixture(scope="session")
def table8_rom() -> Synth:
    rom, manifest = build_table8_rom()
    return Synth(rom, manifest, PROFILES / "synth-table8.yaml")


@pytest.fixture(scope="session")
def gbc_rom() -> Synth:
    rom, manifest = build_gbc_rom()
    return Synth(rom, manifest, PROFILES / "synth-gbc.yaml")


@pytest.fixture
def write_rom(tmp_path):
    """Write ROM bytes to a temporary .gba file and return its path."""

    def _write(rom: bytes, name: str = "game.gba") -> Path:
        path = tmp_path / name
        path.write_bytes(rom)
        return path

    return _write


@pytest.fixture
def mini_index(tmp_path):
    """An index of the invented mini JMdict, built in a temporary folder."""
    from support.dictionary import MINI_XML

    from yomineko.analyze.dictionary.store import build_index
    from yomineko.analyze.dictionary.xml_parser import parse_entries

    path = tmp_path / "index" / "jmdict.sqlite"
    with open(MINI_XML, "rb") as stream:
        build_index(parse_entries(stream), path, {"dictionary_date": "2026-01-02"})
    return path


@pytest.fixture
def mini_dict(mini_index):
    from yomineko.analyze.dictionary.store import Dictionary

    with Dictionary(mini_index) as dictionary:
        yield dictionary
