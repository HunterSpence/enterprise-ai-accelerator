"""
mcp_transports.py — Transport helpers for Enterprise AI Accelerator MCP 2.0
============================================================================

Provides ``run_stdio()``, ``run_sse()``, and ``run_streamable_http()`` so
``mcp_server.py`` can stay focused on the tool/resource/prompt surface without
coupling to transport wiring.

Streamable HTTP (RECOMMENDED — MCP spec 2025-03-26):
    Uses ``mcp.server.streamable_http_manager.StreamableHTTPSessionManager``
    mounted on a Starlette app.  Endpoint: ``/mcp``.

SSE transport (LEGACY — superseded by streamable-http, MCP spec 2025-03-26):
    Uses ``mcp.server.sse.SseServerTransport`` mounted at ``/sse`` + ``/messages``.

stdio is unchanged and remains the default for local Claude Code / Claude Desktop.

Auth (MCP07):
    Set ``EAA_MCP_AUTH_TOKEN`` in the environment to enable bearer-token auth on
    both network transports.  Requests without a matching ``Authorization: Bearer
    <token>`` header receive HTTP 401.  stdio is always exempt.
    Comparison is constant-time to prevent timing attacks.

Audit (MCP08):
    Set ``EAA_MCP_AUDIT=1`` (default ON) to log every tool call to the
    platform's Merkle audit chain.  Set ``EAA_MCP_AUDIT=0`` to opt out.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import os
import time
import warnings
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server import Server

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Startup timestamp for /health uptime_s
# ---------------------------------------------------------------------------

_START_TIME: float = time.monotonic()


def _reset_start_time() -> None:
    """Called once at server startup so uptime_s is accurate."""
    global _START_TIME
    _START_TIME = time.monotonic()


# ---------------------------------------------------------------------------
# Auth helpers (MCP07)
# ---------------------------------------------------------------------------

_AUTH_TOKEN: str | None = os.environ.get("EAA_MCP_AUTH_TOKEN") or None


def _check_bearer(authorization: str | None) -> bool:
    """Constant-time bearer token comparison. Returns True if auth passes."""
    if _AUTH_TOKEN is None:
        return True  # auth not configured — open
    if not authorization:
        return False
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    # hmac.compare_digest prevents timing attacks
    return hmac.compare_digest(parts[1].encode(), _AUTH_TOKEN.encode())


def _make_auth_middleware():
    """Return a Starlette middleware class that enforces bearer auth."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    class BearerAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Health endpoint is always open — clients need it for liveness probes
            if request.url.path == "/health":
                return await call_next(request)
            if not _check_bearer(request.headers.get("authorization")):
                return JSONResponse(
                    {"error": "Unauthorized", "hint": "Provide Authorization: Bearer <EAA_MCP_AUTH_TOKEN>"},
                    status_code=401,
                )
            return await call_next(request)

    return BearerAuthMiddleware


# ---------------------------------------------------------------------------
# Tool audit logging (MCP08)
# ---------------------------------------------------------------------------

_AUDIT_ENABLED: bool = os.environ.get("EAA_MCP_AUDIT", "1") != "0"
_MCP_AUDIT_CHAIN = None  # lazy AuditChain for mcp-tool calls


def _get_mcp_audit_chain():
    """Lazily initialize a dedicated AuditChain for MCP tool-call audit logs."""
    global _MCP_AUDIT_CHAIN
    if _MCP_AUDIT_CHAIN is None:
        audit_dir = os.path.join(os.getcwd(), ".eaa_audit")
        os.makedirs(audit_dir, exist_ok=True)
        from ai_audit_trail.chain import AuditChain
        _MCP_AUDIT_CHAIN = AuditChain(
            db_path=os.path.join(audit_dir, "mcp_tools.db"),
            store_plaintext=False,
        )
    return _MCP_AUDIT_CHAIN


def audit_tool_call(tool_name: str, args: dict[str, Any], result: Any, error: str | None, start_ms: float) -> None:
    """Append a tool-invocation record to the Merkle audit chain.

    Fail-open: any exception here is logged as a warning and swallowed so it
    never propagates back to the caller.
    """
    if not _AUDIT_ENABLED:
        return
    duration_ms = (time.monotonic() * 1000) - start_ms
    try:
        args_json = json.dumps(args, sort_keys=True, default=str)
        args_sha256 = hashlib.sha256(args_json.encode()).hexdigest()
        status = "error" if error else "success"
        output_summary = f"status={status} duration_ms={duration_ms:.1f}"
        if error:
            output_summary += f" error={error[:200]}"
        chain = _get_mcp_audit_chain()
        chain.append(
            session_id="mcp-server",
            model="mcp-tool",
            input_text=f"tool={tool_name} args_sha256={args_sha256}",
            output_text=output_summary,
            input_tokens=0,
            output_tokens=0,
            latency_ms=duration_ms,
            decision_type="TOOL_USE",
            risk_tier="LIMITED",
            system_id="mcp-tool-audit",
            metadata={
                "tool": tool_name,
                "args_sha256": args_sha256,
                "status": status,
                "duration_ms": round(duration_ms, 1),
            },
        )
    except Exception as exc:  # noqa: BLE001
        warnings.warn(f"[EAA audit] chain write failed for tool={tool_name}: {exc}", stacklevel=2)


# ---------------------------------------------------------------------------
# Input validation (MCP03/05)
# ---------------------------------------------------------------------------

_PATH_TRAVERSAL_SEQS = ["..", "~", "%2e", "%2f", "//", "\\"]


