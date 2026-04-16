"""
core/ai_client.py
=================

Thin wrapper around anthropic.AsyncAnthropic that gives every module in the
platform a consistent on-ramp to Opus 4.7 capabilities:

  - Prompt caching on system prompts (5-minute ephemeral cache)
  - Native tool-use structured output (replaces fragile JSON regex parsing)
  - Extended thinking with configurable budgets
  - Citations + Files API helpers
  - Message Batches API for high-volume bulk work (50% discount)

Design note:
The wrapper is intentionally dependency-light: it accepts an existing
`anthropic.AsyncAnthropic` client if one is passed, otherwise constructs
one from the environment. That way we don't force every caller to touch
configuration — but the orchestrator can still inject a shared client
(with e.g. custom httpx transport) when it needs to.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

try:
    import anthropic
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover - anthropic is required at runtime
    anthropic = None  # type: ignore[assignment]
    AsyncAnthropic = None  # type: ignore[assignment]

from core.models import (
    MODEL_COORDINATOR,
    MODEL_OPUS_4_7,
    THINKING_BUDGET_HIGH,
    THINKING_BUDGET_STANDARD,
    CACHE_TTL_5M,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StructuredResponse:
    """Structured output produced via Anthropic native tool use."""

    data: dict[str, Any]
    raw_text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    stop_reason: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ThinkingResponse:
    """Extended-thinking response — captures both visible answer and reasoning trace."""

    text: str
    thinking_trace: str
    model: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.thinking_tokens


@dataclass
class BatchRequest:
    """Single request in a Message Batches submission."""

    custom_id: str
    model: str
    system: str
    messages: list[dict[str, Any]]
    max_tokens: int = 1024
    tools: list[dict[str, Any]] | None = None
    tool_choice: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AIClient
# ---------------------------------------------------------------------------

class AIClient:
    """High-level wrapper around AsyncAnthropic.

    Use the module-level ``get_client()`` for a shared singleton, or construct
    directly to inject a custom ``AsyncAnthropic`` instance.

    All methods are async. Synchronous callers can wrap with ``asyncio.run``.
    """

    def __init__(
        self,
        client: "AsyncAnthropic | None" = None,
        *,
        default_model: str = MODEL_COORDINATOR,
        cache_system_prompts: bool = True,
    ) -> None:
        if client is None:
            if AsyncAnthropic is None:
                raise RuntimeError(
                    "anthropic package not installed — add 'anthropic>=0.69.0' "
                    "to requirements.txt and reinstall."
                )
            client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self._client = client
        self._default_model = default_model
        self._cache_system_prompts = cache_system_prompts

    # ------------------------------------------------------------------
    # Raw passthrough
    # ------------------------------------------------------------------

    @property
    def raw(self) -> "AsyncAnthropic":
        """Direct access to the underlying AsyncAnthropic client."""
        return self._client

    # ------------------------------------------------------------------
    # Structured output via tool use
    # ------------------------------------------------------------------

    async def structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        tool_name: str = "return_result",
        tool_description: str = "Return the structured result.",
        model: str | None = None,
        max_tokens: int = 1024,
        cache_system: bool | None = None,
        extra_messages: list[dict[str, Any]] | None = None,
    ) -> StructuredResponse:
        """Invoke the model with a forced tool call — returns parsed JSON.

        Replaces the ``_parse_json_response`` regex hack in legacy code:
        the model is forced to call ``tool_name`` with arguments that match
        ``schema``. Anthropic validates the schema server-side, so parsing
        is guaranteed (no fence stripping, no ``json.loads`` try/except).
        """
        model = model or self._default_model
        cache_system = self._cache_system_prompts if cache_system is None else cache_system

        system_blocks = _system_blocks(system, cache=cache_system)
        messages: list[dict[str, Any]] = []
        if extra_messages:
            messages.extend(extra_messages)
        messages.append({"role": "user", "content": user})

        tools = [{
            "name": tool_name,
            "description": tool_description,
            "input_schema": schema,
        }]

        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=messages,
            tools=tools,
            tool_choice={"type": "tool", "name": tool_name},
        )

        data, raw_text = _extract_tool_use(response, tool_name)
        usage = getattr(response, "usage", None)
        return StructuredResponse(
            data=data,
            raw_text=raw_text,
            model=model,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) if usage else 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) if usage else 0,
            stop_reason=getattr(response, "stop_reason", "") or "",
        )

    # ------------------------------------------------------------------
    # Extended thinking
    # ------------------------------------------------------------------

    async def thinking(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 4096,
        budget_tokens: int = THINKING_BUDGET_HIGH,
        cache_system: bool | None = None,
    ) -> ThinkingResponse:
        """Invoke extended thinking. Returns visible answer + reasoning trace.

        Use for high-stakes classifications (6R strategy, bias detection,
        policy violations) where the reasoning trace becomes part of the
        EU AI Act Article 12 audit record.
        """
        model = model or MODEL_OPUS_4_7
        cache_system = self._cache_system_prompts if cache_system is None else cache_system

        system_blocks = _system_blocks(system, cache=cache_system)

        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "enabled", "budget_tokens": budget_tokens},
            system=system_blocks,
            messages=[{"role": "user", "content": user}],
        )

        visible_text, thinking_text = _extract_thinking(response)
        usage = getattr(response, "usage", None)
        return ThinkingResponse(
            text=visible_text,
            thinking_trace=thinking_text,
            model=model,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            thinking_tokens=getattr(usage, "cache_read_input_tokens", 0) if usage else 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) if usage else 0,
        )

    # ------------------------------------------------------------------
    # Structured + thinking — best of both worlds
    # ------------------------------------------------------------------

    async def structured_with_thinking(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        tool_name: str = "return_result",
        tool_description: str = "Return the structured result.",
        model: str | None = None,
        max_tokens: int = 2048,
        budget_tokens: int = THINKING_BUDGET_STANDARD,
        cache_system: bool | None = None,
    ) -> tuple[StructuredResponse, str]:
        """Run a structured call with interleaved thinking enabled.

        Returns both the parsed ``StructuredResponse`` and the reasoning
        trace as a plain string — caller decides whether to persist the
        trace into AIAuditTrail as supporting Annex IV evidence.
        """
        model = model or MODEL_OPUS_4_7
        cache_system = self._cache_system_prompts if cache_system is None else cache_system

        system_blocks = _system_blocks(system, cache=cache_system)

        tools = [{
            "name": tool_name,
            "description": tool_description,
            "input_schema": schema,
        }]

        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "enabled", "budget_tokens": budget_tokens},
            system=system_blocks,
            messages=[{"role": "user", "content": user}],
            tools=tools,
            tool_choice={"type": "tool", "name": tool_name},
        )

        data, raw_text = _extract_tool_use(response, tool_name)
        _, thinking_text = _extract_thinking(response)
        usage = getattr(response, "usage", None)
        structured = StructuredResponse(
            data=data,
            raw_text=raw_text,
            model=model,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) if usage else 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) if usage else 0,
            stop_reason=getattr(response, "stop_reason", "") or "",
        )
        return structured, thinking_text

    # ------------------------------------------------------------------
    # Citations — compliance evidence
    # ------------------------------------------------------------------

    async def cite(
        self,
        *,
        system: str,
        question: str,
        documents: Iterable[dict[str, Any]],
        model: str | None = None,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Ask a question against a set of documents with citations enabled.

        Each document dict should follow Anthropic's Files/Citations schema:
            {
              "type": "document",
              "source": {"type": "text", "media_type": "text/plain", "data": "..."},
              "title": "CIS AWS Benchmark 1.5 — Section 2.2",
              "citations": {"enabled": True},
            }

        Returns the raw response JSON — caller extracts content blocks.
        """
        model = model or MODEL_OPUS_4_7

        user_content: list[dict[str, Any]] = list(documents)
        user_content.append({"type": "text", "text": question})

        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=_system_blocks(system, cache=True),
            messages=[{"role": "user", "content": user_content}],
        )
        return response.model_dump() if hasattr(response, "model_dump") else json.loads(
            json.dumps(response, default=str)
        )

    # ------------------------------------------------------------------
    # Batch API — 50% discount for bulk workloads
    # ------------------------------------------------------------------

    async def submit_batch(self, requests: list[BatchRequest]) -> dict[str, Any]:
        """Submit a Message Batches request. Returns the batch object.

        The caller is responsible for polling ``retrieve_batch`` until the
        batch is complete — the helper is intentionally non-blocking so
        callers can submit large jobs and collect results asynchronously.
        """
        payload = [
            {
                "custom_id": r.custom_id,
                "params": {
                    "model": r.model,
                    "max_tokens": r.max_tokens,
                    "system": _system_blocks(r.system, cache=True),
                    "messages": r.messages,
                    **({"tools": r.tools} if r.tools else {}),
                    **({"tool_choice": r.tool_choice} if r.tool_choice else {}),
                    **r.extra,
                },
            }
            for r in requests
        ]
        batch = await self._client.messages.batches.create(requests=payload)
        return batch.model_dump() if hasattr(batch, "model_dump") else dict(batch)

    async def retrieve_batch(self, batch_id: str) -> dict[str, Any]:
        batch = await self._client.messages.batches.retrieve(batch_id)
        return batch.model_dump() if hasattr(batch, "model_dump") else dict(batch)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_SHARED_CLIENT: AIClient | None = None


