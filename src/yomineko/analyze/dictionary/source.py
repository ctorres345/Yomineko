"""Download JMdict. This is the only module in yomineko that touches the network.

It runs only when the user asks (``yomineko dict download``). The download is HTTPS only, has a
timeout and a size cap, and is written to a temporary file that is renamed on success, so an
interrupted download never leaves a half file where the real one should be.
"""

from __future__ import annotations

import email.utils
import os
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import certifi

from yomineko import __version__
from yomineko.analyze.dictionary.xml_parser import DictionaryError

DEFAULT_URL = "https://www.edrdg.org/pub/Nihongo/JMdict_e.gz"
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024  # the file is about 11 MB today
TIMEOUT_SECONDS = 30.0
CHUNK = 1 << 16


@dataclass(frozen=True)
class Downloaded:
    path: Path
    date: str  # YYYY-MM-DD from the server's Last-Modified header, else today (UTC)
    size: int


def _date_from(headers: Any) -> str:
    value = headers.get("Last-Modified") if headers is not None else None
    if value:
        try:
            return email.utils.parsedate_to_datetime(value).date().isoformat()
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc).date().isoformat()


def ssl_context() -> ssl.SSLContext:
    """The system's trusted certificates plus certifi's. A packaged app's Python looks for the
    system ones where they were on the build machine, which on a user's Mac is nowhere, and
    python.org's macOS Python has none until "Install Certificates" is run. Without certifi's the
    download fails there with CERTIFICATE_VERIFY_FAILED."""
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context


def _urlopen(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())


def download_jmdict(
    dest: Path,
    *,
    url: str = DEFAULT_URL,
    urlopen: Callable[..., Any] | None = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    timeout: float = TIMEOUT_SECONDS,
) -> Downloaded:
    """Download ``url`` to ``dest``. ``urlopen`` can be replaced (tests do)."""
    opener = urlopen or _urlopen
    if not url.lower().startswith("https://"):
        raise DictionaryError(f"refusing to download over an insecure connection: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": f"yomineko/{__version__}"})
    try:
        with opener(request, timeout=timeout) as response:
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise DictionaryError(f"the file at {url} is larger than {max_bytes >> 20} MiB")
            date = _date_from(response.headers)
            size = 0
            with open(part, "wb") as out:
                while chunk := response.read(CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise DictionaryError(f"the download exceeded {max_bytes >> 20} MiB")
                    out.write(chunk)
        if size == 0:
            raise DictionaryError(f"the server sent an empty file from {url}")
        os.replace(part, dest)
        return Downloaded(dest, date, size)
    except urllib.error.HTTPError as e:
        raise DictionaryError(f"the server answered HTTP {e.code} for {url}") from e
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise DictionaryError(f"could not download {url}: {reason}") from e
    finally:
        part.unlink(missing_ok=True)
