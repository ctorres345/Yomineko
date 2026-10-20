"""Install the dictionary (download, index) and report what is installed."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yomineko.analyze.dictionary.paths import data_dir, index_path
from yomineko.analyze.dictionary.source import DEFAULT_URL, download_jmdict
from yomineko.analyze.dictionary.store import (
    CREDIT,
    Dictionary,
    build_index_from_gzip,
)
from yomineko.analyze.dictionary.xml_parser import DictionaryError

MAX_XML_BYTES = 512 * 1024 * 1024  # the unpacked file is about 65 MB today


@dataclass(frozen=True)
class DictionaryInfo:
    path: Path
    entries: int
    date: str
    source: str
    credit: str


def dictionary_info(folder: Path | None = None) -> DictionaryInfo | None:
    """What is installed in ``folder`` (default: the user data folder), or ``None``."""
    path = index_path(folder)
    if not path.is_file():
        return None
    with Dictionary(path) as d:
        return DictionaryInfo(
            path=path,
            entries=len(d),
            date=d.meta.get("dictionary_date", "unknown"),
            source=d.meta.get("source_url", "unknown"),
            credit=d.meta.get("credit", CREDIT),
        )


def install_dictionary(
    *,
    url: str = DEFAULT_URL,
    folder: Path | None = None,
    urlopen: Callable[..., Any] | None = None,
) -> DictionaryInfo:
    """Download JMdict from ``url``, build the index, and delete the downloaded archive."""
    folder = folder or data_dir()
    archive = folder / "JMdict_e.gz"
    downloaded = download_jmdict(archive, url=url, urlopen=urlopen)
    try:
        build_index_from_gzip(
            archive,
            index_path(folder),
            meta={"dictionary_date": downloaded.date, "source_url": url, "credit": CREDIT},
            max_xml=MAX_XML_BYTES,
        )
    finally:
        archive.unlink(missing_ok=True)
    info = dictionary_info(folder)
    if info is None:  # pragma: no cover - the index was just written
        raise DictionaryError("the dictionary index was not created")
    return info
