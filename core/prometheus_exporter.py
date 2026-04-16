"""
core/prometheus_exporter.py
===========================

Prometheus metrics for the Enterprise AI Accelerator — exposed at /metrics
via a FastAPI ``APIRouter`` that mounts into the existing app or MCP server.

All metrics follow Prometheus naming conventions:
  - Counters: ``_total`` suffix
  - Histograms: ``_seconds`` / ``_bytes`` suffix
  - Gauges: no suffix

Mount in FastAPI::

    from fastapi import FastAPI
    from core.prometheus_exporter import router as metrics_router

    app = FastAPI()
    app.include_router(metrics_router)

Or standalone::

    uvicorn core.prometheus_exporter:standalone_app --port 9090

Call helpers from anywhere::

    from core.prometheus_exporter import record_llm_call, record_pipeline, record_finding

    record_llm_call(model="claude-opus-4-7", module="migration_scout",
                    outcome="success", input_tokens=1200, output_tokens=450,
                    cache_read=800, latency_seconds=2.3)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guard: prometheus-client is optional (same opt-in model as OTEL)
# ---------------------------------------------------------------------------

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
        REGISTRY,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.debug("prometheus-client not installed — /metrics endpoint will return 503")


# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

_LLM_LATENCY_BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)

if _PROMETHEUS_AVAILABLE:
    # ------------------------------------------------------------------
    # LLM call counter: {model, module, outcome}
    # outcome = "success" | "error" | "timeout"
    # ------------------------------------------------------------------
    LLM_CALLS_TOTAL = Counter(
        "eaa_llm_calls_total",
        "Total LLM API calls made by the platform",
        ["model", "module", "outcome"],
    )

    # ------------------------------------------------------------------
    # Token counters: {model, direction, cache_state}
    # direction    = "input" | "output"
    # cache_state  = "miss" | "read" | "creation"
    # ------------------------------------------------------------------
    LLM_TOKENS_TOTAL = Counter(
        "eaa_llm_tokens_total",
        "Total tokens consumed, partitioned by direction and cache state",
        ["model", "direction", "cache_state"],
    )

    # ------------------------------------------------------------------
    # Latency histogram: {model, module}
    # ------------------------------------------------------------------
    LLM_LATENCY_SECONDS = Histogram(
        "eaa_llm_latency_seconds",
        "LLM call wall-clock latency in seconds",
        ["model", "module"],
        buckets=_LLM_LATENCY_BUCKETS,
    )

    # ------------------------------------------------------------------
    # Pipeline counters: {status}
    # status = "success" | "partial" | "failed"
    # ------------------------------------------------------------------
    PIPELINE_RUNS_TOTAL = Counter(
        "eaa_pipeline_runs_total",
        "Total orchestrator pipeline runs",
        ["status"],
    )

    # ------------------------------------------------------------------
    # Audit chain length (gauge — current value)
    # ------------------------------------------------------------------
    AUDIT_CHAIN_LENGTH = Gauge(
        "eaa_audit_chain_length",
        "Current number of entries in the AI decision audit chain",
    )

    # ------------------------------------------------------------------
    # Findings: {module, severity}
    # severity = "critical" | "high" | "medium" | "low" | "info"
    # ------------------------------------------------------------------
    FINDINGS_TOTAL = Counter(
        "eaa_findings_total",
        "Total findings emitted by analysis modules",
        ["module", "severity"],
    )

    # ------------------------------------------------------------------
    # Cache hit ratio gauge — updated after each LLM call
    # ------------------------------------------------------------------
    CACHE_HIT_RATIO = Gauge(
        "eaa_cache_hit_ratio",
        "Rolling cache hit ratio (cache_read_tokens / total_input_tokens)",
    )

    # ------------------------------------------------------------------
    # Internal rolling counters for cache ratio calculation
    # ------------------------------------------------------------------
    _cache_read_total: int = 0
    _total_input_total: int = 0


# ---------------------------------------------------------------------------
# Public helper functions
# ---------------------------------------------------------------------------

def record_llm_call(
    *,
    model: str,
    module: str,
    outcome: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read: int = 0,
    cache_creation: int = 0,
    latency_seconds: float = 0.0,
) -> None:
    """Record a completed LLM call across all relevant metrics.

    Args:
        model:            Model identifier string (e.g. ``"claude-opus-4-7"``).
        module:           Platform module name (e.g. ``"migration_scout"``).
        outcome:          ``"success"`` | ``"error"`` | ``"timeout"``.
        input_tokens:     Standard (non-cached) input tokens.
        output_tokens:    Output tokens generated.
        cache_read:       Tokens served from Anthropic prompt cache.
        cache_creation:   Tokens written to Anthropic prompt cache.
        latency_seconds:  Wall-clock time for the API call.
    """
    global _cache_read_total, _total_input_total

    if not _PROMETHEUS_AVAILABLE:
        return

    try:
        LLM_CALLS_TOTAL.labels(model=model, module=module, outcome=outcome).inc()

        # Input tokens — split by cache state
        miss_tokens = input_tokens  # tokens paid at full rate
        if miss_tokens > 0:
            LLM_TOKENS_TOTAL.labels(model=model, direction="input", cache_state="miss").inc(miss_tokens)
        if cache_read > 0:
            LLM_TOKENS_TOTAL.labels(model=model, direction="input", cache_state="read").inc(cache_read)
        if cache_creation > 0:
            LLM_TOKENS_TOTAL.labels(model=model, direction="input", cache_state="creation").inc(cache_creation)

        # Output tokens
        if output_tokens > 0:
            LLM_TOKENS_TOTAL.labels(model=model, direction="output", cache_state="miss").inc(output_tokens)

        # Latency
        if latency_seconds > 0:
            LLM_LATENCY_SECONDS.labels(model=model, module=module).observe(latency_seconds)

        # Rolling cache hit ratio
        total_input = input_tokens + cache_read
        _total_input_total += total_input
        _cache_read_total += cache_read
        if _total_input_total > 0:
            CACHE_HIT_RATIO.set(_cache_read_total / _total_input_total)

    except Exception:
        pass  # Never let instrumentation crash the caller


def record_pipeline(*, status: str) -> None:
    """Increment the pipeline runs counter.

    Args:
        status: ``"success"`` | ``"partial"`` | ``"failed"``
    """
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        PIPELINE_RUNS_TOTAL.labels(status=status).inc()
    except Exception:
        pass


def record_finding(*, module: str, severity: str) -> None:
    """Increment the findings counter.

    Args:
        module:   Module that emitted the finding (e.g. ``"policy_guard"``).
        severity: ``"critical"`` | ``"high"`` | ``"medium"`` | ``"low"`` | ``"info"``
    """
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        severity_norm = severity.lower()
        FINDINGS_TOTAL.labels(module=module, severity=severity_norm).inc()
    except Exception:
        pass


def update_chain_length(n: int) -> None:
    """Set the audit chain length gauge.

    Args:
        n: Current number of entries in the audit chain.
    """
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        AUDIT_CHAIN_LENGTH.set(n)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# FastAPI router — GET /metrics
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter
    from fastapi.responses import PlainTextResponse, Response

    router = APIRouter(tags=["observability"])

    @router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
    async def metrics_endpoint() -> Response:
        """Prometheus scrape endpoint.

        Returns metrics in the standard Prometheus text exposition format.
        Returns 503 if prometheus-client is not installed.
        """
        if not _PROMETHEUS_AVAILABLE:
            return Response(
                content="# prometheus-client not installed\n",
                status_code=503,
                media_type="text/plain",
            )
        output = generate_latest(REGISTRY)
        return Response(content=output, media_type=CONTENT_TYPE_LATEST)

except ImportError:
    # FastAPI not installed — router is None, metrics can still be used standalone
    router = None  # type: ignore[assignment]
    logger.debug("FastAPI not installed — /metrics router not created")


# ---------------------------------------------------------------------------
# Standalone app (uvicorn core.prometheus_exporter:standalone_app)
# ---------------------------------------------------------------------------

def _build_standalone_app() -> Any:
    try:
        from fastapi import FastAPI
        app = FastAPI(title="EAA Metrics", docs_url=None, redoc_url=None)
        if router is not None:
            app.include_router(router)
        return app
    except ImportError:
        return None


standalone_app = _build_standalone_app()
