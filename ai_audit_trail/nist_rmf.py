"""
nist_rmf.py — NIST AI Risk Management Framework (RMF) 1.0 integration.

NEW in V2. Maps AIAuditTrail audit log data to specific NIST AI RMF 1.0
subcategory evidence requirements across all four core functions:
GOVERN / MAP / MEASURE / MANAGE.

Key insight: Many NIST AI RMF subcategories AND EU AI Act Article 12
requirements are satisfied by the SAME AIAuditTrail audit log evidence.
This dual-framework mapping is the most efficient compliance path.

Reference: NIST AI 100-1, January 2023
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ai_audit_trail.chain import AuditChain, RiskTier
from ai_audit_trail.eu_ai_act import check_article_12_compliance


# ---------------------------------------------------------------------------
# NIST AI RMF subcategory definitions
# ---------------------------------------------------------------------------

@dataclass
class RMFSubcategory:
    """A single NIST AI RMF subcategory."""
    function: str        # GOVERN | MAP | MEASURE | MANAGE
    subcategory_id: str  # e.g., "MEASURE 2.5"
    title: str
    description: str
    audit_trail_evidence: str  # How AIAuditTrail satisfies this
    eu_ai_act_crossref: Optional[str] = None  # Cross-reference to EU AI Act article


# Core RMF subcategories that AIAuditTrail directly satisfies
_RMF_SUBCATEGORIES: list[RMFSubcategory] = [
    # --- GOVERN ---
    RMFSubcategory(
        function="GOVERN",
        subcategory_id="GOVERN 1.1",
        title="Policies, processes, procedures and practices across the organization",
        description="Policies for AI risk management are established, maintained, and reviewed.",
        audit_trail_evidence="AuditChain provides tamper-evident log of all AI decisions as organizational policy artifact",
        eu_ai_act_crossref="Article 9 (Risk management system)",
    ),
    RMFSubcategory(
        function="GOVERN",
        subcategory_id="GOVERN 1.7",
        title="Processes for decommissioning AI systems",
        description="Processes for decommissioning and phasing out AI systems are documented.",
        audit_trail_evidence="Audit log retention and export provides decommissioning audit trail",
        eu_ai_act_crossref="Article 12.3 (Log retention)",
    ),
    RMFSubcategory(
        function="GOVERN",
        subcategory_id="GOVERN 5.2",
        title="AI risk and impact are evaluated for AI-enabled third-party products",
        description="Risk identification includes AI-enabled products and services from third parties.",
        audit_trail_evidence="system_id field per entry tracks third-party AI system provenance",
        eu_ai_act_crossref="Article 28 (Obligations of deployers)",
    ),

    # --- MAP ---
    RMFSubcategory(
        function="MAP",
        subcategory_id="MAP 1.1",
        title="Context is established for the AI risk assessment",
        description="Context is established to prioritize risk assessment, with a high-level classification.",
        audit_trail_evidence="risk_tier field on every entry (MINIMAL/LIMITED/HIGH/UNACCEPTABLE) per EU AI Act",
        eu_ai_act_crossref="Article 6/7 + Annex III (Risk classification)",
    ),
    RMFSubcategory(
        function="MAP",
        subcategory_id="MAP 1.5",
        title="Likelihood and magnitude of each identified impact are estimated",
        description="The likelihood and magnitude of each identified impact are estimated.",
        audit_trail_evidence="Risk tier + decision_type on every entry enables impact likelihood analysis",
        eu_ai_act_crossref="Article 9.2 (Risk assessment)",
    ),
    RMFSubcategory(
        function="MAP",
        subcategory_id="MAP 2.1",
        title="Scientific findings and established norms used in AI design",
        description="The organization uses scientific findings and established norms during AI design.",
        audit_trail_evidence="SHA-256 Merkle chain provides cryptographic evidence of design decisions",
        eu_ai_act_crossref=None,
    ),
    RMFSubcategory(
        function="MAP",
        subcategory_id="MAP 3.5",
        title="Processes for AI system testing are documented",
        description="Practices and personnel for AI testing are identified and documented.",
        audit_trail_evidence="Test session entries with session_id enable test run traceability",
        eu_ai_act_crossref="Article 9.7 (Testing procedures)",
    ),

    # --- MEASURE ---
    RMFSubcategory(
        function="MEASURE",
        subcategory_id="MEASURE 1.1",
        title="Approaches for measuring AI risks are identified and prioritized",
        description="Approaches for measuring risk, benefits, and impacts are aligned with risk priorities.",
        audit_trail_evidence="QueryEngine.aggregate_stats() provides risk tier distribution and trend data",
        eu_ai_act_crossref="Article 9.4 (Risk identification and analysis)",
    ),
    RMFSubcategory(
        function="MEASURE",
        subcategory_id="MEASURE 2.2",
        title="AI system data and performance are continuously monitored",
        description="Evaluations of AI system performance are routine.",
        audit_trail_evidence="Continuous latency_ms, input_tokens, output_tokens capture enables performance monitoring",
        eu_ai_act_crossref="Article 72 (Post-market monitoring)",
    ),
    RMFSubcategory(
        function="MEASURE",
        subcategory_id="MEASURE 2.5",
        title="AI system to be deployed is demonstrated to be valid and reliable",
        description="The AI system is demonstrated to be valid and reliable through systematic evaluation.",
        audit_trail_evidence="Chain integrity verification (verify_chain()) + Merkle proof per entry demonstrates reliability",
        eu_ai_act_crossref="Article 12.2 (Tamper-evident logging)",
    ),
    RMFSubcategory(
        function="MEASURE",
        subcategory_id="MEASURE 2.6",
        title="AI system to be deployed is demonstrated to be interpretable",
        description="The AI system and its outputs can be explained to relevant stakeholders.",
        audit_trail_evidence="QueryEngine.explain(entry_id) provides per-decision interpretability evidence",
        eu_ai_act_crossref="Article 13 (Transparency + explainability)",
    ),
    RMFSubcategory(
        function="MEASURE",
        subcategory_id="MEASURE 2.7",
        title="AI system security and resilience are evaluated",
        description="AI system security and resilience are evaluated through red-teaming.",
        audit_trail_evidence="Tamper report (TamperReport) with tampered_entries field surfaces security threats",
        eu_ai_act_crossref="Article 15 (Accuracy, robustness, cybersecurity)",
    ),
    RMFSubcategory(
        function="MEASURE",
        subcategory_id="MEASURE 2.10",
        title="Privacy risk of AI system is examined",
        description="Privacy risk of the AI system — as identified in the MAP function — is examined.",
        audit_trail_evidence="Privacy by design: input/output stored as SHA-256 hashes only (no plaintext)",
        eu_ai_act_crossref="Article 10.5 (Privacy and data governance)",
    ),
    RMFSubcategory(
        function="MEASURE",
        subcategory_id="MEASURE 2.13",
        title="Effectiveness of the applied guidelines and standards assessed",
        description="Effectiveness of the applied guidelines, procedures, and standards is periodically assessed.",
        audit_trail_evidence="Article 12 compliance score (0-100) + gap analysis provides effectiveness metric",
        eu_ai_act_crossref="Article 12 (Record-keeping)",
    ),

    # --- MANAGE ---
    RMFSubcategory(
        function="MANAGE",
        subcategory_id="MANAGE 1.3",
        title="Responses to the identified and measured AI risks are prioritized",
        description="Responses to identified, measured AI risks are prioritized based on impact.",
        audit_trail_evidence="Incident priority classification (P0-SAFETY → P3-COST) drives response queue",
        eu_ai_act_crossref="Article 9.5 (Risk management measures)",
    ),
    RMFSubcategory(
        function="MANAGE",
        subcategory_id="MANAGE 2.2",
        title="Mechanisms in place to respond to anomalous AI system behavior",
        description="Mechanisms are in place to respond to anomalous AI system behavior.",
        audit_trail_evidence="detect_article_62_incidents() + IncidentManager auto-detects anomalies from log patterns",
        eu_ai_act_crossref="Article 62 (Reporting serious incidents)",
    ),
    RMFSubcategory(
        function="MANAGE",
        subcategory_id="MANAGE 3.1",
        title="AI risks and benefits from real-world deployment are monitored",
        description="AI risks and benefits from real-world deployment are monitored and evaluated.",
        audit_trail_evidence="Continuous audit log + dashboard provides real-time risk monitoring",
        eu_ai_act_crossref="Article 72 (Post-market monitoring by providers)",
    ),
    RMFSubcategory(
        function="MANAGE",
        subcategory_id="MANAGE 4.1",
        title="Post-deployment AI risks and impacts are evaluated",
        description="Post-deployment AI risks and impacts are evaluated including feedback.",
        audit_trail_evidence="Historical audit log enables post-deployment impact analysis via QueryEngine",
        eu_ai_act_crossref="Article 72 + Article 73 (Incident reporting)",
    ),
]

_RMF_BY_ID: dict[str, RMFSubcategory] = {s.subcategory_id: s for s in _RMF_SUBCATEGORIES}


# ---------------------------------------------------------------------------
# Maturity scoring model
# ---------------------------------------------------------------------------

@dataclass
class RMFMaturityScore:
    """NIST AI RMF maturity score for a single function."""
    function: str
    score: float          # 1.0 - 5.0 scale
    level: str            # Initiated | Repeatable | Defined | Managed | Optimizing
    subcategories_met: list[str]
    subcategories_partial: list[str]
    subcategories_missing: list[str]
    evidence_summary: str

    @property
    def level_description(self) -> str:
        levels = {
            "Initiated": "Ad-hoc processes, not yet repeatable",
            "Repeatable": "Processes exist but are not fully documented",
            "Defined": "Processes are documented and standardized",
            "Managed": "Processes are measured and controlled",
            "Optimizing": "Focus on continuous improvement",
        }
        return levels.get(self.level, "Unknown")


def _score_to_level(score: float) -> str:
    if score >= 4.5:
        return "Optimizing"
    elif score >= 3.5:
        return "Managed"
    elif score >= 2.5:
        return "Defined"
    elif score >= 1.5:
        return "Repeatable"
    return "Initiated"


# ---------------------------------------------------------------------------
# RMF Assessment Engine
# ---------------------------------------------------------------------------

@dataclass
class RMFAssessment:
    """Full NIST AI RMF assessment result."""
    system_id: str
    system_name: str
    assessed_at: str
    govern_score: RMFMaturityScore
    map_score: RMFMaturityScore
    measure_score: RMFMaturityScore
    manage_score: RMFMaturityScore
    overall_score: float
    eu_ai_act_article_12_score: int
    dual_framework_evidence: list[dict[str, str]]  # Where NIST + EU AI Act overlap
    recommendations: list[str]

    @property
    def overall_level(self) -> str:
        return _score_to_level(self.overall_score)

    def get_function_score(self, function: str) -> float:
        """Return function maturity score as a 0-100 percentage."""
        mapping = {
            "GOVERN": self.govern_score,
            "MAP": self.map_score,
            "MEASURE": self.measure_score,
            "MANAGE": self.manage_score,
        }
        score_obj = mapping.get(function.upper())
        if score_obj is None:
            return 0.0
        # Convert 1-5 scale to 0-100 percentage
        return round((score_obj.score - 1.0) / 4.0 * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_id": self.system_id,
            "system_name": self.system_name,
            "assessed_at": self.assessed_at,
            "overall_score": round(self.overall_score, 2),
            "overall_level": self.overall_level,
            "govern": {
                "score": round(self.govern_score.score, 2),
                "level": self.govern_score.level,
                "met": len(self.govern_score.subcategories_met),
                "missing": len(self.govern_score.subcategories_missing),
            },
            "map": {
                "score": round(self.map_score.score, 2),
                "level": self.map_score.level,
                "met": len(self.map_score.subcategories_met),
                "missing": len(self.map_score.subcategories_missing),
            },
            "measure": {
                "score": round(self.measure_score.score, 2),
                "level": self.measure_score.level,
                "met": len(self.measure_score.subcategories_met),
                "missing": len(self.measure_score.subcategories_missing),
            },
            "manage": {
                "score": round(self.manage_score.score, 2),
                "level": self.manage_score.level,
                "met": len(self.manage_score.subcategories_met),
                "missing": len(self.manage_score.subcategories_missing),
            },
            "eu_ai_act_article_12_score": self.eu_ai_act_article_12_score,
            "dual_framework_evidence_count": len(self.dual_framework_evidence),
            "recommendations": self.recommendations,
        }


def assess_nist_rmf(
    chain: AuditChain,
    system_id: str,
    system_name: str,
    has_risk_policy: bool = False,
    has_incident_response_plan: bool = False,
    has_third_party_assessment: bool = False,
) -> RMFAssessment:
    """
    Perform a NIST AI RMF 1.0 assessment based on audit log data.

    Maps log evidence to RMF subcategories. Returns maturity scores
    per function (GOVERN/MAP/MEASURE/MANAGE) on a 1-5 scale.

    Parameters
    ----------
    chain: AuditChain to assess
    system_id: AI system identifier
    system_name: Human-readable system name
    has_risk_policy: Organization has documented AI risk policy
    has_incident_response_plan: Incident response plan exists
    has_third_party_assessment: Third-party AI risk assessment completed
    """
    entries = chain.query(system_id=system_id, limit=1000)
    total_entries = len(entries)
    article_12 = check_article_12_compliance(chain)
    tamper_report = chain.verify_chain()

    recommendations: list[str] = []

    # ---- GOVERN ----
    govern_met = []
    govern_missing = []

    if total_entries > 0:
        govern_met.append("GOVERN 1.1")  # Audit log proves policy exists
    else:
        govern_missing.append("GOVERN 1.1")

    if article_12.score >= 80:
        govern_met.append("GOVERN 1.7")
    else:
        govern_missing.append("GOVERN 1.7")
        recommendations.append("Improve Article 12 score to ≥80 to satisfy GOVERN 1.7")

    if has_third_party_assessment:
        govern_met.append("GOVERN 5.2")
    else:
        govern_missing.append("GOVERN 5.2")
        recommendations.append("Complete third-party AI risk assessment to satisfy GOVERN 5.2")

    if has_risk_policy:
        govern_met.append("GOVERN 1.1 (policy)")

    govern_pct = len(govern_met) / max(len(govern_met) + len(govern_missing), 1)
    govern_score_val = 1.0 + (govern_pct * 4.0)

    # ---- MAP ----
    map_met = []
    map_missing = []

    has_risk_tiers = any(e.risk_tier for e in entries)
    if has_risk_tiers:
        map_met.extend(["MAP 1.1", "MAP 1.5"])
    else:
        map_missing.extend(["MAP 1.1", "MAP 1.5"])
        recommendations.append("Tag all entries with risk_tier to satisfy MAP 1.1 and MAP 1.5")

    if total_entries > 0:
        map_met.append("MAP 2.1")
        map_met.append("MAP 3.5")
    else:
        map_missing.extend(["MAP 2.1", "MAP 3.5"])

    map_pct = len(map_met) / max(len(map_met) + len(map_missing), 1)
    map_score_val = 1.0 + (map_pct * 4.0)

    # ---- MEASURE ----
    measure_met = []
    measure_missing = []

    if total_entries > 0:
        measure_met.extend(["MEASURE 1.1", "MEASURE 2.2", "MEASURE 2.10"])

    if tamper_report.is_valid and total_entries > 0:
        measure_met.extend(["MEASURE 2.5", "MEASURE 2.7"])
    else:
        measure_missing.extend(["MEASURE 2.5", "MEASURE 2.7"])
        if not tamper_report.is_valid:
            recommendations.append(
                "CRITICAL: Resolve chain integrity failures to satisfy MEASURE 2.5 and MEASURE 2.7"
            )

    if total_entries > 0:
        measure_met.extend(["MEASURE 2.6", "MEASURE 2.13"])
    else:
        measure_missing.extend(["MEASURE 2.6", "MEASURE 2.13"])

    measure_pct = len(measure_met) / max(len(measure_met) + len(measure_missing), 1)
    measure_score_val = 1.0 + (measure_pct * 4.0)

    # ---- MANAGE ----
    manage_met = []
    manage_missing = []

    if total_entries > 0:
        manage_met.extend(["MANAGE 2.2", "MANAGE 3.1", "MANAGE 4.1"])

    if has_incident_response_plan:
        manage_met.append("MANAGE 1.3")
    else:
        manage_missing.append("MANAGE 1.3")
        recommendations.append(
            "Implement incident response playbooks to satisfy MANAGE 1.3. "
            "AIAuditTrail IncidentManager provides automated playbooks."
        )

    manage_pct = len(manage_met) / max(len(manage_met) + len(manage_missing), 1)
    manage_score_val = 1.0 + (manage_pct * 4.0)

    # ---- Overall ----
    overall = (govern_score_val + map_score_val + measure_score_val + manage_score_val) / 4.0

    # ---- Dual-framework evidence (NIST + EU AI Act overlap) ----
    dual_evidence = [
        {
            "nist": "MEASURE 2.5",
            "eu_ai_act": "Article 12.2",
            "evidence": "SHA-256 Merkle tree chain integrity verification",
            "status": "SATISFIED" if tamper_report.is_valid else "FAILED",
        },
        {
            "nist": "MEASURE 2.6",
            "eu_ai_act": "Article 13",
            "evidence": "QueryEngine.explain() per-decision interpretability",
            "status": "SATISFIED" if total_entries > 0 else "PENDING",
        },
        {
            "nist": "MANAGE 2.2",
            "eu_ai_act": "Article 62",
            "evidence": "detect_article_62_incidents() anomaly detection from log patterns",
            "status": "SATISFIED" if total_entries > 0 else "PENDING",
        },
        {
            "nist": "MEASURE 2.10",
            "eu_ai_act": "Article 10.5",
            "evidence": "Privacy by design: SHA-256 hashes only, no plaintext stored by default",
            "status": "SATISFIED",
        },
        {
            "nist": "MEASURE 2.13",
            "eu_ai_act": "Article 12",
            "evidence": f"Article 12 compliance score: {article_12.score}/100",
            "status": "SATISFIED" if article_12.score >= 80 else "PARTIAL",
        },
        {
            "nist": "MAP 1.1",
            "eu_ai_act": "Article 6/7 + Annex III",
            "evidence": "risk_tier field on every audit entry (MINIMAL/LIMITED/HIGH/UNACCEPTABLE)",
            "status": "SATISFIED" if has_risk_tiers else "PENDING",
        },
    ]

    return RMFAssessment(
        system_id=system_id,
        system_name=system_name,
        assessed_at=datetime.now(timezone.utc).isoformat(),
        govern_score=RMFMaturityScore(
            function="GOVERN",
            score=govern_score_val,
            level=_score_to_level(govern_score_val),
            subcategories_met=govern_met,
            subcategories_partial=[],
            subcategories_missing=govern_missing,
            evidence_summary=f"Audit log with {total_entries:,} entries; policy artifacts present",
        ),
        map_score=RMFMaturityScore(
            function="MAP",
            score=map_score_val,
            level=_score_to_level(map_score_val),
            subcategories_met=map_met,
            subcategories_partial=[],
            subcategories_missing=map_missing,
            evidence_summary=f"Risk tier classification on {total_entries:,} entries",
        ),
        measure_score=RMFMaturityScore(
            function="MEASURE",
            score=measure_score_val,
            level=_score_to_level(measure_score_val),
            subcategories_met=measure_met,
            subcategories_partial=[],
            subcategories_missing=measure_missing,
            evidence_summary=(
                f"Chain integrity: {'VALID' if tamper_report.is_valid else 'COMPROMISED'}. "
                f"Article 12 score: {article_12.score}/100."
            ),
        ),
        manage_score=RMFMaturityScore(
            function="MANAGE",
            score=manage_score_val,
            level=_score_to_level(manage_score_val),
            subcategories_met=manage_met,
            subcategories_partial=[],
            subcategories_missing=manage_missing,
            evidence_summary="Incident detection and response capabilities",
        ),
        overall_score=overall,
        eu_ai_act_article_12_score=article_12.score,
        dual_framework_evidence=dual_evidence,
        recommendations=recommendations,
    )


def get_rmf_subcategory(subcategory_id: str) -> Optional[RMFSubcategory]:
    """Look up a specific RMF subcategory by ID (e.g., 'MEASURE 2.5')."""
    return _RMF_BY_ID.get(subcategory_id)


def list_rmf_subcategories(function: Optional[str] = None) -> list[RMFSubcategory]:
    """List all RMF subcategories, optionally filtered by function."""
    if function:
        return [s for s in _RMF_SUBCATEGORIES if s.function == function.upper()]
    return list(_RMF_SUBCATEGORIES)
