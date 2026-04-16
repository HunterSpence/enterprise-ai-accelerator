"""
core/telemetry.py
=================

Production-grade OpenTelemetry instrumentation for the Enterprise AI Accelerator.

Design rules:
  - Fully opt-in: if OTEL_EXPORTER_OTLP_ENDPOINT is not set, all calls are no-ops.
  - Idempotent init: calling setup_tracing() multiple times is safe.
  - Backwards compatible: does not modify any existing signatures.
  - 2025 gen_ai.* semantic conventions throughout.

Quick start:
    from core.telemetry import setup_tracing
    setup_tracing("enterprise-ai-accelerator")          # reads env automatically

    from core.telemetry import traced, record_gen_ai_call
    # Then use @traced() on any async function.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Generator, Optional, TypeVar

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 2025 gen_ai.* semantic convention constants
# https://opentelemetry.io/docs/specs/semconv/gen-ai/
# ---------------------------------------------------------------------------

SEMCONV_GEN_AI_SYSTEM = "gen_ai.system"
SEMCONV_GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
SEMCONV_GEN_AI_RESPONSE_ID = "gen_ai.response.id"
SEMCONV_GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
SEMCONV_GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
SEMCONV_GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# Anthropic cache extensions (not yet standardised — use vendor prefix)
SEMCONV_GEN_AI_USAGE_CACHE_READ_TOKENS = "gen_ai.usage.cache_read_input_tokens"
SEMCONV_GEN_AI_USAGE_CACHE_CREATION_TOKENS = "gen_ai.usage.cache_creation_input_tokens"
SEMCONV_GEN_AI_USAGE_THINKING_TOKENS = "gen_ai.usage.thinking_tokens"

# Distributed correlation
CORRELATION_ID_HEADER = "x-correlation-id"
CORRELATION_ID_ATTR = "eaa.correlation_id"


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_initialized: bool = False
_noop: bool = True  # True when OTEL is unavailable or endpoint not configured


# ---------------------------------------------------------------------------
# Lazy OTEL import helpers
# ---------------------------------------------------------------------------

def _otel_available() -> bool:
    try:
        import opentelemetry  # noqa: F401
        return True
    except ImportError:
        return False


def _get_tracer() -> Any:
    """Return the module-level OTEL tracer, or None if not initialised."""
    if _noop:
        return None
    try:
        from opentelemetry import trace
        return trace.get_tracer(
            "enterprise-ai-accelerator",
            schema_url="https://opentelemetry.io/schemas/1.24.0",
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# setup_tracing — idempotent global init
# ---------------------------------------------------------------------------

def setup_tracing(
    service_name: str,
    otlp_endpoint: str | None = None,
    *,
    service_version: str = "2.0.0",
    environment: str | None = None,
) -> None:
    """Configure the global OpenTelemetry TracerProvider.

    Reads OTEL_EXPORTER_OTLP_ENDPOINT from the environment when
    *otlp_endpoint* is not passed explicitly. If neither is present the
    function returns immediately and all subsequent tracing calls are no-ops.

    Args:
        service_name:    The ``service.name`` resource attribute.
        otlp_endpoint:   gRPC OTLP endpoint, e.g. ``http://localhost:4317``.
                         Falls back to ``OTEL_EXPORTER_OTLP_ENDPOINT`` env var.
        service_version: Injected into ``service.version`` resource attribute.
        environment:     ``deployment.environment``; defaults to
                         ``ENVIRONMENT`` env var, then ``"development"``.
    """
    global _initialized, _noop

    if _initialized:
        return

    _initialized = True

    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.debug("OTEL: no endpoint configured — tracing is a no-op")
        _noop = True
        return

    if not _otel_available():
        logger.warning(
            "OTEL: opentelemetry-sdk not installed — tracing is a no-op. "
            "Install opentelemetry-sdk>=1.27.0 to enable."
        )
        _noop = True
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Try gRPC exporter first, fall back to HTTP proto
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            exporter = OTLPSpanExporter(endpoint=endpoint)
        except ImportError:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            exporter = OTLPSpanExporter(endpoint=endpoint)

        env = environment or os.environ.get("ENVIRONMENT", "development")
        resource = Resource.create({
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment": env,
        })

        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        _noop = False
        logger.info("OTEL: tracing configured (endpoint=%s, service=%s)", endpoint, service_name)

    except Exception as exc:
        logger.warning("OTEL: initialisation failed (%s) — tracing is a no-op", exc)
        _noop = True


# ---------------------------------------------------------------------------
# record_gen_ai_call — apply gen_ai.* conventions to an open span
# ---------------------------------------------------------------------------

def record_gen_ai_call(
    span: Any,
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_creation: int = 0,
    stop_reason: str = "",
    thinking_tokens: int | None = None,
    response_id: str | None = None,
) -> None:
    """Apply 2025 gen_ai.* semantic conventions to *span*.

    Safe to call even when *span* is None (no-op path) or when the OTEL SDK
    is not installed — uses duck-typed attribute access throughout.

    Args:
        span:             An OTEL ``Span`` object or our ``SimpleSpan`` proxy.
                          Pass ``None`` to skip silently.
        model:            Model identifier, e.g. ``"claude-opus-4-7"``.
        input_tokens:     Billable input tokens (excluding cache tokens).
        output_tokens:    Output tokens generated.
        cache_read:       Tokens read from Anthropic prompt cache (50% cost).
        cache_creation:   Tokens written to Anthropic prompt cache (125% cost).
        stop_reason:      Anthropic stop reason string, e.g. ``"end_turn"``.
        thinking_tokens:  Extended-thinking token budget consumed (if any).
        response_id:      ``gen_ai.response.id`` — Anthropic message ID.
    """
    if span is None:
        return

    try:
        _set = span.set_attribute
        _set(SEMCONV_GEN_AI_SYSTEM, "anthropic")
        _set(SEMCONV_GEN_AI_REQUEST_MODEL, model)
        _set(SEMCONV_GEN_AI_USAGE_INPUT_TOKENS, input_tokens)
        _set(SEMCONV_GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens)
        if cache_read:
            _set(SEMCONV_GEN_AI_USAGE_CACHE_READ_TOKENS, cache_read)
        if cache_creation:
            _set(SEMCONV_GEN_AI_USAGE_CACHE_CREATION_TOKENS, cache_creation)
        if thinking_tokens is not None:
            _set(SEMCONV_GEN_AI_USAGE_THINKING_TOKENS, thinking_tokens)
        if stop_reason:
            _set(SEMCONV_GEN_AI_RESPONSE_FINISH_REASONS, [stop_reason])
        if response_id:
            _set(SEMCONV_GEN_AI_RESPONSE_ID, response_id)
    except Exception:
        pass  # Never let instrumentation crash the caller


# ---------------------------------------------------------------------------
# @traced — async-aware span decorator
# ---------------------------------------------------------------------------

F = TypeVar("F", bound=Callable[..., Any])


def traced(name: str | None = None) -> Callable[[F], F]:
    """Decorator that wraps an async (or sync) function in an OTEL span.

    When OTEL is not configured this is a true zero-overhead no-op — it
    returns the original callable unchanged.

    Exceptions are recorded on the span with ``SpanStatus.ERROR`` and
    re-raised so callers receive them normally.

    Usage::

        @traced("migration_scout.classify")
        async def classify_workload(payload: dict) -> dict:
            ...

        @traced()  # name defaults to "<module>.<qualname>"
        async def run_pipeline(task: str) -> PipelineResult:
            ...
    """
    def decorator(fn: F) -> F:
        if _noop:
            return fn  # zero overhead in no-op mode

        span_name = name or f"{fn.__module__}.{fn.__qualname__}"

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = _get_tracer()
                if tracer is None:
                    return await fn(*args, **kwargs)
                with tracer.start_as_current_span(span_name) as span:
                    try:
                        result = await fn(*args, **kwargs)
                        return result
                    except Exception as exc:
                        _record_exception(span, exc)
                        raise
            return async_wrapper  # type: ignore[return-value]
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = _get_tracer()
                if tracer is None:
                    return fn(*args, **kwargs)
                with tracer.start_as_current_span(span_name) as span:
                    try:
                        result = fn(*args, **kwargs)
                        return result
                    except Exception as exc:
                        _record_exception(span, exc)
                        raise
            return sync_wrapper  # type: ignore[return-value]

    return decorator


def _record_exception(span: Any, exc: Exception) -> None:
    """Mark a span as errored and record the exception event."""
    try:
        from opentelemetry.trace import StatusCode
        span.set_status(StatusCode.ERROR, str(exc))
        span.record_exception(exc)
    except Exception:
        try:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(exc))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Correlation ID helpers — distributed trace propagation
# ---------------------------------------------------------------------------

def extract_correlation_id(headers: dict[str, str]) -> str:
    """Return the correlation ID from HTTP headers, generating one if absent.

    Checks ``x-correlation-id`` (preferred) then ``x-request-id`` (fallback).
    The returned ID is always a non-empty string.

    Usage::

        cid = extract_correlation_id(request.headers)
        set_correlation_id(cid)
    """
    for header in (CORRELATION_ID_HEADER, "x-request-id", "x-trace-id"):
        value = headers.get(header) or headers.get(header.lower())
        if value:
            return value
    return str(uuid.uuid4())


def set_correlation_id(correlation_id: str) -> None:
    """Attach *correlation_id* to the current active OTEL span.

    No-op when OTEL is not configured.
    """
    if _noop:
        return
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(CORRELATION_ID_ATTR, correlation_id)
    except Exception:
        pass


@contextmanager
def correlation_context(headers: dict[str, str]) -> Generator[str, None, None]:
    """Context manager that extracts the correlation ID and attaches it.

    Usage::

        with correlation_context(request.headers) as cid:
            logger.info("Processing request", correlation_id=cid)
            await handle(request)
    """
    cid = extract_correlation_id(headers)
    set_correlation_id(cid)
    yield cid


# ---------------------------------------------------------------------------
# Span context manager (for manual span management without @traced)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> AsyncGenerator[Any, None]:
    """Async context manager yielding a live span (or None in no-op mode).

    Usage::

        async with telemetry.span("orchestrator.run", {"task": task}) as s:
            result = await orchestrator.run_pipeline(task)
            record_gen_ai_call(s, model=..., input_tokens=..., ...)
    """
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                try:
                    s.set_attribute(k, v)
                except Exception:
                    pass
        try:
            yield s
        except Exception as exc:
            _record_exception(s, exc)
            raise
