"""
Texas TRAIGA — Texas Responsible AI Governance Act
====================================================
Effective: January 1, 2026.
Enforcement agency: Texas Attorney General.
Penalties: $10,000–$200,000 per violation (§ 25.15).

Key design principles:
  - Intent-based scope: applies based on the *intended* use of the AI system,
    not merely its current deployment context.
  - Covers both public and private deployers.
  - Separate tracks for general AI governance and government-specific AI use.

Statutory coverage:
  § 25.01 — Definitions (AI system, developer, deployer, consequential decision,
              prohibited use, sensitive area)
  § 25.02 — Prohibited AI uses (manipulation, deception, social scoring,
              real-time biometric in public spaces without warrant)
  § 25.03 — Mandatory disclosure duties for AI interactions
  § 25.04 — Developer obligations (transparency documentation, testing)
  § 25.05 — Deployer obligations (impact assessment, consumer notice)
  § 25.06 — Government AI use requirements and restrictions
  § 25.07 — Data minimization and retention limits for AI training
  § 25.08 — Cross-border AI data transfer restrictions
  § 25.09 — Algorithmic accountability for automated credit/lending decisions
  § 25.10 — Healthcare AI oversight requirements
  § 25.11 — Employment AI disclosure and human review right
  § 25.12 — High-risk AI system registration with Texas AG
  § 25.13 — Consumer complaint and remediation process
  § 25.14 — Whistleblower protection for AI misuse disclosures
  § 25.15 — Civil penalties ($10K–$200K per violation); intent factor
"""

from __future__ import annotations

