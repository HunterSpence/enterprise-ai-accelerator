"""
policy_guard/thinking_audit.py
==============================

Fable 5 adaptive-thinking wrapper around PolicyGuard's bias detection and
policy scanning outputs. Produces a full reasoning trace suitable for EU
AI Act Article 12 Annex IV technical documentation.

When the stakes of a decision are high (the model flags a hiring-tool
training set as biased, or an IaC template as PCI-DSS non-compliant), the
auditor needs more than a pass/fail — they need "why did the model think
so?" This module returns the thinking trace alongside a validated
structured decision.

Usage:

    auditor = PolicyThinkingAudit()
    audit = await auditor.audit_policy_decision(
        policy_name="CIS AWS 1.5 — 2.2 EBS Encryption",
        resource_summary={...},
        preliminary_verdict="fail",
    )
    audit.reasoning_trace   # persistable into AIAuditTrail
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core import EFFORT_XHIGH, MODEL_FABLE_5, AIClient

_POLICY_AUDIT_SCHEMA = {
    "type": "object",
    "required": ["verdict", "severity", "justification", "control_reference"],
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail", "partial", "not_applicable"]},
        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
        "justification": {"type": "string"},
        "control_reference": {
            "type": "string",
            "description": "Canonical control ID (e.g. 'CIS AWS 2.2', 'SOC 2 CC6.1', 'HIPAA §164.312(a)(2)(iv)').",
        },
        "remediation": {"type": "string"},
        "evidence_cited": {
            "type": "array",
            "items": {"type": "string"},
        },
        "blast_radius": {
            "type": "object",
            "properties": {
                "affected_resources": {"type": "array", "items": {"type": "string"}},
                "data_sensitivity": {"type": "string", "enum": ["public", "internal", "confidential", "restricted"]},
                "exploitability": {"type": "string", "enum": ["theoretical", "low", "medium", "high"]},
            },
        },
    },
}


_BIAS_AUDIT_SCHEMA = {
    "type": "object",
    "required": ["bias_detected", "bias_types", "severity", "evidence"],
    "properties": {
        "bias_detected": {"type": "boolean"},
        "bias_types": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "demographic_parity", "equal_opportunity", "disparate_impact",
                    "representation_bias", "historical_bias", "measurement_bias",
                    "aggregation_bias", "evaluation_bias", "deployment_bias",
                ],
            },
        },
        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "affected_groups": {"type": "array", "items": {"type": "string"}},
        "mitigation": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ordered list of mitigation steps, most effective first.",
        },
        "eu_ai_act_article_references": {
            "type": "array",
            "items": {"type": "string"},
            "description": "EU AI Act articles triggered by this finding.",
        },
    },
}


_POLICY_SYSTEM_PROMPT = (
    "You are a senior cloud security / compliance auditor reviewing a policy "
    "decision for a formal audit record. Think carefully through "
    "the control text, the evidence supplied, plausible alternative verdicts, "
    "and the scope of impact, before returning the final structured verdict. "
    "Your reasoning trace is persisted as Annex IV technical documentation."
)

_BIAS_SYSTEM_PROMPT = (
    "You are a senior ML fairness auditor performing a bias assessment on a "
    "training dataset or model output. Think carefully through the "
    "multiple fairness definitions (demographic parity, equal opportunity, "
    "calibration) and which groups are at risk. Cite concrete evidence from "
    "the provided statistics. Your reasoning trace is persisted as EU AI Act "
    "Article 15 accuracy and robustness documentation."
)


@dataclass
class PolicyAudit:
    policy_name: str
    verdict: str
    severity: str
    justification: str
    control_reference: str
    remediation: str = ""
    evidence_cited: list[str] = field(default_factory=list)
    blast_radius: dict[str, Any] = field(default_factory=dict)
    reasoning_trace: str = ""
    model: str = MODEL_FABLE_5
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class BiasAudit:
    subject: str
    bias_detected: bool
    bias_types: list[str]
    severity: str
    evidence: list[str]
    affected_groups: list[str] = field(default_factory=list)
    mitigation: list[str] = field(default_factory=list)
    eu_ai_act_article_references: list[str] = field(default_factory=list)
    reasoning_trace: str = ""
    model: str = MODEL_FABLE_5
    input_tokens: int = 0
    output_tokens: int = 0


class PolicyThinkingAudit:
    """Adaptive-thinking wrapper for high-stakes policy and bias decisions."""

    def __init__(
        self,
        ai: AIClient | None = None,
        effort: str = EFFORT_XHIGH,
    ) -> None:
        self._ai = ai or AIClient(default_model=MODEL_FABLE_5)
        self._effort = effort

    async def audit_policy_decision(
        self,
        *,
        policy_name: str,
        resource_summary: dict[str, Any],
        preliminary_verdict: str,
        preliminary_evidence: list[str] | None = None,
    ) -> PolicyAudit:
        import json as _json

        user = (
            f"## Policy under review\n{policy_name}\n\n"
            f"## Preliminary verdict\n{preliminary_verdict}\n\n"
            f"## Resource under audit\n"
            f"```json\n{_json.dumps(resource_summary, indent=2, default=str)}\n```\n\n"
            f"## Preliminary evidence\n"
            + ("\n".join(f"- {e}" for e in (preliminary_evidence or [])) or "(none)")
        )

        structured, thinking = await self._ai.structured_with_thinking(
            system=_POLICY_SYSTEM_PROMPT,
            user=user,
            schema=_POLICY_AUDIT_SCHEMA,
            model=MODEL_FABLE_5,
            max_tokens=16_000,
            effort=self._effort,
        )

        data = structured.data
        return PolicyAudit(
            policy_name=policy_name,
            verdict=data.get("verdict", preliminary_verdict),
            severity=data.get("severity", "medium"),
            justification=data.get("justification", ""),
            control_reference=data.get("control_reference", ""),
            remediation=data.get("remediation", ""),
            evidence_cited=data.get("evidence_cited", []),
            blast_radius=data.get("blast_radius", {}),
            reasoning_trace=thinking,
            model=structured.model,
            input_tokens=structured.input_tokens,
            output_tokens=structured.output_tokens,
        )

    async def audit_bias_decision(
        self,
        *,
        subject: str,
        statistics: dict[str, Any],
        preliminary_flags: list[str] | None = None,
    ) -> BiasAudit:
        import json as _json

        user = (
            f"## Subject\n{subject}\n\n"
            f"## Dataset / model statistics\n"
            f"```json\n{_json.dumps(statistics, indent=2, default=str)}\n```\n\n"
            f"## Preliminary bias flags\n"
            + ("\n".join(f"- {f}" for f in (preliminary_flags or [])) or "(none)")
        )

        structured, thinking = await self._ai.structured_with_thinking(
            system=_BIAS_SYSTEM_PROMPT,
            user=user,
            schema=_BIAS_AUDIT_SCHEMA,
            model=MODEL_FABLE_5,
            max_tokens=16_000,
            effort=self._effort,
        )

        data = structured.data
        return BiasAudit(
            subject=subject,
            bias_detected=bool(data.get("bias_detected", False)),
            bias_types=data.get("bias_types", []),
            severity=data.get("severity", "medium"),
            evidence=data.get("evidence", []),
            affected_groups=data.get("affected_groups", []),
            mitigation=data.get("mitigation", []),
            eu_ai_act_article_references=data.get("eu_ai_act_article_references", []),
            reasoning_trace=thinking,
            model=structured.model,
            input_tokens=structured.input_tokens,
            output_tokens=structured.output_tokens,
        )
