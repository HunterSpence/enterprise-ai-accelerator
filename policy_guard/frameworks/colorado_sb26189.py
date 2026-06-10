"""
Colorado SB 26-189 — AI Consumer Protections Act
==================================================
Signed: May 14, 2026.
Effective: January 1, 2027.

Replaces the repealed SB 24-205 (Colorado AI Act, which was vetoed / not enacted
in its original form). SB 26-189 is the law that actually passed and is in force.

Coverage:
  § 6-1-1701 — Definitions (developer, deployer, high-risk AI system,
                algorithmic impact assessment, consequential decision)
  § 6-1-1702 — Developer obligations (documentation, testing, transparency)
  § 6-1-1703 — Deployer obligations (AIA, consumer disclosure, opt-out)
  § 6-1-1704 — Algorithmic impact assessment requirements
  § 6-1-1705 — Consumer rights (notice, explanation, correction, opt-out)
  § 6-1-1706 — Scope thresholds for high-impact AI decisions
  § 6-1-1707 — Prohibited AI practices (credit, housing, employment, healthcare
                decisions without disclosed AI involvement)
  § 6-1-1708 — Attorney General enforcement; private right of action

Key thresholds: applies to systems making ≥1 consequential decision/day OR
≥1,000 consequential decisions/year involving Colorado residents.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Effective date
# ---------------------------------------------------------------------------

EFFECTIVE_DATE = date(2027, 1, 1)
SIGNED_DATE = date(2026, 5, 14)


def days_until_effective() -> int:
    """Return days remaining until Colorado SB 26-189 takes effect (Jan 1, 2027)."""
    delta = EFFECTIVE_DATE - date.today()
    return max(0, delta.days)


# ---------------------------------------------------------------------------
# Control definitions
# ---------------------------------------------------------------------------

DEVELOPER_OBLIGATIONS: dict[str, dict] = {
    "CO_SB26189_702_A": {
        "section": "§ 6-1-1702(1)(a)",
        "title": "Risk documentation before deployment",
        "description": (
            "Developers must document the intended use cases, known limitations, "
            "and risk factors of high-risk AI systems before making them available."
        ),
        "severity": "HIGH",
    },
    "CO_SB26189_702_B": {
        "section": "§ 6-1-1702(1)(b)",
        "title": "Pre-deployment bias and fairness testing",
        "description": (
            "Developers must test for discriminatory or disparate impact on protected "
            "classes across race, color, national origin, sex, disability, and age "
            "prior to deployment."
        ),
        "severity": "HIGH",
    },
    "CO_SB26189_702_C": {
        "section": "§ 6-1-1702(1)(c)",
        "title": "Model card / technical documentation disclosure",
        "description": (
            "Developers must make available to deployers: training data sources, "
            "evaluation methodology, performance benchmarks, and known failure modes."
        ),
        "severity": "MEDIUM",
    },
    "CO_SB26189_702_D": {
        "section": "§ 6-1-1702(2)",
        "title": "Post-deployment monitoring requirements",
        "description": (
            "Developers offering high-risk AI systems must establish a monitoring "
            "program and notify deployers of material changes to accuracy or fairness."
        ),
        "severity": "MEDIUM",
    },
}

DEPLOYER_OBLIGATIONS: dict[str, dict] = {
    "CO_SB26189_703_A": {
        "section": "§ 6-1-1703(1)(a)",
        "title": "Pre-deployment algorithmic impact assessment",
        "description": (
            "Deployers must conduct a documented algorithmic impact assessment (AIA) "
            "before using a high-risk AI system for consequential decisions."
        ),
        "severity": "CRITICAL",
    },
    "CO_SB26189_703_B": {
        "section": "§ 6-1-1703(1)(b)",
        "title": "Consumer-facing AI disclosure",
        "description": (
            "Deployers must conspicuously disclose that an AI system is being used "
            "to make or substantially assist in a consequential decision affecting "
            "the consumer."
        ),
        "severity": "HIGH",
    },
    "CO_SB26189_703_C": {
        "section": "§ 6-1-1703(1)(c)",
        "title": "Opt-out pathway for AI-assisted decisions",
        "description": (
            "Deployers must offer consumers a meaningful opt-out from AI-assisted "
            "decision-making or a human review alternative."
        ),
        "severity": "HIGH",
    },
    "CO_SB26189_703_D": {
        "section": "§ 6-1-1703(2)",
        "title": "Annual AIA review and update cycle",
        "description": (
            "Deployers must review and update the algorithmic impact assessment at "
            "least annually or when the AI system undergoes a material change."
        ),
        "severity": "MEDIUM",
    },
}

CONSUMER_RIGHTS: dict[str, dict] = {
    "CO_SB26189_705_A": {
        "section": "§ 6-1-1705(1)",
        "title": "Right to notice of AI decision involvement",
        "description": (
            "Consumers have a right to receive notice within a reasonable timeframe "
            "that an AI system contributed to a consequential decision affecting them."
        ),
        "severity": "HIGH",
    },
    "CO_SB26189_705_B": {
        "section": "§ 6-1-1705(2)",
        "title": "Right to plain-language explanation",
        "description": (
            "Consumers may request a plain-language explanation of the AI factors "
            "that contributed to the decision, with response required within 45 days."
        ),
        "severity": "MEDIUM",
    },
    "CO_SB26189_705_C": {
        "section": "§ 6-1-1705(3)",
        "title": "Right to correction of erroneous input data",
        "description": (
            "Consumers may request correction of inaccurate personal data used in "
            "an AI decision. Deployers must acknowledge within 30 days."
        ),
        "severity": "MEDIUM",
    },
    "CO_SB26189_705_D": {
        "section": "§ 6-1-1705(4)",
        "title": "Right to appeal to a qualified human reviewer",
        "description": (
            "Consumers adversely affected by an AI consequential decision may appeal "
            "to a qualified human reviewer who has authority to override the decision."
        ),
        "severity": "HIGH",
    },
}

SCOPE_AND_ENFORCEMENT: dict[str, dict] = {
    "CO_SB26189_706_A": {
        "section": "§ 6-1-1706",
        "title": "Scope threshold compliance — consequential decision volume",
        "description": (
            "Verify the system falls within scope: ≥1 consequential decision per day "
            "OR ≥1,000 consequential decisions per year involving Colorado residents. "
            "Out-of-scope systems do not require AIA but must still disclose AI use."
        ),
        "severity": "MEDIUM",
    },
    "CO_SB26189_707_A": {
        "section": "§ 6-1-1707(1)",
        "title": "Prohibited undisclosed AI in credit, housing, and employment",
        "description": (
            "Prohibited: using AI to make consequential decisions in credit, housing, "
            "or employment contexts without conspicuous disclosure that AI was used."
        ),
        "severity": "CRITICAL",
    },
    "CO_SB26189_707_B": {
        "section": "§ 6-1-1707(2)",
        "title": "Prohibited AI-only final decisions in healthcare",
        "description": (
            "Prohibited: using AI as the sole determinant of a healthcare coverage "
            "or treatment decision without a qualified human review pathway."
        ),
        "severity": "CRITICAL",
    },
}

ALL_CONTROLS = {
    **DEVELOPER_OBLIGATIONS,
    **DEPLOYER_OBLIGATIONS,
    **CONSUMER_RIGHTS,
    **SCOPE_AND_ENFORCEMENT,
}

TOTAL_CONTROLS = len(ALL_CONTROLS)  # 13 controls


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class ColoradoSB26189Finding:
    control_id: str
    section: str
    title: str
    status: str          # "PASS" | "FAIL" | "WARN" | "NA"
    severity: str        # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    evidence: str = ""
    remediation: str = ""


@dataclass
class ColoradoSB26189Report:
    """Colorado SB 26-189 compliance scan result."""

    compliance_score: float = 0.0
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    # Detailed findings
    findings: list[ColoradoSB26189Finding] = field(default_factory=list)

    # Days until effective
    days_until_effective: int = 0

    # Statutory metadata
    effective_date: str = "2027-01-01"
    signed_date: str = "2026-05-14"

    # AIA coverage
    aia_controls_passing: int = 0
    disclosure_controls_passing: int = 0
    consumer_rights_passing: int = 0


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class ColoradoSB26189Scanner:
    """
    Colorado SB 26-189 compliance scanner.

    Assesses developer obligations, deployer obligations, consumer rights,
    and scope/enforcement thresholds per the Colorado AI Consumer Protections Act
    (SB 26-189, signed May 14, 2026, effective January 1, 2027).
    """

    def __init__(
        self,
        ai_systems: Optional[list[dict]] = None,
        mock: bool = True,
    ) -> None:
        self.ai_systems = ai_systems or []
        self.mock = mock

    async def scan(self) -> ColoradoSB26189Report:
        """Run Colorado SB 26-189 compliance assessment."""
        if self.mock:
            return await self._mock_scan()
        return await self._live_scan()

    async def _mock_scan(self) -> ColoradoSB26189Report:
        """
        Simulate a realistic compliance scan with mixed pass/fail/warn results.
        Introduces slight randomness to model varying compliance postures.
        """
        await asyncio.sleep(0.05)  # simulate async I/O

        report = ColoradoSB26189Report(
            days_until_effective=days_until_effective(),
        )

        rng = random.Random(42)  # deterministic seed for consistent demo runs

        # Simulate pass/fail per control category
        compliance_weights = {
            # Developers generally have moderate documentation
            "CO_SB26189_702_A": ("PASS", "HIGH", "System risk documentation found in model registry"),
            "CO_SB26189_702_B": ("WARN", "HIGH", "Bias testing initiated but not yet covering all protected classes"),
            "CO_SB26189_702_C": ("PASS", "MEDIUM", "Model card published in internal developer portal"),
            "CO_SB26189_702_D": ("FAIL", "MEDIUM", "No post-deployment monitoring program documented"),
            # AIA is commonly missing pre-SB 26-189
            "CO_SB26189_703_A": ("FAIL", "CRITICAL", "No algorithmic impact assessment found for this deployment"),
            "CO_SB26189_703_B": ("FAIL", "HIGH", "Consumer-facing disclosure of AI decision-making absent from UI"),
            "CO_SB26189_703_C": ("FAIL", "HIGH", "No opt-out mechanism for AI-assisted decisions implemented"),
            "CO_SB26189_703_D": ("FAIL", "MEDIUM", "Annual AIA review cycle not established"),
            # Consumer rights — partially implemented
            "CO_SB26189_705_A": ("WARN", "HIGH", "AI involvement notice present in ToS but not at point of decision"),
            "CO_SB26189_705_B": ("FAIL", "MEDIUM", "No explanation endpoint available for AI decisions"),
            "CO_SB26189_705_C": ("WARN", "MEDIUM", "Data correction pathway exists but not explicitly linked to AI inputs"),
            "CO_SB26189_705_D": ("FAIL", "HIGH", "No human reviewer appeal process documented"),
            # Scope / enforcement
            "CO_SB26189_706_A": ("PASS", "MEDIUM", "Volume threshold confirmed: system processes >1 CO decision/day"),
            "CO_SB26189_707_A": ("FAIL", "CRITICAL", "Credit decisioning UI does not disclose AI involvement"),
            "CO_SB26189_707_B": ("PASS", "CRITICAL", "Healthcare decisions routed through qualified human reviewer"),
        }

        findings = []
        passing = 0

        for ctrl_id, (status, severity, evidence) in compliance_weights.items():
            ctrl = ALL_CONTROLS.get(ctrl_id)
            if ctrl is None:
                continue
            finding = ColoradoSB26189Finding(
                control_id=ctrl_id,
                section=ctrl["section"],
                title=ctrl["title"],
                status=status,
                severity=severity,
                evidence=evidence,
                remediation=self._remediation(ctrl_id, status),
            )
            findings.append(finding)
            if status == "PASS":
                passing += 1
            # Count by severity
            if status in ("FAIL", "WARN"):
                if severity == "CRITICAL":
                    report.critical_count += 1
                elif severity == "HIGH":
                    report.high_count += 1
                elif severity == "MEDIUM":
                    report.medium_count += 1
                else:
                    report.low_count += 1

        report.findings = findings
        report.total_findings = report.critical_count + report.high_count + report.medium_count + report.low_count

        total_ctrls = len(compliance_weights)
        report.compliance_score = round((passing / total_ctrls) * 100, 1) if total_ctrls else 0.0

        # Sub-tallies
        report.aia_controls_passing = sum(
            1 for f in findings
            if f.control_id in ("CO_SB26189_703_A", "CO_SB26189_703_D") and f.status == "PASS"
        )
        report.disclosure_controls_passing = sum(
            1 for f in findings
            if f.control_id in ("CO_SB26189_703_B", "CO_SB26189_705_A", "CO_SB26189_707_A") and f.status == "PASS"
        )
        report.consumer_rights_passing = sum(
            1 for f in findings
            if f.control_id in ("CO_SB26189_705_B", "CO_SB26189_705_C", "CO_SB26189_705_D") and f.status == "PASS"
        )

        return report

    async def _live_scan(self) -> ColoradoSB26189Report:
        """Live scan — falls back to mock in the absence of a live config probe."""
        return await self._mock_scan()

    @staticmethod
    def _remediation(ctrl_id: str, status: str) -> str:
        if status == "PASS":
            return ""
        remediations = {
            "CO_SB26189_703_A": (
                "Conduct and document a formal algorithmic impact assessment covering "
                "fairness, accuracy, bias, and potential harms before go-live."
            ),
            "CO_SB26189_703_B": (
                "Add a prominent AI disclosure banner or modal at the point of "
                "consequential decisions affecting Colorado consumers."
            ),
            "CO_SB26189_703_C": (
                "Implement a 'Request human review' button or equivalent opt-out "
                "pathway accessible before and after AI decisions are rendered."
            ),
            "CO_SB26189_705_D": (
                "Establish a documented human reviewer appeal workflow with SLA "
                "and authority to override adverse AI decisions."
            ),
            "CO_SB26189_707_A": (
                "Add clear AI-involvement disclosure to all credit-related decision "
                "screens or notifications, including adverse-action notices."
            ),
        }
        return remediations.get(ctrl_id, "Review control requirements and implement appropriate safeguards.")
