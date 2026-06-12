"""
core/ai_client.py
=================

Thin wrapper around anthropic.AsyncAnthropic that gives every module in the
platform a consistent on-ramp to the June-2026 Claude API surface:

  - Adaptive thinking + effort levels (Fable 5 / Opus 4.8 / Sonnet 4.6) —
    the legacy ``budget_tokens`` shape 400s on Fable 5 and is translated here
  - Summarized reasoning traces (``display: "summarized"``) so the EU AI Act
    Annex IV audit story keeps working on Fable 5, where the raw chain of
    thought is never returned
  - Structured outputs via ``output_config.format`` (schema-guaranteed JSON;
    compatible with thinking, unlike forced tool_choice)
  - Refusal handling: Fable 5 safety classifiers return HTTP 200 with
    ``stop_reason: "refusal"`` — surfaced as a typed RefusalError, with
    optional server-side fallback to Opus 4.8 in the same round trip
  - Prompt caching on system prompts (5-minute ephemeral cache)
  - Token counting via the count_tokens endpoint (never tiktoken)
  - Message Batches API for high-volume bulk work (50% discount)

Design note:
The wrapper is intentionally dependency-light: it accepts an existing
`anthropic.AsyncAnthropic` client if one is passed, otherwise constructs
one from the environment. That way we don't force every caller to touch
configuration — but the orchestrator can still inject a shared client
(with e.g. custom httpx transport) when it needs to.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import warnings
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

try:
    import anthropic
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover - anthropic is required at runtime
    anthropic = None  # type: ignore[assignment]
    AsyncAnthropic = None  # type: ignore[assignment]

from core.models import (
    BETA_SERVER_SIDE_FALLBACK,
    BETA_TASK_BUDGETS,
    CACHE_TTL_5M,
    DEFAULT_EFFORT,
    DEFAULT_MAX_TOKENS,
    MODEL_COORDINATOR,
    MODEL_FALLBACK,
    TASK_BUDGET_MIN_TOKENS,
    effort_for_budget,
    is_fable,
    supports_adaptive_thinking,
    supports_effort,
    validate_effort,
)

logger = logging.getLogger(__name__)

_BAD_REQUEST_ERROR: tuple = (
    (anthropic.BadRequestError,) if anthropic is not None else ()
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RefusalError(RuntimeError):
    """Raised when the model declines a request (``stop_reason: "refusal"``).

    Fable 5 runs safety classifiers on incoming requests. A declined request
    is a *successful* HTTP 200 whose ``stop_reason`` is ``"refusal"`` — code
    that reads ``response.content[0]`` unconditionally breaks on it. The
    platform surfaces it as this typed exception instead, carrying the
    structured ``stop_details`` so callers (and the audit trail) can record
    the policy category.

    When server-side fallbacks are enabled (the default for Fable 5 calls),
    this exception means the *entire* fallback chain declined.
    """

    def __init__(
        self,
        message: str = "Model declined the request (stop_reason=refusal)",
        *,
        category: str | None = None,
        explanation: str | None = None,
        model: str = "",
    ) -> None:
        super().__init__(message)
        self.category = category
        self.explanation = explanation
        self.model = model


# ---------------------------------------------------------------------------
# Response dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StructuredResponse:
    """Structured output produced via Anthropic structured outputs."""

    data: dict[str, Any]
    raw_text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    stop_reason: str = ""
    served_by_fallback: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ThinkingResponse:
    """Adaptive-thinking response — captures both visible answer and the
    summarized reasoning trace (Fable 5 never returns the raw chain of
    thought; ``display: "summarized"`` yields a readable summary)."""

    text: str
    thinking_trace: str
    model: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int = 0  # not separately reported by the API; kept for compat
    cache_read_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class BatchRequest:
    """Single request in a Message Batches submission."""

    custom_id: str
    model: str
    system: str
    messages: list[dict[str, Any]]
    max_tokens: int = DEFAULT_MAX_TOKENS
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

    Parameters
    ----------
    enable_fallbacks:
        When True (default; env kill-switch ``EAA_ENABLE_FALLBACKS=0``),
        Fable 5 calls are sent with the server-side fallbacks beta so a
        safety-classifier refusal is retried on ``MODEL_FALLBACK`` (Opus 4.8)
        in the same round trip. Refusals that survive the whole chain raise
        :class:`RefusalError`.
    """

    def __init__(
        self,
        client: AsyncAnthropic | None = None,
        *,
        default_model: str = MODEL_COORDINATOR,
        cache_system_prompts: bool = True,
        enable_fallbacks: bool | None = None,
    ) -> None:
        if client is None:
            if AsyncAnthropic is None:
                raise RuntimeError(
                    "anthropic package not installed — add 'anthropic>=0.109.0' "
                    "to requirements.txt and reinstall."
                )
            client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self._client = client
        self._default_model = default_model
        self._cache_system_prompts = cache_system_prompts
        if enable_fallbacks is None:
            enable_fallbacks = os.environ.get("EAA_ENABLE_FALLBACKS", "1") != "0"
        self._enable_fallbacks = enable_fallbacks

    # ------------------------------------------------------------------
    # Raw passthrough
    # ------------------------------------------------------------------

    @property
    def raw(self) -> AsyncAnthropic:
        """Direct access to the underlying AsyncAnthropic client."""
        return self._client

    # ------------------------------------------------------------------
    # Central request path — fallbacks + refusal handling
    # ------------------------------------------------------------------

    async def _create(self, *, _betas: list[str] | None = None, **kwargs: Any) -> Any:
        """Single choke-point for messages.create.

        Routes Fable 5 calls through the server-side fallbacks beta (refusal
        → retried on MODEL_FALLBACK in one round trip), degrades gracefully
        when the API surface rejects the beta, and converts a surviving
        ``stop_reason: "refusal"`` into a typed RefusalError. Extra beta
        headers (e.g. task budgets) come in via ``_betas``.
        """
        model = kwargs.get("model", "")
        betas = list(_betas or [])
        use_fallbacks = (
            self._enable_fallbacks
            and is_fable(model)
            and MODEL_FALLBACK
            and model != MODEL_FALLBACK
        )
        if use_fallbacks:
            try:
                response = await self._client.beta.messages.create(
                    betas=[BETA_SERVER_SIDE_FALLBACK, *betas],
                    fallbacks=[{"model": MODEL_FALLBACK}],
                    **kwargs,
                )
            except _BAD_REQUEST_ERROR as exc:  # pragma: no cover - provider-dependent
                if "fallback" in str(exc).lower():
                    # This API surface (e.g. Bedrock/Vertex) rejects the
                    # fallbacks beta — degrade once and remember.
                    logger.warning(
                        "Server-side fallbacks rejected by provider; disabling: %s", exc
                    )
                    self._enable_fallbacks = False
                    response = await self._create(_betas=betas, **kwargs)
                else:
                    raise
        elif betas:
            response = await self._client.beta.messages.create(betas=betas, **kwargs)
        else:
            response = await self._client.messages.create(**kwargs)

        self._raise_on_refusal(response, model)
        return response

    @staticmethod
    def _task_budget(
        output_config: dict[str, Any],
        betas: list[str],
        model: str,
        task_budget_tokens: int | None,
    ) -> None:
        """Attach a task budget (beta) when requested and supported.

        Task budgets give the model a running token countdown for a whole
        agentic run — a suggestion it self-moderates against, distinct from
        the enforced ``max_tokens`` ceiling. Minimum 20,000 tokens.
        """
        if not task_budget_tokens:
            return
        if not (is_fable(model) or "opus-4-7" in model or "opus-4-8" in model):
            return
        output_config["task_budget"] = {
            "type": "tokens",
            "total": max(TASK_BUDGET_MIN_TOKENS, int(task_budget_tokens)),
        }
        betas.append(BETA_TASK_BUDGETS)

    @staticmethod
    def _raise_on_refusal(response: Any, model: str) -> None:
        # Branch on stop_reason only — stop_details is informational and can
        # be None even on a real refusal.
        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            raise RefusalError(
                category=getattr(details, "category", None) if details else None,
                explanation=getattr(details, "explanation", None) if details else None,
                model=getattr(response, "model", model) or model,
            )

    def _thinking_param(self, model: str) -> dict[str, Any] | None:
        """Correct ``thinking`` argument for the target model.

        Fable 5 / Opus 4.8 family: adaptive with summarized display — the
        display opt-in is what keeps the Annex IV reasoning trace non-empty
        (the default on these models is ``omitted``: empty thinking text).
        Sonnet 4.6: plain adaptive. Models without adaptive support
        (Haiku 4.5): None — caller falls back to no thinking.
        """
        if not supports_adaptive_thinking(model):
            return None
        if is_fable(model) or "opus-4-7" in model or "opus-4-8" in model:
            return {"type": "adaptive", "display": "summarized"}
        return {"type": "adaptive"}

    @staticmethod
    def _resolve_effort(effort: str | None, budget_tokens: int | None) -> str:
        if budget_tokens is not None:
            warnings.warn(
                "budget_tokens is deprecated (the API rejects it on Fable 5 / "
                "Opus 4.7+). Pass effort='low|medium|high|xhigh|max' instead.",
                DeprecationWarning,
                stacklevel=3,
            )
            if effort is None:
                return effort_for_budget(budget_tokens)
        return validate_effort(effort) if effort else DEFAULT_EFFORT

    # ------------------------------------------------------------------
    # Structured output via output_config.format (structured outputs)
    # ------------------------------------------------------------------

    async def structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        tool_name: str = "return_result",          # deprecated, ignored
        tool_description: str = "Return the structured result.",  # deprecated, ignored
        model: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        cache_system: bool | None = None,
        extra_messages: list[dict[str, Any]] | None = None,
        effort: str | None = None,
        task_budget_tokens: int | None = None,
    ) -> StructuredResponse:
        """Invoke the model with a guaranteed-JSON response.

        Uses structured outputs (``output_config.format`` with a JSON
        schema): the API constrains generation so the text block is valid
        JSON matching ``schema`` — no fence stripping, no regex, and (unlike
        the older forced-tool-call pattern) fully compatible with thinking,
        which is always on for Fable 5.

        ``tool_name`` / ``tool_description`` are retained for backward
        compatibility but no longer used.
        """
        model = model or self._default_model
        cache_system = self._cache_system_prompts if cache_system is None else cache_system

        system_blocks = _system_blocks(system, cache=cache_system)
        messages: list[dict[str, Any]] = []
        if extra_messages:
            messages.extend(extra_messages)
        messages.append({"role": "user", "content": user})

        output_config: dict[str, Any] = {
            "format": {"type": "json_schema", "schema": _strict_schema(schema)},
        }
        if effort and supports_effort(model):
            output_config["effort"] = validate_effort(effort)
        betas: list[str] = []
        self._task_budget(output_config, betas, model, task_budget_tokens)

        response = await self._create(
            _betas=betas,
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=messages,
            output_config=output_config,
        )

        data, raw_text = _extract_json_text(response)
        usage = getattr(response, "usage", None)
        return StructuredResponse(
            data=data,
            raw_text=raw_text,
            model=getattr(response, "model", model) or model,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) if usage else 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) if usage else 0,
            stop_reason=getattr(response, "stop_reason", "") or "",
            served_by_fallback=_served_by_fallback(response),
        )

    # ------------------------------------------------------------------
    # Adaptive thinking
    # ------------------------------------------------------------------

    async def thinking(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        effort: str | None = None,
        budget_tokens: int | None = None,  # deprecated → effort
        cache_system: bool | None = None,
    ) -> ThinkingResponse:
        """Invoke adaptive thinking. Returns visible answer + reasoning trace.

        Use for high-stakes classifications (6R strategy, bias detection,
        policy violations) where the reasoning trace becomes part of the
        EU AI Act Article 12 audit record. On Fable 5 the trace is the
        model's *summarized* reasoning (the raw chain of thought is never
        returned by the API); the summary is what gets persisted as
        Annex IV evidence.

        ``effort`` (low/medium/high/xhigh/max) replaces the deprecated
        ``budget_tokens`` — depth control without a fixed token budget.
        """
        model = model or self._default_model
        cache_system = self._cache_system_prompts if cache_system is None else cache_system
        effort = self._resolve_effort(effort, budget_tokens)

        system_blocks = _system_blocks(system, cache=cache_system)

        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": user}],
        )
        thinking = self._thinking_param(model)
        if thinking is not None:
            kwargs["thinking"] = thinking
        if supports_effort(model):
            kwargs["output_config"] = {"effort": effort}

        response = await self._create(**kwargs)

        visible_text, thinking_text = _extract_thinking(response)
        usage = getattr(response, "usage", None)
        return ThinkingResponse(
            text=visible_text,
            thinking_trace=thinking_text,
            model=getattr(response, "model", model) or model,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            thinking_tokens=0,  # thinking spend is folded into output_tokens
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
        tool_name: str = "return_result",          # deprecated, ignored
        tool_description: str = "Return the structured result.",  # deprecated, ignored
        model: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        effort: str | None = None,
        budget_tokens: int | None = None,  # deprecated → effort
        cache_system: bool | None = None,
        task_budget_tokens: int | None = None,
    ) -> tuple[StructuredResponse, str]:
        """Run a structured call with adaptive thinking enabled.

        Returns both the parsed ``StructuredResponse`` and the summarized
        reasoning trace as a plain string — caller decides whether to persist
        the trace into AIAuditTrail as supporting Annex IV evidence.

        Structured outputs are compatible with thinking (the older forced
        tool_choice pattern was not), so this is now the same request shape
        as :meth:`structured` plus the thinking parameter.
        """
        model = model or self._default_model
        cache_system = self._cache_system_prompts if cache_system is None else cache_system
        effort = self._resolve_effort(effort, budget_tokens)

        system_blocks = _system_blocks(system, cache=cache_system)

        output_config: dict[str, Any] = {
            "format": {"type": "json_schema", "schema": _strict_schema(schema)},
        }
        if supports_effort(model):
            output_config["effort"] = effort
        betas: list[str] = []
        self._task_budget(output_config, betas, model, task_budget_tokens)

        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": user}],
            output_config=output_config,
        )
        thinking = self._thinking_param(model)
        if thinking is not None:
            kwargs["thinking"] = thinking

        response = await self._create(_betas=betas, **kwargs)

        data, raw_text = _extract_json_text(response)
        _, thinking_text = _extract_thinking(response)
        usage = getattr(response, "usage", None)
        structured = StructuredResponse(
            data=data,
            raw_text=raw_text,
            model=getattr(response, "model", model) or model,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) if usage else 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) if usage else 0,
            stop_reason=getattr(response, "stop_reason", "") or "",
            served_by_fallback=_served_by_fallback(response),
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
        max_tokens: int = 4096,
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
        (Citations are incompatible with structured outputs, so this path
        stays plain-text by design.)
        """
        model = model or self._default_model

        user_content: list[dict[str, Any]] = list(documents)
        user_content.append({"type": "text", "text": question})

        response = await self._create(
            model=model,
            max_tokens=max_tokens,
            system=_system_blocks(system, cache=True),
            messages=[{"role": "user", "content": user_content}],
        )
        return response.model_dump() if hasattr(response, "model_dump") else json.loads(
            json.dumps(response, default=str)
        )

    # ------------------------------------------------------------------
    # Token counting — accurate, model-specific (never tiktoken)
    # ------------------------------------------------------------------

    async def count_tokens(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: Any,
    ) -> int:
        """Count input tokens via the count_tokens endpoint.

        Token counts are model-specific — Fable 5 shares the Opus 4.8
        tokenizer, but Haiku/Sonnet-era counts differ. Use this before
        large submissions instead of client-side estimates.
        """
        model = model or self._default_model
        if system is not None:
            kwargs["system"] = system
        result = await self._client.messages.count_tokens(
            model=model, messages=messages, **kwargs
        )
        return getattr(result, "input_tokens", 0)

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


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize a JSON schema for structured outputs.

    Structured outputs require ``additionalProperties: false`` on every
    object. Caller schemas predate that requirement, so we deep-copy and
    inject it recursively rather than pushing the constraint onto every
    call site.
    """
    normalized = copy.deepcopy(schema)

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "additionalProperties" not in node:
                node["additionalProperties"] = False
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(normalized)
    return normalized


