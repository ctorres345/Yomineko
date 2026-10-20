"""Helpers for tests that need a dictionary: the invented mini JMdict and a fake network."""

from __future__ import annotations

import gzip
import io
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from support.synthrom import DATA_DIR

MINI_XML = DATA_DIR / "mini_jmdict.xml"
MINI_ENTRY_COUNT = 14
# ids of the entries that share the reading こと, in id order
KOTO_IDS = [9000001, 9000002, 9000003]


def mini_xml_bytes() -> bytes:
    return MINI_XML.read_bytes()


def mini_gz_bytes() -> bytes:
    return gzip.compress(mini_xml_bytes())


class FakeResponse:
    """What urlopen returns: a context manager with .headers and .read()."""

    def __init__(self, body: bytes, headers: Mapping[str, str] | None = None, fail_after: int = -1):
        self._body = io.BytesIO(body)
        self.headers: Mapping[str, str] = headers or {}
        self._fail_after = fail_after  # raise OSError once this many bytes were read
        self._read = 0

    def read(self, size: int = -1) -> bytes:
        if 0 <= self._fail_after <= self._read:
            raise OSError("connection reset")
        data = self._body.read(size)
        self._read += len(data)
        return data

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def fake_urlopen(
    body: bytes,
    headers: Mapping[str, str] | None = None,
    fail_after: int = -1,
) -> tuple[Callable[..., Any], list[tuple[Any, float]]]:
    """A urlopen replacement plus the list of (request, timeout) it was called with."""
    calls: list[tuple[Any, float]] = []

    def urlopen(request: Any, timeout: float = 0, context: Any = None) -> FakeResponse:
        calls.append((request, timeout))
        return FakeResponse(body, headers, fail_after)

    return urlopen, calls


def write_gz(path: Path, xml: bytes) -> Path:
    path.write_bytes(gzip.compress(xml))
    return path
