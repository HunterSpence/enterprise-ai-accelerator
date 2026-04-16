"""
agent_ops/agents.py
===================

Specialized sub-agents that wrap enterprise analysis modules.

Opus 4.7 upgrade (2026-04):
  - Haiku 4.5 remains the high-volume worker for Architecture/Migration/Compliance
  - ReportAgent is promoted to Sonnet 4.6 (better narrative synthesis)
  - Every agent now uses native tool-use structured output via ``core.AIClient``,
    replacing the fragile ``_parse_json_response`` regex path
  - Every agent's system prompt rides on the 5-minute ephemeral prompt cache,
    so repeated pipeline runs pay the input-token cost once per window

Backwards compatibility:
  - ``_parse_json_response`` is kept as a deprecated helper for any external
    caller that imported it. New code should use ``core.ai_client.AIClient``.
"""

from __future__ import annotations

import asyncio  # noqa: F401  (kept for backwards compatibility of callers)
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import anthropic

from core import (
    AIClient,
    MODEL_REPORTER,
    MODEL_WORKER,
)


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
    # Opus 4.7 upgrade: capture per-call telemetry so the orchestrator can
    # surface cache hit-rate and total token spend in the activity log.
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cache_read: int = 0
    tokens_cache_creation: int = 0
    model: str = ""


# ---------------------------------------------------------------------------
# Base agent
# ---------------------------------------------------------------------------

_WORKER_MODEL = MODEL_WORKER         # claude-haiku-4-5-20251001
_REPORTER_MODEL = MODEL_REPORTER     # claude-sonnet-4-6


class BaseAgent:
    """Thin wrapper around a single Claude call with a focused system prompt."""

    name: str = "base"
    system_prompt: str = "You are a helpful assistant."
    # The schema the model is forced to emit via tool-use. Subclasses override.
    schema: dict[str, Any] = {"type": "object"}
    tool_name: str = "return_result"
    tool_description: str = "Return the structured result."
    model: str = _WORKER_MODEL
    max_tokens: int = 1024

    def __init__(
        self,
        client: anthropic.AsyncAnthropic | AIClient,
    ) -> None:
        # Accept either a raw AsyncAnthropic (legacy call sites) or an
        # already-constructed AIClient. This keeps the public ctor signature
        # backwards compatible while letting new callers inject the wrapper.
        if isinstance(client, AIClient):
            self._ai = client
        else:
            self._ai = AIClient(client)

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

    async def _call_structured(self, user: str) -> tuple[dict[str, Any], Any]:
        """Shared helper: run the model with forced tool-use and return parsed data."""
        response = await self._ai.structured(
            system=self.system_prompt,
            user=user,
            schema=self.schema,
            tool_name=self.tool_name,
            tool_description=self.tool_description,
            model=self.model,
            max_tokens=self.max_tokens,
        )
        return response.data, response


# ---------------------------------------------------------------------------
# Architecture Agent
# ---------------------------------------------------------------------------

class ArchitectureAgent(BaseAgent):
    """CloudIQ-style AWS assessment producer."""

    name = "ArchitectureAgent"
    system_prompt = (
        "You are an AWS solutions architect performing a CloudIQ analysis. "
        "Given an AWS environment configuration, identify: "
        "(1) over-provisioned or under-utilized resources, "
        "(2) single points of failure, "
        "(3) missing redundancy, "
        "(4) security gaps (open ports, overly permissive IAM, public S3). "
        "Be specific — cite resource IDs and regions."
    )
    tool_name = "emit_architecture_findings"
    tool_description = "Emit structured CloudIQ findings for the supplied AWS environment."
    schema = {
        "type": "object",
        "required": ["findings", "risk_level", "resources_analyzed", "recommendations"],
        "properties": {
            "findings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific, resource-cited findings.",
            },
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
            },
            "resources_analyzed": {"type": "integer", "minimum": 0},
            "recommendations": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }

    async def _execute(self, payload: dict[str, Any]) -> AgentResult:
        aws_config = payload.get("aws_config", {})
        user = (
            "Analyze this AWS environment configuration:\n\n"
            f"```json\n{json.dumps(aws_config, indent=2)}\n```"
        )
        data, resp = await self._call_structured(user)

        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.DONE,
            findings=data.get("findings", []),
            raw_output=resp.raw_text,
            metadata={
                "risk_level": data.get("risk_level", "unknown"),
                "resources_analyzed": data.get("resources_analyzed", 0),
                "recommendations": data.get("recommendations", []),
            },
            tokens_input=resp.input_tokens,
            tokens_output=resp.output_tokens,
            tokens_cache_read=resp.cache_read_tokens,
            tokens_cache_creation=resp.cache_creation_tokens,
            model=resp.model,
        )


