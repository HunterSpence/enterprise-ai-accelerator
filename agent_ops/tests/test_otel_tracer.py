"""
Tests for agent_ops/otel_tracer.py
"""
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agent_ops.otel_tracer import (
    AgentOpsTracer,
    SimpleSpan,
    ATTR_SERVICE_NAME,
    ATTR_SERVICE_VERSION,
    ATTR_AGENT_NAME,
    ATTR_EU_AI_ARTICLE,
    ATTR_EU_AI_SYSTEM,
    ATTR_EU_AI_HUMAN_OVERSIGHT,
    ATTR_GEN_AI_SYSTEM,
    ATTR_PIPELINE_TASK,
    ATTR_PIPELINE_STATUS,
    ATTR_AGENT_FINDINGS,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_INPUT_TOKENS,
    ATTR_GEN_AI_OUTPUT_TOKENS,
)


# ---------------------------------------------------------------------------
# SimpleSpan tests
# ---------------------------------------------------------------------------

class TestSimpleSpan:

    def _make_span(self, operation="test.op", service="test-service"):
        return SimpleSpan(
            trace_id="abc123",
            span_id="def456",
            parent_span_id=None,
            operation_name=operation,
            service_name=service,
        )

    def test_span_creation(self):
        span = self._make_span()
        assert span.trace_id == "abc123"
        assert span.span_id == "def456"
        assert span.operation_name == "test.op"
        assert span.service_name == "test-service"

    def test_span_default_status_ok(self):
        span = self._make_span()
        assert span.status == "OK"

    def test_span_default_no_end_time(self):
        span = self._make_span()
        assert span.end_time_ns is None

    def test_set_attribute(self):
        span = self._make_span()
        span.set_attribute("key", "value")
        assert span.attributes["key"] == "value"

    def test_set_attribute_overwrite(self):
        span = self._make_span()
        span.set_attribute("key", "old")
        span.set_attribute("key", "new")
        assert span.attributes["key"] == "new"

    def test_add_event(self):
        span = self._make_span()
        span.add_event("something.happened", {"detail": "x"})
        assert len(span.events) == 1
        assert span.events[0]["name"] == "something.happened"
        assert span.events[0]["attributes"]["detail"] == "x"

    def test_add_event_no_attributes(self):
        span = self._make_span()
        span.add_event("simple.event")
        assert span.events[0]["attributes"] == {}

    def test_set_status_error(self):
        span = self._make_span()
        span.set_status("ERROR", "something broke")
        assert span.status == "ERROR"
        assert span.status_message == "something broke"

    def test_finish_sets_end_time(self):
        span = self._make_span()
        assert span.end_time_ns is None
        span.finish()
        assert span.end_time_ns is not None
        assert span.end_time_ns >= span.start_time_ns

    def test_duration_ms_before_finish_is_zero(self):
        span = self._make_span()
        assert span.duration_ms == 0.0

    def test_duration_ms_after_finish(self):
        span = self._make_span()
        span.finish()
        assert span.duration_ms >= 0.0

    def test_to_dict_shape(self):
        span = self._make_span()
        span.finish()
        d = span.to_dict()
        for key in ("traceId", "spanId", "operationName", "serviceName",
                    "startTimeNs", "endTimeNs", "durationMs", "attributes",
                    "events", "status"):
            assert key in d

    def test_to_dict_values(self):
        span = self._make_span()
        span.set_attribute("foo", "bar")
        span.finish()
        d = span.to_dict()
        assert d["traceId"] == "abc123"
        assert d["attributes"]["foo"] == "bar"
        assert d["status"] == "OK"

    def test_parent_span_id_in_dict(self):
        span = SimpleSpan(
            trace_id="t1", span_id="s1", parent_span_id="p1",
            operation_name="child.op", service_name="svc"
        )
        assert span.to_dict()["parentSpanId"] == "p1"


# ---------------------------------------------------------------------------
# AgentOpsTracer — construction
# ---------------------------------------------------------------------------

class TestTracerConstruction:

    def test_default_construction(self):
        tracer = AgentOpsTracer()
        assert tracer.service_name == "enterprise-ai-accelerator"
        assert tracer.export_mode == "console"

    def test_custom_service_name(self):
        tracer = AgentOpsTracer(service_name="my-service")
        assert tracer.service_name == "my-service"

    def test_eu_ai_act_mode_off_by_default(self):
        tracer = AgentOpsTracer()
        assert tracer.eu_ai_act_mode is False

    def test_eu_ai_act_mode_enabled(self):
        tracer = AgentOpsTracer(eu_ai_act_mode=True, ai_system_name="my-ai")
        assert tracer.eu_ai_act_mode is True
        assert tracer.ai_system_name == "my-ai"

    def test_file_export_mode(self):
        tracer = AgentOpsTracer(export_mode="file", trace_file="./test_traces.jsonl")
        assert tracer.export_mode == "file"
        assert "test_traces.jsonl" in tracer.trace_file

    def test_otel_not_available_without_package(self):
        # In this environment opentelemetry-sdk may not be installed;
        # either way the tracer should still initialise without crashing.
        tracer = AgentOpsTracer(export_mode="otlp", otlp_endpoint="http://localhost:4317")
        assert tracer is not None


