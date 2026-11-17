"""Restrict the API to requests addressed to, and sent from, this machine.

The API has no authentication and serves transcripts (personal data), so other web pages
open in the same browser must not reach it:

- **Host check** blocks DNS rebinding: a hostile domain re-pointed at 127.0.0.1 still sends
  its own name in the ``Host`` header.
- **Origin check** blocks cross-site requests, including hijacking the
  ``/api/v1/voice-turn`` WebSocket (browsers apply no CORS to WebSockets) and "simple"
  cross-site POSTs such as form uploads. Requests without ``Origin`` (curl, scripts,
  same-origin GETs) pass: a hostile page can't send those from the victim's browser.

Both checks run for HTTP and WebSocket scopes. Extra hostnames come from
``TRANSCIBIO_ALLOWED_HOSTS`` (see ``config.parse_allowed_hosts``).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# RFC 6455 "policy violation"; closing before accept makes the server answer HTTP 403.
_WS_POLICY_VIOLATION = 1008


def _hostname(url: str) -> str | None:
    """Lower-cased hostname without port or IPv6 brackets; None if absent or malformed."""
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, *, allowed_hosts: tuple[str, ...]) -> None:
        self.app = app
        self.allowed_hosts = frozenset(allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        rejection = (
            self._rejection(Headers(scope=scope))
            if scope["type"] in ("http", "websocket")
            else None
        )
        if rejection is None:
            await self.app(scope, receive, send)
        elif scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": _WS_POLICY_VIOLATION})
        else:
            status_code, reason = rejection
            await PlainTextResponse(reason, status_code=status_code)(scope, receive, send)

    def _rejection(self, headers: Headers) -> tuple[int, str] | None:
        if _hostname(f"//{headers.get('host', '')}") not in self.allowed_hosts:
            return 400, "Invalid host header"
        origin = headers.get("origin")
        if origin is not None and _hostname(origin) not in self.allowed_hosts:
            return 403, "Cross-origin request rejected"
        return None
