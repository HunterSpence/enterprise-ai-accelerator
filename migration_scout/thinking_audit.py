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
    audited.reasoning_trace  # Fable 5 summarized reasoning trace
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core import EFFORT_XHIGH, MODEL_FABLE_5, AIClient

# NOTE: structured outputs require additionalProperties=false on every
# object, so the evidence-weight map is expressed as an array of
# {attribute, weight} pairs and folded back into a dict after parsing.
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
            "type": "array",
            "description": "Input attributes and their weight in the decision (0..1).",
            "items": {
                "type": "object",
                "required": ["attribute", "weight"],
                "properties": {
                    "attribute": {"type": "string"},
                    "weight": {"type": "number"},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
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
    "Then return the final structured classification."
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
    model: str = MODEL_FABLE_5
    input_tokens: int = 0
    output_tokens: int = 0


class ThinkingAudit:
    """Run Fable 5 adaptive-thinking audits on high-stakes 6R classifications."""

    def __init__(self, ai: AIClient | None = None, effort: str = EFFORT_XHIGH) -> None:
        self._ai = ai or AIClient(default_model=MODEL_FABLE_5)
        self._effort = effort

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
            model=MODEL_FABLE_5,
            max_tokens=16_000,
            effort=self._effort,
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
            evidence_weight=_weights_to_dict(data.get("evidence_weight", [])),
            reasoning_trace=thinking,
            model=structured.model,
            input_tokens=structured.input_tokens,
            output_tokens=structured.output_tokens,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _weights_to_dict(weights: Any) -> dict[str, float]:
    """Fold the schema's [{attribute, weight}] array back into a dict.

    Also accepts a plain dict for backward compatibility with persisted
    pre-v0.5.0 records.
    """
    if isinstance(weights, dict):
        return {str(k): float(v) for k, v in weights.items() if isinstance(v, (int, float))}
    result: dict[str, float] = {}
    if isinstance(weights, list):
        for entry in weights:
            if isinstance(entry, dict) and "attribute" in entry and "weight" in entry:
                try:
                    result[str(entry["attribute"])] = float(entry["weight"])
                except (TypeError, ValueError):
                    continue
    return result


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
