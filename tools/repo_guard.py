#!/usr/bin/env python3
"""Keep ROMs, archives, decks and dumped game scripts out of the repo.

Fails when a file
  (a) has a ROM/archive/deck extension, or
  (b) outside tests/ has more than MAX_JP_LINES lines that each contain a
      run of MIN_JP_RUN or more Japanese characters (a kana table passes, a script dump
      does not).

Modes:
  --all              every tracked file (CI)
  --staged           files added or modified in the index (pre-commit)
  --hook             read a Claude Code hook payload on stdin; check the file being written
  PATH [PATH ...]    explicit files

Exit code 0 = clean, 2 = violation (2 is what Claude Code hooks treat as "block").
Standard library only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

BLOCKED_EXT = {".gba", ".gbc", ".gb", ".nds", ".iso", ".cso", ".zip", ".7z", ".rar", ".apkg"}
EXEMPT_DIRS = ("tests/",)
MIN_JP_RUN = 10
MAX_JP_LINES = 5
JP_RUN = re.compile(f"[぀-ヿ一-鿿ｦ-ﾟ]{{{MIN_JP_RUN},}}")


def check_path(path: str) -> str | None:
    ext = PurePosixPath(path.replace("\\", "/")).suffix.lower()
    if ext in BLOCKED_EXT:
        return f"{path}: files of type {ext} (ROMs, archives, decks) must never be committed"
    return None


def check_text(path: str, text: str) -> str | None:
    norm = path.replace("\\", "/")
    if any(norm.startswith(d) or f"/{d}" in norm for d in EXEMPT_DIRS):
        return None
    lines = sum(1 for line in text.splitlines() if JP_RUN.search(line))
    if lines > MAX_JP_LINES:
        return (
            f"{path}: {lines} lines with {MIN_JP_RUN}+ consecutive Japanese characters; "
            "this looks like game text. Only tests/ (synthetic text) may hold that much."
        )
    return None


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def check_blob(path: str, data: bytes) -> list[str]:
    problems = []
    p = check_path(path)
    if p:
        problems.append(p)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return problems
    p = check_text(path, text)
    if p:
        problems.append(p)
    return problems


def run_files(paths: list[str], from_index: bool) -> list[str]:
    problems: list[str] = []
    for path in paths:
        try:
            data = git("show", f":{path}") if from_index else Path(path).read_bytes()
        except (OSError, subprocess.CalledProcessError):
            data = b""
        problems += check_blob(path, data)
    return problems


def run_hook() -> list[str]:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return []
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    if not path:
        return []
    content = tool_input.get("content") or tool_input.get("new_string") or ""
    problems = []
    p = check_path(path)
    if p:
        problems.append(p)
    p = check_text(_relative(path), content)
    if p:
        problems.append(p)
    return problems


def _relative(path: str) -> str:
    """Make an absolute path repo-relative so the exempt-directory check works."""
    norm = path.replace("\\", "/")
    for marker in ("/tests/",):
        if marker in norm:
            return norm[norm.index(marker) + 1 :]
    return norm


def main(argv: list[str]) -> int:
    if "--hook" in argv:
        problems = run_hook()
    elif "--all" in argv:
        files = git("ls-files", "-z").decode("utf-8").split("\0")
        problems = run_files([f for f in files if f], from_index=False)
    elif "--staged" in argv:
        out = git("diff", "--cached", "--name-only", "--diff-filter=AM", "-z")
        problems = run_files([f for f in out.decode("utf-8").split("\0") if f], from_index=True)
    else:
        problems = run_files([a for a in argv if not a.startswith("--")], from_index=False)
    for p in problems:
        print("repo_guard: " + p, file=sys.stderr)
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
