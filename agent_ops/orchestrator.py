"""
agent_ops/orchestrator.py
=========================

Coordinator agent that decomposes a high-level enterprise IT task into
parallel sub-agent work, collects results, and synthesizes a final output.

Opus 4.7 upgrade (2026-04):
  - Coordinator promoted from Opus 4.6 → Opus 4.7 (``claude-opus-4-7``)
  - Coordinator plan now uses the ``core.AIClient`` wrapper so the system
    prompt rides the 5-minute ephemeral cache (repeated runs pay once)
  - Coordinator plan is produced via forced tool-use — the response is
    schema-validated rather than parsed as free text
  - Per-agent token usage (including cache reads) is surfaced in the
    PipelineResult so executive dashboards can show the cost-efficiency
    story alongside the reasoning story

Architecture:
  - Opus 4.7 coordinator decomposes the task
  - Architecture / Migration / Compliance workers run in parallel (Haiku 4.5)
  - Sonnet 4.6 ReportAgent synthesizes the final briefing
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import anthropic

from agent_ops.agents import (
    AgentResult,
    AgentStatus,
    ArchitectureAgent,
    ComplianceAgent,
    MigrationAgent,
    ReportAgent,
)
from agent_ops.otel_tracer import AgentOpsTracer
from core import AIClient, MODEL_COORDINATOR

logger = logging.getLogger(__name__)

# Opus 4.7 — the platform's coordinator-tier model (was 4-6 pre-upgrade).
_COORDINATOR_MODEL = MODEL_COORDINATOR


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class AgentActivity:
    """Single log entry emitted during pipeline execution."""
    timestamp: str
    agent: str
    event: str  # started | completed | failed
    detail: str = ""

    @classmethod
    def now(cls, agent: str, event: str, detail: str = "") -> "AgentActivity":
        return cls(
            timestamp=datetime.utcnow().strftime("%H:%M:%S.%f")[:-3],
            agent=agent,
            event=event,
            detail=detail,
        )


@dataclass
class TokenUsageSummary:
    """Aggregated token usage across the pipeline — surfaces the Opus 4.7
    prompt-cache efficiency in cost-conscious executive dashboards."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cache_hit_ratio(self) -> float:
        denom = self.input_tokens + self.cache_read_tokens
        return self.cache_read_tokens / denom if denom else 0.0


@dataclass
class PipelineResult:
    task: str
    status: str  # success | partial | failed
    total_duration_seconds: float
    coordinator_plan: str
    coordinator_model: str = _COORDINATOR_MODEL
    agent_results: dict[str, AgentResult] = field(default_factory=dict)
    activity_log: list[AgentActivity] = field(default_factory=list)
    executive_summary: str = ""
    top_risks: list[str] = field(default_factory=list)
    strategic_recommendations: list[str] = field(default_factory=list)
    quick_wins: list[str] = field(default_factory=list)
    roadmap_90_day: list[dict[str, Any]] = field(default_factory=list)
    overall_health_score: int = 0
    total_findings: int = 0
    token_usage: TokenUsageSummary = field(default_factory=TokenUsageSummary)

    @property
    def succeeded_agents(self) -> list[str]:
        return [
            name
            for name, r in self.agent_results.items()
            if r.status == AgentStatus.DONE
        ]

    @property
    def failed_agents(self) -> list[str]:
        return [
            name
            for name, r in self.agent_results.items()
            if r.status == AgentStatus.FAILED
        ]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

# Schema for the coordinator's structured work-plan output.
_COORDINATOR_PLAN_SCHEMA = {
    "type": "object",
    "required": ["plan_summary", "decomposition"],
    "properties": {
        "plan_summary": {
            "type": "string",
            "description": "3-4 sentence executive-ready plan.",
        },
        "decomposition": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["agent", "focus", "priority"],
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": [
                            "ArchitectureAgent",
                            "MigrationAgent",
                            "ComplianceAgent",
                            "ReportAgent",
                        ],
                    },
                    "focus": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                },
            },
        },
        "estimated_runtime_seconds": {"type": "integer", "minimum": 0},
    },
}


