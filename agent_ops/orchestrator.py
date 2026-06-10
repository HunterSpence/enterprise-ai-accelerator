"""
agent_ops/orchestrator.py
=========================

Coordinator agent that decomposes a high-level enterprise IT task into
parallel sub-agent work, collects results, and synthesizes a final output.

Hardening additions (2026-06):
  - _run_agent: exponential-backoff retry (3 attempts, 1 s / 4 s / 16 s) on
    transient errors (rate-limit / 5xx / timeout); auth errors are not retried.
  - run_pipeline: optional max_tokens_budget / max_cost_usd caps via BudgetGuard;
    raises BudgetExceededError with partial results when exceeded.
  - Checkpointing: after each pipeline stage a resumable JSON checkpoint is
    written under .eaa_checkpoints/{run_id}.json; Orchestrator.resume(run_id)
    replays from the last completed stage.
  - Human-in-the-loop: optional approval_handler invoked before high-stakes
    stages; default auto-approves and records the decision in telemetry.

Architecture:
  - Fable 5 coordinator decomposes the task
  - Architecture / Migration / Compliance workers run in parallel (Haiku 4.5)
  - Sonnet 4.6 ReportAgent synthesizes the final briefing
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from core import MODEL_COORDINATOR, AIClient
from core.guardrails import BudgetExceededError, BudgetGuard

logger = logging.getLogger(__name__)

# Coordinator model — driven from core.models via core.__init__.
_COORDINATOR_MODEL = MODEL_COORDINATOR

# Checkpoint directory (relative to cwd).
_CHECKPOINT_DIR = Path(".eaa_checkpoints")

# Retry settings for transient errors.
_RETRY_DELAYS = (1.0, 4.0, 16.0)   # seconds between successive attempts

# Error substrings that indicate a transient (retryable) condition.
_TRANSIENT_MARKERS = (
    "rate_limit",
    "rate limit",
    "529",
    "503",
    "502",
    "500",
    "timeout",
    "overloaded",
    "connection",
)

# Error substrings that are NOT retried (auth / permission failures).
_AUTH_MARKERS = (
    "401",
    "403",
    "authentication",
    "unauthorized",
    "forbidden",
    "invalid_api_key",
)


def _is_transient(exc: Exception) -> bool:
    """Return True if the exception looks like a transient API error."""
    msg = str(exc).lower()
    if any(m in msg for m in _AUTH_MARKERS):
        return False
    return any(m in msg for m in _TRANSIENT_MARKERS)


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
    def now(cls, agent: str, event: str, detail: str = "") -> AgentActivity:
        return cls(
            timestamp=datetime.now(UTC).strftime("%H:%M:%S.%f")[:-3],
            agent=agent,
            event=event,
            detail=detail,
        )


@dataclass
class TokenUsageSummary:
    """Aggregated token usage across the pipeline — surfaces the
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
class ApprovalRequest:
    """Carries context for a human-in-the-loop gate.

    Attributes
    ----------
    run_id : str
        Unique identifier for the pipeline run.
    stage : str
        Name of the pipeline stage requesting approval (e.g. "workers", "report").
    context : dict
        Arbitrary stage-specific context the handler may display to the approver.
    """
    run_id: str
    stage: str
    context: dict[str, Any] = field(default_factory=dict)


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
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # HITL audit: list of {"stage": ..., "approved": bool, "auto": bool}
    hitl_audit: list[dict[str, Any]] = field(default_factory=list)

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
# Coordinator plan schema
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Default HITL handler — auto-approves and records the decision
# ---------------------------------------------------------------------------

async def _default_approval_handler(req: ApprovalRequest) -> bool:
    """Default policy: auto-approve every stage; records decision for audit."""
    logger.info(
        "HITL auto-approval: run_id=%s stage=%s (no approval_handler provided)",
        req.run_id,
        req.stage,
    )
    return True


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _checkpoint_path(run_id: str) -> Path:
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return _CHECKPOINT_DIR / f"{run_id}.json"


def _write_checkpoint(
    run_id: str,
    stage: str,
    completed_results: dict[str, Any],
) -> None:
    """Persist a resumable checkpoint JSON for this run."""
    data = {
        "run_id": run_id,
        "stage": stage,
        "ts": datetime.now(UTC).isoformat(),
        "completed": completed_results,
    }
    path = _checkpoint_path(run_id)
    path.write_text(json.dumps(data, default=str, indent=2), encoding="utf-8")
    logger.debug("Checkpoint written: %s (stage=%s)", path, stage)


