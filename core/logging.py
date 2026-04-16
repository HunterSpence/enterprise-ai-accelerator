"""
core/logging.py
===============

Structured logging for the Enterprise AI Accelerator using structlog.

Features:
  - JSON renderer in production (LOG_FORMAT=json or ENVIRONMENT != development)
  - Human-readable coloured console output in development
  - Automatic OTEL trace_id / span_id injection into every log record
    (when opentelemetry-sdk is available and a span is active)
  - Standard Python logging integration — third-party libraries route
    through structlog automatically

Usage::

    from core.logging import configure_logging, get_logger

    # Once at startup (idempotent):
    configure_logging(level="INFO")

    # In any module:
    logger = get_logger(__name__)
    logger.info("pipeline_started", task=task, model=model)

    # With bound context:
    log = logger.bind(module="migration_scout", correlation_id=cid)
    log.warning("low_confidence", workload_id=wid, confidence=0.62)
"""

from __future__ import annotations

import logging
import logging.config
import os
import sys
from typing import Any

_configured: bool = False


# ---------------------------------------------------------------------------
# OTEL trace context processor
# ---------------------------------------------------------------------------

def _otel_trace_context_processor(
    logger: Any,  # noqa: ARG001
    method: str,  # noqa: ARG001
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Inject active OTEL trace_id and span_id into the log record.

    No-op when opentelemetry-sdk is not installed or no span is active.
    This runs as a structlog processor — it receives and returns event_dict.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.trace import format_span_id, format_trace_id

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            event_dict["trace_id"] = format_trace_id(ctx.trace_id)
            event_dict["span_id"] = format_span_id(ctx.span_id)
    except Exception:
        pass
    return event_dict


# ---------------------------------------------------------------------------
# configure_logging — idempotent
# ---------------------------------------------------------------------------

def configure_logging(
    level: str = "INFO",
    *,
    force_json: bool | None = None,
    service_name: str = "enterprise-ai-accelerator",
) -> None:
    """Configure structlog and stdlib logging.

    Safe to call multiple times — subsequent calls after the first are no-ops.

    Args:
        level:        Python log level string: ``"DEBUG"``, ``"INFO"``,
                      ``"WARNING"``, ``"ERROR"``, ``"CRITICAL"``.
        force_json:   Override auto-detection. ``True`` = always JSON,
                      ``False`` = always console. ``None`` = auto
                      (JSON when ENVIRONMENT != development or
                       LOG_FORMAT=json).
        service_name: Injected as ``service`` field on every log record.
    """
    global _configured
    if _configured:
        return
    _configured = True

    try:
        import structlog
    except ImportError:
        # structlog not installed — fall back to stdlib
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            stream=sys.stdout,
        )
        logging.getLogger(__name__).warning(
            "structlog not installed — using stdlib logging (install structlog>=24.1.0)"
        )
        return

    # Determine output format
    env = os.environ.get("ENVIRONMENT", "development")
    log_format = os.environ.get("LOG_FORMAT", "")

    if force_json is None:
        use_json = (env != "development") or (log_format.lower() == "json")
    else:
        use_json = force_json

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Shared processors (always applied)
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _otel_trace_context_processor,
        structlog.processors.StackInfoRenderer(),
    ]

    if use_json:
        # Production: newline-delimited JSON — grep/jq friendly, Grafana Loki ready
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: coloured human-readable output
        shared_processors.append(structlog.dev.set_exc_info)
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)

    # Quieten noisy third-party loggers
    for noisy in ("anthropic", "httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Inject service name into every log record via structlog contextvars
    structlog.contextvars.bind_contextvars(service=service_name)


# ---------------------------------------------------------------------------
# get_logger — preferred alias throughout the codebase
# ---------------------------------------------------------------------------

def get_logger(name: str) -> Any:
    """Return a structlog-wrapped logger for *name*.

    Falls back to a stdlib logger when structlog is not installed.

    Usage::

        logger = get_logger(__name__)
        logger.info("found_findings", count=len(findings), module="policy_guard")
    """
    try:
        import structlog
        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)
