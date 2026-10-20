"""Check that the web extra is installed, before anything imports it."""

from __future__ import annotations

import importlib.util

from yomineko.errors import MissingExtraError

PACKAGES = ("fastapi", "uvicorn", "jinja2", "multipart")


def require_web_extra() -> None:
    missing = [name for name in PACKAGES if importlib.util.find_spec(name) is None]
    if missing:
        raise MissingExtraError(
            "the web interface needs extra packages "
            f'({", ".join(missing)}). Install them with: pip install "yomineko[web]"'
        )
