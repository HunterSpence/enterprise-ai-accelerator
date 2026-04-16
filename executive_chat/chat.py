"""
executive_chat/chat.py
======================

Unified CTO / CIO chat layer. Loads every module's findings into a single
Opus 4.7 system prompt (up to 1M tokens) and answers executive questions
with schema-validated structured responses.

Typical flow:

    bundle = BriefingBundle(
        architecture_findings=arch_result.metadata,
        migration_plan=mig_result.metadata,
        compliance_violations=comp_result.metadata,
        finops_anomalies=finops_anomalies,
        audit_trail_summary=audit_summary,
    )
    chat = ExecutiveChat(AIClient())
    answer = await chat.ask(bundle, "Which workloads should we migrate first?")

The briefing is cached with ``cache_control: {"type": "1h"}`` so follow-up
questions during a 60-minute session pay cache-read prices (~0.1x) rather
than re-ingesting the full briefing every turn.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core import AIClient, MODEL_OPUS_4_7, THINKING_BUDGET_HIGH


# ---------------------------------------------------------------------------
# Briefing bundle — the full enterprise context loaded into system prompt
# ---------------------------------------------------------------------------

@dataclass
class BriefingBundle:
    """The full snapshot of enterprise analysis pushed into the chat system prompt."""

    architecture_findings: dict[str, Any] = field(default_factory=dict)
    migration_plan: dict[str, Any] = field(default_factory=dict)
    compliance_violations: dict[str, Any] = field(default_factory=dict)
    finops_anomalies: list[dict[str, Any]] = field(default_factory=list)
    audit_trail_summary: dict[str, Any] = field(default_factory=dict)
    risk_score: dict[str, Any] = field(default_factory=dict)
    organization_context: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        """Render the briefing as a single string block (for cached system prompt)."""
        sections = [
            ("## Organization Context", self.organization_context),
            ("## Architecture — CloudIQ findings", self.architecture_findings),
            ("## Migration — 6R plan", self.migration_plan),
            ("## Compliance — PolicyGuard violations", self.compliance_violations),
            ("## FinOps — Cost anomalies", {"anomalies": self.finops_anomalies}),
            ("## AIAuditTrail — Governance posture", self.audit_trail_summary),
            ("## Unified Risk Score — RiskAggregator output", self.risk_score),
        ]
        chunks: list[str] = []
        for title, body in sections:
            if not body:
                continue
            chunks.append(title)
            chunks.append("```json")
            chunks.append(json.dumps(body, indent=2, default=str))
            chunks.append("```")
        return "\n".join(chunks)


# ---------------------------------------------------------------------------
# Answer schema
# ---------------------------------------------------------------------------

@dataclass
class ExecutiveAnswer:
    """Structured answer returned to the executive UI."""

    answer: str
    confidence: str                 # low | medium | high
    supporting_findings: list[str]
    recommended_actions: list[str]
    risk_flags: list[str]
    follow_up_questions: list[str]
    source_modules: list[str]
    raw: dict[str, Any] = field(default_factory=dict)


_ANSWER_SCHEMA = {
    "type": "object",
    "required": [
        "answer", "confidence", "supporting_findings",
        "recommended_actions", "source_modules",
    ],
    "properties": {
        "answer": {
            "type": "string",
            "description": "Direct executive-ready answer (3-6 sentences).",
        },
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
        "supporting_findings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Finding IDs or short summaries that back the answer.",
        },
        "recommended_actions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concrete next steps, ordered by priority.",
        },
        "risk_flags": {
            "type": "array",
            "items": {"type": "string"},
        },
        "follow_up_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "source_modules": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "cloud_iq",
                    "migration_scout",
                    "policy_guard",
                    "finops_intelligence",
                    "ai_audit_trail",
                    "risk_aggregator",
                ],
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_PREFIX = (
    "You are the Enterprise AI Accelerator's executive chat assistant. "
    "You have been given a complete briefing from all six analysis modules "
    "(CloudIQ, MigrationScout, PolicyGuard, FinOps Intelligence, AIAuditTrail, "
    "and the unified RiskAggregator) covering the organization's cloud, "
    "migration, compliance, cost, and AI-governance posture. "
    "Your job is to answer C-suite questions directly, cite the underlying "
    "findings, and always propose a concrete next action. "
    "When in doubt, bias toward transparency about what the data does and "
    "does not support — do not speculate beyond the briefing.\n\n"
    "========== FULL ENTERPRISE BRIEFING (cached for 1h) ==========\n"
)


class ExecutiveChat:
    """Wraps an ``AIClient`` with an executive-chat-specific flow.

    Holds the ``BriefingBundle`` as the long-lived, 1h-cached system prompt
    prefix. Individual ``ask`` calls are cheap because only the user turn
    plus schema live outside the cache boundary.
    """

    def __init__(self, ai: AIClient | None = None) -> None:
        self._ai = ai or AIClient(default_model=MODEL_OPUS_4_7)

    def _build_system_prompt(self, bundle: BriefingBundle) -> str:
        return _SYSTEM_PROMPT_PREFIX + bundle.render()

    async def ask(
        self,
        bundle: BriefingBundle,
        question: str,
        *,
        use_extended_thinking: bool = False,
        max_tokens: int = 2048,
    ) -> ExecutiveAnswer:
        """Answer a question against the provided briefing bundle."""
        system = self._build_system_prompt(bundle)

        if use_extended_thinking:
            structured, thinking = await self._ai.structured_with_thinking(
                system=system,
                user=question,
                schema=_ANSWER_SCHEMA,
                tool_name="return_executive_answer",
                tool_description="Return the structured executive answer.",
                model=MODEL_OPUS_4_7,
                max_tokens=max_tokens,
                budget_tokens=THINKING_BUDGET_HIGH,
            )
            data = dict(structured.data)
            data.setdefault("thinking_trace", thinking)
        else:
            structured = await self._ai.structured(
                system=system,
                user=question,
                schema=_ANSWER_SCHEMA,
                tool_name="return_executive_answer",
                tool_description="Return the structured executive answer.",
                model=MODEL_OPUS_4_7,
                max_tokens=max_tokens,
            )
            data = structured.data

        return ExecutiveAnswer(
            answer=data.get("answer", ""),
            confidence=data.get("confidence", "medium"),
            supporting_findings=data.get("supporting_findings", []),
            recommended_actions=data.get("recommended_actions", []),
            risk_flags=data.get("risk_flags", []),
            follow_up_questions=data.get("follow_up_questions", []),
            source_modules=data.get("source_modules", []),
            raw=data,
        )
