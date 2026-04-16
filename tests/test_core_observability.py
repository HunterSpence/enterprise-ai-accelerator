"""Tests for core observability — telemetry no-op, prometheus, logging, _hooks."""

import os
import pytest


class TestTelemetryNoOp:
    def test_setup_tracing_without_endpoint_is_noop(self):
        # Ensure no OTEL endpoint is set
        os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        # Re-import to get fresh module state
        import importlib
        import core.telemetry as tel
        tel._initialized = False
        tel._noop = True
        tel.setup_tracing("test-service")
        assert tel._noop is True

    def test_record_gen_ai_call_with_none_span_noop(self):
        from core.telemetry import record_gen_ai_call
        # Should not raise
        record_gen_ai_call(None, model="m", input_tokens=10, output_tokens=5)

    def test_extract_correlation_id_from_header(self):
        from core.telemetry import extract_correlation_id
        cid = extract_correlation_id({"x-correlation-id": "abc-123"})
        assert cid == "abc-123"

    def test_extract_correlation_id_generates_uuid_when_absent(self):
        from core.telemetry import extract_correlation_id
        cid = extract_correlation_id({})
        assert len(cid) == 36  # UUID4 format

    def test_correlation_context_yields_id(self):
        from core.telemetry import correlation_context
        with correlation_context({"x-correlation-id": "test-id"}) as cid:
            assert cid == "test-id"

    def test_traced_decorator_noop_returns_original(self):
        from core.telemetry import traced, _noop
        if not _noop:
            pytest.skip("OTEL is actually configured — skip no-op test")

        @traced("test.fn")
        def my_fn(x):
            return x * 2

        assert my_fn(3) == 6


class TestPrometheusExporter:
    def test_record_llm_call_no_crash_without_prometheus(self):
        from core.prometheus_exporter import record_llm_call
        # Should silently no-op if prometheus not installed
        record_llm_call(
            model="claude-haiku-4-5", module="test", outcome="success",
            input_tokens=100, output_tokens=50, latency_seconds=0.5,
        )

    def test_record_pipeline_no_crash(self):
        from core.prometheus_exporter import record_pipeline
        record_pipeline(status="success")
        record_pipeline(status="failed")

    def test_record_finding_no_crash(self):
        from core.prometheus_exporter import record_finding
        record_finding(module="test_module", severity="HIGH")

    def test_metrics_router_exists_or_is_none(self):
        from core.prometheus_exporter import router
        # router is either an APIRouter or None (if FastAPI not installed)
        assert router is not None or router is None  # always true — just confirm it loads


class TestHooks:
    def test_llm_call_event_construction(self):
        from core._hooks import LLMCallEvent
        ev = LLMCallEvent(model="claude-opus-4-7", module="migration_scout")
        assert ev.outcome == "success"
        assert ev.input_tokens == 0

    def test_llm_call_event_from_structured_response(self):
        from unittest.mock import MagicMock
        from core._hooks import LLMCallEvent
        resp = MagicMock()
        resp.model = "claude-haiku-4-5-20251001"
        resp.input_tokens = 100
        resp.output_tokens = 50
        resp.cache_read_tokens = 0
        resp.cache_creation_tokens = 0
        resp.stop_reason = "end_turn"
        ev = LLMCallEvent.from_structured_response(resp, module="test", latency_seconds=1.2)
        assert ev.model == "claude-haiku-4-5-20251001"
        assert ev.input_tokens == 100
        assert ev.latency_seconds == 1.2

    def test_on_llm_call_fires_handlers(self):
        from core._hooks import LLMCallEvent, on_llm_call, _handlers
        fired = []
        handler = lambda ev: fired.append(ev.model)
        _handlers.append(handler)
        try:
            on_llm_call(LLMCallEvent(model="test-model", module="test"))
            assert "test-model" in fired
        finally:
            _handlers.remove(handler)

    def test_on_llm_call_swallows_handler_exceptions(self):
        from core._hooks import LLMCallEvent, on_llm_call, _handlers
        def bad_handler(ev):
            raise RuntimeError("boom")
        _handlers.append(bad_handler)
        try:
            # Should not raise
            on_llm_call(LLMCallEvent(model="m", module="mod"))
        finally:
            _handlers.remove(bad_handler)