def get_client(default_model: str | None = None) -> AIClient:
    """Return a process-wide shared AIClient (lazy-constructed)."""
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None:
        _SHARED_CLIENT = AIClient(
            default_model=default_model or MODEL_COORDINATOR,
        )
    return _SHARED_CLIENT


def _system_blocks(system: str, *, cache: bool) -> list[dict[str, Any]] | str:
    """Build the ``system`` argument.

    When caching is enabled we emit the structured form:
        [{"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}]

    The 5-minute ephemeral cache is usually what you want for a single
    pipeline run — the coordinator and the worker agents reuse the same
    system prompt across many sub-calls, so the cache hit rate approaches
    the ratio of (calls - 1) / calls.
    """
    if not cache:
        return system
    return [
        {
            "type": "text",
            "text": system,
            "cache_control": {"type": CACHE_TTL_5M},
        }
    ]


def _extract_tool_use(response: Any, tool_name: str) -> tuple[dict[str, Any], str]:
    """Pull the forced tool-use arguments out of a response."""
    for block in getattr(response, "content", []) or []:
        btype = getattr(block, "type", None) or (isinstance(block, dict) and block.get("type"))
        if btype == "tool_use":
            name = getattr(block, "name", None) or (isinstance(block, dict) and block.get("name"))
            if name == tool_name:
                inp = getattr(block, "input", None) or (isinstance(block, dict) and block.get("input"))
                inp = inp or {}
                return dict(inp), json.dumps(inp, default=str)
    return {}, ""


def _extract_thinking(response: Any) -> tuple[str, str]:
    """Split a response into (visible text, thinking trace)."""
    visible: list[str] = []
    thinking: list[str] = []
    for block in getattr(response, "content", []) or []:
        btype = getattr(block, "type", None) or (isinstance(block, dict) and block.get("type"))
        if btype == "thinking":
            text = getattr(block, "thinking", None) or (isinstance(block, dict) and block.get("thinking")) or ""
            thinking.append(text)
        elif btype == "text":
            text = getattr(block, "text", None) or (isinstance(block, dict) and block.get("text")) or ""
            visible.append(text)
    return "\n".join(visible).strip(), "\n".join(thinking).strip()
