"""Words the learner marked "I know this", remembered on this computer for every game.

    <root>/known.json   {"jmdict_ids": [1000220, 1578850, ...]}

Only JMdict entry ids are stored, never game text (the same rule as review files), so one list
serves every game in the workspace. A missing or damaged file reads as no words marked, but a
change to a damaged file is refused rather than written over it. Changes are made under a lock and
written to a new file that then replaces the old one, so two clicks at once never lose the list.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterable
from pathlib import Path

from yomineko.errors import YominekoError
from yomineko.pipeline.workspace import Workspace

KNOWN_NAME = "known.json"

_lock = threading.Lock()  # the web server answers requests on several threads


def known_path(workspace: Workspace) -> Path:
    return workspace.root / KNOWN_NAME


def _read(path: Path) -> frozenset[int] | None:
    """The ids in the file; an empty set when there is no file, None when it is damaged."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return frozenset()
    except OSError:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    ids = data.get("jmdict_ids") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        return None
    return frozenset(i for i in ids if isinstance(i, int) and not isinstance(i, bool) and i > 0)


def load_known(workspace: Workspace) -> frozenset[int]:
    """The JMdict ids marked known; anything in the file that is not an id is ignored."""
    return _read(known_path(workspace)) or frozenset()


def _write(workspace: Workspace, ids: Iterable[int]) -> None:
    path = known_path(workspace)
    kept = sorted({int(i) for i in ids})
    if not kept:
        path.unlink(missing_ok=True)
        return
    workspace.root.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{KNOWN_NAME}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps({"jmdict_ids": kept}) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _change(workspace: Workspace, add: Iterable[int], remove: Iterable[int]) -> frozenset[int]:
    with _lock:
        path = known_path(workspace)
        current = _read(path)
        if current is None:
            raise YominekoError(
                f"{path} is damaged, so it was left as it is: fix or delete it, then try again."
            )
        known = (current | set(add)) - set(remove)
        _write(workspace, known)
        return known


def save_known(workspace: Workspace, ids: Iterable[int]) -> None:
    """Remember exactly ``ids`` (an empty list removes the file)."""
    with _lock:
        _write(workspace, ids)


def mark_known(workspace: Workspace, ids: Iterable[int]) -> frozenset[int]:
    """Add ``ids`` to the known words; the new set."""
    return _change(workspace, add=ids, remove=())


def unmark_known(workspace: Workspace, ids: Iterable[int]) -> frozenset[int]:
    """Take ``ids`` off the known words; the new set."""
    return _change(workspace, add=(), remove=ids)
