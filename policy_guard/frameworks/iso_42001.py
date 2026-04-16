"""
ISO/IEC 42001:2023 — Artificial Intelligence Management System (AIMS)
======================================================================
Source: ISO/IEC 42001:2023 (published October 2023)

Structure:
  - Clauses 4–10: Core AIMS requirements (management system structure)
  - Annex A: Information security controls for AI (A.2 through A.10)
  - Cross-mappings to EU AI Act articles and NIST AI RMF 2.0 subcategories

Control count: 52 controls (32 clause-level + 20 Annex A)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Clause 4: Context of the Organization
# ---------------------------------------------------------------------------

CLAUSE_4_CONTROLS: dict[str, dict] = {
    "4.1": {
        "title": "Understanding the organization and its context",
        "description": "Determine external and internal issues relevant to AI management system purpose.",
        "evidence_needed": ["Internal/external issue register", "AIMS context document", "Stakeholder analysis"],
        "weight": "high",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-1.5",
    },
    "4.2": {
        "title": "Understanding needs and expectations of interested parties",
        "description": "Identify stakeholders relevant to the AIMS and their requirements.",
        "evidence_needed": ["Stakeholder register", "Stakeholder needs analysis", "Regulatory requirements list"],
        "weight": "high",
        "eu_ai_act": "Article 13",
        "nist_ai_rmf": "MAP-3.1",
    },
    "4.3": {
        "title": "Determining the scope of the AIMS",
        "description": "Define the boundaries and applicability of the AI management system.",
        "evidence_needed": ["AIMS scope statement", "AI system inventory within scope", "Exclusions justification"],
        "weight": "high",
        "eu_ai_act": "Article 11",
        "nist_ai_rmf": "MAP-1.1",
    },
    "4.4": {
        "title": "Artificial Intelligence Management System",
        "description": "Establish, implement, maintain, and continually improve the AIMS.",
        "evidence_needed": ["AIMS implementation plan", "AIMS maintenance records", "Improvement log"],
        "weight": "critical",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-1.1",
    },
}

# ---------------------------------------------------------------------------
# Clause 5: Leadership
# ---------------------------------------------------------------------------

CLAUSE_5_CONTROLS: dict[str, dict] = {
    "5.1": {
        "title": "Leadership and commitment",
        "description": "Top management shall demonstrate leadership and commitment to the AIMS.",
        "evidence_needed": ["Board AI governance charter", "Executive AI risk briefings", "Resource allocation records"],
        "weight": "high",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-2.2",
    },
    "5.2": {
        "title": "AI policy",
        "description": "Top management shall establish an AI policy aligned with organizational purpose.",
        "evidence_needed": ["Documented AI policy", "Policy communication records", "Policy review history"],
        "weight": "critical",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-1.1",
    },
    "5.3": {
        "title": "Organizational roles, responsibilities and authorities",
        "description": "Assign and communicate responsibilities and authorities for AIMS-relevant roles.",
        "evidence_needed": ["RACI matrix for AI governance", "AI role definitions", "Delegation of authority"],
        "weight": "high",
        "eu_ai_act": "Article 14",
        "nist_ai_rmf": "GOVERN-1.2",
    },
}

# ---------------------------------------------------------------------------
# Clause 6: Planning
# ---------------------------------------------------------------------------

CLAUSE_6_CONTROLS: dict[str, dict] = {
    "6.1": {
        "title": "Actions to address risks and opportunities",
        "description": "Plan actions to address AI risks and opportunities and integrate into AIMS.",
        "evidence_needed": ["AI risk register", "Risk treatment plan", "Opportunity analysis"],
        "weight": "critical",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-1.3",
    },
    "6.1.1": {
        "title": "General risk and opportunity planning",
        "description": "Determine risks and opportunities relevant to the context and intended outcomes.",
        "evidence_needed": ["Risk and opportunity log", "AIMS planning records"],
        "weight": "high",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "MAP-1.5",
    },
    "6.1.2": {
        "title": "AI risk assessment",
        "description": "Establish, implement, and maintain an AI risk assessment process.",
        "evidence_needed": ["AI risk assessment methodology", "Risk assessment results", "Risk acceptance criteria"],
        "weight": "critical",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "MAP-2.3",
    },
    "6.1.3": {
        "title": "AI risk treatment",
        "description": "Apply the AI risk assessment process to produce a risk treatment plan.",
        "evidence_needed": ["Risk treatment plan", "Selected risk treatment options", "Statement of applicability"],
        "weight": "critical",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "MANAGE-1.3",
    },
    "6.2": {
        "title": "AI objectives and planning to achieve them",
        "description": "Establish AI objectives consistent with the AI policy and plan how to achieve them.",
        "evidence_needed": ["AI objectives documentation", "Success metrics", "Progress tracking records"],
        "weight": "medium",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-1.5",
    },
}

# ---------------------------------------------------------------------------
# Clause 7: Support
# ---------------------------------------------------------------------------

CLAUSE_7_CONTROLS: dict[str, dict] = {
    "7.1": {
        "title": "Resources",
        "description": "Determine and provide resources needed for the establishment and maintenance of the AIMS.",
        "evidence_needed": ["AI budget allocation", "Resource inventory", "Headcount plan"],
        "weight": "medium",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "MANAGE-2.1",
    },
    "7.2": {
        "title": "Competence",
        "description": "Determine necessary competence for persons working under the organization's control.",
        "evidence_needed": ["Competency framework", "Training records", "Skills gap analysis"],
        "weight": "medium",
        "eu_ai_act": "Article 4",
        "nist_ai_rmf": "GOVERN-3.1",
    },
    "7.3": {
        "title": "Awareness",
        "description": "Ensure persons working under the organization's control are aware of the AI policy.",
        "evidence_needed": ["Awareness training completion records", "Internal comms on AI policy"],
        "weight": "medium",
        "eu_ai_act": "Article 4",
        "nist_ai_rmf": "GOVERN-1.4",
    },
    "7.4": {
        "title": "Communication",
        "description": "Determine internal and external communication relevant to the AIMS.",
        "evidence_needed": ["Communication plan", "Stakeholder communication records"],
        "weight": "medium",
        "eu_ai_act": "Article 13",
        "nist_ai_rmf": "MANAGE-3.1",
    },
    "7.5": {
        "title": "Documented information",
        "description": "Maintain documented information required by the AIMS and determined as necessary.",
        "evidence_needed": ["Document control procedure", "AIMS document register", "Records retention policy"],
        "weight": "high",
        "eu_ai_act": "Article 11",
        "nist_ai_rmf": "GOVERN-1.1",
    },
}

# ---------------------------------------------------------------------------
# Clause 8: Operation
# ---------------------------------------------------------------------------

CLAUSE_8_CONTROLS: dict[str, dict] = {
    "8.1": {
        "title": "Operational planning and control",
        "description": "Plan, implement, control, and maintain processes to meet AIMS requirements.",
        "evidence_needed": ["AI lifecycle procedures", "Change management records", "Operational controls"],
        "weight": "high",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-4.2",
    },
    "8.2": {
        "title": "AI risk assessment (operational)",
        "description": "Perform AI risk assessments at planned intervals or when significant changes occur.",
        "evidence_needed": ["Periodic risk assessment reports", "Trigger-based reassessment records"],
        "weight": "high",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "MAP-4.1",
    },
    "8.3": {
        "title": "AI system impact assessment",
        "description": "Conduct impact assessments for AI systems considering ethical, societal, and legal impacts.",
        "evidence_needed": ["AI impact assessment reports", "Ethical review records", "Legal compliance review"],
        "weight": "critical",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "MAP-2.2",
    },
    "8.4": {
        "title": "AI system lifecycle",
        "description": "Establish and control processes for the AI system lifecycle from design to decommissioning.",
        "evidence_needed": ["AI system lifecycle policy", "Design review records", "Deployment approval gates"],
        "weight": "high",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-6.1",
    },
    "8.5": {
        "title": "Data management for AI",
        "description": "Establish processes for data acquisition, processing, and quality management for AI.",
        "evidence_needed": ["Data governance policy", "Data quality reports", "Data lineage documentation"],
        "weight": "critical",
        "eu_ai_act": "Article 10",
        "nist_ai_rmf": "MAP-3.3",
    },
    "8.6": {
        "title": "AI system verification and validation",
        "description": "Verify and validate AI systems against requirements before deployment.",
        "evidence_needed": ["V&V plan", "Testing results", "Acceptance criteria records"],
        "weight": "high",
        "eu_ai_act": "Article 15",
        "nist_ai_rmf": "MEASURE-2.2",
    },
    "8.7": {
        "title": "AI system incident management",
        "description": "Establish and maintain procedures for managing AI system incidents.",
        "evidence_needed": ["AI incident response plan", "Incident log", "Root cause analysis records"],
        "weight": "high",
        "eu_ai_act": "Article 62",
        "nist_ai_rmf": "MANAGE-1.2",
    },
    "8.8": {
        "title": "AI system decommissioning",
        "description": "Establish and maintain procedures for decommissioning AI systems.",
        "evidence_needed": ["Decommissioning checklist", "Data disposal records", "Sunset communication plan"],
        "weight": "medium",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "MANAGE-3.2",
    },
}

# ---------------------------------------------------------------------------
# Clause 9: Performance Evaluation
# ---------------------------------------------------------------------------

CLAUSE_9_CONTROLS: dict[str, dict] = {
    "9.1": {
        "title": "Monitoring, measurement, analysis and evaluation",
        "description": "Evaluate AI system performance and AIMS effectiveness.",
        "evidence_needed": ["KPI dashboard for AI systems", "Monitoring methodology", "Performance reports"],
        "weight": "high",
        "eu_ai_act": "Article 72",
        "nist_ai_rmf": "MANAGE-2.4",
    },
    "9.2": {
        "title": "Internal audit",
        "description": "Conduct internal audits at planned intervals to verify AIMS conformance.",
        "evidence_needed": ["Internal audit plan", "Audit reports", "Corrective action records"],
        "weight": "high",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-2.1",
    },
    "9.3": {
        "title": "Management review",
        "description": "Top management shall review the AIMS at planned intervals.",
        "evidence_needed": ["Management review meeting minutes", "Review inputs and outputs", "Action items log"],
        "weight": "medium",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-2.2",
    },
}

# ---------------------------------------------------------------------------
# Clause 10: Improvement
# ---------------------------------------------------------------------------

CLAUSE_10_CONTROLS: dict[str, dict] = {
    "10.1": {
        "title": "Continual improvement",
        "description": "Continually improve the suitability, adequacy, and effectiveness of the AIMS.",
        "evidence_needed": ["Improvement objectives log", "Improvement initiative tracker"],
        "weight": "medium",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "MANAGE-2.2",
    },
    "10.2": {
        "title": "Nonconformity and corrective action",
        "description": "React to nonconformities and take corrective action to eliminate causes.",
        "evidence_needed": ["Nonconformity register", "Root cause analysis", "Corrective action verification"],
        "weight": "medium",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "MEASURE-3.3",
    },
}

# ---------------------------------------------------------------------------
# Annex A: Controls (A.2 through A.10)
# ---------------------------------------------------------------------------

ANNEX_A_CONTROLS: dict[str, dict] = {
    "A.2.2": {
        "title": "AI policy",
        "description": "Establish and maintain a documented AI policy covering responsible use, risk tolerance, and governance.",
        "evidence_needed": ["AI policy document", "Policy approval records", "Policy distribution evidence"],
        "weight": "critical",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-1.1",
    },
    "A.2.3": {
        "title": "Allocation of AI roles and responsibilities",
        "description": "Clearly define and document roles and responsibilities for AI risk management.",
        "evidence_needed": ["RACI chart", "Role descriptions", "Accountability assignments"],
        "weight": "high",
        "eu_ai_act": "Article 14",
        "nist_ai_rmf": "GOVERN-1.2",
    },
    "A.3.2": {
        "title": "Internal AI system impact assessment",
        "description": "Conduct documented impact assessments for AI systems on individuals, groups, and society.",
        "evidence_needed": ["Impact assessment methodology", "Assessment reports per AI system"],
        "weight": "critical",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "MAP-3.5",
    },
    "A.3.3": {
        "title": "AI use objectives",
        "description": "Define specific objectives for the use and deployment of AI systems.",
        "evidence_needed": ["AI use case registry with objectives", "Success criteria documentation"],
        "weight": "medium",
        "eu_ai_act": "Article 13",
        "nist_ai_rmf": "MAP-2.2",
    },
    "A.4.2": {
        "title": "Intended use of AI",
        "description": "Document the intended use cases, operational environment, and user groups for each AI system.",
        "evidence_needed": ["Intended use statement", "Operational environment description"],
        "weight": "high",
        "eu_ai_act": "Article 13",
        "nist_ai_rmf": "MAP-2.2",
    },
    "A.4.3": {
        "title": "Considerations for AI system lifecycle",
        "description": "Apply controls addressing design, development, testing, deployment, and decommissioning phases.",
        "evidence_needed": ["AI lifecycle gate documentation", "Stage-gate review records"],
        "weight": "high",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "GOVERN-4.2",
    },
    "A.5.2": {
        "title": "Documentation of AI system",
        "description": "Maintain comprehensive documentation for each AI system covering architecture, data, and performance.",
        "evidence_needed": ["Model card or system card", "Architecture documentation", "Training data documentation"],
        "weight": "high",
        "eu_ai_act": "Article 11",
        "nist_ai_rmf": "MAP-2.2",
    },
    "A.6.1": {
        "title": "Functionality and performance",
        "description": "Verify that AI systems perform as intended under defined conditions.",
        "evidence_needed": ["Performance test results", "Benchmarking reports", "Regression test records"],
        "weight": "high",
        "eu_ai_act": "Article 15",
        "nist_ai_rmf": "MEASURE-2.2",
    },
    "A.6.2": {
        "title": "AI system reliability",
        "description": "Ensure AI systems operate reliably within their operational context.",
        "evidence_needed": ["Reliability testing reports", "Uptime/availability metrics", "Failure mode analysis"],
        "weight": "medium",
        "eu_ai_act": "Article 15",
        "nist_ai_rmf": "MEASURE-2.7",
    },
    "A.7.3": {
        "title": "Data quality",
        "description": "Establish and maintain processes to ensure data quality throughout the AI lifecycle.",
        "evidence_needed": ["Data quality framework", "Data profiling reports", "Quality gate records"],
        "weight": "critical",
        "eu_ai_act": "Article 10",
        "nist_ai_rmf": "MEASURE-2.3",
    },
    "A.7.4": {
        "title": "Data privacy and PII protection in AI",
        "description": "Implement controls to protect personal data and PII used in AI systems.",
        "evidence_needed": ["Privacy impact assessment", "Data minimization evidence", "Consent management records"],
        "weight": "critical",
        "eu_ai_act": "Article 10",
        "nist_ai_rmf": "MEASURE-2.6",
    },
    "A.8.2": {
        "title": "AI system transparency",
        "description": "Ensure AI systems operate transparently and provide meaningful explanations.",
        "evidence_needed": ["Explainability documentation", "Transparency disclosure", "User-facing AI disclosure"],
        "weight": "high",
        "eu_ai_act": "Article 13",
        "nist_ai_rmf": "MEASURE-2.9",
    },
    "A.8.4": {
        "title": "Testing approach for AI",
        "description": "Define and execute a comprehensive testing strategy for AI systems.",
        "evidence_needed": ["Test strategy document", "Test execution reports", "Defect tracking records"],
        "weight": "high",
        "eu_ai_act": "Article 9",
        "nist_ai_rmf": "MEASURE-1.1",
    },
    "A.9.1": {
        "title": "AI system monitoring post-deployment",
        "description": "Monitor deployed AI systems for performance degradation, bias drift, and unexpected behavior.",
        "evidence_needed": ["Monitoring dashboard", "Alert configuration", "Anomaly investigation records"],
        "weight": "high",
        "eu_ai_act": "Article 72",
        "nist_ai_rmf": "MEASURE-2.11",
    },
    "A.9.4": {
        "title": "Incident and problem management for AI",
        "description": "Establish procedures for detecting, reporting, and managing AI-related incidents.",
        "evidence_needed": ["AI incident response procedure", "Incident log", "Post-incident review records"],
        "weight": "high",
        "eu_ai_act": "Article 62",
        "nist_ai_rmf": "MANAGE-1.2",
    },
    "A.10.2": {
        "title": "Third-party AI system suppliers",
        "description": "Evaluate and manage risks from third-party AI systems and components.",
        "evidence_needed": ["Third-party AI risk assessment", "Supplier questionnaire", "Contract AI clauses"],
        "weight": "high",
        "eu_ai_act": "Article 25",
        "nist_ai_rmf": "GOVERN-6.1",
    },
    "A.10.3": {
        "title": "Responsibilities for third-party AI",
        "description": "Clearly define responsibilities when using third-party AI systems or components.",
        "evidence_needed": ["Shared responsibility matrix", "Third-party agreement", "SLA for AI components"],
        "weight": "medium",
        "eu_ai_act": "Article 25",
        "nist_ai_rmf": "GOVERN-1.6",
    },
}

# Merge all controls for total count
ALL_CONTROLS: dict[str, dict] = {
    **CLAUSE_4_CONTROLS,
    **CLAUSE_5_CONTROLS,
    **CLAUSE_6_CONTROLS,
    **CLAUSE_7_CONTROLS,
    **CLAUSE_8_CONTROLS,
    **CLAUSE_9_CONTROLS,
    **CLAUSE_10_CONTROLS,
    **ANNEX_A_CONTROLS,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ISO42001Finding:
    control_id: str
    title: str
    status: str
    severity: str
    details: str
    remediation: str
    eu_ai_act_mapping: str
    nist_ai_rmf_mapping: str


@dataclass
class ISO42001Report:
    controls_total: int
    controls_passing: int
    controls_failing: int
    findings: list[ISO42001Finding]
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
# Mock state — realistic gap for a newly AI-adopting enterprise
# ---------------------------------------------------------------------------

MOCK_ISO42001_STATE: dict[str, bool] = {
    "4.1": False, "4.2": False, "4.3": True, "4.4": False,
    "5.1": False, "5.2": False, "5.3": False,
    "6.1": False, "6.1.1": False, "6.1.2": False, "6.1.3": False, "6.2": False,
    "7.1": True, "7.2": True, "7.3": False, "7.4": False, "7.5": False,
    "8.1": False, "8.2": False, "8.3": False, "8.4": False, "8.5": False,
    "8.6": False, "8.7": False, "8.8": False,
    "9.1": False, "9.2": False, "9.3": False,
    "10.1": False, "10.2": False,
    "A.2.2": False, "A.2.3": False, "A.3.2": False, "A.3.3": False,
    "A.4.2": False, "A.4.3": False, "A.5.2": False, "A.6.1": False,
    "A.6.2": False, "A.7.3": False, "A.7.4": False, "A.8.2": False,
    "A.8.4": False, "A.9.1": False, "A.9.4": False, "A.10.2": False,
    "A.10.3": False,
}


def _severity_for_weight(weight: str) -> str:
    return {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}.get(weight, "MEDIUM")


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class ISO42001Scanner:
    """ISO/IEC 42001:2023 AIMS scanner — 49 controls across clauses 4-10 and Annex A."""

    def __init__(self, mock: bool = True) -> None:
        self.mock = mock

    async def scan(self) -> ISO42001Report:
        await asyncio.sleep(0)
        state = MOCK_ISO42001_STATE if self.mock else {}
        findings: list[ISO42001Finding] = []
        passing = 0
        failing = 0

        for ctrl_id, ctrl in ALL_CONTROLS.items():
            passed = state.get(ctrl_id, False)
            severity = _severity_for_weight(ctrl.get("weight", "medium"))

            if passed:
                passing += 1
            else:
                failing += 1
                findings.append(ISO42001Finding(
                    control_id=ctrl_id,
                    title=ctrl["title"],
                    status="FAIL",
                    severity=severity,
                    details=(
                        f"[ISO 42001 {ctrl_id}] {ctrl['title']} — Not implemented. "
                        f"Missing: {', '.join(ctrl['evidence_needed'])}"
                    ),
                    remediation=(
                        f"To satisfy ISO 42001 {ctrl_id}, create:\n"
                        + "\n".join(f"  - {e}" for e in ctrl["evidence_needed"])
                    ),
                    eu_ai_act_mapping=ctrl.get("eu_ai_act", ""),
                    nist_ai_rmf_mapping=ctrl.get("nist_ai_rmf", ""),
                ))

        report = ISO42001Report(
            controls_total=len(ALL_CONTROLS),
            controls_passing=passing,
            controls_failing=failing,
            findings=findings,
        )
        report.compute()
        return report


class ISO42001Framework:
    """Sync wrapper for test compatibility."""

    def run_assessment(self) -> ISO42001Report:
        scanner = ISO42001Scanner(mock=True)
        return asyncio.run(scanner.scan())
