"""
mcp_transports.py — Transport helpers for Enterprise AI Accelerator MCP 2.0
============================================================================

Provides ``run_stdio()`` and ``run_sse()`` so ``mcp_server.py`` can stay
focused on the tool/resource/prompt surface without coupling to transport
wiring.

SSE transport uses ``mcp.server.sse.SseServerTransport`` (MCP SDK 1.27.0+)
mounted inside a Starlette application.  The stdio path is unchanged.

Usage (via mcp_server.py CLI):
    python mcp_server.py                         # stdio (default)
    python mcp_server.py --transport sse          # SSE on 0.0.0.0:8765
    python mcp_server.py --transport sse --host 127.0.0.1 --port 9000
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server import Server

# ---------------------------------------------------------------------------
# Startup timestamp for /health uptime_s
# ---------------------------------------------------------------------------

_START_TIME: float = time.monotonic()


def _reset_start_time() -> None:
    """Called once at server startup so uptime_s is accurate."""
    global _START_TIME
    _START_TIME = time.monotonic()


# ---------------------------------------------------------------------------
# stdio
# ---------------------------------------------------------------------------

async def run_stdio(server: "Server") -> None:
    """Run the MCP server over stdio (default transport, unchanged)."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# ---------------------------------------------------------------------------
# SSE
# ---------------------------------------------------------------------------

async def run_sse(
    server: "Server",
    host: str = "0.0.0.0",
    port: int = 8765,
) -> None:
    """Run the MCP server over SSE (HTTP transport).

    Mounts the MCP SSE endpoint at ``/sse`` and the POST message endpoint at
    ``/messages``.  A ``GET /health`` route returns liveness metadata.

    Client configuration (Claude Desktop SSE mode):
        {
          "mcpServers": {
            "enterprise-ai-accelerator": {
              "url": "http://localhost:8765/sse",
              "transport": "sse"
            }
          }
        }
    """
    import uvicorn
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route
    from mcp.server.sse import SseServerTransport

    _reset_start_time()

    sse_transport = SseServerTransport("/messages")

    # --- SSE connect handler ---
    async def handle_sse(scope, receive, send):  # ASGI
        async with sse_transport.connect_sse(scope, receive, send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    # --- POST message handler ---
    async def handle_messages(scope, receive, send):
        await sse_transport.handle_post_message(scope, receive, send)

    # --- Health endpoint ---
    async def health(request: Request) -> JSONResponse:
        from mcp_server import _TOOLS, _RESOURCES, _PROMPTS  # lazy import to avoid circularity
        return JSONResponse({
            "status": "ok",
            "tools": len(_TOOLS),
            "resources": len(_RESOURCES),
            "prompts": len(_PROMPTS),
            "uptime_s": round(time.monotonic() - _START_TIME, 1),
        })

    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/sse", handle_sse),
            Mount("/messages", app=handle_messages),
        ],
    )

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    srv = uvicorn.Server(config)
    await srv.serve()