# ---------------------------------------------------------------------------
# Migration Agent
# ---------------------------------------------------------------------------

class MigrationAgent(BaseAgent):
    """6R framework (Retire/Retain/Rehost/Replatform/Repurchase/Refactor) classifier."""

    name = "MigrationAgent"
    system_prompt = (
        "You are an AWS migration strategist using the 6R framework. "
        "For each workload, assign one of: Retire, Retain, Rehost, Replatform, "
        "Repurchase, or Refactor. Justify each decision with business and technical rationale. "
        "Estimate migration effort (low/medium/high) and risk (low/medium/high)."
    )
    tool_name = "emit_migration_plan"
    tool_description = "Emit a 6R migration plan for the supplied workload inventory."
    schema = {
        "type": "object",
        "required": ["workload_plans", "total_workloads"],
        "properties": {
            "workload_plans": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["workload_name", "strategy", "rationale", "effort", "risk"],
                    "properties": {
                        "workload_name": {"type": "string"},
                        "strategy": {
                            "type": "string",
                            "enum": [
                                "Retire", "Retain", "Rehost",
                                "Replatform", "Repurchase", "Refactor",
                            ],
                        },
                        "rationale": {"type": "string"},
                        "effort": {"type": "string", "enum": ["low", "medium", "high"]},
                        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                        "estimated_weeks": {"type": "integer", "minimum": 0},
                    },
                },
            },
            "total_workloads": {"type": "integer", "minimum": 0},
            "quick_wins": {"type": "array", "items": {"type": "string"}},
            "high_risk_items": {"type": "array", "items": {"type": "string"}},
        },
    }

    async def _execute(self, payload: dict[str, Any]) -> AgentResult:
        workloads = payload.get("workload_inventory", [])
        user = (
            "Develop migration plans for these workloads:\n\n"
            f"```json\n{json.dumps(workloads, indent=2)}\n```"
        )
        data, resp = await self._call_structured(user)

        plans = data.get("workload_plans", [])
        findings = [
            f"{p.get('workload_name', '?')}: {p.get('strategy', '?')} "
            f"({p.get('effort', '?')} effort)"
            for p in plans
        ]

        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.DONE,
            findings=findings,
            raw_output=resp.raw_text,
            metadata={
                "total_workloads": data.get("total_workloads", len(plans)),
                "quick_wins": data.get("quick_wins", []),
                "high_risk_items": data.get("high_risk_items", []),
                "workload_plans": plans,
            },
            tokens_input=resp.input_tokens,
            tokens_output=resp.output_tokens,
            tokens_cache_read=resp.cache_read_tokens,
            tokens_cache_creation=resp.cache_creation_tokens,
            model=resp.model,
        )


# ---------------------------------------------------------------------------
# Compliance Agent
# ---------------------------------------------------------------------------

