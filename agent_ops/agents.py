"""
agent_ops/agents.py

Specialized sub-agents that wrap enterprise analysis modules.
Each agent uses Claude Haiku for cost-efficient, focused execution.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import anthropic


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class AgentResult:
    agent_name: str
    status: AgentStatus
    findings: list[str] = field(default_factory=list)
    raw_output: str = ""
    duration_seconds: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Base agent
# ---------------------------------------------------------------------------

# Haiku is the cost-efficient worker model for all sub-agents.
_WORKER_MODEL = "claude-haiku-4-5-20251001"


class BaseAgent:
    """
    Thin wrapper around a single Claude Haiku call with a focused system prompt.
    Subclasses define their system prompt and the tool they expose to the model.
    """

    name: str = "base"
    system_prompt: str = "You are a helpful assistant."

    def __init__(self, client: anthropic.AsyncAnthropic) -> None:
        self._client = client

    async def run(self, payload: dict[str, Any]) -> AgentResult:
        start = time.monotonic()
        try:
            result = await self._execute(payload)
            result.duration_seconds = time.monotonic() - start
            return result
        except Exception as exc:
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                error=str(exc),
                duration_seconds=time.monotonic() - start,
            )

    async def _execute(self, payload: dict[str, Any]) -> AgentResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Architecture Agent
# ---------------------------------------------------------------------------

class ArchitectureAgent(BaseAgent):
    """
    Analyzes AWS infrastructure and produces a CloudIQ-style assessment.
    Wraps the cloudiq module's analyzer logic.
    """

    name = "ArchitectureAgent"
    system_prompt = (
        "You are an AWS solutions architect performing a CloudIQ analysis. "
        "Given an AWS environment configuration, identify: "
        "(1) over-provisioned or under-utilized resources, "
        "(2) single points of failure, "
        "(3) missing redundancy, "
        "(4) security gaps (open ports, overly permissive IAM, public S3). "
        "Be specific — cite resource IDs and regions. "
        "Return findings as a JSON object: "
        '{"findings": ["...", ...], "risk_level": "low|medium|high|critical", '
        '"resources_analyzed": N, "recommendations": ["...", ...]}'
    )

    async def _execute(self, payload: dict[str, Any]) -> AgentResult:
        aws_config = payload.get("aws_config", {})

        response = await self._client.messages.create(
            model=_WORKER_MODEL,
            max_tokens=1024,
            system=self.system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Analyze this AWS environment configuration:\n\n"
                        f"```json\n{json.dumps(aws_config, indent=2)}\n```\n\n"
                        "Return ONLY the JSON object described in your instructions."
                    ),
                }
            ],
        )

        raw = response.content[0].text.strip()
        parsed = _parse_json_response(raw)

        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.DONE,
            findings=parsed.get("findings", []),
            raw_output=raw,
            metadata={
                "risk_level": parsed.get("risk_level", "unknown"),
                "resources_analyzed": parsed.get("resources_analyzed", 0),
                "recommendations": parsed.get("recommendations", []),
            },
        )


# ---------------------------------------------------------------------------
# Migration Agent
# ---------------------------------------------------------------------------

class MigrationAgent(BaseAgent):
    """
    Applies the 6R framework (Retire/Retain/Rehost/Replatform/Repurchase/Refactor)
    to a workload inventory. Wraps migration_scout logic.
    """

    name = "MigrationAgent"
    system_prompt = (
        "You are an AWS migration strategist using the 6R framework. "
        "For each workload, assign one of: Retire, Retain, Rehost, Replatform, "
        "Repurchase, or Refactor. Justify each decision with business and technical rationale. "
        "Estimate migration effort (low/medium/high) and risk (low/medium/high). "
        "Return a JSON object: "
        '{"workload_plans": [{"workload_name": "...", "strategy": "...", '
        '"rationale": "...", "effort": "...", "risk": "...", "estimated_weeks": N}], '
        '"total_workloads": N, "quick_wins": ["..."], "high_risk_items": ["..."]}'
    )

    async def _execute(self, payload: dict[str, Any]) -> AgentResult:
        workloads = payload.get("workload_inventory", [])

        response = await self._client.messages.create(
            model=_WORKER_MODEL,
            max_tokens=1024,
            system=self.system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Develop migration plans for these workloads:\n\n"
                        f"```json\n{json.dumps(workloads, indent=2)}\n```\n\n"
                        "Return ONLY the JSON object described in your instructions."
                    ),
                }
            ],
        )

        raw = response.content[0].text.strip()
        parsed = _parse_json_response(raw)

        plans = parsed.get("workload_plans", [])
        findings = [
            f"{p['workload_name']}: {p['strategy']} ({p.get('effort','?')} effort)"
            for p in plans
        ]

        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.DONE,
            findings=findings,
            raw_output=raw,
            metadata={
                "total_workloads": parsed.get("total_workloads", len(plans)),
                "quick_wins": parsed.get("quick_wins", []),
                "high_risk_items": parsed.get("high_risk_items", []),
                "workload_plans": plans,
            },
        )


# ---------------------------------------------------------------------------
# Compliance Agent
# ---------------------------------------------------------------------------

class ComplianceAgent(BaseAgent):
    """
    Checks IaC templates against security and compliance policies.
    Wraps policy_guard checker logic.
    """

    name = "ComplianceAgent"
    system_prompt = (
        "You are a cloud compliance and security auditor (PolicyGuard). "
        "Review IaC configurations against: CIS AWS Benchmark, SOC 2 Type II controls, "
        "GDPR data residency rules, and PCI-DSS network segmentation. "
        "Flag every violation with severity (critical/high/medium/low) and the "
        "specific control ID that is breached. "
        "Return a JSON object: "
        '{"violations": [{"control": "...", "severity": "...", "resource": "...", '
        '"description": "...", "remediation": "..."}], '
        '"compliance_score": N, "frameworks_checked": ["..."], '
        '"pass_count": N, "fail_count": N}'
    )

    async def _execute(self, payload: dict[str, Any]) -> AgentResult:
        iac_config = payload.get("iac_config", {})

        response = await self._client.messages.create(
            model=_WORKER_MODEL,
            max_tokens=1024,
            system=self.system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Audit this infrastructure-as-code configuration for compliance violations:\n\n"
                        f"```json\n{json.dumps(iac_config, indent=2)}\n```\n\n"
                        "Return ONLY the JSON object described in your instructions."
                    ),
                }
            ],
        )

        raw = response.content[0].text.strip()
        parsed = _parse_json_response(raw)

        violations = parsed.get("violations", [])
        findings = [
            f"[{v.get('severity','?').upper()}] {v.get('control','?')}: {v.get('resource','?')}"
            for v in violations
        ]

        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.DONE,
            findings=findings,
            raw_output=raw,
            metadata={
                "compliance_score": parsed.get("compliance_score", 0),
                "frameworks_checked": parsed.get("frameworks_checked", []),
                "pass_count": parsed.get("pass_count", 0),
                "fail_count": parsed.get("fail_count", len(violations)),
                "violations": violations,
            },
        )


# ---------------------------------------------------------------------------
# Report Agent
# ---------------------------------------------------------------------------

class ReportAgent(BaseAgent):
    """
    Synthesizes outputs from the three analysis agents into a board-ready
    executive summary. Wraps executive_report generation logic.
    """

    name = "ReportAgent"
    system_prompt = (
        "You are a management consultant writing a board-level executive briefing. "
        "You receive findings from three specialist AI agents: architecture analysis, "
        "migration planning, and compliance review. "
        "Synthesize these into a concise, action-oriented executive summary suitable "
        "for a C-suite audience. Use business language — no jargon. "
        "Structure: Executive Summary (3 sentences), Top 5 Risks, Strategic Recommendations, "
        "Quick Wins (implementable within 30 days), 90-Day Roadmap. "
        "Return a JSON object: "
        '{"executive_summary": "...", "top_risks": ["...", ...], '
        '"strategic_recommendations": ["...", ...], "quick_wins": ["...", ...], '
        '"roadmap_90_day": [{"phase": "...", "actions": ["..."]}], '
        '"overall_health_score": N}'
    )

    async def _execute(self, payload: dict[str, Any]) -> AgentResult:
        arch_result: AgentResult = payload["architecture_result"]
        mig_result: AgentResult = payload["migration_result"]
        comp_result: AgentResult = payload["compliance_result"]
        task_description: str = payload.get("task", "Enterprise IT Analysis")

        synthesis_input = {
            "task": task_description,
            "architecture_findings": arch_result.findings,
            "architecture_metadata": arch_result.metadata,
            "migration_findings": mig_result.findings,
            "migration_metadata": mig_result.metadata,
            "compliance_findings": comp_result.findings,
            "compliance_metadata": comp_result.metadata,
        }

        response = await self._client.messages.create(
            model=_WORKER_MODEL,
            max_tokens=2048,
            system=self.system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Synthesize these multi-agent analysis results into an executive briefing:\n\n"
                        f"```json\n{json.dumps(synthesis_input, indent=2)}\n```\n\n"
                        "Return ONLY the JSON object described in your instructions."
                    ),
                }
            ],
        )

        raw = response.content[0].text.strip()
        parsed = _parse_json_response(raw)

        findings = [
            parsed.get("executive_summary", ""),
            *[f"Risk: {r}" for r in parsed.get("top_risks", [])],
        ]

        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.DONE,
            findings=[f for f in findings if f],
            raw_output=raw,
            metadata=parsed,
        )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict[str, Any]:
    """
    Extract JSON from a model response that may include markdown fences.
    Falls back to an empty dict rather than crashing the pipeline.
    """
    # Strip markdown code fences if present
    if "```" in text:
        lines = text.split("\n")
        inside = False
        json_lines: list[str] = []
        for line in lines:
            if line.startswith("```"):
                inside = not inside
                continue
            if inside:
                json_lines.append(line)
        text = "\n".join(json_lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Best-effort: locate the first { ... } block
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return {}
