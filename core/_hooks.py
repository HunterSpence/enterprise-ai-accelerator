"""
core/_hooks.py
==============

Non-breaking observability hook infrastructure for AIClient.

This module defines ``LLMCallEvent`` and ``on_llm_call()``.  AIClient does NOT
call this automatically — callers opt in by wrapping AIClient methods at the
application layer, keeping the client itself dependency-free.

--------------------------------------------------------------------
Integration pattern (recommended — wrap at call site):
--------------------------------------------------------------------

    import time
    from core._hooks import LLMCallEvent, on_llm_call
    from core.ai_client import get_client

    client = get_client()

    start = time.perf_counter()
    result = await client.structured(system=sys, user=usr, schema=schema)
    latency = time.perf_counter() - start

    on_llm_call(LLMCallEvent(
        model=result.model,
        module="migration_scout",
        outcome="success",
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cache_read=result.cache_read_tokens,
        cache_creation=result.cache_creation_tokens,
        stop_reason=result.stop_reason,
        latency_seconds=latency,
    ))

--------------------------------------------------------------------
App startup (once, before first request):
--------------------------------------------------------------------

    from core.telemetry import setup_tracing
    from core.logging import configure_logging

    configure_logging(level="INFO")
    setup_tracing("enterprise-ai-accelerator")  # reads OTEL_EXPORTER_OTLP_ENDPOINT

--------------------------------------------------------------------
FastAPI metrics mount:
--------------------------------------------------------------------

    from fastapi import FastAPI
    from core.prometheus_exporter import router as metrics_router

    app = FastAPI()
    app.include_router(metrics_router)          # exposes GET /metrics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class LLMCallEvent:
    """Carries all observability-relevant data from a single LLM API call.

    Populated by the caller immediately after ``await client.<method>()``
    returns.  All token counts default to 0 — callers fill only what they
    have.
    """

    model: str
    module: str
    outcome: str = "success"         # "success" | "error" | "timeout"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_creation: int = 0
    thinking_tokens: int | None = None
    stop_reason: str = ""
    response_id: str | None = None
    latency_seconds: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_structured_response(
        cls,
        response: Any,
        *,
        module: str,
        latency_seconds: float = 0.0,
        outcome: str = "success",
    ) -> "LLMCallEvent":
        """Convenience constructor from a ``StructuredResponse``."""
        return cls(
            model=getattr(response, "model", "unknown"),
            module=module,
            outcome=outcome,
            input_tokens=getattr(response, "input_tokens", 0),
            output_tokens=getattr(response, "output_tokens", 0),
            cache_read=getattr(response, "cache_read_tokens", 0),
            cache_creation=getattr(response, "cache_creation_tokens", 0),
            stop_reason=getattr(response, "stop_reason", ""),
            latency_seconds=latency_seconds,
        )

    @classmethod
    def from_thinking_response(
        cls,
        response: Any,
        *,
        module: str,
        latency_seconds: float = 0.0,
        outcome: str = "success",
    ) -> "LLMCallEvent":
        """Convenience constructor from a ``ThinkingResponse``."""
        return cls(
            model=getattr(response, "model", "unknown"),
            module=module,
            outcome=outcome,
            input_tokens=getattr(response, "input_tokens", 0),
            output_tokens=getattr(response, "output_tokens", 0),
            cache_read=getattr(response, "cache_read_tokens", 0),
            thinking_tokens=getattr(response, "thinking_tokens", None),
            latency_seconds=latency_seconds,
        )


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_handlers: list[Callable[[LLMCallEvent], None]] = []


def register_handler(handler: Callable[[LLMCallEvent], None]) -> None:
    """Register a callable to be invoked on every ``on_llm_call()``.

    Handlers run synchronously in registration order.  Exceptions are caught
    and logged — they never propagate to the caller.

    The default setup registers the OTEL + Prometheus handlers automatically
    when ``setup_default_handlers()`` is called.
    """
    _handlers.append(handler)


def on_llm_call(event: LLMCallEvent) -> None:
    """Fire all registered handlers for a completed LLM call.

    Thread-safe (handlers are read-only after startup).  Never raises.
    """
    for handler in _handlers:
        try:
            handler(event)
        except Exception:
            pass  # instrumentation must never crash the caller


# ---------------------------------------------------------------------------
# Default handler implementations
# ---------------------------------------------------------------------------

def _prometheus_handler(event: LLMCallEvent) -> None:
    """Push event data into Prometheus metrics."""
    try:
        from core.prometheus_exporter import record_llm_call
        record_llm_call(
            model=event.model,
            module=event.module,
            outcome=event.outcome,
            input_tokens=event.input_tokens,
            output_tokens=event.output_tokens,
            cache_read=event.cache_read,
            cache_creation=event.cache_creation,
            latency_seconds=event.latency_seconds,
        )
    except Exception:
        pass


def _otel_handler(event: LLMCallEvent) -> None:
    """Add gen_ai.* attributes to the currently active OTEL span (if any)."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.is_recording():
            from core.telemetry import record_gen_ai_call
            record_gen_ai_call(
                span,
                model=event.model,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                cache_read=event.cache_read,
                cache_creation=event.cache_creation,
                stop_reason=event.stop_reason,
                thinking_tokens=event.thinking_tokens,
                response_id=event.response_id,
            )
    except Exception:
        pass


def _structlog_handler(event: LLMCallEvent) -> None:
    """Emit a structured log line for every LLM call."""
    try:
        from core.logging import get_logger
        log = get_logger("core._hooks")
        log.info(
            "llm_call",
            model=event.model,
            module=event.module,
            outcome=event.outcome,
            input_tokens=event.input_tokens,
            output_tokens=event.output_tokens,
            cache_read=event.cache_read,
            cache_creation=event.cache_creation,
            latency_seconds=round(event.latency_seconds, 3),
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Convenience: register all default handlers at once
# ---------------------------------------------------------------------------

def setup_default_handlers() -> None:
    """Register Prometheus + OTEL + structlog handlers.

    Call once at startup, after ``setup_tracing()`` and
    ``configure_logging()``.  Idempotent — safe to call multiple times
    (handlers are only appended once per process).

    Usage::

        from core._hooks import setup_default_handlers
        from core.telemetry import setup_tracing
        from core.logging import configure_logging

        configure_logging()
        setup_tracing("enterprise-ai-accelerator")
        setup_default_handlers()
    """
    if _prometheus_handler not in _handlers:
        register_handler(_prometheus_handler)
    if _otel_handler not in _handlers:
        register_handler(_otel_handler)
    if _structlog_handler not in _handlers:
        register_handler(_structlog_handler)
