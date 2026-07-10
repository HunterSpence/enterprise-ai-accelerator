"""
Colorado SB 26-189 — AI Consumer Protections Act
==================================================
QUARANTINED (P0-23, 2026-07-10): this scanner is disabled.

This module's docstring previously asserted specific statutory section
numbers, a specific relationship/status for the repealed SB 24-205, and
specific numeric applicability thresholds — none of which were verified
against enacted primary legal text and may be fabricated. This module must
not be used, invoked, or represented as a live legal assessment of Colorado
AI-law compliance in any mode (mock or live).

``ColoradoSB26189Scanner.scan()`` always raises ``NotImplementedError``.
Rebuilding this framework requires sourcing every control, threshold, and
citation directly from the enacted Colorado statute (primary source) — not
from this file. The control dictionaries below are kept only as a
placeholder data shape for that future rebuild; each "section" value has
been scrubbed to "UNVERIFIED" because the original citations could not be
confirmed against primary law.
"""

from __future__ import annotations

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
        "section": "UNVERIFIED",
        "title": "Risk documentation before deployment",
        "description": (
            "Developers must document the intended use cases, known limitations, "
            "and risk factors of high-risk AI systems before making them available."
        ),
        "severity": "HIGH",
    },
    "CO_SB26189_702_B": {
        "section": "UNVERIFIED",
        "title": "Pre-deployment bias and fairness testing",
        "description": (
            "Developers must test for discriminatory or disparate impact on protected "
            "classes across race, color, national origin, sex, disability, and age "
            "prior to deployment."
        ),
        "severity": "HIGH",
    },
    "CO_SB26189_702_C": {
        "section": "UNVERIFIED",
        "title": "Model card / technical documentation disclosure",
        "description": (
            "Developers must make available to deployers: training data sources, "
            "evaluation methodology, performance benchmarks, and known failure modes."
        ),
        "severity": "MEDIUM",
    },
    "CO_SB26189_702_D": {
        "section": "UNVERIFIED",
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
        "section": "UNVERIFIED",
        "title": "Pre-deployment algorithmic impact assessment",
        "description": (
            "Deployers must conduct a documented algorithmic impact assessment (AIA) "
            "before using a high-risk AI system for consequential decisions."
        ),
        "severity": "CRITICAL",
    },
    "CO_SB26189_703_B": {
        "section": "UNVERIFIED",
        "title": "Consumer-facing AI disclosure",
        "description": (
            "Deployers must conspicuously disclose that an AI system is being used "
            "to make or substantially assist in a consequential decision affecting "
            "the consumer."
        ),
        "severity": "HIGH",
    },
    "CO_SB26189_703_C": {
        "section": "UNVERIFIED",
        "title": "Opt-out pathway for AI-assisted decisions",
        "description": (
            "Deployers must offer consumers a meaningful opt-out from AI-assisted "
            "decision-making or a human review alternative."
        ),
        "severity": "HIGH",
    },
    "CO_SB26189_703_D": {
        "section": "UNVERIFIED",
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
        "section": "UNVERIFIED",
        "title": "Right to notice of AI decision involvement",
        "description": (
            "Consumers have a right to receive notice within a reasonable timeframe "
            "that an AI system contributed to a consequential decision affecting them."
        ),
        "severity": "HIGH",
    },
    "CO_SB26189_705_B": {
        "section": "UNVERIFIED",
        "title": "Right to plain-language explanation",
        "description": (
            "Consumers may request a plain-language explanation of the AI factors "
            "that contributed to the decision, with response required within 45 days."
        ),
        "severity": "MEDIUM",
    },
    "CO_SB26189_705_C": {
        "section": "UNVERIFIED",
        "title": "Right to correction of erroneous input data",
        "description": (
            "Consumers may request correction of inaccurate personal data used in "
            "an AI decision. Deployers must acknowledge within 30 days."
        ),
        "severity": "MEDIUM",
    },
    "CO_SB26189_705_D": {
        "section": "UNVERIFIED",
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
        "section": "UNVERIFIED",
        "title": "Scope threshold compliance — consequential decision volume",
        "description": (
            "Verify the system falls within scope: ≥1 consequential decision per day "
            "OR ≥1,000 consequential decisions per year involving Colorado residents. "
            "Out-of-scope systems do not require AIA but must still disclose AI use."
        ),
        "severity": "MEDIUM",
    },
    "CO_SB26189_707_A": {
        "section": "UNVERIFIED",
        "title": "Prohibited undisclosed AI in credit, housing, and employment",
        "description": (
            "Prohibited: using AI to make consequential decisions in credit, housing, "
            "or employment contexts without conspicuous disclosure that AI was used."
        ),
        "severity": "CRITICAL",
    },
    "CO_SB26189_707_B": {
        "section": "UNVERIFIED",
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
    QUARANTINED (P0-23) — see module docstring.

    This scanner previously misstated the repealed SB 24-205's status,
    invented applicability thresholds and private-right-of-action claims,
    and returned those fabricated results as if they were a real assessment
    in both mock and "live" mode. It is disabled pending a rebuild sourced
    from the enacted Colorado statute. ``scan()`` always raises.
    """

    def __init__(
        self,
        ai_systems: Optional[list[dict]] = None,
        mock: bool = True,
    ) -> None:
        self.ai_systems = ai_systems or []
        self.mock = mock

    async def scan(self) -> ColoradoSB26189Report:
        """Always raises — see class docstring and P0-23."""
        raise NotImplementedError(
            "ColoradoSB26189Scanner is quarantined pending rebuild from enacted "
            "primary legal text (P0-23) — not usable for any real or demo "
            "compliance assessment. See policy_guard/frameworks/colorado_sb26189.py "
            "module docstring."
        )