def validate_tool_args(tool_name: str, args: dict[str, Any]) -> str | None:
    """
    Validate args before dispatch. Returns an error string or None if valid.

    Checks:
    - Path-like string args must not contain traversal sequences.
    - Enum-typed args validated against allowed values (from _TOOLS inputSchema).
    - Numeric bounds checked where schema specifies minimum/maximum.
    """
    from mcp_server import _TOOLS  # lazy to avoid import cycle

    schema = next((t.inputSchema for t in _TOOLS if t.name == tool_name), None)
    if schema is None:
        return None  # unknown tool — dispatch handles it

    props = schema.get("properties", {})
    for key, val in args.items():
        prop_schema = props.get(key, {})
        prop_type = prop_schema.get("type")

        # Path traversal check on string values that look path-like
        if isinstance(val, str) and (
            "path" in key.lower() or "dir" in key.lower() or "file" in key.lower()
        ):
            lower_val = val.lower()
            for seq in _PATH_TRAVERSAL_SEQS:
                if seq in lower_val:
                    return f"Argument '{key}' contains forbidden path sequence '{seq}'"

        # Enum validation
        allowed = prop_schema.get("enum")
        if allowed is not None and val not in allowed:
            return f"Argument '{key}' must be one of {allowed}, got {val!r}"

        # Numeric bounds
        if prop_type in ("integer", "number") and isinstance(val, (int, float)):
            if "minimum" in prop_schema and val < prop_schema["minimum"]:
                return f"Argument '{key}' must be >= {prop_schema['minimum']}, got {val}"
            if "maximum" in prop_schema and val > prop_schema["maximum"]:
                return f"Argument '{key}' must be <= {prop_schema['maximum']}, got {val}"

    return None


# ---------------------------------------------------------------------------
# Health endpoint builder (shared by both network transports)
# ---------------------------------------------------------------------------

def _build_health_handler(active_transports: list[str]):
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    async def health(request: Request) -> JSONResponse:
        from mcp_server import _TOOLS, _RESOURCES, _PROMPTS
        return JSONResponse({
            "status": "ok",
            "tools": len(_TOOLS),
            "resources": len(_RESOURCES),
            "prompts": len(_PROMPTS),
            "transports": active_transports,
            "auth_enabled": _AUTH_TOKEN is not None,
            "audit_enabled": _AUDIT_ENABLED,
            "uptime_s": round(time.monotonic() - _START_TIME, 1),
        })

    return health


# ---------------------------------------------------------------------------
# stdio
# ---------------------------------------------------------------------------

async def run_stdio(server: "Server") -> None:
    """Run the MCP server over stdio (default transport, unchanged)."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# ---------------------------------------------------------------------------
# Streamable HTTP (RECOMMENDED — MCP spec 2025-03-26)
# ---------------------------------------------------------------------------

async def run_streamable_http(
    server: "Server",
    host: str = "0.0.0.0",
    port: int = 8765,
) -> None:
    """Run the MCP server over Streamable HTTP (recommended network transport).

    Mounts the MCP endpoint at ``/mcp``.  A ``GET /health`` route returns
    liveness metadata including ``transports: ["streamable-http"]``.

    Client configuration (Claude Desktop / Claude Code streamable-http):

        {
          "mcpServers": {
            "enterprise-ai-accelerator": {
              "url": "http://localhost:8765/mcp",
              "transport": "streamable-http"
            }
          }
        }

    Auth: set ``EAA_MCP_AUTH_TOKEN`` to require ``Authorization: Bearer <token>``.
    Audit: set ``EAA_MCP_AUDIT=0`` to disable per-call Merkle chain logging.
    """
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    _reset_start_time()

    session_manager = StreamableHTTPSessionManager(app=server, stateless=False)

    async def handle_mcp(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            yield

    health = _build_health_handler(["streamable-http"])

    routes = [
        Route("/health", health, methods=["GET"]),
        Mount("/mcp", app=handle_mcp),
    ]

    app = Starlette(routes=routes, lifespan=lifespan)

    if _AUTH_TOKEN is not None:
        middleware_cls = _make_auth_middleware()
        from starlette.middleware import Middleware
        app.add_middleware(middleware_cls)

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    srv = uvicorn.Server(config)
    await srv.serve()


# ---------------------------------------------------------------------------
# SSE (LEGACY — superseded by streamable-http, MCP spec 2025-03-26)
# ---------------------------------------------------------------------------

async def run_sse(
    server: "Server",
    host: str = "0.0.0.0",
    port: int = 8765,
) -> None:
    """Run the MCP server over SSE (legacy HTTP transport).

    Mounts the MCP SSE endpoint at ``/sse`` and the POST message endpoint at
    ``/messages``.  A ``GET /health`` route returns liveness metadata.

    .. deprecated::
        SSE transport is superseded by streamable-http (MCP spec 2025-03-26).
        Use ``--transport streamable-http`` for new deployments.

    Client configuration (Claude Desktop SSE mode — legacy):

        {
          "mcpServers": {
            "enterprise-ai-accelerator": {
              "url": "http://localhost:8765/sse",
              "transport": "sse"
            }
          }
        }

    Auth: set ``EAA_MCP_AUTH_TOKEN`` to require ``Authorization: Bearer <token>``.
    """
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from mcp.server.sse import SseServerTransport

    _reset_start_time()

    sse_transport = SseServerTransport("/messages")

    async def handle_sse(scope, receive, send):
        async with sse_transport.connect_sse(scope, receive, send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    async def handle_messages(scope, receive, send):
        await sse_transport.handle_post_message(scope, receive, send)

    health = _build_health_handler(["sse"])

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/sse", handle_sse),
        Mount("/messages", app=handle_messages),
    ]

    app = Starlette(routes=routes)

    if _AUTH_TOKEN is not None:
        middleware_cls = _make_auth_middleware()
        app.add_middleware(middleware_cls)

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    srv = uvicorn.Server(config)
    await srv.serve()