import asyncio
import random
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
        "section": "§ 25.02(a)(1)",
        "title": "Prohibition on subliminal manipulation AI",
        "description": (
            "AI systems must not employ subliminal, subconscious, or deceptive "
            "techniques to manipulate individuals' behavior or decisions without "
            "their awareness or meaningful consent."
        ),
        "severity": "CRITICAL",
    },
    "TX_TRAIGA_2501_B": {
        "section": "§ 25.02(a)(2)",
        "title": "Prohibition on social scoring AI",
        "description": (
            "AI systems must not assign or apply social credit or trustworthiness "
            "scores to individuals that restrict their access to goods, services, "
            "or opportunities in unrelated domains."
        ),
        "severity": "CRITICAL",
    },
    "TX_TRAIGA_2501_C": {
        "section": "§ 25.02(a)(3)",
        "title": "Prohibition on real-time biometric identification without warrant",
        "description": (
            "Real-time remote biometric identification of individuals in publicly "
            "accessible spaces by law enforcement is prohibited without a valid "
            "court order or exigent circumstances exception."
        ),
        "severity": "CRITICAL",
    },
    "TX_TRAIGA_2501_D": {
        "section": "§ 25.02(a)(4)",
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
        "section": "§ 25.03(a)",
        "title": "Disclosure of AI interaction — chatbots and conversational AI",
        "description": (
            "Entities deploying AI systems for direct consumer interaction must "
            "disclose that the consumer is interacting with an AI system at the "
            "start of the interaction and upon request."
        ),
        "severity": "HIGH",
    },
    "TX_TRAIGA_2503_B": {
        "section": "§ 25.03(b)",
        "title": "Disclosure in AI-generated written content",
        "description": (
            "Substantial written communications produced by AI systems must be "
            "labeled or disclosed as AI-generated when presented as factual or "
            "authoritative to consumers."
        ),
        "severity": "MEDIUM",
    },
    "TX_TRAIGA_2503_C": {
        "section": "§ 25.03(c)",
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
        "section": "§ 25.04(a)",
        "title": "Intended-use documentation and scope declaration",
        "description": (
            "Developers must document the intended use, intended user population, "
            "and foreseeable high-risk uses of AI systems. Scope is defined by "
            "intended use — not current deployment — (intent-based scope rule)."
        ),
        "severity": "HIGH",
    },
    "TX_TRAIGA_2504_B": {
        "section": "§ 25.04(b)",
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
        "section": "§ 25.06(a)",
        "title": "Government AI use inventory and public disclosure",
        "description": (
            "State agencies using AI systems for government decision-making must "
            "maintain a public inventory of deployed AI systems, their purposes, "
            "and associated risk assessments."
        ),
        "severity": "HIGH",
    },
    "TX_TRAIGA_2506_B": {
        "section": "§ 25.06(b)",
        "title": "No AI-only final decisions in government benefits determination",
        "description": (
            "Government agencies may not use AI as the sole determinant of any "
            "benefits, licensing, or enforcement decision without human review "
            "by a qualified official with override authority."
        ),
        "severity": "CRITICAL",
    },
    "TX_TRAIGA_2506_C": {
        "section": "§ 25.06(c)",
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
        "section": "§ 25.09",
        "title": "Algorithmic accountability in credit and lending AI",
        "description": (
            "Deployers using AI in credit or lending decisions must implement "
            "bias testing, maintain model documentation, and provide individualized "
            "explanation of adverse decisions citing AI factors."
        ),
        "severity": "HIGH",
    },
    "TX_TRAIGA_2512_A": {
        "section": "§ 25.12",
        "title": "High-risk AI registration with Texas AG",
        "description": (
            "Entities deploying high-risk AI systems (as defined by consequential "
            "decision volume or sensitive domain) must register with the Texas "
            "Attorney General annually, including a risk summary."
        ),
        "severity": "HIGH",
    },
    "TX_TRAIGA_2515_A": {
        "section": "§ 25.15",
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
    Texas TRAIGA compliance scanner.

    Assesses prohibited AI use prohibitions, mandatory disclosure duties,
    developer obligations, government AI restrictions, and penalty exposure
    per the Texas Responsible AI Governance Act (effective January 1, 2026).

    Note: Scope is intent-based. A system intended for high-risk applications
    is in scope even if not currently deployed in those contexts.
    """

    def __init__(
        self,
        ai_systems: Optional[list[dict]] = None,
        mock: bool = True,
    ) -> None:
        self.ai_systems = ai_systems or []
        self.mock = mock

    async def scan(self) -> TexasTRAIGAReport:
        """Run Texas TRAIGA compliance assessment."""
        if self.mock:
            return await self._mock_scan()
        return await self._live_scan()

    async def _mock_scan(self) -> TexasTRAIGAReport:
        """
        Simulate a realistic compliance assessment reflecting typical enterprise posture.
        Enterprise AI systems generally avoid prohibited uses but lag on disclosures.
        """
        await asyncio.sleep(0.05)

        report = TexasTRAIGAReport(
            currently_in_effect=is_in_effect(),
        )

        # Simulated compliance results
        compliance_map = {
            # Prohibited uses — enterprise systems generally avoid
            "TX_TRAIGA_2501_A": ("PASS", "CRITICAL", "No subliminal manipulation techniques identified in model outputs"),
            "TX_TRAIGA_2501_B": ("PASS", "CRITICAL", "No social scoring features found in deployed system"),
            "TX_TRAIGA_2501_C": ("NA",   "CRITICAL", "System does not use real-time biometric ID in public spaces"),
            "TX_TRAIGA_2501_D": ("WARN", "HIGH",     "AI-generated content pipeline exists; deepfake safeguards unverified"),
            # Disclosure duties — commonly lagging
            "TX_TRAIGA_2503_A": ("FAIL", "HIGH",     "Chat interface does not disclose AI nature at session start"),
            "TX_TRAIGA_2503_B": ("WARN", "MEDIUM",   "AI-generated reports lack consistent labeling"),
            "TX_TRAIGA_2503_C": ("FAIL", "HIGH",     "Adverse decision notices do not reference AI contribution"),
            # Developer obligations
            "TX_TRAIGA_2504_A": ("PASS", "HIGH",     "Intended-use documentation found in system design artifacts"),
            "TX_TRAIGA_2504_B": ("WARN", "HIGH",     "Disparate impact testing performed but not formally documented"),
            # Government AI — N/A for private deployers (unless deploying to gov)
            "TX_TRAIGA_2506_A": ("NA",   "HIGH",     "Private-sector deployer; government inventory rule not applicable"),
            "TX_TRAIGA_2506_B": ("NA",   "CRITICAL", "Private-sector deployer; government benefits rule not applicable"),
            "TX_TRAIGA_2506_C": ("NA",   "CRITICAL", "Private-sector deployer; criminal justice rule not applicable"),
            # Accountability
            "TX_TRAIGA_2509_A": ("FAIL", "HIGH",     "Credit AI model lacks individualized adverse-action explanation"),
            "TX_TRAIGA_2512_A": ("FAIL", "HIGH",     "No TRAIGA registration with Texas AG on record"),
            "TX_TRAIGA_2515_A": ("WARN", "CRITICAL", "2 known TRAIGA disclosure gaps create penalty exposure"),
        }

        penalty_notes = {
            "TX_TRAIGA_2503_A": "$10K–$200K per violation — each undisclosed interaction is a separate violation",
            "TX_TRAIGA_2515_A": "Good-faith compliance program may reduce penalty; document remediation steps",
        }

        findings = []
        passing = 0
        applicable = 0

        for ctrl_id, (status, severity, evidence) in compliance_map.items():
            ctrl = ALL_CONTROLS.get(ctrl_id)
            if ctrl is None:
                continue
            finding = TexasTRAIGAFinding(
                control_id=ctrl_id,
                section=ctrl["section"],
                title=ctrl["title"],
                status=status,
                severity=severity,
                evidence=evidence,
                remediation=self._remediation(ctrl_id, status),
                penalty_exposure=penalty_notes.get(ctrl_id),
            )
            findings.append(finding)
            if status == "NA":
                continue
            applicable += 1
            if status == "PASS":
                passing += 1
            elif status in ("FAIL", "WARN"):
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
        report.compliance_score = round((passing / applicable) * 100, 1) if applicable else 0.0

        # Sub-tallies
        report.prohibited_uses_passing = sum(
            1 for f in findings
            if f.control_id in PROHIBITED_USES and f.status == "PASS"
        )
        report.disclosure_controls_passing = sum(
            1 for f in findings
            if f.control_id in DISCLOSURE_DUTIES and f.status == "PASS"
        )
        report.government_ai_passing = sum(
            1 for f in findings
            if f.control_id in GOVERNMENT_AI and f.status == "PASS"
        )

        return report

    async def _live_scan(self) -> TexasTRAIGAReport:
        """Live scan — falls back to mock absent a real config probe."""
        return await self._mock_scan()

    @staticmethod
    def _remediation(ctrl_id: str, status: str) -> str:
        if status in ("PASS", "NA"):
            return ""
        remediations = {
            "TX_TRAIGA_2503_A": (
                "Add an 'You are speaking with an AI assistant' disclosure at the "
                "beginning of every AI chat session. Must be prominent and unavoidable."
            ),
            "TX_TRAIGA_2503_C": (
                "Amend all adverse-action notification templates to include: "
                "'This decision was made with the assistance of an AI system. "
                "Primary contributing factors: [list].' "
            ),
            "TX_TRAIGA_2509_A": (
                "Implement a per-decision explanation endpoint for the credit AI model "
                "surfacing the top N contributing features in plain language."
            ),
            "TX_TRAIGA_2512_A": (
                "Complete TRAIGA high-risk AI system registration with the Texas AG "
                "at txag.gov/AI-registry (due annually; first filing overdue Jan 2026)."
            ),
            "TX_TRAIGA_2515_A": (
                "Document all known compliance gaps, remediation timelines, and good-faith "
                "efforts. A documented compliance program is a mitigating factor under § 25.15."
            ),
        }
        return remediations.get(
            ctrl_id,
            "Review applicable TRAIGA section and implement required safeguards.",
        )
