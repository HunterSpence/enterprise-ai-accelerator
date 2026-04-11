"""
HIPAA — AI Systems Compliance — PolicyGuard Implementation
===========================================================
45 CFR Parts 160 and 164 (HIPAA Security Rule, Privacy Rule, Breach Notification Rule)
Applied specifically to AI systems that handle Protected Health Information (PHI).

Covers:
  - Administrative Safeguards (§164.308)
  - Physical Safeguards (§164.310)
  - Technical Safeguards (§164.312)
  - PHI handling in AI training and inference
  - Minimum necessary rule for AI training data
  - De-identification standards (Expert Determination + Safe Harbor)
  - Business Associate Agreement requirements
  - Audit logging of AI decisions affecting patient care
  - Right to access and right to receive explanations
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# HIPAA Safeguard Definitions — AI-Specific
# ---------------------------------------------------------------------------

ADMINISTRATIVE_SAFEGUARDS: dict[str, dict] = {
    "164.308(a)(1)": {
        "title": "Security Management Process",
        "requirement": "Implement policies and procedures to prevent, detect, contain, and correct security violations.",
        "ai_context": (
            "AI systems processing PHI must be included in the security risk assessment. "
            "Risk analysis must cover: model training data containing PHI, inference inputs/outputs with PHI, "
            "API endpoints that receive PHI, and model artifacts that could reveal PHI."
        ),
        "required": [
            "Risk analysis document covering AI systems handling PHI",
            "Risk management plan addressing AI-specific PHI risks",
            "Security incident procedures for AI inference failures",
            "Security evaluation of AI system changes",
        ],
        "severity": "CRITICAL",
        "standard": "Required",
    },
    "164.308(a)(2)": {
        "title": "Assigned Security Responsibility",
        "requirement": "Identify the security official responsible for the development and implementation of policies and procedures.",
        "ai_context": (
            "A designated HIPAA Security Officer must be accountable for AI systems handling PHI. "
            "AI model owners must be identified and their HIPAA obligations documented."
        ),
        "required": [
            "HIPAA Security Officer designation",
            "AI system owner assignments for PHI-handling models",
            "Accountability documentation for each AI system touching PHI",
        ],
        "severity": "HIGH",
        "standard": "Required",
    },
    "164.308(a)(3)": {
        "title": "Workforce Security",
        "requirement": "Implement policies and procedures to ensure workforce members have appropriate access to ePHI.",
        "ai_context": (
            "Only workforce members with a legitimate need may access AI training datasets containing PHI. "
            "Data scientists working with PHI must be authorized, trained, and subject to access revocation."
        ),
        "required": [
            "Access authorization procedure for AI/ML PHI datasets",
            "Workforce clearance/background check records for AI team members with PHI access",
            "Access termination procedures for AI system access",
            "Minimum necessary access policy for AI training environments",
        ],
        "severity": "HIGH",
        "standard": "Required",
    },
    "164.308(a)(4)": {
        "title": "Information Access Management",
        "requirement": "Implement policies and procedures for authorizing access to ePHI.",
        "ai_context": (
            "Access to AI model endpoints that return PHI-derived predictions must be controlled. "
            "Isolating PHI from non-PHI training data is required. "
            "The AI system must implement role-based access to PHI outputs."
        ),
        "required": [
            "Access control list for AI systems processing PHI",
            "Segregation of PHI training data from non-PHI data",
            "AI inference endpoint authorization controls",
            "Documentation of minimum necessary access for AI operations",
        ],
        "severity": "CRITICAL",
        "standard": "Required",
    },
    "164.308(a)(5)": {
        "title": "Security Awareness and Training",
        "requirement": "Implement a security awareness and training program for all workforce members.",
        "ai_context": (
            "AI/ML engineers working with PHI must receive HIPAA-specific training including: "
            "PHI de-identification requirements, minimum necessary rule in AI contexts, "
            "risk of model memorization (privacy attack vectors), and breach notification obligations."
        ),
        "required": [
            "HIPAA training completion records for AI team",
            "Training curriculum including AI-specific PHI risks",
            "Malicious software protection for ML workstations",
        ],
        "severity": "MEDIUM",
        "standard": "Required",
    },
    "164.308(a)(6)": {
        "title": "Security Incident Procedures",
        "requirement": "Implement policies and procedures to address security incidents.",
        "ai_context": (
            "AI-specific security incidents include: model inversion attacks that reveal PHI, "
            "adversarial inputs that expose PHI from training data, data poisoning of PHI-containing datasets, "
            "and unintentional PHI in AI-generated text outputs."
        ),
        "required": [
            "AI-specific security incident response procedures",
            "Incident log covering AI security events",
            "Response and reporting procedures for AI-related PHI breaches",
        ],
        "severity": "HIGH",
        "standard": "Required",
    },
    "164.308(a)(7)": {
        "title": "Contingency Plan",
        "requirement": "Establish (and implement as needed) policies and procedures for responding to an emergency.",
        "ai_context": (
            "AI systems used in clinical decision support must have contingency plans for: "
            "model serving outages (manual process fallback), "
            "corrupt model artifacts (rollback procedure), "
            "data backup for PHI used in AI pipelines."
        ),
        "required": [
            "Data backup plan for AI training data containing PHI",
            "Disaster recovery plan for AI inference systems in clinical use",
            "Emergency mode operation procedure for AI-dependent clinical workflows",
            "Testing and revision procedures for AI contingency plans",
        ],
        "severity": "HIGH",
        "standard": "Required",
    },
    "164.308(a)(8)": {
        "title": "Evaluation",
        "requirement": "Perform a periodic technical and nontechnical evaluation of security.",
        "ai_context": (
            "AI systems handling PHI must be included in HIPAA security evaluations. "
            "Evaluations should cover model drift (which may indicate data issues), "
            "access control effectiveness, and logging completeness."
        ),
        "required": [
            "AI system inclusion in annual HIPAA security evaluation",
            "Evaluation results documentation",
            "Remediation tracking for identified gaps",
        ],
        "severity": "MEDIUM",
        "standard": "Required",
    },
}

PHYSICAL_SAFEGUARDS: dict[str, dict] = {
    "164.310(a)(1)": {
        "title": "Facility Access Controls",
        "requirement": "Implement policies and procedures to limit physical access to ePHI systems.",
        "ai_context": (
            "Physical servers or workstations used for AI training on PHI datasets must have "
            "physical access controls. On-premises ML compute (GPU clusters with PHI data) must "
            "be in access-controlled facilities."
        ),
        "required": [
            "Physical access control records for ML compute infrastructure",
            "Visitor access logs for data centers with PHI AI workloads",
            "Maintenance records for AI training hardware",
        ],
        "severity": "MEDIUM",
        "standard": "Required",
    },
    "164.310(b)": {
        "title": "Workstation Use",
        "requirement": "Implement policies and procedures for proper workstation use.",
        "ai_context": (
            "Data scientist workstations used to access PHI for AI training must be restricted. "
            "PHI must not be stored on local workstations during AI model development."
        ),
        "required": [
            "Workstation use policy for AI/ML development",
            "Prohibition on local PHI storage during model development",
            "Screen lock and encryption requirements for ML workstations",
        ],
        "severity": "MEDIUM",
        "standard": "Required",
    },
    "164.310(c)": {
        "title": "Workstation Security",
        "requirement": "Implement physical safeguards for all workstations accessing ePHI.",
        "ai_context": (
            "AI development workstations with access to PHI datasets must be physically secured. "
            "Remote access to PHI AI environments must go through secured, authenticated connections."
        ),
        "required": [
            "Physical security controls for AI development workstations",
            "VPN/secure remote access for PHI AI environments",
            "Device encryption on ML workstations",
        ],
        "severity": "MEDIUM",
        "standard": "Required",
    },
    "164.310(d)(1)": {
        "title": "Device and Media Controls",
        "requirement": "Implement policies and procedures for receipt and removal of hardware containing ePHI.",
        "ai_context": (
            "AI training datasets containing PHI must be tracked as physical or electronic media. "
            "Disposal of media containing AI training data with PHI must follow HIPAA disposal requirements."
        ),
        "required": [
            "Media inventory for PHI AI training data",
            "Data disposal procedure for AI training datasets",
            "Media re-use policy for AI compute storage",
        ],
        "severity": "MEDIUM",
        "standard": "Required",
    },
}

TECHNICAL_SAFEGUARDS: dict[str, dict] = {
    "164.312(a)(1)": {
        "title": "Access Control",
        "requirement": "Implement technical policies and procedures for electronic information systems that maintain ePHI.",
        "ai_context": (
            "AI inference APIs returning PHI-derived predictions must have unique user identification. "
            "Emergency access procedure must exist for clinical AI systems. "
            "PHI in AI systems must be encrypted and access logged per user."
        ),
        "required": [
            "Unique user IDs for AI system access",
            "Emergency access procedure for clinical AI",
            "Automatic logoff for AI model interfaces",
            "Encryption/decryption for AI training data containing PHI",
        ],
        "severity": "CRITICAL",
        "standard": "Required",
    },
    "164.312(b)": {
        "title": "Audit Controls",
        "requirement": "Implement hardware, software, and/or procedural mechanisms to record and examine activity.",
        "ai_context": (
            "Every AI decision that uses or outputs PHI must be logged. "
            "Audit logs must capture: user ID, timestamp, AI model version, input summary, output/prediction, "
            "confidence score, and any human override. "
            "Logs must be retained per state law (minimum 6 years under HIPAA)."
        ),
        "required": [
            "AI decision audit logs with required fields",
            "Log retention compliance (6-year minimum)",
            "Log integrity protection (tamper-evident)",
            "Regular review of AI audit logs for anomalies",
        ],
        "severity": "CRITICAL",
        "standard": "Required",
    },
    "164.312(c)(1)": {
        "title": "Integrity Controls",
        "requirement": "Implement policies to protect ePHI from improper alteration or destruction.",
        "ai_context": (
            "AI training datasets containing PHI must be protected from unauthorized modification. "
            "Data lineage and checksums should ensure that PHI used in AI training has not been "
            "corrupted or tampered with — which could affect model outputs used for clinical decisions."
        ),
        "required": [
            "Cryptographic checksums for PHI training datasets",
            "Integrity monitoring for AI data pipelines",
            "Data lineage for PHI used in AI training",
        ],
        "severity": "HIGH",
        "standard": "Required",
    },
    "164.312(d)": {
        "title": "Person or Entity Authentication",
        "requirement": "Implement procedures to verify that a person or entity seeking access to ePHI is the one claimed.",
        "ai_context": (
            "Authentication mechanisms for AI systems processing PHI must be strong. "
            "API calls to AI inference endpoints handling PHI must be authenticated. "
            "Multi-factor authentication for human users accessing PHI-containing AI systems."
        ),
        "required": [
            "MFA for human access to PHI AI systems",
            "API authentication for AI inference endpoints handling PHI",
            "Service-to-service authentication for AI data pipelines",
        ],
        "severity": "HIGH",
        "standard": "Required",
    },
    "164.312(e)(1)": {
        "title": "Transmission Security",
        "requirement": "Implement technical security measures to guard against unauthorized access to ePHI.",
        "ai_context": (
            "PHI transmitted to or from AI inference APIs must be encrypted in transit (TLS 1.2+ minimum). "
            "Batch PHI data transferred to AI training environments must use encrypted transfer protocols."
        ),
        "required": [
            "TLS encryption for AI API endpoints handling PHI",
            "Encrypted data transfer for PHI to AI training environments",
            "Network encryption configuration evidence",
        ],
        "severity": "HIGH",
        "standard": "Required",
    },
}

# AI-specific HIPAA considerations
AI_PHI_CONTROLS: dict[str, dict] = {
    "HIPAA-AI-1": {
        "title": "PHI De-identification for AI Training Data",
        "requirement": (
            "HIPAA requires de-identification of PHI before use in AI training unless there is "
            "valid authorization from each patient. De-identification must meet either: "
            "Expert Determination method (45 CFR §164.514(b)(1)) or "
            "Safe Harbor method (45 CFR §164.514(b)(2))."
        ),
        "ai_context": (
            "AI training datasets derived from EHR, medical images, or clinical notes must be de-identified. "
            "Safe Harbor requires removing 18 specific identifiers. Expert Determination requires a qualified "
            "statistician to attest that re-identification risk is very small. "
            "Note: De-identified data is NO LONGER covered by HIPAA — but re-identification through "
            "AI model memorization is a known risk that must be addressed."
        ),
        "required": [
            "De-identification certification for all PHI-derived AI training data",
            "Safe Harbor checklist (18 identifier removal confirmation) OR Expert Determination letter",
            "Re-identification risk assessment",
            "Data Use Agreement (DUA) if using limited data sets",
        ],
        "severity": "CRITICAL",
        "standard": "Required",
    },
    "HIPAA-AI-2": {
        "title": "Minimum Necessary Rule for AI Training Data",
        "requirement": (
            "The minimum necessary rule (45 CFR §164.502(b)) requires limiting PHI access to the "
            "minimum necessary to accomplish the intended purpose."
        ),
        "ai_context": (
            "AI training datasets must use the minimum necessary PHI. If a model can be trained "
            "with age-group instead of exact birth date, or with diagnosis category instead of full "
            "clinical note, the more specific PHI should not be used. "
            "Data scientists must document why each PHI field included in training data is necessary."
        ),
        "required": [
            "Minimum necessary assessment for each PHI field in AI training data",
            "Documented justification for including each PHI field",
            "Feature selection review considering minimum necessary principle",
            "Privacy-preserving ML alternatives considered (federated learning, differential privacy)",
        ],
        "severity": "HIGH",
        "standard": "Required",
    },
    "HIPAA-AI-3": {
        "title": "Business Associate Agreement for AI Vendors",
        "requirement": (
            "AI vendors processing PHI on behalf of a covered entity are Business Associates "
            "and require a Business Associate Agreement (BAA) per 45 CFR §164.502(e)."
        ),
        "ai_context": (
            "This applies to: cloud ML platforms (AWS SageMaker, Azure ML, GCP Vertex) if PHI is processed; "
            "AI foundation model APIs (if PHI is sent as inference input); "
            "AI annotation tools (if annotators see PHI); "
            "MLOps platforms (MLflow, Weights & Biases) if PHI flows through them. "
            "Consumer AI products (ChatGPT, Claude) typically do NOT have BAAs available — "
            "PHI must NEVER be sent to these services."
        ),
        "required": [
            "BAA with cloud ML provider (AWS, Azure, GCP)",
            "BAA with AI inference API provider (if PHI is sent)",
            "Inventory of all AI vendors who may touch PHI",
            "Confirmation that no PHI is sent to AI vendors without BAA",
        ],
        "severity": "CRITICAL",
        "standard": "Required",
    },
    "HIPAA-AI-4": {
        "title": "AI Decision Audit Logging for Clinical Decisions",
        "requirement": (
            "AI systems contributing to clinical decisions must maintain audit logs sufficient for "
            "post-hoc review of any decision, including the model version, inputs, and output."
        ),
        "ai_context": (
            "If an AI system flags a patient for sepsis risk, recommends a drug, or flags a radiology "
            "image — that decision must be logged with: timestamp, patient ID (or encounter ID), "
            "AI model version, input features used (hashed), AI output/recommendation, confidence score, "
            "and clinician action taken (accepted/overridden). "
            "Required for CMS quality reporting and potential malpractice defense."
        ),
        "required": [
            "Clinical AI decision log with required fields",
            "Log retention policy (6 years minimum, some states 10+ years)",
            "Human override logging",
            "Linkage between AI decision log and EHR record",
        ],
        "severity": "CRITICAL",
        "standard": "Required",
    },
    "HIPAA-AI-5": {
        "title": "Right of Access to PHI Used in AI",
        "requirement": (
            "Under 45 CFR §164.524, individuals have the right to access their PHI. "
            "If an AI system uses a patient's PHI to generate a recommendation, "
            "the patient's right to access that PHI applies."
        ),
        "ai_context": (
            "Patients can request to see what PHI was used in AI-assisted clinical decisions. "
            "AI systems must be able to identify which patient records were used in specific decisions. "
            "This is technically challenging for batch-trained models — patient data used in training "
            "is embedded in model weights and cannot be directly accessed, but data from inference must "
            "be available for access requests."
        ),
        "required": [
            "Process for responding to HIPAA access requests for AI-used PHI",
            "Ability to identify what PHI an AI system used for a specific patient decision",
            "Distinction documented between training data (model weights) and inference data",
        ],
        "severity": "MEDIUM",
        "standard": "Required",
    },
    "HIPAA-AI-6": {
        "title": "Model Memorization Risk Assessment",
        "requirement": (
            "AI models trained on PHI can memorize specific patient records and reproduce them "
            "when queried (model inversion, membership inference attacks). "
            "This constitutes a potential unauthorized PHI disclosure."
        ),
        "ai_context": (
            "A model trained on clinical notes may reproduce exact text from those notes when prompted. "
            "Language models, in particular, can memorize training data including PHI. "
            "Healthcare AI providers must assess and mitigate this risk via: "
            "differential privacy during training, regular extraction attack testing, "
            "and output filtering to detect PHI in model outputs."
        ),
        "required": [
            "Membership inference attack testing results",
            "Model inversion attack testing results",
            "Differential privacy assessment",
            "Output PHI detection and filtering",
        ],
        "severity": "HIGH",
        "standard": "Addressable",
    },
}


# ---------------------------------------------------------------------------
# Mock HIPAA state
# ---------------------------------------------------------------------------

MOCK_HIPAA_STATE = {
    # Administrative
    "164.308(a)(1)": False,  # AI not included in risk assessment
    "164.308(a)(2)": True,   # Security officer exists
    "164.308(a)(3)": False,  # Workforce access for AI not managed
    "164.308(a)(4)": False,  # PHI access controls for AI not documented
    "164.308(a)(5)": False,  # AI team not HIPAA trained
    "164.308(a)(6)": False,  # No AI-specific incident procedures
    "164.308(a)(7)": False,  # No AI contingency plan
    "164.308(a)(8)": False,  # AI not in security evaluation

    # Physical
    "164.310(a)(1)": True,
    "164.310(b)": False,
    "164.310(c)": True,
    "164.310(d)(1)": False,

    # Technical
    "164.312(a)(1)": False,  # No unique IDs for AI system access
    "164.312(b)": False,     # No AI audit logs
    "164.312(c)(1)": False,  # No data integrity for AI training data
    "164.312(d)": False,     # No MFA for AI PHI systems
    "164.312(e)(1)": True,   # TLS in place

    # AI-specific
    "HIPAA-AI-1": False,     # PHI not de-identified for training
    "HIPAA-AI-2": False,     # Minimum necessary not assessed for AI
    "HIPAA-AI-3": False,     # No BAA with AI vendors
    "HIPAA-AI-4": False,     # No clinical AI decision logging
    "HIPAA-AI-5": False,     # No HIPAA access process for AI
    "HIPAA-AI-6": False,     # No model memorization risk assessment
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class HIPAAFinding:
    control_id: str
    title: str
    status: str
    severity: str
    category: str
    details: str
    remediation: str


@dataclass
class HIPAAReport:
    ai_systems_evaluated: int
    findings: list[HIPAAFinding]
    compliance_score: float = 0.0
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    baa_required_vendors: list[str] = field(default_factory=list)

    def compute(self) -> None:
        self.total_findings = len([f for f in self.findings if f.status == "FAIL"])
        self.critical_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "CRITICAL"])
        self.high_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "HIGH"])
        self.medium_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "MEDIUM"])
        self.low_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "LOW"])
        pass_count = len([f for f in self.findings if f.status == "PASS"])
        total = pass_count + self.total_findings
        self.compliance_score = (pass_count / total * 100) if total > 0 else 100.0


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class HIPAAScanner:
    """
    HIPAA Security Rule compliance scanner with AI-specific extensions.
    Focuses on PHI handling in AI training and inference pipelines.
    """

    def __init__(
        self,
        ai_systems: Optional[list[dict]] = None,
        mock: bool = True,
    ) -> None:
        self.ai_systems = ai_systems or []
        self.mock = mock

    async def scan(self) -> HIPAAReport:
        await asyncio.sleep(0)

        state = MOCK_HIPAA_STATE if self.mock else {}
        all_findings: list[HIPAAFinding] = []

        all_control_sets = [
            ("Administrative Safeguards §164.308", ADMINISTRATIVE_SAFEGUARDS),
            ("Physical Safeguards §164.310", PHYSICAL_SAFEGUARDS),
            ("Technical Safeguards §164.312", TECHNICAL_SAFEGUARDS),
            ("AI-Specific PHI Controls", AI_PHI_CONTROLS),
        ]

        for category, controls in all_control_sets:
            for control_id, control in controls.items():
                passed = state.get(control_id, True)
                severity = control["severity"]

                all_findings.append(HIPAAFinding(
                    control_id=control_id,
                    title=control["title"],
                    status="PASS" if passed else "FAIL",
                    severity=severity,
                    category=category,
                    details=(
                        f"[{control_id}] COMPLIANT — {control['title']}" if passed
                        else (
                            f"[{control_id}] NON-COMPLIANT — {control['title']}\n"
                            f"Requirement: {control['requirement']}\n"
                            f"AI Context: {control['ai_context']}"
                        )
                    ),
                    remediation=(
                        "" if passed else (
                            f"To remediate {control_id}:\n"
                            + "\n".join(f"  - {r}" for r in control["required"])
                        )
                    ),
                ))

        # Identify BAA-required AI vendors from mock data
        baa_vendors = []
        if not state.get("HIPAA-AI-3", True):
            baa_vendors = [
                "AWS SageMaker (if PHI processed in training)",
                "Azure Machine Learning (if PHI in datasets)",
                "Google Vertex AI (if PHI in training data)",
                "MLflow (if PHI flows through experiment tracking)",
                "Weights & Biases (if PHI in run metadata)",
                "Any LLM API used for clinical summarization (OpenAI, Anthropic, etc.)",
            ]

        report = HIPAAReport(
            ai_systems_evaluated=len(self.ai_systems),
            findings=all_findings,
            baa_required_vendors=baa_vendors,
        )
        report.compute()
        return report