# ---------------------------------------------------------------------------
# start_span / finish_span
# ---------------------------------------------------------------------------

class TestSpanLifecycle:

    def test_start_span_returns_simple_span(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("my.operation")
        assert isinstance(span, SimpleSpan)

    def test_start_span_sets_service_name(self):
        tracer = AgentOpsTracer(service_name="svc", export_mode="console")
        span = tracer.start_span("op")
        assert span.attributes[ATTR_SERVICE_NAME] == "svc"

    def test_start_span_unique_ids(self):
        tracer = AgentOpsTracer(export_mode="console")
        span1 = tracer.start_span("op1")
        span2 = tracer.start_span("op2")
        assert span1.span_id != span2.span_id
        # Without parent, trace IDs may also differ
        assert span1.trace_id != span2.trace_id

    def test_start_span_with_parent_inherits_trace_id(self):
        tracer = AgentOpsTracer(export_mode="console")
        parent = tracer.start_span("parent.op")
        child = tracer.start_span("child.op", parent_span=parent)
        assert child.trace_id == parent.trace_id
        assert child.parent_span_id == parent.span_id

    def test_start_span_no_parent_has_none_parent_id(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("op")
        assert span.parent_span_id is None

    def test_start_span_with_attributes(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("op", attributes={"custom.key": "custom.value"})
        assert span.attributes["custom.key"] == "custom.value"

    def test_finish_span_sets_end_time(self, capsys):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("op")
        tracer.finish_span(span)
        assert span.end_time_ns is not None

    def test_finish_span_error_sets_status(self, capsys):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("op")
        tracer.finish_span(span, error=ValueError("test error"))
        assert span.status == "ERROR"
        assert "test error" in span.status_message

    def test_finish_span_exports_console(self, capsys):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("op")
        tracer.finish_span(span)
        out = capsys.readouterr().out
        assert "op" in out or len(out) > 0

    def test_finish_span_exports_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_file = os.path.join(tmp, "traces.jsonl")
            tracer = AgentOpsTracer(export_mode="file", trace_file=trace_file)
            span = tracer.start_span("op")
            tracer.finish_span(span)
            assert os.path.exists(trace_file)
            with open(trace_file) as f:
                lines = [json.loads(l) for l in f if l.strip()]
            assert len(lines) == 1
            assert lines[0]["operationName"] == "op"


# ---------------------------------------------------------------------------
# EU AI Act mode
# ---------------------------------------------------------------------------

class TestEUAIActMode:

    def test_eu_ai_act_attributes_set_on_span(self):
        tracer = AgentOpsTracer(
            export_mode="console",
            eu_ai_act_mode=True,
            ai_system_name="risk-model",
        )
        span = tracer.start_span("pipeline.run")
        assert span.attributes[ATTR_EU_AI_ARTICLE] == "12"
        assert span.attributes[ATTR_EU_AI_SYSTEM] == "risk-model"

    def test_eu_ai_act_human_oversight_initially_false(self):
        tracer = AgentOpsTracer(export_mode="console", eu_ai_act_mode=True)
        span = tracer.start_span("op")
        assert span.attributes[ATTR_EU_AI_HUMAN_OVERSIGHT] is False

    def test_eu_ai_act_off_no_eu_attrs(self):
        tracer = AgentOpsTracer(export_mode="console", eu_ai_act_mode=False)
        span = tracer.start_span("op")
        assert ATTR_EU_AI_ARTICLE not in span.attributes

    def test_record_pipeline_result_sets_human_oversight_true(self):
        tracer = AgentOpsTracer(export_mode="console", eu_ai_act_mode=True)
        span = tracer.start_span("pipeline.run")
        result = SimpleNamespace(
            status="success",
            total_findings=0,
            overall_health_score=95,
            total_duration_seconds=10.5,
            succeeded_agents=["arch"],
            failed_agents=[],
        )
        tracer.record_pipeline_result(span, result)
        assert span.attributes[ATTR_EU_AI_HUMAN_OVERSIGHT] is True

    def test_record_pipeline_result_adds_article12_event(self):
        tracer = AgentOpsTracer(export_mode="console", eu_ai_act_mode=True)
        span = tracer.start_span("pipeline.run")
        result = SimpleNamespace(
            status="success",
            total_findings=0,
            overall_health_score=95,
            total_duration_seconds=5.0,
            succeeded_agents=[],
            failed_agents=[],
        )
        tracer.record_pipeline_result(span, result)
        event_names = [e["name"] for e in span.events]
        assert "eu_ai_act.article_12.record" in event_names


# ---------------------------------------------------------------------------
# trace_agent
# ---------------------------------------------------------------------------

class TestTraceAgent:

    def test_trace_agent_returns_span(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.trace_agent("ArchitectureAgent")
        assert isinstance(span, SimpleSpan)

    def test_trace_agent_sets_name_attribute(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.trace_agent("PolicyAgent")
        assert span.attributes[ATTR_AGENT_NAME] == "PolicyAgent"

    def test_trace_agent_with_parent(self):
        tracer = AgentOpsTracer(export_mode="console")
        parent = tracer.start_span("pipeline.run")
        child = tracer.trace_agent("ChildAgent", parent_span=parent)
        assert child.trace_id == parent.trace_id
        assert child.parent_span_id == parent.span_id

    def test_trace_agent_sets_gen_ai_system(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.trace_agent("SomeAgent")
        assert span.attributes[ATTR_GEN_AI_SYSTEM] == "anthropic"

    def test_trace_agent_operation_name_format(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.trace_agent("MyAgent")
        assert "myagent" in span.operation_name


# ---------------------------------------------------------------------------
# trace_pipeline async context manager
# ---------------------------------------------------------------------------

class TestTracePipeline:

    def test_trace_pipeline_yields_span(self):
        tracer = AgentOpsTracer(export_mode="console")

        async def _run():
            async with tracer.trace_pipeline("test-task") as span:
                assert isinstance(span, SimpleSpan)
                assert span.attributes[ATTR_PIPELINE_TASK] == "test-task"

        asyncio.run(_run())

    def test_trace_pipeline_sets_success_status(self):
        tracer = AgentOpsTracer(export_mode="console")
        captured = {}

        async def _run():
            async with tracer.trace_pipeline("task") as span:
                captured["span"] = span

        asyncio.run(_run())
        assert captured["span"].attributes.get(ATTR_PIPELINE_STATUS) == "success"

    def test_trace_pipeline_finishes_span(self):
        tracer = AgentOpsTracer(export_mode="console")
        captured = {}

        async def _run():
            async with tracer.trace_pipeline("task") as span:
                captured["span"] = span

        asyncio.run(_run())
        assert captured["span"].end_time_ns is not None

    def test_trace_pipeline_propagates_exception(self):
        tracer = AgentOpsTracer(export_mode="console")

        async def _run():
            with pytest.raises(ValueError):
                async with tracer.trace_pipeline("task") as span:
                    raise ValueError("pipeline failed")

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# record_agent_result
# ---------------------------------------------------------------------------

class TestRecordAgentResult:

    def test_record_agent_result_sets_findings_count(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("agent.op")
        result = SimpleNamespace(
            status="success",
            findings=["f1", "f2", "f3"],
            metadata={},
            error=None,
        )
        tracer.record_agent_result(span, result)
        assert span.attributes[ATTR_AGENT_FINDINGS] == 3

    def test_record_agent_result_sets_model(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("agent.op")
        result = SimpleNamespace(
            status="success",
            findings=[],
            metadata={"model": "claude-sonnet-4-6", "input_tokens": 500, "output_tokens": 100},
            error=None,
        )
        tracer.record_agent_result(span, result)
        assert span.attributes[ATTR_GEN_AI_MODEL] == "claude-sonnet-4-6"

    def test_record_agent_result_sets_token_counts(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("agent.op")
        result = SimpleNamespace(
            status=None,
            findings=[],
            metadata={"input_tokens": 1000, "output_tokens": 200},
            error=None,
        )
        tracer.record_agent_result(span, result)
        assert span.attributes[ATTR_GEN_AI_INPUT_TOKENS] == 1000
        assert span.attributes[ATTR_GEN_AI_OUTPUT_TOKENS] == 200

    def test_record_agent_result_none_is_noop(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("agent.op")
        tracer.record_agent_result(span, None)
        assert ATTR_AGENT_FINDINGS not in span.attributes

    def test_record_agent_result_error_sets_status(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("agent.op")
        result = SimpleNamespace(
            status=None,
            findings=[],
            metadata={},
            error="Connection timeout",
        )
        tracer.record_agent_result(span, result)
        assert span.status == "ERROR"


# ---------------------------------------------------------------------------
# export_trace_summary
# ---------------------------------------------------------------------------

class TestExportTraceSummary:

    def test_empty_spans_returns_empty_dict(self):
        tracer = AgentOpsTracer(export_mode="console")
        assert tracer.export_trace_summary([]) == {}

    def test_summary_shape(self):
        tracer = AgentOpsTracer(service_name="svc", export_mode="console")
        span = tracer.start_span("root.op")
        span.finish()
        summary = tracer.export_trace_summary([span])
        for key in ("traceId", "serviceName", "totalSpans", "status", "spans"):
            assert key in summary

    def test_summary_status_ok_no_errors(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("op")
        span.finish()
        summary = tracer.export_trace_summary([span])
        assert summary["status"] == "OK"
        assert summary["errorCount"] == 0

    def test_summary_status_error_when_error_span(self):
        tracer = AgentOpsTracer(export_mode="console")
        span = tracer.start_span("op")
        span.set_status("ERROR", "bad")
        span.finish()
        summary = tracer.export_trace_summary([span])
        assert summary["status"] == "ERROR"
        assert summary["errorCount"] == 1
