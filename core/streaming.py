"""
core/streaming.py
=================

SSE-friendly streaming wrappers around Anthropic's async streaming API.

WIRING (one-liner — plain generator):
    from core.streaming import stream_completion
    async for event in stream_completion(ai, system="You are...", user="Hello"):
        print(event.type, event.data)

WIRING (FastAPI SSE endpoint):
    from core.streaming import stream_sse
    from fastapi.responses import StreamingResponse

    @app.post("/chat/stream")
    async def chat(req: ChatRequest):
        return StreamingResponse(
            stream_sse(req, ai, system=SYSTEM_PROMPT, user=req.message),
            media_type="text/event-stream",
        )

StreamEvent types:
    "text"       — visible assistant text delta
    "thinking"   — extended-thinking delta (for audit trace logging)
    "tool_use"   — tool_use block started (name + partial input JSON)
    "stop"       — stream ended; data contains stop_reason
    "error"      — unrecoverable error; data contains message
    "usage"      — final token usage summary (JSON)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# StreamEvent
# ---------------------------------------------------------------------------

@dataclass
class StreamEvent:
    """A single event emitted by ``stream_completion``.

    Attributes
    ----------
    type:
        One of: "text", "thinking", "tool_use", "stop", "error", "usage".
    data:
        - text / thinking: the delta string
        - tool_use: JSON string {"name": str, "input_delta": str}
        - stop: stop_reason string
        - error: error message string
        - usage: JSON string {"input_tokens": int, "output_tokens": int}
    block_index:
        Content block index from Anthropic's event (useful for interleaved
        thinking + tool_use ordering).
    """

    type: str
    data: str
    block_index: int = 0

    def to_sse(self) -> str:
        """Format as a Server-Sent Events line (``data: {...}\\n\\n``)."""
        payload = json.dumps(
            {"type": self.type, "data": self.data, "block_index": self.block_index}
        )
        return f"data: {payload}\n\n"


# ---------------------------------------------------------------------------
# stream_completion
# ---------------------------------------------------------------------------

async def stream_completion(
    ai: Any,
    *,
    system: str,
    user: str,
    model: Optional[str] = None,
    max_tokens: int = 2048,
    budget_tokens: int = 0,
    tools: Optional[list[dict[str, Any]]] = None,
    cache_system: bool = True,
    extra_messages: Optional[list[dict[str, Any]]] = None,
) -> AsyncGenerator[StreamEvent, None]:
    """Async generator yielding StreamEvents as Anthropic streams.

    Parameters
    ----------
    ai:
        ``AIClient`` instance (core.ai_client).
    system:
        System prompt text.
    user:
        User message text.
    model:
        Model ID. Defaults to ai._default_model.
    max_tokens:
        Max output tokens.
    budget_tokens:
        If > 0, enables extended thinking with this budget.
    tools:
        Optional list of tool dicts (Anthropic tool schema format).
    cache_system:
        If True, wraps system in ephemeral cache_control block.
    extra_messages:
        Optional prior turns to prepend before the user message.
    """
    model = model or ai._default_model

    # Build system blocks
    if cache_system:
        system_blocks = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system_blocks = system  # type: ignore[assignment]

    messages: list[dict[str, Any]] = list(extra_messages or [])
    messages.append({"role": "user", "content": user})

    create_kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_blocks,
        "messages": messages,
    }
    if budget_tokens > 0:
        create_kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget_tokens}
    if tools:
        create_kwargs["tools"] = tools

    try:
        # Anthropic async streaming context manager
        async with ai.raw.messages.stream(**create_kwargs) as stream:
            # Track active tool_use block for input_json_delta accumulation
            active_tool: Optional[dict[str, Any]] = None

            async for event in stream:
                event_type = getattr(event, "type", None)

                # --- content_block_start ---
                if event_type == "content_block_start":
                    block = getattr(event, "content_block", None)
                    block_idx = getattr(event, "index", 0)
                    if block and getattr(block, "type", None) == "tool_use":
                        active_tool = {
                            "name": getattr(block, "name", ""),
                            "id": getattr(block, "id", ""),
                            "index": block_idx,
                            "input_buffer": "",
                        }
                        yield StreamEvent(
                            type="tool_use",
                            data=json.dumps(
                                {"name": active_tool["name"], "input_delta": ""}
                            ),
                            block_index=block_idx,
                        )
                    elif block and getattr(block, "type", None) == "thinking":
                        active_tool = None  # reset
                    else:
                        active_tool = None

                # --- content_block_delta ---
                elif event_type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    block_idx = getattr(event, "index", 0)
                    delta_type = getattr(delta, "type", None)

                    if delta_type == "text_delta":
                        text = getattr(delta, "text", "") or ""
                        yield StreamEvent(type="text", data=text, block_index=block_idx)

                    elif delta_type == "thinking_delta":
                        thinking = getattr(delta, "thinking", "") or ""
                        yield StreamEvent(type="thinking", data=thinking, block_index=block_idx)

                    elif delta_type == "input_json_delta":
                        partial = getattr(delta, "partial_json", "") or ""
                        if active_tool is not None:
                            active_tool["input_buffer"] += partial
                            yield StreamEvent(
                                type="tool_use",
                                data=json.dumps(
                                    {
                                        "name": active_tool["name"],
                                        "input_delta": partial,
                                    }
                                ),
                                block_index=block_idx,
                            )

                # --- message_delta (stop_reason + usage) ---
                elif event_type == "message_delta":
                    delta = getattr(event, "delta", None)
                    usage = getattr(event, "usage", None)
                    stop_reason = getattr(delta, "stop_reason", None) or "end_turn"
                    yield StreamEvent(type="stop", data=stop_reason)
                    if usage:
                        yield StreamEvent(
                            type="usage",
                            data=json.dumps(
                                {
                                    "input_tokens": getattr(usage, "input_tokens", 0),
                                    "output_tokens": getattr(usage, "output_tokens", 0),
                                }
                            ),
                        )

    except Exception as exc:
        logger.error("stream_completion error: %s", exc)
        yield StreamEvent(type="error", data=str(exc))


# ---------------------------------------------------------------------------
# stream_sse — FastAPI helper
# ---------------------------------------------------------------------------

async def stream_sse(
    request: Any,
    ai: Any,
    *,
    system: str,
    user: str,
    model: Optional[str] = None,
    max_tokens: int = 2048,
    budget_tokens: int = 0,
    tools: Optional[list[dict[str, Any]]] = None,
    on_event: Optional[Any] = None,
) -> AsyncGenerator[str, None]:
    """Async generator of SSE-formatted strings for FastAPI StreamingResponse.

    Usage in a FastAPI route:
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            stream_sse(request, ai, system=SYS, user=req.message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    Parameters
    ----------
    request:
        The incoming FastAPI Request object (reserved for future per-request
        auth / cancellation — not used directly yet).
    on_event:
        Optional async callable ``(StreamEvent) -> None`` for side-effects
        (e.g. persisting thinking traces to audit log). Called for every event
        before it is yielded to the client.
    """
    async for event in stream_completion(
        ai,
        system=system,
        user=user,
        model=model,
        max_tokens=max_tokens,
        budget_tokens=budget_tokens,
        tools=tools,
    ):
        if on_event is not None:
            try:
                await on_event(event)
            except Exception as exc:
                logger.warning("stream_sse on_event callback error: %s", exc)
        yield event.to_sse()

    # Send a terminal event so the client knows the stream closed cleanly
    yield "data: [DONE]\n\n"
