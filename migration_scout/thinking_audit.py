"""
migration_scout/thinking_audit.py
=================================

Opus 4.7 extended-thinking audit layer on top of the existing 6R assessor.

When a workload is flagged as high-business-criticality or lands on a
Replatform/Refactor path, auditors (and risk committees) want to see the
chain of reasoning that produced the recommendation. The existing Haiku
enrichment in ``assessor.py`` returns only a rationale; this module runs
the same decision through Opus 4.7 with extended thinking enabled, then
returns BOTH the final classification AND the reasoning trace — suitable
for persistence into AIAuditTrail as Annex IV technical documentation.

This module deliberately does not replace ``WorkloadAssessor`` — it wraps
it. Callers opt in:

    assessor = WorkloadAssessor(use_ai=True)
    standard = assessor.assess_workload(w)
    auditor = ThinkingAudit()
    audited = await auditor.audit(w, standard)
    audited.reasoning_trace  # full Opus 4.7 thinking trace
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core import AIClient, MODEL_OPUS_4_7, THINKING_BUDGET_XHIGH


_AUDIT_SCHEMA = {
    "type": "object",
    "required": ["strategy", "rationale", "confidence", "concerns"],
    "properties": {
        "strategy": {
            "type": "string",
            "enum": ["Rehost", "Replatform", "Repurchase", "Refactor", "Retire", "Retain"],
        },
        "rationale": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "concerns": {"type": "array", "items": {"type": "string"}},
        "blockers": {"type": "array", "items": {"type": "string"}},
        "evidence_weight": {
            "type": "object",
            "additionalProperties": {"type": "number"},
            "description": "Map of input attribute → weight in the decision (0..1).",
        },
    },
}


_SYSTEM_PROMPT = (
    "You are a senior migration architect performing an AUDITABLE 6R classification. "
    "Unlike a real-time classification call, your reasoning trace is going to be "
    "persisted as Annex IV technical documentation for an AI governance audit. "
    "Use the extended-thinking budget to walk through: "
    "(1) what the workload's technical profile implies, "
    "(2) what the business criticality + license cost + team familiarity imply, "
    "(3) which 6R strategies are plausible and why you rejected the others, "
    "(4) what evidence would change your answer. "
    "Then return the final classification via the tool."
)


@dataclass
class AuditedAssessment:
    workload_name: str
    ml_strategy: str
    ai_strategy: str
    audited_strategy: str
    confidence: str
    rationale: str
    concerns: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    evidence_weight: dict[str, float] = field(default_factory=dict)
    reasoning_trace: str = ""
    model: str = MODEL_OPUS_4_7
    input_tokens: int = 0
    output_tokens: int = 0


class ThinkingAudit:
    """Run Opus 4.7 extended-thinking audits on high-stakes 6R classifications."""

    def __init__(self, ai: AIClient | None = None, thinking_budget: int = THINKING_BUDGET_XHIGH) -> None:
        self._ai = ai or AIClient(default_model=MODEL_OPUS_4_7)
        self._thinking_budget = thinking_budget

    async def audit(
        self,
        workload: Any,
        standard_assessment: Any | None = None,
    ) -> AuditedAssessment:
        """Audit a WorkloadInventory + optional pre-existing WorkloadAssessment.

        ``workload`` is typed as ``Any`` to avoid a hard import dependency on
        pydantic models — any object with ``name``, ``workload_type``,
        ``business_criticality`` etc. attributes works. Dicts also work.
        """
        profile = _serialize_workload(workload)
        ml_strategy = _field(standard_assessment, "ml_strategy") or _field(standard_assessment, "strategy") or "unknown"
        ai_strategy = _field(standard_assessment, "strategy") or ml_strategy

        user = (
            "Audit the following workload and the existing preliminary 6R classification.\n"
            "Produce a final classification plus the reasoning trace that an auditor "
            "would need to accept the decision.\n\n"
            f"## Workload profile\n```json\n{json.dumps(profile, indent=2, default=str)}\n```\n\n"
            f"## Preliminary classification\n"
            f"- ML strategy: {ml_strategy}\n"
            f"- AI-enriched strategy: {ai_strategy}\n"
        )

        structured, thinking = await self._ai.structured_with_thinking(
            system=_SYSTEM_PROMPT,
            user=user,
            schema=_AUDIT_SCHEMA,
            tool_name="emit_audited_classification",
            tool_description="Return the audited 6R classification.",
            model=MODEL_OPUS_4_7,
            max_tokens=2048,
            budget_tokens=self._thinking_budget,
        )

        data = structured.data
        return AuditedAssessment(
            workload_name=profile.get("name", "unknown"),
            ml_strategy=str(ml_strategy),
            ai_strategy=str(ai_strategy),
            audited_strategy=data.get("strategy", ai_strategy),
            confidence=data.get("confidence", "medium"),
            rationale=data.get("rationale", ""),
            concerns=data.get("concerns", []),
            blockers=data.get("blockers", []),
            evidence_weight=data.get("evidence_weight", {}),
            reasoning_trace=thinking,
            model=structured.model,
            input_tokens=structured.input_tokens,
            output_tokens=structured.output_tokens,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_workload(workload: Any) -> dict[str, Any]:
    """Best-effort attribute grab for dataclasses, pydantic models, and dicts."""
    if isinstance(workload, dict):
        return dict(workload)
    if hasattr(workload, "model_dump"):
        return workload.model_dump()
    if hasattr(workload, "__dict__"):
        return {
            k: v
            for k, v in vars(workload).items()
            if not k.startswith("_")
        }
    return {"value": str(workload)}


def _field(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
