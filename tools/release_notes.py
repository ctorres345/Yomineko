#!/usr/bin/env python3
"""Release notes for a version tag, read from CHANGELOG.md, for the release workflow.

    python tools/release_notes.py v1.2.3    print the "## 1.2.3" section of the changelog

The tag must be ``v`` plus the package's ``__version__`` and the changelog must have a
section for it, so a tag pushed before the version bump fails before anything is published.
Exit code 0 = fine, 1 = the tag cannot be released. Standard library only.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "src" / "yomineko" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
VERSION = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)
NEW_BLOCK = re.compile(r"^(?:[-*+] |1[.)] |#{1,6} |>|\|)")  # what can interrupt a paragraph


class ReleaseError(Exception):
    """The tag does not match the package, or the changelog has no section for it.

    Not a YominekoError: this tool is standard library only and runs before the package is
    installed."""


def package_version(text: str) -> str:
    found = VERSION.search(text)
    if not found:
        raise ReleaseError("no __version__ in src/yomineko/__init__.py")
    return found.group(1)


def section(changelog: str, version: str) -> str:
    """The body of the ``## <version>`` section (a date may follow the version), trimmed."""
    heading = re.compile(rf"^## {re.escape(version)}(?: \(.*\))?[ \t]*$", re.MULTILINE)
    found = heading.search(changelog)
    if not found:
        raise ReleaseError(f"CHANGELOG.md has no '## {version}' section")
    following = re.compile(r"^## ", re.MULTILINE).search(changelog, found.end())
    body = changelog[found.end() : following.start() if following else len(changelog)].strip()
    if not body:
        raise ReleaseError(f"the '## {version}' section of CHANGELOG.md is empty")
    return body


def unwrap(body: str) -> str:
    """Join the changelog's hard-wrapped lines: GitHub shows each line break of a release body.

    A line continues the one before it unless either is blank, it starts a new block (a list
    item, heading, quote, table row or code fence) or the one before it is a heading. Code
    blocks are left alone."""
    out: list[str] = []
    in_code = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        joins = (
            not in_code
            and out
            and stripped
            and out[-1].strip()
            and not out[-1].lstrip().startswith(("#", "```"))
            and not NEW_BLOCK.match(stripped)
        )
        if joins:
            out[-1] = f"{out[-1].rstrip()} {stripped}"
        else:
            out.append(line)
    return "\n".join(out)


def notes(tag: str, version_text: str, changelog: str) -> str:
    version = package_version(version_text)
    if tag != f"v{version}":
        raise ReleaseError(
            f"tag {tag} does not match the package version {version} (expected v{version})"
        )
    return unwrap(section(changelog, version))


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0].startswith("-"):
        print(__doc__, file=sys.stderr)
        return 1
    try:
        body = notes(
            argv[0], VERSION_FILE.read_text(encoding="utf-8"), CHANGELOG.read_text(encoding="utf-8")
        )
    except ReleaseError as e:
        print(f"cannot release: {e}", file=sys.stderr)
        return 1
    if isinstance(sys.stdout, io.TextIOWrapper):  # the notes may hold Japanese; a Windows
        sys.stdout.reconfigure(encoding="utf-8")  # console's code page may not
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
