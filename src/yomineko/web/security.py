"""Keep other web pages, and other computers, away from the local server.

The server can read ROMs and write files, so a page open in the same browser must not be able to
make it act. Four rules:

- it only listens on 127.0.0.1 (see ``server.py``);
- ``Host`` must be localhost or an IP loopback address, which defeats DNS rebinding (a hostile site
  pointing its own name at 127.0.0.1);
- a request that changes anything (not GET, HEAD or OPTIONS) must carry an ``Origin`` equal to the
  page it came from, and the per-run token in a ``SameSite=Strict`` cookie, which another site's
  forms cannot send;
- an upload larger than the biggest ROM is refused before it is read.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Awaitable, Callable
from typing import Final

from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

COOKIE: Final = "yomineko_token"
ALLOWED_HOSTS: Final = ["localhost", "127.0.0.1"]  # the server listens on 127.0.0.1 only
SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS"})
MAX_UPLOAD: Final = 33 * 1024 * 1024  # a 32 MiB ROM plus form overhead
HEADERS: Final = {
    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # not "no-referrer": browsers then send "Origin: null" on form posts, which the check refuses
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
}
# fonts and styles: kept, but checked against the server's ETag on each use, so a page does not
# download 5 MB of fonts again and a newer version's files are never served stale
STATIC_CACHE: Final = "no-cache"

Call = Callable[[Request], Awaitable[Response]]


def new_token() -> str:
    return secrets.token_urlsafe(32)


def refusal(request: Request, token: str) -> str | None:
    """Why a request must be refused, or ``None`` if it may go ahead."""
    if request.method in SAFE_METHODS:
        return None
    origin = request.headers.get("origin")
    if not origin or URL(origin).netloc != request.headers.get("host"):
        return "refused: the request did not come from this page (Origin)"
    if not hmac.compare_digest(request.cookies.get(COOKIE, ""), token):
        return "refused: reload the page and try again (token)"
    length = request.headers.get("content-length")
    if length is None or not length.isdigit():
        return "refused: the upload has no declared size"
    if int(length) > MAX_UPLOAD:
        return f"refused: larger than {MAX_UPLOAD >> 20} MiB, more than any ROM"
    return None


def guard(token: str) -> Callable[[Request, Call], Awaitable[Response]]:
    """A middleware function enforcing the rules above and adding the security headers."""

    async def middleware(request: Request, call_next: Call) -> Response:
        why = refusal(request, token)
        response: Response = (
            PlainTextResponse(why, status_code=403) if why else await call_next(request)
        )
        for name, value in HEADERS.items():
            response.headers[name] = value
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = STATIC_CACHE
        if request.cookies.get(COOKIE) != token:
            response.set_cookie(COOKIE, token, httponly=True, samesite="strict")
        return response

    return middleware
