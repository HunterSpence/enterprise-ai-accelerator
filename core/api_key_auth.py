"""
api_key_auth.py — Shared, fail-closed API-key gate for every EAA REST surface.

Each FastAPI app mounts ``api_key_dependency()`` as an app-level dependency.
Health, docs, and OpenAPI paths are exempt so liveness probes and the docs page
stay reachable without a credential.

Secure-by-default behaviour (this is the whole point of the module):
  - ``EAA_DEV_MODE=true``           -> auth bypassed. Local demos only; never set
                                       this in a deployed image.
  - ``EAA_API_KEY`` set             -> business routes require a matching
                                       ``X-API-Key`` header (constant-time compare).
  - neither set                     -> business routes return 503. The server
                                       refuses to expose an unauthenticated
                                       surface rather than silently running open.

There is deliberately no default key. A shipped default credential is worse than
no credential, because operators forget to change it.
"""

# NOTE: intentionally NO `from __future__ import annotations` here. FastAPI
# resolves the dependency's parameter annotations via get_type_hints against this
# module's globals, so `Request` must be a real module-level name at runtime — a
# stringized annotation pointing at a locally-imported symbol makes FastAPI treat
# `request` as a query parameter and every route 422s.

import hmac
import os

from fastapi import Header, HTTPException, WebSocketException
from starlette.requests import HTTPConnection

_EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")


def _dev_mode() -> bool:
    return os.environ.get("EAA_DEV_MODE", "").strip().lower() in ("true", "1", "yes")


def _configured_key() -> str | None:
    key = os.environ.get("EAA_API_KEY", "").strip()
    return key or None


def _decide(path: str, provided: str, *, dev_mode: bool, configured: str | None) -> int:
    """Pure auth decision. Returns an HTTP status: 200 allow, 401 bad key, 503 unconfigured.

    Separated from the FastAPI dependency so the security logic is unit-testable
    without an app/Request. ``provided`` is the caller's X-API-Key header ("" if absent).
    """
    if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
        return 200
    if dev_mode:
        return 200
    if configured is None:
        return 503
    if provided and hmac.compare_digest(provided, configured):
        return 200
    return 401


def api_key_dependency():
    """Build the FastAPI dependency. Call at app-construction time::

        app = FastAPI(dependencies=[Depends(api_key_dependency())])

    Uses ``HTTPConnection`` (the common base of Request and WebSocket) so the
    same app-level gate works for both HTTP routes and WebSocket routes — a
    ``Request``-typed dependency would crash every WebSocket connection.
    """

    async def _dep(conn: HTTPConnection, x_api_key: str = Header(default="")) -> None:
        code = _decide(
            conn.url.path,
            x_api_key,
            dev_mode=_dev_mode(),
            configured=_configured_key(),
        )
        if code == 200:
            return
        if conn.scope.get("type") == "websocket":
            # HTTPException isn't valid on a WS handshake; close with a policy code.
            raise WebSocketException(code=1008, reason="Authentication required")
        detail = (
            "Server auth is not configured. Set EAA_API_KEY, or "
            "EAA_DEV_MODE=true for local demos."
            if code == 503
            else "Invalid or missing X-API-Key header"
        )
        raise HTTPException(status_code=code, detail=detail)

    return _dep


def _selftest() -> None:
    # Exempt paths are always open.
    assert _decide("/health", "", dev_mode=False, configured=None) == 200
    assert _decide("/openapi.json", "", dev_mode=False, configured="k") == 200
    # Fail-closed: no key configured, not dev -> 503, never open.
    assert _decide("/scan", "", dev_mode=False, configured=None) == 503
    assert _decide("/scan", "anything", dev_mode=False, configured=None) == 503
    # Dev mode bypasses everything.
    assert _decide("/scan", "", dev_mode=True, configured=None) == 200
    # Configured key: correct allows, wrong/missing 401s.
    assert _decide("/scan", "secret", dev_mode=False, configured="secret") == 200
    assert _decide("/scan", "wrong", dev_mode=False, configured="secret") == 401
    assert _decide("/scan", "", dev_mode=False, configured="secret") == 401
    print("api_key_auth self-test passed")


if __name__ == "__main__":
    _selftest()
