"""Turn a transcription (code, character) into a ``.tbl`` the table8 and table16 codecs read."""

from __future__ import annotations

from pathlib import Path

HEX = frozenset("0123456789ABCDEF")


class TranscriptionError(ValueError):
    """A line of the transcription cannot be used."""


def read_transcription(path: Path) -> dict[str, str]:
    """``code<TAB>character`` per line (``#`` starts a comment): upper-case hex code to text."""
    mapping: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        code, sep, text = raw.partition("\t")
        code = code.strip().upper()
        if not sep or not text or len(code) not in (2, 4) or not set(code) <= HEX:
            raise TranscriptionError(f"{path}:{number}: expected 'HH<TAB>text' or 'HHHH<TAB>text'")
        if code in mapping:
            raise TranscriptionError(f"{path}:{number}: code {code} appears twice")
        mapping[code] = text
    return mapping


def build_table(mapping: dict[str, str], header: str = "") -> tuple[str, list[tuple[str, str]]]:
    """The table text and the aliases. A character already drawn by an earlier code is not listed
    twice (a table must map back uniquely): the later code is returned as an alias, for a ``plain``
    rule in the profile."""
    lines = [f"# {h}" for h in header.splitlines()] if header else []
    seen: dict[str, str] = {}
    aliases: list[tuple[str, str]] = []
    for code in sorted(mapping, key=lambda c: (len(c), c)):
        text = mapping[code]
        if text in seen:
            aliases.append((code, text))
            continue
        seen[text] = code
        lines.append(f"{code}={text}")
    return "\n".join(lines) + "\n", aliases


def write_table(mapping: dict[str, str], path: Path, header: str = "") -> list[tuple[str, str]]:
    text, aliases = build_table(mapping, header)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return aliases