class ComplianceAgent(BaseAgent):
    """PolicyGuard-style IaC compliance auditor."""

    name = "ComplianceAgent"
    system_prompt = (
        "You are a cloud compliance and security auditor (PolicyGuard). "
        "Review IaC configurations against: CIS AWS Benchmark, SOC 2 Type II controls, "
        "GDPR data residency rules, and PCI-DSS network segmentation. "
        "Flag every violation with severity (critical/high/medium/low) and the "
        "specific control ID that is breached."
    )
    tool_name = "emit_compliance_violations"
    tool_description = "Emit structured compliance violations for the IaC configuration."
    schema = {
        "type": "object",
        "required": ["violations", "compliance_score", "pass_count", "fail_count"],
        "properties": {
            "violations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["control", "severity", "resource", "description"],
                    "properties": {
                        "control": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low"],
                        },
                        "resource": {"type": "string"},
                        "description": {"type": "string"},
                        "remediation": {"type": "string"},
                    },
                },
            },
            "compliance_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "frameworks_checked": {"type": "array", "items": {"type": "string"}},
            "pass_count": {"type": "integer", "minimum": 0},
            "fail_count": {"type": "integer", "minimum": 0},
        },
    }

    async def _execute(self, payload: dict[str, Any]) -> AgentResult:
        iac_config = payload.get("iac_config", {})
        user = (
            "Audit this infrastructure-as-code configuration for compliance violations:\n\n"
            f"```json\n{json.dumps(iac_config, indent=2)}\n```"
        )
        data, resp = await self._call_structured(user)

        violations = data.get("violations", [])
        findings = [
            f"[{v.get('severity', '?').upper()}] {v.get('control', '?')}: "
            f"{v.get('resource', '?')}"
            for v in violations
        ]

        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.DONE,
            findings=findings,
            raw_output=resp.raw_text,
            metadata={
                "compliance_score": data.get("compliance_score", 0),
                "frameworks_checked": data.get("frameworks_checked", []),
                "pass_count": data.get("pass_count", 0),
                "fail_count": data.get("fail_count", len(violations)),
                "violations": violations,
            },
            tokens_input=resp.input_tokens,
            tokens_output=resp.output_tokens,
            tokens_cache_read=resp.cache_read_tokens,
            tokens_cache_creation=resp.cache_creation_tokens,
            model=resp.model,
        )


# ---------------------------------------------------------------------------
# Report Agent — promoted to Sonnet 4.6
# ---------------------------------------------------------------------------

class ReportAgent(BaseAgent):
    """Board-level executive briefing synthesizer. Uses Sonnet 4.6 for better prose."""

    name = "ReportAgent"
    model = _REPORTER_MODEL   # promoted from Haiku to Sonnet 4.6
    max_tokens = 2048
    system_prompt = (
        "You are a management consultant writing a board-level executive briefing. "
        "You receive findings from three specialist AI agents: architecture analysis, "
        "migration planning, and compliance review. "
        "Synthesize these into a concise, action-oriented executive summary suitable "
        "for a C-suite audience. Use business language — no jargon. "
        "Structure: Executive Summary (3 sentences), Top 5 Risks, Strategic Recommendations, "
        "Quick Wins (implementable within 30 days), 90-Day Roadmap."
    )
    tool_name = "emit_executive_briefing"
    tool_description = "Emit the board-level executive briefing as structured JSON."
    schema = {
        "type": "object",
        "required": [
            "executive_summary", "top_risks",
            "strategic_recommendations", "quick_wins",
            "roadmap_90_day", "overall_health_score",
        ],
        "properties": {
            "executive_summary": {"type": "string"},
            "top_risks": {"type": "array", "items": {"type": "string"}},
            "strategic_recommendations": {"type": "array", "items": {"type": "string"}},
            "quick_wins": {"type": "array", "items": {"type": "string"}},
            "roadmap_90_day": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["phase", "actions"],
                    "properties": {
                        "phase": {"type": "string"},
                        "actions": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "overall_health_score": {"type": "integer", "minimum": 0, "maximum": 100},
        },
    }

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
        user = (
            "Synthesize these multi-agent analysis results into an executive briefing:\n\n"
            f"```json\n{json.dumps(synthesis_input, indent=2)}\n```"
        )
        data, resp = await self._call_structured(user)

        findings = [
            data.get("executive_summary", ""),
            *[f"Risk: {r}" for r in data.get("top_risks", [])],
        ]

        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.DONE,
            findings=[f for f in findings if f],
            raw_output=resp.raw_text,
            metadata=data,
            tokens_input=resp.input_tokens,
            tokens_output=resp.output_tokens,
            tokens_cache_read=resp.cache_read_tokens,
            tokens_cache_creation=resp.cache_creation_tokens,
            model=resp.model,
        )


# ---------------------------------------------------------------------------
# Legacy compatibility — do not remove, kept for imports in external scripts
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict[str, Any]:
    """Deprecated JSON extractor.

    Left in place because external consumers imported it; new code should
    use native tool-use via ``core.AIClient.structured``.
    """
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
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return {}
