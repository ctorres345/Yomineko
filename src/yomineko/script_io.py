"""Read and write script files (the canonical JSON that ``yomineko extract`` produces)."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from pydantic import ValidationError

from yomineko.errors import YominekoError
from yomineko.model import READABLE_VERSIONS, SCHEMA_VERSION, Script


class ScriptError(YominekoError):
    """A script file is missing, damaged, or from a different schema version."""


def write_script(script: Script, path: str | Path) -> Path:
    """Write through a temporary file, so a reader or a crash never sees half a script."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(script.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)
    return path


def read_script(path: str | Path) -> Script:
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise ScriptError(f"{path}: cannot read script file: {e.strerror or e}") from e
    try:  # the quick way, for a file of this version (less than half the time on a long script)
        return Script.model_validate_json(raw)
    except ValidationError:
        pass  # an older version or a damaged file: the steps below say which
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as e:  # json.JSONDecodeError and bad UTF-8 are both ValueErrors
        raise ScriptError(f"{path}: not a valid script file (not JSON): {e}") from e
    version = data.get("schema_version") if isinstance(data, dict) else None
    if version not in READABLE_VERSIONS:
        raise ScriptError(
            f"{path}: script schema version is {version!r}, but this yomineko reads "
            f"versions {READABLE_VERSIONS[0]} to {READABLE_VERSIONS[-1]}. "
            "Re-run `yomineko extract` with this version."
        )
    data["schema_version"] = SCHEMA_VERSION  # older files lack only fields that default
    try:
        return Script.model_validate(data)
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:5]
        )
        raise ScriptError(f"{path}: not a valid script file: {problems}") from e