def _extract_json_text(response: Any) -> tuple[dict[str, Any], str]:
    """Pull the structured-outputs JSON out of the first text block.

    With ``output_config.format`` the API guarantees the text block is valid
    JSON matching the schema — but a thinking block may precede it, so we
    scan for the first text block rather than indexing content[0].
    """
    for block in getattr(response, "content", []) or []:
        btype = getattr(block, "type", None) or (isinstance(block, dict) and block.get("type"))
        if btype == "text":
            text = getattr(block, "text", None) or (isinstance(block, dict) and block.get("text")) or ""
            if not text:
                continue
            try:
                return json.loads(text), text
            except (json.JSONDecodeError, TypeError):
                logger.warning("structured outputs: text block was not valid JSON")
                return {}, text
    return {}, ""


def _served_by_fallback(response: Any) -> bool:
    """True when a server-side fallback model produced this message.

    The served-by signal is a ``fallback_message`` entry in
    ``usage.iterations`` (the ``fallback`` content block only marks switch
    points and is absent on sticky-served turns).
    """
    usage = getattr(response, "usage", None)
    iterations = getattr(usage, "iterations", None) if usage else None
    if not iterations:
        return False
    for entry in iterations:
        etype = getattr(entry, "type", None) or (isinstance(entry, dict) and entry.get("type"))
        if etype == "fallback_message":
            return True
    return False


def _extract_tool_use(response: Any, tool_name: str) -> tuple[dict[str, Any], str]:
    """Pull forced tool-use arguments out of a response.

    Legacy helper retained for callers that still drive their own tool loop;
    the structured() path now uses structured outputs instead.
    """
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
