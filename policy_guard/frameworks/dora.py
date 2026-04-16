"""
Digital Operational Resilience Act (DORA) — PolicyGuard Implementation
=======================================================================
Source: Regulation (EU) 2022/2554 — DORA
        Entered into application: 17 January 2025

Chapters covered:
  - Chapter II:  ICT risk management (Articles 5-14)
  - Chapter III: ICT-related incident management (Articles 15-23)
  - Chapter IV:  Digital operational resilience testing (Articles 24-27)
  - Chapter V:   Third-party risk management (Articles 28-44)
  - Chapter VI:  Information sharing (Articles 45-49)
  - Chapter VII: Competent authorities oversight (Articles 50-56)

Scope: Financial entities operating in the EU — banks, investment firms,
       payment institutions, insurance undertakings, and their critical ICT third-party providers.

Control count: 57 controls
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Chapter II: ICT Risk Management (Articles 5-14)
# ---------------------------------------------------------------------------

ICT_RISK_MANAGEMENT: dict[str, dict] = {
    "DORA-5.1": {
        "article": "Article 5(1)",
        "title": "ICT risk management framework — board responsibility",
        "description": "Management body bears responsibility for ICT risk management and adopts and reviews the ICT risk management framework.",
        "evidence_needed": ["Board-approved ICT risk management framework", "Board meeting minutes showing ICT risk review", "Management accountability attestation"],
        "weight": "critical",
        "nist_800_53": "RA-1",
        "iso_27001": "5.1",
    },
    "DORA-5.2": {
        "article": "Article 5(2)",
        "title": "ICT risk management — management responsibility",
        "description": "Management body defines, approves, oversees, and is responsible for ICT risk strategy.",
        "evidence_needed": ["ICT risk strategy document", "Executive risk committee charter", "Approval records"],
        "weight": "critical",
        "nist_800_53": "PM-1",
        "iso_27001": "5.3",
    },
    "DORA-6.1": {
        "article": "Article 6(1)",
        "title": "ICT risk management framework — elements",
        "description": "Maintain a robust and documented ICT risk management framework as part of the overall risk management system.",
        "evidence_needed": ["ICT risk management framework document", "Integration with enterprise risk framework", "Annual review records"],
        "weight": "critical",
        "nist_800_53": "RA-3",
        "iso_27001": "6.1",
    },
    "DORA-6.4": {
        "article": "Article 6(4)",
        "title": "ICT risk management strategy",
        "description": "Define a comprehensive ICT risk management strategy specifying risk tolerance and mitigation approaches.",
        "evidence_needed": ["ICT risk strategy with risk appetite statement", "Risk tolerance thresholds", "Annual strategy review"],
        "weight": "high",
        "nist_800_53": "RA-2",
        "iso_27001": "6.1.2",
    },
    "DORA-7.1": {
        "article": "Article 7",
        "title": "ICT systems, protocols and tools",
        "description": "Use and maintain updated ICT systems, protocols, and tools appropriate to ICT risk management.",
        "evidence_needed": ["ICT asset inventory", "Asset management procedure", "Software lifecycle records"],
        "weight": "high",
        "nist_800_53": "CM-8",
        "iso_27001": "8.1",
    },
    "DORA-8.1": {
        "article": "Article 8(1)",
        "title": "Identification of ICT risk sources",
        "description": "Identify and classify ICT assets, information assets, and supporting infrastructure.",
        "evidence_needed": ["ICT asset classification register", "Information asset inventory", "Dependency mapping"],
        "weight": "high",
        "nist_800_53": "RA-3",
        "iso_27001": "8.1",
    },
    "DORA-8.2": {
        "article": "Article 8(2)",
        "title": "Identification of business functions supported by ICT",
        "description": "Identify critical functions and processes and their ICT dependencies.",
        "evidence_needed": ["Business function to ICT dependency map", "Critical function register", "BIA (Business Impact Analysis)"],
        "weight": "high",
        "nist_800_53": "CP-2",
        "iso_27001": "8.2",
    },
    "DORA-9.1": {
        "article": "Article 9(1)",
        "title": "Protection of ICT systems — security controls",
        "description": "Implement security controls to continuously protect ICT systems and information.",
        "evidence_needed": ["Security control catalogue", "Control implementation evidence", "Security baseline documentation"],
        "weight": "critical",
        "nist_800_53": "AC-1",
        "iso_27001": "A.8",
    },
    "DORA-9.2": {
        "article": "Article 9(2)",
        "title": "ICT change management",
        "description": "Manage ICT changes through a controlled change management process.",
        "evidence_needed": ["Change management policy", "Change request records", "Change advisory board minutes"],
        "weight": "high",
        "nist_800_53": "CM-3",
        "iso_27001": "A.8.32",
    },
    "DORA-9.3": {
        "article": "Article 9(3)",
        "title": "Network security and segmentation",
        "description": "Implement network security measures including segmentation, access controls, and monitoring.",
        "evidence_needed": ["Network segmentation diagram", "Firewall rule review", "Network access control policy"],
        "weight": "high",
        "nist_800_53": "SC-7",
        "iso_27001": "A.8.20",
    },
    "DORA-10.1": {
        "article": "Article 10(1)",
        "title": "Continuous detection of anomalous activities",
        "description": "Implement mechanisms to promptly detect anomalous activities and ICT-related incidents.",
        "evidence_needed": ["SIEM or anomaly detection deployment", "Alert thresholds documentation", "Detection coverage report"],
        "weight": "critical",
        "nist_800_53": "SI-4",
        "iso_27001": "A.8.16",
    },
    "DORA-10.2": {
        "article": "Article 10(2)",
        "title": "Logging and monitoring",
        "description": "Enable comprehensive logging and monitoring of ICT systems to support incident detection.",
        "evidence_needed": ["Log management policy", "Log retention configuration", "Monitoring coverage documentation"],
        "weight": "high",
        "nist_800_53": "AU-2",
        "iso_27001": "A.8.15",
    },
    "DORA-11.1": {
        "article": "Article 11(1)",
        "title": "Business continuity and ICT recovery",
        "description": "Establish and maintain a comprehensive ICT business continuity policy.",
        "evidence_needed": ["ICT business continuity plan", "BCP test records", "Recovery objectives (RTO/RPO)"],
        "weight": "critical",
        "nist_800_53": "CP-1",
        "iso_27001": "A.5.30",
    },
    "DORA-11.3": {
        "article": "Article 11(3)",
        "title": "Backup and data restoration",
        "description": "Implement backup procedures and verify data restoration capability.",
        "evidence_needed": ["Backup policy", "Backup test results", "Data restoration drill records"],
        "weight": "critical",
        "nist_800_53": "CP-9",
        "iso_27001": "A.8.13",
    },
    "DORA-12.1": {
        "article": "Article 12(1)",
        "title": "Recovery and restoration plans",
        "description": "Establish, document, and test ICT recovery and restoration plans.",
        "evidence_needed": ["Disaster recovery plan", "DR test results", "Recovery procedure runbooks"],
        "weight": "critical",
        "nist_800_53": "CP-10",
        "iso_27001": "A.5.30",
    },
    "DORA-13.1": {
        "article": "Article 13(1)",
        "title": "Learning and evolving from ICT incidents",
        "description": "Establish a process to learn from ICT incidents and integrate lessons into security controls.",
        "evidence_needed": ["Post-incident review process", "Lessons learned register", "Control improvement records"],
        "weight": "medium",
        "nist_800_53": "IR-4",
        "iso_27001": "A.5.26",
    },
    "DORA-14.1": {
        "article": "Article 14",
        "title": "Communication plans for ICT risk",
        "description": "Implement crisis communication plans covering internal and external ICT risk communication.",
        "evidence_needed": ["ICT crisis communication plan", "Stakeholder communication templates", "Communication drill records"],
        "weight": "medium",
        "nist_800_53": "CP-2",
        "iso_27001": "A.5.29",
    },
}

# ---------------------------------------------------------------------------
# Chapter III: ICT-Related Incident Management (Articles 15-23)
# ---------------------------------------------------------------------------

INCIDENT_MANAGEMENT: dict[str, dict] = {
    "DORA-15.1": {
        "article": "Article 15(1)",
        "title": "ICT incident management process",
        "description": "Establish, document, and test an ICT-related incident management process.",
        "evidence_needed": ["ICT incident management procedure", "Incident classification criteria", "Escalation matrix"],
        "weight": "critical",
        "nist_800_53": "IR-1",
        "iso_27001": "A.5.24",
    },
    "DORA-16.1": {
        "article": "Article 16(1)",
        "title": "Classification of ICT-related incidents",
        "description": "Classify ICT-related incidents according to criteria set by EBA/ESMA/EIOPA RTS.",
        "evidence_needed": ["Incident classification matrix", "Materiality threshold documentation", "Classification examples"],
        "weight": "high",
        "nist_800_53": "IR-5",
        "iso_27001": "A.5.25",
    },
    "DORA-17.1": {
        "article": "Article 17(1)",
        "title": "Major incident reporting to competent authorities",
        "description": "Report major ICT-related incidents to the competent authority within prescribed timeframes.",
        "evidence_needed": ["Reporting procedure to competent authority", "Initial notification template (4h)", "Intermediate report template (72h)"],
        "weight": "critical",
        "nist_800_53": "IR-6",
        "iso_27001": "A.5.26",
    },
    "DORA-17.3": {
        "article": "Article 17(3)",
        "title": "Final incident report submission",
        "description": "Submit a final root cause analysis report within one month of major incident notification.",
        "evidence_needed": ["Final incident report template", "Root cause analysis methodology", "Reporting timeline tracker"],
        "weight": "high",
        "nist_800_53": "IR-6",
        "iso_27001": "A.5.26",
    },
    "DORA-19.1": {
        "article": "Article 19",
        "title": "Harmonised reporting for payment-related operational incidents",
        "description": "Apply harmonized reporting requirements for payment-related incidents as applicable.",
        "evidence_needed": ["Payment incident classification", "Reporting threshold documentation"],
        "weight": "medium",
        "nist_800_53": "IR-6",
        "iso_27001": "A.5.26",
    },
    "DORA-20.1": {
        "article": "Article 20",
        "title": "Voluntary notification of significant cyber threats",
        "description": "Voluntarily notify competent authorities of significant cyber threats prior to materialization.",
        "evidence_needed": ["Threat notification procedure", "Threat intelligence monitoring capability"],
        "weight": "medium",
        "nist_800_53": "RA-3",
        "iso_27001": "A.6.8",
    },
}

# ---------------------------------------------------------------------------
# Chapter IV: Digital Operational Resilience Testing (Articles 24-27)
# ---------------------------------------------------------------------------

RESILIENCE_TESTING: dict[str, dict] = {
    "DORA-24.1": {
        "article": "Article 24(1)",
        "title": "General resilience testing programme",
        "description": "Establish and maintain a digital operational resilience testing programme.",
        "evidence_needed": ["Annual resilience testing programme", "Test scope documentation", "Test completion records"],
        "weight": "high",
        "nist_800_53": "CA-8",
        "iso_27001": "A.5.36",
    },
    "DORA-25.1": {
        "article": "Article 25(1)",
        "title": "Testing of ICT tools and systems",
        "description": "Test ICT tools and systems using vulnerability assessments and penetration testing at least annually.",
        "evidence_needed": ["Penetration testing results", "Vulnerability scan reports", "Remediation tracking"],
        "weight": "high",
        "nist_800_53": "CA-8",
        "iso_27001": "A.8.8",
    },
    "DORA-26.1": {
        "article": "Article 26(1)",
        "title": "Advanced Threat-Led Penetration Testing (TLPT)",
        "description": "Perform TLPT at least every three years (applies to significant financial entities).",
        "evidence_needed": ["TLPT completion certificate", "TLPT scope and methodology", "Remediation plan for TLPT findings"],
        "weight": "high",
        "nist_800_53": "CA-8(1)",
        "iso_27001": "A.5.36",
    },
    "DORA-26.3": {
        "article": "Article 26(3)",
        "title": "TLPT with critical ICT third-party providers",
        "description": "Include critical ICT third-party providers in TLPT scope where applicable.",
        "evidence_needed": ["Third-party TLPT participation agreement", "Joint TLPT scope document"],
        "weight": "medium",
        "nist_800_53": "CA-8",
        "iso_27001": "A.5.22",
    },
}

# ---------------------------------------------------------------------------
# Chapter V: Third-Party Risk Management (Articles 28-44)
# ---------------------------------------------------------------------------

THIRD_PARTY_RISK: dict[str, dict] = {
    "DORA-28.1": {
        "article": "Article 28(1)",
        "title": "Third-party ICT risk management principles",
        "description": "Adopt and regularly review a strategy for ICT third-party risk, including a register of all ICT third-party providers.",
        "evidence_needed": ["Third-party ICT risk strategy", "ICT third-party register", "Annual review records"],
        "weight": "critical",
        "nist_800_53": "SA-9",
        "iso_27001": "A.5.21",
    },
    "DORA-28.2": {
        "article": "Article 28(2)",
        "title": "Pre-contractual due diligence for ICT third-parties",
        "description": "Perform due diligence before entering into ICT third-party service arrangements.",
        "evidence_needed": ["Due diligence questionnaire", "Third-party risk assessment records", "Security assessment results"],
        "weight": "high",
        "nist_800_53": "SA-9",
        "iso_27001": "A.5.20",
    },
    "DORA-28.3": {
        "article": "Article 28(3)",
        "title": "ICT third-party register of information",
        "description": "Maintain a register of all contractual arrangements with ICT third-party service providers.",
        "evidence_needed": ["Contractual arrangements register", "Critical provider identification", "Annual register review"],
        "weight": "high",
        "nist_800_53": "SA-9",
        "iso_27001": "A.5.21",
    },
    "DORA-29.1": {
        "article": "Article 29(1)",
        "title": "Preliminary assessment for critical functions",
        "description": "Assess ICT concentration risk before outsourcing critical or important functions.",
        "evidence_needed": ["Concentration risk assessment", "Critical function designation", "Exit strategy documentation"],
        "weight": "high",
        "nist_800_53": "SA-9",
        "iso_27001": "A.5.22",
    },
    "DORA-30.1": {
        "article": "Article 30(1)",
        "title": "Key contractual provisions for ICT third parties",
        "description": "Ensure ICT third-party contracts include mandatory elements: service description, security standards, audit rights, incident reporting, exit clauses.",
        "evidence_needed": ["Model ICT contract clauses", "Contract review checklist", "Sample compliant contract"],
        "weight": "critical",
        "nist_800_53": "SA-9",
        "iso_27001": "A.5.20",
    },
    "DORA-30.3": {
        "article": "Article 30(3)",
        "title": "Subcontracting and data location requirements",
        "description": "Address subcontracting arrangements and data location requirements in ICT contracts.",
        "evidence_needed": ["Subcontracting disclosure requirements", "Data location clauses", "Sub-processor register"],
        "weight": "medium",
        "nist_800_53": "SA-9",
        "iso_27001": "A.5.20",
    },
    "DORA-31.1": {
        "article": "Article 31(1)",
        "title": "Critical ICT third-party designation",
        "description": "Comply with requirements for critical ICT third-party providers as designated by ESAs.",
        "evidence_needed": ["Critical provider designation assessment", "Oversight compliance documentation"],
        "weight": "medium",
        "nist_800_53": "SA-9",
        "iso_27001": "A.5.22",
    },
}

# ---------------------------------------------------------------------------
# Chapter VI: Information Sharing (Articles 45-49)
# ---------------------------------------------------------------------------

INFORMATION_SHARING: dict[str, dict] = {
    "DORA-45.1": {
        "article": "Article 45(1)",
        "title": "Information sharing arrangements",
        "description": "Financial entities may exchange cyber threat information through trusted information sharing arrangements.",
        "evidence_needed": ["Information sharing policy", "Trusted community participation records"],
        "weight": "low",
        "nist_800_53": "PM-15",
        "iso_27001": "A.6.8",
    },
    "DORA-45.2": {
        "article": "Article 45(2)",
        "title": "Confidentiality of shared information",
        "description": "Maintain confidentiality and protect sensitive information shared under information sharing arrangements.",
        "evidence_needed": ["Information handling agreement", "Classification procedure for shared data"],
        "weight": "medium",
        "nist_800_53": "PM-15",
        "iso_27001": "A.5.12",
    },
}

# ---------------------------------------------------------------------------
# Chapter VII: Oversight Framework (Articles 50-56)
# ---------------------------------------------------------------------------

OVERSIGHT: dict[str, dict] = {
    "DORA-50.1": {
        "article": "Article 50",
        "title": "Cooperation with ESA oversight",
        "description": "Cooperate with ESA Lead Overseer for critical ICT third-party providers.",
        "evidence_needed": ["Oversight cooperation procedure", "Lead Overseer contact records"],
        "weight": "medium",
        "nist_800_53": "PL-1",
        "iso_27001": "A.5.31",
    },
    "DORA-54.1": {
        "article": "Article 54(1)",
        "title": "Compliance with oversight recommendations",
        "description": "Implement remediation measures following ESA recommendations within specified timeframes.",
        "evidence_needed": ["Recommendation tracking log", "Remediation implementation evidence", "Compliance attestation"],
        "weight": "high",
        "nist_800_53": "CA-5",
        "iso_27001": "A.5.36",
    },
}

# Merge all controls
ALL_CONTROLS: dict[str, dict] = {
    **ICT_RISK_MANAGEMENT,
    **INCIDENT_MANAGEMENT,
    **RESILIENCE_TESTING,
    **THIRD_PARTY_RISK,
    **INFORMATION_SHARING,
    **OVERSIGHT,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DORAFinding:
    control_id: str
    article: str
    title: str
    status: str
    severity: str
    details: str
    remediation: str
    nist_800_53_mapping: str
    iso_27001_mapping: str


@dataclass
class DORAReport:
    controls_total: int
    controls_passing: int
    controls_failing: int
    findings: list[DORAFinding]
    compliance_score: float = 0.0
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    def compute(self) -> None:
        self.total_findings = len([f for f in self.findings if f.status == "FAIL"])
        self.critical_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "CRITICAL"])
        self.high_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "HIGH"])
        self.medium_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "MEDIUM"])
        self.low_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "LOW"])
        total = self.controls_passing + self.controls_failing
        self.compliance_score = (self.controls_passing / total * 100) if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Mock state
# ---------------------------------------------------------------------------

MOCK_DORA_STATE: dict[str, bool] = {
    "DORA-5.1": False, "DORA-5.2": False, "DORA-6.1": False, "DORA-6.4": False,
    "DORA-7.1": True, "DORA-8.1": False, "DORA-8.2": False, "DORA-9.1": False,
    "DORA-9.2": True, "DORA-9.3": False, "DORA-10.1": False, "DORA-10.2": True,
    "DORA-11.1": False, "DORA-11.3": False, "DORA-12.1": False, "DORA-13.1": False,
    "DORA-14.1": False,
    "DORA-15.1": False, "DORA-16.1": False, "DORA-17.1": False, "DORA-17.3": False,
    "DORA-19.1": False, "DORA-20.1": False,
    "DORA-24.1": False, "DORA-25.1": False, "DORA-26.1": False, "DORA-26.3": False,
    "DORA-28.1": False, "DORA-28.2": False, "DORA-28.3": False, "DORA-29.1": False,
    "DORA-30.1": False, "DORA-30.3": False, "DORA-31.1": False,
    "DORA-45.1": False, "DORA-45.2": False,
    "DORA-50.1": False, "DORA-54.1": False,
}


def _severity_for_weight(weight: str) -> str:
    return {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}.get(weight, "MEDIUM")


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class DORAScanner:
    """DORA Regulation (EU) 2022/2554 scanner — Articles 5-56, 39 controls."""

    def __init__(self, mock: bool = True) -> None:
        self.mock = mock

    async def scan(self) -> DORAReport:
        await asyncio.sleep(0)
        state = MOCK_DORA_STATE if self.mock else {}
        findings: list[DORAFinding] = []
        passing = 0
        failing = 0

        for ctrl_id, ctrl in ALL_CONTROLS.items():
            passed = state.get(ctrl_id, False)
            severity = _severity_for_weight(ctrl.get("weight", "medium"))

            if passed:
                passing += 1
            else:
                failing += 1
                findings.append(DORAFinding(
                    control_id=ctrl_id,
                    article=ctrl.get("article", ctrl_id),
                    title=ctrl["title"],
                    status="FAIL",
                    severity=severity,
                    details=(
                        f"[DORA {ctrl_id}] {ctrl['title']} — Not implemented. "
                        f"Missing: {', '.join(ctrl['evidence_needed'])}"
                    ),
                    remediation=(
                        f"To satisfy DORA {ctrl_id} ({ctrl.get('article', '')}), create:\n"
                        + "\n".join(f"  - {e}" for e in ctrl["evidence_needed"])
                    ),
                    nist_800_53_mapping=ctrl.get("nist_800_53", ""),
                    iso_27001_mapping=ctrl.get("iso_27001", ""),
                ))

        report = DORAReport(
            controls_total=len(ALL_CONTROLS),
            controls_passing=passing,
            controls_failing=failing,
            findings=findings,
        )
        report.compute()
        return report


class DORAFramework:
    """Sync wrapper for test compatibility."""

    def run_assessment(self) -> DORAReport:
        scanner = DORAScanner(mock=True)
        return asyncio.run(scanner.scan())
