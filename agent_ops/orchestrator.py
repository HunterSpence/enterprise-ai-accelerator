"""
agent_ops/orchestrator.py

Coordinator agent that decomposes a high-level enterprise IT task into
parallel sub-agent work, collects results, and synthesizes a final output.

Architecture:
  - Coordinator uses Claude Opus for high-complexity reasoning
  - Sub-agents (Architecture, Migration, Compliance, Report) use Claude Haiku
  - All sub-agents run in parallel via asyncio.gather
  - ReportAgent runs after the three analysis agents complete
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

logger = logging.getLogger(__name__)

# Opus handles coordinator reasoning; Haiku handles sub-agent execution.
_COORDINATOR_MODEL = "claude-opus-4-6"


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
class PipelineResult:
    task: str
    status: str  # success | partial | failed
    total_duration_seconds: float
    coordinator_plan: str
    agent_results: dict[str, AgentResult] = field(default_factory=dict)
    activity_log: list[AgentActivity] = field(default_factory=list)
    executive_summary: str = ""
    top_risks: list[str] = field(default_factory=list)
    strategic_recommendations: list[str] = field(default_factory=list)
    quick_wins: list[str] = field(default_factory=list)
    roadmap_90_day: list[dict[str, Any]] = field(default_factory=list)
    overall_health_score: int = 0
    total_findings: int = 0

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

class Orchestrator:
    """
    Coordinator agent: receives a high-level enterprise task, delegates to
    specialized sub-agents in parallel, and synthesizes a unified output.

    Usage:
        client = anthropic.AsyncAnthropic(api_key="...")
        orch = Orchestrator(client)
        result = await orch.run_pipeline(task, config)
    """

    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        on_activity: Callable[[AgentActivity], None] | None = None,
    ) -> None:
        self._client = client
        self._on_activity = on_activity or (lambda _: None)
        self._arch_agent = ArchitectureAgent(client)
        self._mig_agent = MigrationAgent(client)
        self._comp_agent = ComplianceAgent(client)
        self._report_agent = ReportAgent(client)

    async def run_pipeline(
        self, task: str, config: dict[str, Any]
    ) -> PipelineResult:
        """
        Full pipeline:
          1. Coordinator plans the task decomposition
          2. Architecture, Migration, Compliance agents run in parallel
          3. Report agent synthesizes their outputs
          4. Final result assembled and returned
        """
        pipeline_start = time.monotonic()
        activity_log: list[AgentActivity] = []

        def log(agent: str, event: str, detail: str = "") -> None:
            entry = AgentActivity.now(agent, event, detail)
            activity_log.append(entry)
            self._on_activity(entry)
            logger.info("[%s] %s %s %s", entry.timestamp, agent, event, detail)

        # ------------------------------------------------------------------
        # Step 1: Coordinator plans the work
        # ------------------------------------------------------------------
        log("Coordinator", "started", f"Task: {task}")
        coordinator_plan = await self._coordinator_plan(task, config)
        log("Coordinator", "completed", "Work plan generated")

        # ------------------------------------------------------------------
        # Step 2: Analysis agents run in parallel
        # ------------------------------------------------------------------
        log("ArchitectureAgent", "started", "Analyzing AWS environment")
        log("MigrationAgent", "started", "Planning workload migrations")
        log("ComplianceAgent", "started", "Auditing compliance posture")

        arch_payload = {"aws_config": config.get("aws_config", {})}
        mig_payload = {"workload_inventory": config.get("workload_inventory", [])}
        comp_payload = {"iac_config": config.get("iac_config", {})}

        arch_result, mig_result, comp_result = await asyncio.gather(
            self._run_agent(self._arch_agent, arch_payload),
            self._run_agent(self._mig_agent, mig_payload),
            self._run_agent(self._comp_agent, comp_payload),
            return_exceptions=False,
        )

        for result, name in [
            (arch_result, "ArchitectureAgent"),
            (mig_result, "MigrationAgent"),
            (comp_result, "ComplianceAgent"),
        ]:
            if result.status == AgentStatus.DONE:
                log(name, "completed", f"{len(result.findings)} findings")
            else:
                log(name, "failed", result.error or "unknown error")

        # ------------------------------------------------------------------
        # Step 3: Report agent synthesizes the analysis results
        # ------------------------------------------------------------------
        log("ReportAgent", "started", "Synthesizing executive briefing")

        report_payload = {
            "task": task,
            "architecture_result": arch_result,
            "migration_result": mig_result,
            "compliance_result": comp_result,
        }
        report_result = await self._run_agent(self._report_agent, report_payload)

        if report_result.status == AgentStatus.DONE:
            log("ReportAgent", "completed", "Executive briefing ready")
        else:
            log("ReportAgent", "failed", report_result.error or "unknown error")

        # ------------------------------------------------------------------
        # Step 4: Assemble final result
        # ------------------------------------------------------------------
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

        all_done = all(
            r.status == AgentStatus.DONE for r in agent_results.values()
        )
        any_done = any(
            r.status == AgentStatus.DONE for r in agent_results.values()
        )
        pipeline_status = "success" if all_done else ("partial" if any_done else "failed")

        report_meta = report_result.metadata if report_result.status == AgentStatus.DONE else {}

        log("Coordinator", "completed", f"Pipeline {pipeline_status} — {total_findings} total findings")

        return PipelineResult(
            task=task,
            status=pipeline_status,
            total_duration_seconds=time.monotonic() - pipeline_start,
            coordinator_plan=coordinator_plan,
            agent_results=agent_results,
            activity_log=activity_log,
            executive_summary=report_meta.get("executive_summary", ""),
            top_risks=report_meta.get("top_risks", []),
            strategic_recommendations=report_meta.get("strategic_recommendations", []),
            quick_wins=report_meta.get("quick_wins", []),
            roadmap_90_day=report_meta.get("roadmap_90_day", []),
            overall_health_score=report_meta.get("overall_health_score", 0),
            total_findings=total_findings,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _coordinator_plan(
        self, task: str, config: dict[str, Any]
    ) -> str:
        """
        Use Opus to reason about the task and produce a brief work plan.
        This demonstrates the coordinator-level intelligence: understanding
        what needs to be analyzed and why, before delegating to sub-agents.
        """
        environment_summary = {
            "aws_regions": config.get("aws_config", {}).get("regions", []),
            "workload_count": len(config.get("workload_inventory", [])),
            "iac_resources": len(
                config.get("iac_config", {}).get("resources", [])
            ),
        }

        response = await self._client.messages.create(
            model=_COORDINATOR_MODEL,
            max_tokens=512,
            system=(
                "You are an enterprise AI orchestration coordinator. "
                "Given a high-level IT transformation task and environment context, "
                "produce a concise 3-4 sentence work plan explaining how you will "
                "decompose this task across specialist agents: Architecture Analyst, "
                "Migration Planner, Compliance Checker, and Report Generator. "
                "Be direct and specific about what each agent will focus on."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Task: {task}\n\n"
                        f"Environment context:\n"
                        f"```json\n{json.dumps(environment_summary, indent=2)}\n```"
                    ),
                }
            ],
        )

        return response.content[0].text.strip()

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
