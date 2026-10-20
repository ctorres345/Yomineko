"""Where the downloaded dictionary lives.

Default: the per-user data folder (``%LOCALAPPDATA%\\yomineko`` on Windows,
``~/.local/share/yomineko`` on Linux, ``~/Library/Application Support/yomineko`` on macOS).
Set ``YOMINEKO_DATA_DIR`` to use another folder, for example in tests or on a shared drive.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

ENV_VAR = "YOMINEKO_DATA_DIR"
INDEX_NAME = "jmdict.sqlite"


def data_dir() -> Path:
    override = os.environ.get(ENV_VAR)
    return Path(override) if override else Path(user_data_dir("yomineko", appauthor=False))


def index_path(folder: Path | None = None) -> Path:
    return (folder or data_dir()) / INDEX_NAME
