"""
Texas TRAIGA — Texas Responsible AI Governance Act
====================================================
QUARANTINED (P0-23, 2026-07-10): this scanner is disabled.

The statutory section numbers, the "high-risk AI registry" concept, and a
fabricated remediation URL for the Texas Attorney General's office that used
to live in this module were NOT verified against enacted primary legal text
and may be fabricated. That URL has been removed outright. This module must
not be used, invoked, or represented as a live legal assessment of Texas
TRAIGA compliance in any mode (mock or live).

``TexasTRAIGAScanner.scan()`` always raises ``NotImplementedError``. Rebuilding
this framework requires sourcing every control directly from the enacted
Texas statute (primary source) — not from this file. The control dictionaries
below are kept only as a placeholder data shape for that future rebuild; each
"section" value has been scrubbed to "UNVERIFIED" because the original
citations could not be confirmed against primary law.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Key dates
# ---------------------------------------------------------------------------

EFFECTIVE_DATE = date(2026, 1, 1)
PENALTY_MIN = 10_000       # USD per violation
PENALTY_MAX = 200_000      # USD per violation


def is_in_effect() -> bool:
    """Return True if TRAIGA is currently in effect."""
    return date.today() >= EFFECTIVE_DATE


# ---------------------------------------------------------------------------
# Control definitions (15 controls across key sections)
# ---------------------------------------------------------------------------

PROHIBITED_USES: dict[str, dict] = {
    "TX_TRAIGA_2501_A": {
        "section": "UNVERIFIED",
        "title": "Prohibition on subliminal manipulation AI",
        "description": (
            "AI systems must not employ subliminal, subconscious, or deceptive "
            "techniques to manipulate individuals' behavior or decisions without "
            "their awareness or meaningful consent."
        ),
        "severity": "CRITICAL",
    },
    "TX_TRAIGA_2501_B": {
        "section": "UNVERIFIED",
        "title": "Prohibition on social scoring AI",
        "description": (
            "AI systems must not assign or apply social credit or trustworthiness "
            "scores to individuals that restrict their access to goods, services, "
            "or opportunities in unrelated domains."
        ),
        "severity": "CRITICAL",
    },
    "TX_TRAIGA_2501_C": {
        "section": "UNVERIFIED",
        "title": "Prohibition on real-time biometric identification without warrant",
        "description": (
            "Real-time remote biometric identification of individuals in publicly "
            "accessible spaces by law enforcement is prohibited without a valid "
            "court order or exigent circumstances exception."
        ),
        "severity": "CRITICAL",
    },
    "TX_TRAIGA_2501_D": {
        "section": "UNVERIFIED",
        "title": "Prohibition on AI-generated deceptive identity impersonation",
        "description": (
            "AI must not be deployed to generate realistic impersonations of real "
            "individuals without consent in contexts designed to deceive recipients "
            "into believing the impersonation is authentic."
        ),
        "severity": "HIGH",
    },
}

DISCLOSURE_DUTIES: dict[str, dict] = {
    "TX_TRAIGA_2503_A": {
        "section": "UNVERIFIED",
        "title": "Disclosure of AI interaction — chatbots and conversational AI",
        "description": (
            "Entities deploying AI systems for direct consumer interaction must "
            "disclose that the consumer is interacting with an AI system at the "
            "start of the interaction and upon request."
        ),
        "severity": "HIGH",
    },
    "TX_TRAIGA_2503_B": {
        "section": "UNVERIFIED",
        "title": "Disclosure in AI-generated written content",
        "description": (
            "Substantial written communications produced by AI systems must be "
            "labeled or disclosed as AI-generated when presented as factual or "
            "authoritative to consumers."
        ),
        "severity": "MEDIUM",
    },
    "TX_TRAIGA_2503_C": {
        "section": "UNVERIFIED",
        "title": "Adverse action notice — AI role disclosure",
        "description": (
            "Where an AI system contributed to an adverse decision (credit denial, "
            "job rejection, benefit denial), the notice must disclose the AI role "
            "and provide explanation of primary decision factors."
        ),
        "severity": "HIGH",
    },
}

DEVELOPER_OBLIGATIONS: dict[str, dict] = {
    "TX_TRAIGA_2504_A": {
        "section": "UNVERIFIED",
        "title": "Intended-use documentation and scope declaration",
        "description": (
            "Developers must document the intended use, intended user population, "
            "and foreseeable high-risk uses of AI systems. Scope is defined by "
            "intended use — not current deployment — (intent-based scope rule)."
        ),
        "severity": "HIGH",
    },
    "TX_TRAIGA_2504_B": {
        "section": "UNVERIFIED",
        "title": "Performance and disparate-impact testing",
        "description": (
            "Developers must test for differential performance across protected "
            "characteristics before and after deployment, documenting results and "
            "any mitigation actions taken."
        ),
        "severity": "HIGH",
    },
}

GOVERNMENT_AI: dict[str, dict] = {
    "TX_TRAIGA_2506_A": {
        "section": "UNVERIFIED",
        "title": "Government AI use inventory and public disclosure",
        "description": (
            "State agencies using AI systems for government decision-making must "
            "maintain a public inventory of deployed AI systems, their purposes, "
            "and associated risk assessments."
        ),
        "severity": "HIGH",
    },
    "TX_TRAIGA_2506_B": {
        "section": "UNVERIFIED",
        "title": "No AI-only final decisions in government benefits determination",
        "description": (
            "Government agencies may not use AI as the sole determinant of any "
            "benefits, licensing, or enforcement decision without human review "
            "by a qualified official with override authority."
        ),
        "severity": "CRITICAL",
    },
    "TX_TRAIGA_2506_C": {
        "section": "UNVERIFIED",
        "title": "Human-in-the-loop for government criminal justice AI",
        "description": (
            "AI systems used in pretrial risk assessment, sentencing recommendations, "
            "or parole decisions must be accompanied by human review and may not "
            "constitute the sole basis for incarceration decisions."
        ),
        "severity": "CRITICAL",
    },
}

ACCOUNTABILITY_AND_ENFORCEMENT: dict[str, dict] = {
    "TX_TRAIGA_2509_A": {
        "section": "UNVERIFIED",
        "title": "Algorithmic accountability in credit and lending AI",
        "description": (
            "Deployers using AI in credit or lending decisions must implement "
            "bias testing, maintain model documentation, and provide individualized "
            "explanation of adverse decisions citing AI factors."
        ),
        "severity": "HIGH",
    },
    "TX_TRAIGA_2512_A": {
        "section": "UNVERIFIED",
        "title": "High-risk AI registration with Texas AG",
        "description": (
            "Entities deploying high-risk AI systems (as defined by consequential "
            "decision volume or sensitive domain) must register with the Texas "
            "Attorney General annually, including a risk summary."
        ),
        "severity": "HIGH",
    },
    "TX_TRAIGA_2515_A": {
        "section": "UNVERIFIED",
        "title": "Civil penalty exposure tracking ($10K–$200K per violation)",
        "description": (
            "Track all known violations and remediation status. TRAIGA imposes "
            "$10,000–$200,000 per violation; penalties scale with intent and harm. "
            "A compliance program demonstrating good-faith effort may mitigate."
        ),
        "severity": "CRITICAL",
    },
}

ALL_CONTROLS = {
    **PROHIBITED_USES,
    **DISCLOSURE_DUTIES,
    **DEVELOPER_OBLIGATIONS,
    **GOVERNMENT_AI,
    **ACCOUNTABILITY_AND_ENFORCEMENT,
}

TOTAL_CONTROLS = len(ALL_CONTROLS)  # 15 controls


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class TexasTRAIGAFinding:
    control_id: str
    section: str
    title: str
    status: str         # "PASS" | "FAIL" | "WARN" | "NA"
    severity: str       # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    evidence: str = ""
    remediation: str = ""
    penalty_exposure: Optional[str] = None


@dataclass
class TexasTRAIGAReport:
    """Texas TRAIGA compliance scan result."""

    compliance_score: float = 0.0
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    findings: list[TexasTRAIGAFinding] = field(default_factory=list)

    # Metadata
    effective_date: str = "2026-01-01"
    currently_in_effect: bool = True
    penalty_range: str = "$10,000–$200,000 per violation"

    # Category tallies
    prohibited_uses_passing: int = 0
    disclosure_controls_passing: int = 0
    government_ai_passing: int = 0


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class TexasTRAIGAScanner:
    """
    QUARANTINED (P0-23) — see module docstring.

    This scanner previously fabricated statutory section citations, a
    "high-risk AI registry" concept, and a fabricated Texas AG registration
    remediation URL, and returned those fabricated results as if they were a
    real assessment in both mock and "live" mode. It is disabled pending a
    rebuild sourced from the enacted Texas statute. ``scan()`` always raises.
    """

    def __init__(
        self,
        ai_systems: Optional[list[dict]] = None,
        mock: bool = True,
    ) -> None:
        self.ai_systems = ai_systems or []
        self.mock = mock

    async def scan(self) -> TexasTRAIGAReport:
        """Always raises — see class docstring and P0-23."""
        raise NotImplementedError(
            "TexasTRAIGAScanner is quarantined pending rebuild from enacted "
            "primary legal text (P0-23) — not usable for any real or demo "
            "compliance assessment. See policy_guard/frameworks/texas_traiga.py "
            "module docstring."
        )