class Orchestrator:
    """Coordinator agent: receives a high-level enterprise task, delegates
    to specialized sub-agents in parallel, and synthesizes a unified output.

    Usage:
        client = anthropic.AsyncAnthropic(api_key="...")
        orch = Orchestrator(client)
        result = await orch.run_pipeline(task, config)
    """

    def __init__(
        self,
        client: anthropic.AsyncAnthropic | AIClient,
        on_activity: Callable[[AgentActivity], None] | None = None,
        tracer: AgentOpsTracer | None = None,
    ) -> None:
        self._ai = client if isinstance(client, AIClient) else AIClient(client)
        self._client = self._ai.raw  # backwards compatibility for callers reading ._client
        self._on_activity = on_activity or (lambda _: None)
        self._arch_agent = ArchitectureAgent(self._ai)
        self._mig_agent = MigrationAgent(self._ai)
        self._comp_agent = ComplianceAgent(self._ai)
        self._report_agent = ReportAgent(self._ai)
        self._tracer = tracer or AgentOpsTracer(export_mode="console")

    async def run_pipeline(
        self, task: str, config: dict[str, Any]
    ) -> PipelineResult:
        pipeline_start = time.monotonic()
        activity_log: list[AgentActivity] = []

        def log(agent: str, event: str, detail: str = "") -> None:
            entry = AgentActivity.now(agent, event, detail)
            activity_log.append(entry)
            self._on_activity(entry)
            logger.info("[%s] %s %s %s", entry.timestamp, agent, event, detail)

        # 1. Coordinator plans the work -------------------------------------
        log("Coordinator", "started", f"Task: {task}")
        pipeline_span = self._tracer.start_span(
            "agentops.pipeline",
            attributes={
                "agent_ops.pipeline.task": task,
                "agent_ops.pipeline.coordinator_model": _COORDINATOR_MODEL,
            },
        )
        coordinator_plan, coordinator_decomp = await self._coordinator_plan(task, config)
        log("Coordinator", "completed", "Work plan generated")

        # 2. Analysis agents run in parallel --------------------------------
        log("ArchitectureAgent", "started", "Analyzing AWS environment")
        log("MigrationAgent", "started", "Planning workload migrations")
        log("ComplianceAgent", "started", "Auditing compliance posture")

        arch_payload = {"aws_config": config.get("aws_config", {})}
        mig_payload = {"workload_inventory": config.get("workload_inventory", [])}
        comp_payload = {"iac_config": config.get("iac_config", {})}

        arch_span = self._tracer.trace_agent("ArchitectureAgent", parent_span=pipeline_span)
        mig_span = self._tracer.trace_agent("MigrationAgent", parent_span=pipeline_span)
        comp_span = self._tracer.trace_agent("ComplianceAgent", parent_span=pipeline_span)

        arch_result, mig_result, comp_result = await asyncio.gather(
            self._run_agent(self._arch_agent, arch_payload),
            self._run_agent(self._mig_agent, mig_payload),
            self._run_agent(self._comp_agent, comp_payload),
            return_exceptions=False,
        )

        for result, name, span in [
            (arch_result, "ArchitectureAgent", arch_span),
            (mig_result, "MigrationAgent", mig_span),
            (comp_result, "ComplianceAgent", comp_span),
        ]:
            self._tracer.record_agent_result(span, result)
            self._tracer.finish_span(span)
            if result.status == AgentStatus.DONE:
                log(name, "completed", f"{len(result.findings)} findings")
            else:
                log(name, "failed", result.error or "unknown error")

        # 3. Report agent synthesizes ---------------------------------------
        log("ReportAgent", "started", "Synthesizing executive briefing")
        report_span = self._tracer.trace_agent("ReportAgent", parent_span=pipeline_span)

        report_payload = {
            "task": task,
            "architecture_result": arch_result,
            "migration_result": mig_result,
            "compliance_result": comp_result,
        }
        report_result = await self._run_agent(self._report_agent, report_payload)
        self._tracer.record_agent_result(report_span, report_result)
        self._tracer.finish_span(report_span)

        if report_result.status == AgentStatus.DONE:
            log("ReportAgent", "completed", "Executive briefing ready")
        else:
            log("ReportAgent", "failed", report_result.error or "unknown error")

        # 4. Assemble final result ------------------------------------------
        agent_results = {
            "ArchitectureAgent": arch_result,
            "MigrationAgent": mig_result,
            "ComplianceAgent": comp_result,
            "ReportAgent": report_result,
        }

        total_findings = sum(
            len(r.findings)
            for r in [arch_result, mig_result, comp_result]
        )

        all_done = all(r.status == AgentStatus.DONE for r in agent_results.values())
        any_done = any(r.status == AgentStatus.DONE for r in agent_results.values())
        pipeline_status = "success" if all_done else ("partial" if any_done else "failed")

        report_meta = (
            report_result.metadata if report_result.status == AgentStatus.DONE else {}
        )

        # Aggregate token usage across all four agents.
        usage = TokenUsageSummary()
        for r in agent_results.values():
            usage.input_tokens += r.tokens_input
            usage.output_tokens += r.tokens_output
            usage.cache_read_tokens += r.tokens_cache_read
            usage.cache_creation_tokens += r.tokens_cache_creation

        log(
            "Coordinator",
            "completed",
            f"Pipeline {pipeline_status} — {total_findings} findings, "
            f"{usage.total_tokens} tokens ({usage.cache_read_tokens} cached)",
        )

        # Close pipeline span with telemetry.
        self._tracer.record_pipeline_result(pipeline_span, None)
        pipeline_span.set_attribute("agent_ops.pipeline.status", pipeline_status)
        pipeline_span.set_attribute("agent_ops.pipeline.total_findings", total_findings)
        pipeline_span.set_attribute(
            "agent_ops.pipeline.duration_s",
            round(time.monotonic() - pipeline_start, 3),
        )
        pipeline_span.set_attribute("agent_ops.pipeline.input_tokens", usage.input_tokens)
        pipeline_span.set_attribute("agent_ops.pipeline.output_tokens", usage.output_tokens)
        pipeline_span.set_attribute(
            "agent_ops.pipeline.cache_read_tokens", usage.cache_read_tokens
        )
        self._tracer.finish_span(pipeline_span)

        return PipelineResult(
            task=task,
            status=pipeline_status,
            total_duration_seconds=time.monotonic() - pipeline_start,
            coordinator_plan=coordinator_plan,
            coordinator_model=_COORDINATOR_MODEL,
            agent_results=agent_results,
            activity_log=activity_log,
            executive_summary=report_meta.get("executive_summary", ""),
            top_risks=report_meta.get("top_risks", []),
            strategic_recommendations=report_meta.get("strategic_recommendations", []),
            quick_wins=report_meta.get("quick_wins", []),
            roadmap_90_day=report_meta.get("roadmap_90_day", []),
            overall_health_score=report_meta.get("overall_health_score", 0),
            total_findings=total_findings,
            token_usage=usage,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _coordinator_plan(
        self, task: str, config: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]]]:
        """Use Opus 4.7 with a forced tool-call so the plan is validated, not parsed."""
        environment_summary = {
            "aws_regions": config.get("aws_config", {}).get("regions", []),
            "workload_count": len(config.get("workload_inventory", [])),
            "iac_resources": len(
                config.get("iac_config", {}).get("resources", [])
            ),
        }

        system = (
            "You are an enterprise AI orchestration coordinator. "
            "Given a high-level IT transformation task and environment context, "
            "produce a 3-4 sentence work plan and a decomposition across four "
            "specialist agents: ArchitectureAgent, MigrationAgent, ComplianceAgent, "
            "ReportAgent. Be specific about what each agent will focus on."
        )
        user = (
            f"Task: {task}\n\n"
            f"Environment context:\n"
            f"```json\n{json.dumps(environment_summary, indent=2)}\n```"
        )

        response = await self._ai.structured(
            system=system,
            user=user,
            schema=_COORDINATOR_PLAN_SCHEMA,
            tool_name="emit_coordinator_plan",
            tool_description="Emit the coordinator work plan as structured data.",
            model=_COORDINATOR_MODEL,
            max_tokens=1024,
        )

        data = response.data
        plan_summary = str(data.get("plan_summary", "")).strip()
        decomposition = data.get("decomposition", []) or []
        return plan_summary, decomposition

    @staticmethod
    async def _run_agent(
        agent: Any, payload: dict[str, Any]
    ) -> AgentResult:
        """Thin wrapper so exceptions from any agent don't crash the gather."""
        try:
            return await agent.run(payload)
        except Exception as exc:
            return AgentResult(
                agent_name=getattr(agent, "name", "unknown"),
                status=AgentStatus.FAILED,
                error=str(exc),
            )