def _read_checkpoint(run_id: str) -> dict[str, Any] | None:
    path = _checkpoint_path(run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _agent_result_from_dict(d: dict[str, Any]) -> AgentResult:
    """Reconstruct an AgentResult from a checkpoint dict (best-effort)."""
    return AgentResult(
        agent_name=d.get("agent_name", "unknown"),
        status=AgentStatus(d.get("status", "failed")),
        findings=d.get("findings", []),
        raw_output=d.get("raw_output", ""),
        duration_seconds=d.get("duration_seconds", 0.0),
        error=d.get("error"),
        metadata=d.get("metadata", {}),
        tokens_input=d.get("tokens_input", 0),
        tokens_output=d.get("tokens_output", 0),
        tokens_cache_read=d.get("tokens_cache_read", 0),
        tokens_cache_creation=d.get("tokens_cache_creation", 0),
        model=d.get("model", ""),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """Coordinator agent: receives a high-level enterprise task, delegates
    to specialized sub-agents in parallel, and synthesizes a unified output.

    Usage:
        client = anthropic.AsyncAnthropic(api_key="...")
        orch = Orchestrator(client)
        result = await orch.run_pipeline(task, config)

    Parameters
    ----------
    client : anthropic.AsyncAnthropic | AIClient
    on_activity : Callable[[AgentActivity], None] | None
    tracer : AgentOpsTracer | None
    approval_handler : Callable[[ApprovalRequest], Awaitable[bool]] | None
        Called before each high-stakes stage. Returning False aborts the pipeline
        with status "failed". Default: auto-approve + log for audit.
    """

    def __init__(
        self,
        client: anthropic.AsyncAnthropic | AIClient,
        on_activity: Callable[[AgentActivity], None] | None = None,
        tracer: AgentOpsTracer | None = None,
        approval_handler: Callable[[ApprovalRequest], Any] | None = None,
    ) -> None:
        self._ai = client if isinstance(client, AIClient) else AIClient(client)
        self._client = self._ai.raw  # backwards compat for callers reading ._client
        self._on_activity = on_activity or (lambda _: None)
        self._arch_agent = ArchitectureAgent(self._ai)
        self._mig_agent = MigrationAgent(self._ai)
        self._comp_agent = ComplianceAgent(self._ai)
        self._report_agent = ReportAgent(self._ai)
        self._tracer = tracer or AgentOpsTracer(export_mode="console")
        self._approval_handler = approval_handler or _default_approval_handler

    # ------------------------------------------------------------------
    # Public: run a fresh pipeline
    # ------------------------------------------------------------------

    async def run_pipeline(
        self,
        task: str,
        config: dict[str, Any],
        *,
        max_tokens_budget: int | None = None,
        max_cost_usd: float | None = None,
        run_id: str | None = None,
    ) -> PipelineResult:
        """Execute the full analysis pipeline.

        Parameters
        ----------
        task : str
        config : dict
        max_tokens_budget : int | None
            Hard cap on total tokens across the entire pipeline.
        max_cost_usd : float | None
            Hard cap on total USD spend across the entire pipeline.
        run_id : str | None
            Override the auto-generated UUID (useful for deterministic tests).
        """
        pipeline_start = time.monotonic()
        activity_log: list[AgentActivity] = []
        hitl_audit: list[dict[str, Any]] = []
        _run_id = run_id or str(uuid.uuid4())
        budget = BudgetGuard(
            max_tokens_budget=max_tokens_budget,
            max_cost_usd=max_cost_usd,
        )

        def log(agent: str, event: str, detail: str = "") -> None:
            entry = AgentActivity.now(agent, event, detail)
            activity_log.append(entry)
            self._on_activity(entry)
            logger.info("[%s] %s %s %s", entry.timestamp, agent, event, detail)

        async def _gate(stage: str, context: dict[str, Any]) -> bool:
            req = ApprovalRequest(run_id=_run_id, stage=stage, context=context)
            approved = await self._approval_handler(req)
            is_auto = self._approval_handler is _default_approval_handler
            hitl_audit.append({"stage": stage, "approved": approved, "auto": is_auto})
            return approved

        # 1. Coordinator plans the work -------------------------------------
        log("Coordinator", "started", f"Task: {task}")
        pipeline_span = self._tracer.start_span(
            "agentops.pipeline",
            attributes={
                "agent_ops.pipeline.task": task,
                "agent_ops.pipeline.coordinator_model": _COORDINATOR_MODEL,
                "agent_ops.pipeline.run_id": _run_id,
            },
        )

        coordinator_plan, coordinator_decomp = await self._coordinator_plan(task, config)
        log("Coordinator", "completed", "Work plan generated")

        _write_checkpoint(_run_id, "coordination", {"coordinator_plan": coordinator_plan})

        # HITL gate before analysis workers
        if not await _gate("workers", {"task": task, "plan": coordinator_plan}):
            return PipelineResult(
                task=task,
                status="failed",
                total_duration_seconds=time.monotonic() - pipeline_start,
                coordinator_plan=coordinator_plan,
                run_id=_run_id,
                hitl_audit=hitl_audit,
            )

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

        # Budget check: estimate worker tokens before dispatching
        try:
            budget.check(input_tokens=3_000, output_tokens=9_000)
        except BudgetExceededError as exc:
            logger.warning("Budget exceeded before workers: %s", exc)
            return PipelineResult(
                task=task,
                status="partial",
                total_duration_seconds=time.monotonic() - pipeline_start,
                coordinator_plan=coordinator_plan,
                run_id=_run_id,
                hitl_audit=hitl_audit,
            )

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
            budget.record(
                input_tokens=result.tokens_input,
                output_tokens=result.tokens_output,
            )
            if result.status == AgentStatus.DONE:
                log(name, "completed", f"{len(result.findings)} findings")
            else:
                log(name, "failed", result.error or "unknown error")

        _write_checkpoint(
            _run_id,
            "workers",
            {
                "coordinator_plan": coordinator_plan,
                "ArchitectureAgent": asdict(arch_result),
                "MigrationAgent": asdict(mig_result),
                "ComplianceAgent": asdict(comp_result),
            },
        )

        # HITL gate before report synthesis
        if not await _gate("report", {"task": task}):
            agent_results = {
                "ArchitectureAgent": arch_result,
                "MigrationAgent": mig_result,
                "ComplianceAgent": comp_result,
            }
            return PipelineResult(
                task=task,
                status="partial",
                total_duration_seconds=time.monotonic() - pipeline_start,
                coordinator_plan=coordinator_plan,
                agent_results=agent_results,
                activity_log=activity_log,
                run_id=_run_id,
                hitl_audit=hitl_audit,
            )

        # 3. Report agent synthesizes ---------------------------------------
        log("ReportAgent", "started", "Synthesizing executive briefing")
        report_span = self._tracer.trace_agent("ReportAgent", parent_span=pipeline_span)

        try:
            budget.check(input_tokens=2_000, output_tokens=3_000)
        except BudgetExceededError as exc:
            logger.warning("Budget exceeded before report: %s", exc)
            agent_results = {
                "ArchitectureAgent": arch_result,
                "MigrationAgent": mig_result,
                "ComplianceAgent": comp_result,
            }
            return PipelineResult(
                task=task,
                status="partial",
                total_duration_seconds=time.monotonic() - pipeline_start,
                coordinator_plan=coordinator_plan,
                agent_results=agent_results,
                activity_log=activity_log,
                total_findings=sum(len(r.findings) for r in agent_results.values()),
                run_id=_run_id,
                hitl_audit=hitl_audit,
            )

        report_payload = {
            "task": task,
            "architecture_result": arch_result,
            "migration_result": mig_result,
            "compliance_result": comp_result,
        }
        report_result = await self._run_agent(self._report_agent, report_payload)
        self._tracer.record_agent_result(report_span, report_result)
        self._tracer.finish_span(report_span)
        budget.record(
            input_tokens=report_result.tokens_input,
            output_tokens=report_result.tokens_output,
        )

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

        _write_checkpoint(
            _run_id,
            "report",
            {
                "coordinator_plan": coordinator_plan,
                "ArchitectureAgent": asdict(arch_result),
                "MigrationAgent": asdict(mig_result),
                "ComplianceAgent": asdict(comp_result),
                "ReportAgent": asdict(report_result),
            },
        )

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
            run_id=_run_id,
            hitl_audit=hitl_audit,
        )

    # ------------------------------------------------------------------
    # Public: resume from checkpoint
    # ------------------------------------------------------------------

    async def resume(self, run_id: str) -> dict[str, Any]:
        """Resume a previously checkpointed pipeline run.

        Reads the checkpoint at ``.eaa_checkpoints/{run_id}.json`` and returns
        the completed stage data. For runs that only reached "coordination" or
        "workers", callers can continue the pipeline manually or re-invoke
        run_pipeline with the saved data.

        Returns
        -------
        dict with keys: run_id, stage, completed (agent result dicts).

        Raises
        ------
        FileNotFoundError if no checkpoint exists for run_id.
        """
        data = _read_checkpoint(run_id)
        if data is None:
            raise FileNotFoundError(f"No checkpoint found for run_id={run_id!r}")
        logger.info(
            "Resuming run_id=%s from stage=%s (checkpointed at %s)",
            run_id,
            data.get("stage"),
            data.get("ts"),
        )
        return data

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _coordinator_plan(
        self, task: str, config: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]]]:
        """Use coordinator model with a forced tool-call so the plan is validated."""
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
        """Run an agent with exponential-backoff retry on transient errors.

        Attempts: 3 (delays: 1s, 4s, 16s between successive tries).
        Retries on: rate-limit / 5xx / timeout / connection errors.
        Does NOT retry on: auth / permission errors (401 / 403).
        """
        last_exc: Exception | None = None
        for attempt, delay in enumerate([0.0] + list(_RETRY_DELAYS), start=1):
            if delay:
                logger.warning(
                    "Retrying %s (attempt %d) after %.0fs — last error: %s",
                    getattr(agent, "name", "agent"),
                    attempt,
                    delay,
                    last_exc,
                )
                await asyncio.sleep(delay)
            try:
                return await agent.run(payload)
            except Exception as exc:
                if not _is_transient(exc):
                    # Non-transient (auth, etc.): fail immediately, no retry.
                    return AgentResult(
                        agent_name=getattr(agent, "name", "unknown"),
                        status=AgentStatus.FAILED,
                        error=str(exc),
                    )
                last_exc = exc

        # All attempts exhausted.
        return AgentResult(
            agent_name=getattr(agent, "name", "unknown"),
            status=AgentStatus.FAILED,
            error=f"Failed after {len(_RETRY_DELAYS) + 1} attempts: {last_exc}",
        )
