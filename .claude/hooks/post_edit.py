#!/usr/bin/env python3
"""PostToolUse hook: after a Python file is written, run ruff on it and the fast tests.

Reads the hook payload on stdin. Exits 2 with the tool output on stderr when something
fails, so Claude sees it. Does nothing if the project venv does not exist yet.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def venv_python() -> Path | None:
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        p = ROOT / rel
        if p.exists():
            return p
    return None


def run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
    return r.returncode, (r.stdout + r.stderr).strip()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    path = (payload.get("tool_input") or {}).get("file_path") or ""
    norm = path.replace("\\", "/")
    if not norm.endswith(".py"):
        return 0
    py = venv_python()
    if py is None:
        return 0
    failures = []
    code, out = run([str(py), "-m", "ruff", "check", path])
    if code != 0 and "No module named ruff" not in out:
        failures.append("ruff:\n" + out)
    if "/src/" in norm or "/tests/" in norm:
        code, out = run([str(py), "-m", "pytest", "-q", "-x", "-m", "not realrom"])
        # 5 = no tests collected yet; "No module named pytest" = dev extras not installed
        if code not in (0, 5) and "No module named pytest" not in out:
            failures.append("pytest:\n" + out[-3000:])
    if failures:
        print("\n\n".join(failures), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
