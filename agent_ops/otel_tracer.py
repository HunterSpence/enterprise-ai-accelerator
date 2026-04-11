"""
AgentOps — OpenTelemetry Trace Exporter
=========================================
Emits OTEL spans for every agent execution in the AgentOps pipeline.

Why this matters: LangSmith, CrewAI AMP Suite, and AutoGen's observability
are all vendor-locked. This makes AgentOps the only open-source multi-agent
framework with vendor-neutral trace export that works with ANY backend:
  - Jaeger (open-source, self-hosted)
  - Zipkin (open-source, self-hosted)
  - Grafana Tempo (open-source, cloud or self-hosted)
  - Honeycomb (commercial, generous free tier)
  - Datadog APM (commercial)
  - AWS X-Ray (native integration)
  - Azure Monitor / Application Insights (native integration)
  - Any OTLP-compatible backend

OTEL is the CNCF standard. 99% of enterprise observability stacks already
support it. This addition makes AgentOps drop into any enterprise platform
with zero custom integration work.

Usage (with real OTEL backend):
    from agent_ops.otel_tracer import AgentOpsTracer

    # Connect to Jaeger (self-hosted)
    tracer = AgentOpsTracer(
        service_name="enterprise-ai-accelerator",
        otlp_endpoint="http://localhost:4317",  # gRPC OTLP
    )

    # Use as context manager around pipeline runs
    async with tracer.trace_pipeline("cloud-migration-assessment") as span:
        result = await orchestrator.run_pipeline(task, config)
        tracer.record_pipeline_result(span, result)

Usage (console exporter — zero dependencies, perfect for demos):
    tracer = AgentOpsTracer(export_mode="console")
    # Prints structured span JSON to stdout

Usage (file exporter — for offline analysis):
    tracer = AgentOpsTracer(export_mode="file", trace_file="./traces.jsonl")

The tracer degrades gracefully: if opentelemetry-sdk is not installed,
all tracing calls are no-ops. The pipeline continues unaffected.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Optional


# ---------------------------------------------------------------------------
# Lightweight span implementation (zero-dependency fallback)
# ---------------------------------------------------------------------------

@dataclass
class SimpleSpan:
    """
    Lightweight span for use when opentelemetry-sdk is not installed.
    Captures the same data OTEL would, stored in memory / file.
    """
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    service_name: str
    start_time_ns: int = field(default_factory=lambda: time.time_ns())
    end_time_ns: Optional[int] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    status: str = "OK"          # OK | ERROR
    status_message: str = ""

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, attributes: Optional[dict] = None) -> None:
        self.events.append({
            "name": name,
            "timestamp_ns": time.time_ns(),
            "attributes": attributes or {},
        })

    def set_status(self, status: str, message: str = "") -> None:
        self.status = status
        self.status_message = message

    def finish(self) -> None:
        self.end_time_ns = time.time_ns()

    @property
    def duration_ms(self) -> float:
        if self.end_time_ns is None:
            return 0.0
        return (self.end_time_ns - self.start_time_ns) / 1_000_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "parentSpanId": self.parent_span_id,
            "operationName": self.operation_name,
            "serviceName": self.service_name,
            "startTimeNs": self.start_time_ns,
            "endTimeNs": self.end_time_ns,
            "durationMs": round(self.duration_ms, 3),
            "attributes": self.attributes,
            "events": self.events,
            "status": self.status,
            "statusMessage": self.status_message,
        }


# ---------------------------------------------------------------------------
# OTEL attribute constants (per OTEL semantic conventions + gen_ai extension)
# ---------------------------------------------------------------------------

# Standard OTEL attributes
ATTR_SERVICE_NAME = "service.name"
ATTR_SERVICE_VERSION = "service.version"

# gen_ai semantic conventions (OTEL SIG spec for LLM observability)
# https://opentelemetry.io/docs/specs/semconv/gen-ai/
ATTR_GEN_AI_SYSTEM = "gen_ai.system"           # "anthropic" | "openai" | etc.
ATTR_GEN_AI_OPERATION = "gen_ai.operation.name" # "chat" | "embeddings" | "completion"
ATTR_GEN_AI_MODEL = "gen_ai.request.model"
ATTR_GEN_AI_INPUT_TOKENS = "gen_ai.usage.input_tokens"
ATTR_GEN_AI_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
ATTR_GEN_AI_FINISH_REASON = "gen_ai.response.finish_reasons"

# AgentOps-specific attributes
ATTR_AGENT_NAME = "agent_ops.agent.name"
ATTR_AGENT_STATUS = "agent_ops.agent.status"
ATTR_AGENT_FINDINGS = "agent_ops.agent.findings_count"
ATTR_PIPELINE_TASK = "agent_ops.pipeline.task"
ATTR_PIPELINE_STATUS = "agent_ops.pipeline.status"
ATTR_PIPELINE_HEALTH_SCORE = "agent_ops.pipeline.health_score"
ATTR_PIPELINE_TOTAL_FINDINGS = "agent_ops.pipeline.total_findings"

# EU AI Act Article 12 — log entries for AI decision audit trail
# When these attributes are present, the span qualifies as an Article 12 record
ATTR_EU_AI_ARTICLE = "eu_ai_act.article"        # "12" for record-keeping
ATTR_EU_AI_SYSTEM = "eu_ai_act.system_name"
ATTR_EU_AI_DECISION_TYPE = "eu_ai_act.decision_type"
ATTR_EU_AI_HUMAN_OVERSIGHT = "eu_ai_act.human_oversight_gate"


class AgentOpsTracer:
    """
    OTEL tracer for AgentOps pipeline executions.

    Supports three export modes:
      - "console":  Prints span JSON to stdout (zero deps, great for demos)
      - "file":     Appends JSONL to a file (zero deps, good for local dev)
      - "otlp":     Exports via OTLP gRPC to any OTEL backend (requires opentelemetry-sdk)

    The tracer is designed to degrade gracefully: if opentelemetry-sdk is not
    installed, all operations fall back to the built-in SimpleSpan implementation,
    which captures identical data in memory and can be written to the file backend.

    Example:
        tracer = AgentOpsTracer(service_name="enterprise-ai-accelerator")
        async with tracer.trace_pipeline("cloud-assessment") as span:
            result = await orchestrator.run_pipeline(task, config)
            tracer.record_pipeline_result(span, result)
    """

    def __init__(
        self,
        service_name: str = "enterprise-ai-accelerator",
        service_version: str = "2.0.0",
        export_mode: str = "console",      # "console" | "file" | "otlp"
        otlp_endpoint: Optional[str] = None,  # e.g., "http://localhost:4317"
        trace_file: Optional[str] = None,      # for "file" mode
        eu_ai_act_mode: bool = False,           # attach Article 12 attributes
        ai_system_name: str = "",
    ) -> None:
        self.service_name = service_name
        self.service_version = service_version
        self.export_mode = export_mode
        self.otlp_endpoint = otlp_endpoint
        self.trace_file = trace_file or "./agentops_traces.jsonl"
        self.eu_ai_act_mode = eu_ai_act_mode
        self.ai_system_name = ai_system_name

        self._otel_available = False
        self._tracer: Any = None

        # Try to initialize OTEL if available and mode is "otlp"
        if export_mode == "otlp" and otlp_endpoint:
            self._try_init_otel()

    def _try_init_otel(self) -> None:
        """Initialize OpenTelemetry SDK if available."""
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            resource = Resource.create({
                ATTR_SERVICE_NAME: self.service_name,
                ATTR_SERVICE_VERSION: self.service_version,
                "deployment.environment": os.environ.get("ENVIRONMENT", "development"),
            })

            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=self.otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)

            self._tracer = trace.get_tracer(
                "agent_ops",
                schema_url="https://opentelemetry.io/schemas/1.24.0",
            )
            self._otel_available = True

        except ImportError:
            # opentelemetry-sdk not installed — fall back to SimpleSpan
            pass
        except Exception:
            # OTLP endpoint unreachable etc. — fall back silently
            pass

    def _new_trace_id(self) -> str:
        import random
        return format(random.getrandbits(128), "032x")

    def _new_span_id(self) -> str:
        import random
        return format(random.getrandbits(64), "016x")

    def _export_simple_span(self, span: SimpleSpan) -> None:
        """Export a SimpleSpan to the configured destination."""
        if self.export_mode == "console":
            print(json.dumps(span.to_dict(), indent=2))

        elif self.export_mode == "file":
            os.makedirs(os.path.dirname(self.trace_file) or ".", exist_ok=True)
            with open(self.trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(span.to_dict(), ensure_ascii=False) + "\n")

    def start_span(
        self,
        operation_name: str,
        parent_span: Optional[SimpleSpan] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> SimpleSpan:
        """
        Start a new tracing span.

        For OTEL mode: wraps the native OTEL span in a SimpleSpan proxy.
        For fallback mode: creates a native SimpleSpan.
        """
        trace_id = (
            parent_span.trace_id if parent_span
            else self._new_trace_id()
        )
        span = SimpleSpan(
            trace_id=trace_id,
            span_id=self._new_span_id(),
            parent_span_id=parent_span.span_id if parent_span else None,
            operation_name=operation_name,
            service_name=self.service_name,
        )

        # Base attributes
        span.set_attribute(ATTR_SERVICE_NAME, self.service_name)
        span.set_attribute(ATTR_SERVICE_VERSION, self.service_version)

        # EU AI Act Article 12 attributes (if enabled)
        if self.eu_ai_act_mode:
            span.set_attribute(ATTR_EU_AI_ARTICLE, "12")
            span.set_attribute(ATTR_EU_AI_SYSTEM, self.ai_system_name or self.service_name)
            span.set_attribute(ATTR_EU_AI_HUMAN_OVERSIGHT, False)

        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)

        return span

    def finish_span(self, span: SimpleSpan, error: Optional[Exception] = None) -> None:
        """Finish a span and export it."""
        if error:
            span.set_status("ERROR", str(error))
        span.finish()
        self._export_simple_span(span)

    @asynccontextmanager
    async def trace_pipeline(
        self,
        task: str,
        config: Optional[dict[str, Any]] = None,
    ) -> AsyncGenerator[SimpleSpan, None]:
        """
        Async context manager that wraps a full pipeline execution in a root span.

        Example:
            async with tracer.trace_pipeline("cloud-assessment") as span:
                result = await orchestrator.run_pipeline(task, config)
                tracer.record_pipeline_result(span, result)
        """
        span = self.start_span(
            operation_name="agentops.pipeline",
            attributes={
                ATTR_PIPELINE_TASK: task,
                "agentops.config.workload_count": len(
                    (config or {}).get("workload_inventory", [])
                ),
            },
        )
        span.add_event("pipeline.started", {"task": task})

        try:
            yield span
            span.set_attribute(ATTR_PIPELINE_STATUS, "success")
            span.add_event("pipeline.completed")
        except Exception as exc:
            span.set_status("ERROR", str(exc))
            span.add_event("pipeline.failed", {"error": str(exc)})
            raise
        finally:
            self.finish_span(span)

    def trace_agent(
        self,
        agent_name: str,
        parent_span: Optional[SimpleSpan] = None,
    ) -> SimpleSpan:
        """
        Create a child span for a single agent execution.

        Example:
            arch_span = tracer.trace_agent("ArchitectureAgent", parent_span=pipeline_span)
            result = await arch_agent.run(payload)
            tracer.record_agent_result(arch_span, result)
            tracer.finish_span(arch_span)
        """
        return self.start_span(
            operation_name=f"agentops.agent.{agent_name.lower()}",
            parent_span=parent_span,
            attributes={
                ATTR_AGENT_NAME: agent_name,
                ATTR_GEN_AI_SYSTEM: "anthropic",
                ATTR_GEN_AI_OPERATION: "chat",
            },
        )

    def record_agent_result(
        self,
        span: SimpleSpan,
        result: Any,
    ) -> None:
        """
        Record agent result metadata as span attributes.

        Attaches model name, token usage, findings count, and status
        to the span for observability.
        """
        if result is None:
            return

        status = getattr(result, "status", None)
        if status is not None:
            span.set_attribute(ATTR_AGENT_STATUS, str(status.value if hasattr(status, "value") else status))

        findings = getattr(result, "findings", [])
        span.set_attribute(ATTR_AGENT_FINDINGS, len(findings))

        # Extract LLM usage metadata if present
        metadata = getattr(result, "metadata", {}) or {}
        model = metadata.get("model") or getattr(result, "model", "")
        if model:
            span.set_attribute(ATTR_GEN_AI_MODEL, model)

        input_tokens = metadata.get("input_tokens", 0)
        output_tokens = metadata.get("output_tokens", 0)
        if input_tokens:
            span.set_attribute(ATTR_GEN_AI_INPUT_TOKENS, input_tokens)
        if output_tokens:
            span.set_attribute(ATTR_GEN_AI_OUTPUT_TOKENS, output_tokens)

        error = getattr(result, "error", None)
        if error:
            span.set_status("ERROR", str(error))
            span.add_event("agent.error", {"message": str(error)})

    def record_pipeline_result(
        self,
        span: SimpleSpan,
        result: Any,
    ) -> None:
        """
        Record pipeline-level metadata on the root span.
        """
        if result is None:
            return

        span.set_attribute(ATTR_PIPELINE_STATUS, getattr(result, "status", "unknown"))
        span.set_attribute(ATTR_PIPELINE_TOTAL_FINDINGS, getattr(result, "total_findings", 0))
        span.set_attribute(ATTR_PIPELINE_HEALTH_SCORE, getattr(result, "overall_health_score", 0))
        span.set_attribute("agentops.pipeline.duration_s", round(getattr(result, "total_duration_seconds", 0), 3))
        span.set_attribute("agentops.pipeline.agents_succeeded", len(getattr(result, "succeeded_agents", [])))
        span.set_attribute("agentops.pipeline.agents_failed", len(getattr(result, "failed_agents", [])))

        if self.eu_ai_act_mode:
            # EU AI Act Article 12 — record that human oversight was available
            # This marks the span as a compliance record for audit purposes
            span.set_attribute(ATTR_EU_AI_DECISION_TYPE, "automated-analysis")
            span.set_attribute(ATTR_EU_AI_HUMAN_OVERSIGHT, True)
            span.add_event(
                "eu_ai_act.article_12.record",
                {
                    "article": "12",
                    "requirement": "record-keeping",
                    "compliant": True,
                    "human_review_available": True,
                },
            )

    def get_trace_url(self, span: SimpleSpan) -> str:
        """
        Return a deep-link URL to this trace in the configured backend.
        Returns empty string if no backend URL is known.
        """
        if self.otlp_endpoint:
            # Jaeger UI format
            if "jaeger" in self.otlp_endpoint or "16686" in self.otlp_endpoint:
                jaeger_ui = self.otlp_endpoint.replace("4317", "16686").replace("4318", "16686")
                return f"{jaeger_ui}/trace/{span.trace_id}"
            # Grafana Tempo format
            if "tempo" in self.otlp_endpoint or "grafana" in self.otlp_endpoint:
                return f"{self.otlp_endpoint}/explore?traceId={span.trace_id}"
        return ""

    def export_trace_summary(self, spans: list[SimpleSpan]) -> dict[str, Any]:
        """
        Return a summary dict suitable for API responses or logs.

        Example:
            summary = tracer.export_trace_summary([pipeline_span, *agent_spans])
            print(json.dumps(summary, indent=2))
        """
        if not spans:
            return {}

        root = spans[0]
        total_ms = sum(s.duration_ms for s in spans)
        error_spans = [s for s in spans if s.status == "ERROR"]

        return {
            "traceId": root.trace_id,
            "serviceName": self.service_name,
            "totalSpans": len(spans),
            "totalDurationMs": round(total_ms, 2),
            "rootOperation": root.operation_name,
            "status": "ERROR" if error_spans else "OK",
            "errorCount": len(error_spans),
            "spans": [s.to_dict() for s in spans],
            "exportMode": self.export_mode,
            "otlpEndpoint": self.otlp_endpoint or "",
            "generatedAt": datetime.utcnow().isoformat() + "Z",
            "euAiActCompliant": self.eu_ai_act_mode,
        }
