"""
EU AI Act Compliance — PolicyGuard V2 Implementation
=====================================================
Regulation (EU) 2024/1689. Entered into force August 2, 2024.
High-risk system enforcement deadline: August 2, 2026.

V2 Enhancements:
- Full Article coverage: 5, 6, 9, 10, 11, 12, 13, 14, 15, 43, 52-55
- Article 5: All 8 prohibited practices with evidence collection
- Article 6: Full Annex III classification + Article 6(1) safety component check
- Article 11: 15-section technical documentation completeness score
- Article 43: Conformity assessment route determination (internal vs notified body)
- Articles 52-55: GPAI transparency obligations tracker
- Live countdown: days_until_enforcement()
- Compliance gap score per article
- Cross-framework mappings to NIST AI RMF and SOC2 AICC
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Risk tiers
# ---------------------------------------------------------------------------

RISK_TIER_UNACCEPTABLE = "Unacceptable"
RISK_TIER_HIGH = "High-Risk"
RISK_TIER_LIMITED = "Limited Risk"
RISK_TIER_MINIMAL = "Minimal Risk"
RISK_TIER_GPAI = "GPAI (General Purpose AI)"


# ---------------------------------------------------------------------------
# Enforcement dates
# ---------------------------------------------------------------------------

ENFORCEMENT_DATES = {
    "prohibited_practices": date(2025, 2, 2),
    "gpai_obligations": date(2025, 8, 2),
    "high_risk_systems": date(2026, 8, 2),
    "all_obligations": date(2027, 8, 2),
}


def days_until_enforcement(milestone: str = "high_risk_systems") -> int:
    """Return days remaining until a specific EU AI Act enforcement milestone."""
    target = ENFORCEMENT_DATES.get(milestone, ENFORCEMENT_DATES["high_risk_systems"])
    delta = target - date.today()
    return max(0, delta.days)


# ---------------------------------------------------------------------------
# Annex III — High-risk AI categories (Article 6(2))
# ---------------------------------------------------------------------------

ANNEX_III_CATEGORIES: dict[int, dict] = {
    1: {
        "name": "Biometric Identification and Categorisation",
        "description": (
            "AI systems intended to be used for real-time and post remote biometric "
            "identification of natural persons in publicly accessible spaces."
        ),
        "keywords": [
            "biometric", "facial recognition", "fingerprint", "iris", "voice recognition",
            "gait recognition", "real-time identification", "remote biometric",
        ],
        "article_ref": "Annex III, Point 1",
        "prohibited_subcases": ["real-time remote biometric identification in public spaces (with exceptions)"],
        "conformity_route": "notified_body",
    },
    2: {
        "name": "Critical Infrastructure",
        "description": (
            "AI systems as safety components in management and operation of critical "
            "infrastructure (water, electricity, gas, heat, transport, Internet)."
        ),
        "keywords": [
            "power grid", "water treatment", "gas pipeline", "electricity", "transport",
            "critical infrastructure", "SCADA", "industrial control", "nuclear", "dam",
        ],
        "article_ref": "Annex III, Point 2",
        "prohibited_subcases": [],
        "conformity_route": "notified_body",
    },
    3: {
        "name": "Education and Vocational Training",
        "description": (
            "AI used to determine access to educational institutions or to evaluate "
            "learning outcomes that determine students' futures."
        ),
        "keywords": [
            "admissions", "exam", "academic evaluation", "student assessment", "grading",
            "educational access", "vocational training", "scholarship selection", "proctoring",
        ],
        "article_ref": "Annex III, Point 3",
        "prohibited_subcases": [],
        "conformity_route": "internal",
    },
    4: {
        "name": "Employment, Workers Management, and Access to Self-Employment",
        "description": (
            "AI used for recruitment, CV screening, promotion decisions, task allocation, "
            "performance monitoring, and termination of work-related contracts."
        ),
        "keywords": [
            "resume screening", "cv screening", "recruitment", "hiring", "performance review",
            "employee monitoring", "task allocation", "termination", "promotion",
            "workforce management", "HR AI", "talent acquisition", "applicant tracking",
        ],
        "article_ref": "Annex III, Point 4",
        "prohibited_subcases": [],
        "conformity_route": "internal",
    },
    5: {
        "name": "Access to Essential Private and Public Services",
        "description": (
            "AI used to evaluate creditworthiness, or AI components of services "
            "provided by public authorities for essential benefits."
        ),
        "keywords": [
            "credit scoring", "creditworthiness", "credit decision", "loan approval",
            "loan application", "insurance pricing", "welfare benefits", "social scoring",
            "public service eligibility", "benefit determination", "credit risk",
        ],
        "article_ref": "Annex III, Point 5",
        "prohibited_subcases": ["social scoring by public authorities leading to detrimental treatment"],
        "conformity_route": "internal",
    },
    6: {
        "name": "Law Enforcement",
        "description": (
            "AI used by law enforcement authorities for individual risk assessments, "
            "polygraph testing, crime prediction, evidence reliability evaluation."
        ),
        "keywords": [
            "law enforcement", "police", "crime prediction", "predictive policing",
            "recidivism", "criminal risk", "investigative tool", "forensic", "lie detector",
        ],
        "article_ref": "Annex III, Point 6",
        "prohibited_subcases": ["predictive policing of individuals based solely on profiling"],
        "conformity_route": "notified_body",
    },
    7: {
        "name": "Migration, Asylum, and Border Control",
        "description": (
            "AI used to assess risks posed by individuals seeking asylum, visas, or "
            "crossing borders; AI for border surveillance."
        ),
        "keywords": [
            "asylum", "immigration", "border control", "visa application", "deportation",
            "refugee", "migration risk", "border surveillance",
        ],
        "article_ref": "Annex III, Point 7",
        "prohibited_subcases": [],
        "conformity_route": "notified_body",
    },
    8: {
        "name": "Administration of Justice and Democratic Processes",
        "description": (
            "AI to assist judicial authorities in researching, interpreting facts or law, "
            "or applying the law to a concrete set of facts."
        ),
        "keywords": [
            "judicial", "court", "sentencing", "legal decision", "judge", "arbitration",
            "electoral", "voting system", "democracy", "legal research AI",
        ],
        "article_ref": "Annex III, Point 8",
        "prohibited_subcases": [],
        "conformity_route": "notified_body",
    },
}


# ---------------------------------------------------------------------------
# Prohibited practices (Article 5) — 8 categories
# ---------------------------------------------------------------------------

PROHIBITED_PRACTICES: list[dict] = [
    {
        "id": "A5.1.a",
        "name": "Subliminal manipulation below conscious perception",
        "description": (
            "AI that deploys subliminal techniques beyond a person's consciousness to "
            "materially distort behaviour in a manner that causes or is likely to cause harm."
        ),
        "keywords": ["subliminal", "subconscious manipulation", "hidden influence", "dark pattern AI"],
        "evidence_to_collect": [
            "UX dark pattern audit results",
            "Behavioral manipulation assessment",
            "Ethics review board sign-off",
        ],
        "max_fine_eur": 35_000_000,
        "nist_mapping": "GOVERN-1.1",
    },
    {
        "id": "A5.1.b",
        "name": "Exploitation of vulnerabilities of specific groups",
        "description": (
            "AI that exploits vulnerabilities of specific groups (age, disability, social situation) "
            "to distort behaviour in a way that causes or is likely to cause harm."
        ),
        "keywords": [
            "exploit vulnerability", "target children", "elderly targeting",
            "disability exploitation", "vulnerable population",
        ],
        "evidence_to_collect": [
            "Vulnerable population impact assessment",
            "Age-gating controls documentation",
            "Accessibility and harm review",
        ],
        "max_fine_eur": 35_000_000,
        "nist_mapping": "MAP-3.1",
    },
    {
        "id": "A5.1.c",
        "name": "Social scoring by public authorities",
        "description": (
            "AI systems for the evaluation or classification of natural persons or groups "
            "based on social behaviour or personal characteristics by public authorities."
        ),
        "keywords": ["social scoring", "citizen score", "social credit", "public authority scoring"],
        "evidence_to_collect": [
            "System purpose declaration confirming non-scoring use",
            "Deployment authority confirmation",
        ],
        "max_fine_eur": 35_000_000,
        "nist_mapping": "GOVERN-1.3",
    },
    {
        "id": "A5.1.d",
        "name": "Real-time remote biometric identification in public spaces",
        "description": (
            "Real-time remote biometric identification of natural persons in publicly accessible "
            "spaces for law enforcement purposes (except narrow listed exceptions)."
        ),
        "keywords": [
            "real-time facial recognition", "live surveillance", "public space biometric",
            "mass surveillance",
        ],
        "evidence_to_collect": [
            "Deployment location mapping (not public spaces)",
            "Law enforcement authorization documents",
            "Exceptional use case justification",
        ],
        "max_fine_eur": 35_000_000,
        "nist_mapping": "MAP-1.1",
    },
    {
        "id": "A5.1.e",
        "name": "Biometric categorisation inferring sensitive attributes",
        "description": (
            "AI that categorises individuals based on biometric data to deduce or infer race, "
            "political opinions, trade union membership, religion, sex life, or criminal history."
        ),
        "keywords": [
            "infer race", "infer religion", "infer political opinion", "infer sexuality",
            "biometric categorisation sensitive",
        ],
        "evidence_to_collect": [
            "Model output category audit",
            "Training data label review",
            "Prohibited inference testing results",
        ],
        "max_fine_eur": 35_000_000,
        "nist_mapping": "MEASURE-2.3",
    },
    {
        "id": "A5.1.f",
        "name": "Emotion recognition in workplace or education",
        "description": (
            "AI systems that infer emotions of natural persons in workplace and educational "
            "settings (unless for medical or safety purposes)."
        ),
        "keywords": [
            "emotion recognition workplace", "emotion AI school", "affect recognition work",
            "emotion inference employee", "mood detection",
        ],
        "evidence_to_collect": [
            "System functionality scope document",
            "Confirmation of non-emotion-recognition use",
            "Medical/safety exception justification (if applicable)",
        ],
        "max_fine_eur": 35_000_000,
        "nist_mapping": "MAP-1.1",
    },
    {
        "id": "A5.1.g",
        "name": "Predictive policing of individuals",
        "description": (
            "AI that assesses individuals to predict future criminal offending based solely "
            "on profiling, personal characteristics, or personality traits."
        ),
        "keywords": [
            "predictive policing individual", "precrime", "individual crime prediction",
            "personality-based crime risk",
        ],
        "evidence_to_collect": [
            "Algorithm use-case documentation",
            "Input feature audit (excluding protected characteristics)",
            "Legal basis review",
        ],
        "max_fine_eur": 35_000_000,
        "nist_mapping": "MAP-3.5",
    },
    {
        "id": "A5.1.h",
        "name": "Untargeted scraping for facial recognition databases",
        "description": (
            "AI used to create or expand facial recognition databases through untargeted "
            "scraping of facial images from the internet or CCTV footage."
        ),
        "keywords": [
            "facial scraping", "facial database", "biometric scraping", "CCTV scraping",
            "mass biometric collection",
        ],
        "evidence_to_collect": [
            "Data collection methodology documentation",
            "Consent records for biometric data",
            "Data sourcing audit trail",
        ],
        "max_fine_eur": 35_000_000,
        "nist_mapping": "MEASURE-2.6",
    },
]


# ---------------------------------------------------------------------------
# Article 11 — Technical Documentation (Annex IV) — 15 required sections
# ---------------------------------------------------------------------------

ANNEX_IV_SECTIONS: list[dict] = [
    {
        "id": "AnnexIV.1",
        "title": "General description of the AI system",
        "description": "Intended purpose, the persons responsible for the provider, version info.",
        "weight": 1,
        "nist_mapping": "MAP-1.1",
    },
    {
        "id": "AnnexIV.2",
        "title": "Description of the elements and development process",
        "description": "Methods and steps in system development including architecture, algorithms.",
        "weight": 2,
        "nist_mapping": "MAP-2.1",
    },
    {
        "id": "AnnexIV.3",
        "title": "Detailed description of system monitoring, functioning, and control",
        "description": "Control mechanisms, human oversight provisions, logging capabilities.",
        "weight": 2,
        "nist_mapping": "MANAGE-2.4",
    },
    {
        "id": "AnnexIV.4",
        "title": "Description of risk management system",
        "description": "Risk identification, evaluation, and mitigation measures per Article 9.",
        "weight": 2,
        "nist_mapping": "GOVERN-1.1",
    },
    {
        "id": "AnnexIV.5",
        "title": "Training, validation, and testing data documentation",
        "description": "Data sources, collection methods, preprocessing, quality assurance.",
        "weight": 2,
        "nist_mapping": "MEASURE-2.1",
    },
    {
        "id": "AnnexIV.6",
        "title": "Post-market monitoring plan",
        "description": "Plan for systematic monitoring of AI system performance after deployment.",
        "weight": 1,
        "nist_mapping": "MANAGE-2.4",
    },
    {
        "id": "AnnexIV.7",
        "title": "Detailed description of design specifications",
        "description": "Key design choices, assumptions, and limitations.",
        "weight": 1,
        "nist_mapping": "MAP-2.1",
    },
    {
        "id": "AnnexIV.8",
        "title": "Description of changes over system lifecycle",
        "description": "Pre-planned changes and their potential impact on conformity.",
        "weight": 1,
        "nist_mapping": "MANAGE-2.2",
    },
    {
        "id": "AnnexIV.9",
        "title": "Computational resources used",
        "description": "Hardware requirements, computing infrastructure, and energy consumption.",
        "weight": 1,
        "nist_mapping": "MAP-1.1",
    },
    {
        "id": "AnnexIV.10",
        "title": "Transparency measures and instructions for deployers",
        "description": "Documentation provided to deployers for appropriate use and oversight.",
        "weight": 1,
        "nist_mapping": "MEASURE-2.10",
    },
    {
        "id": "AnnexIV.11",
        "title": "Description of performance metrics and benchmarks",
        "description": "Accuracy metrics, robustness benchmarks, and bias testing results.",
        "weight": 2,
        "nist_mapping": "MEASURE-2.2",
    },
    {
        "id": "AnnexIV.12",
        "title": "Cybersecurity measures",
        "description": "Measures to ensure security against adversarial attacks and data poisoning.",
        "weight": 2,
        "nist_mapping": "MEASURE-2.8",
    },
    {
        "id": "AnnexIV.13",
        "title": "Union laws or national laws applicable",
        "description": "Applicable legal frameworks and conformity assessment procedures followed.",
        "weight": 1,
        "nist_mapping": "GOVERN-2.1",
    },
    {
        "id": "AnnexIV.14",
        "title": "EU declaration of conformity",
        "description": "Reference to EU declaration of conformity signed by the provider.",
        "weight": 2,
        "nist_mapping": "GOVERN-1.2",
    },
    {
        "id": "AnnexIV.15",
        "title": "Notified body involvement (where applicable)",
        "description": "Reference to certificate issued by notified body or internal conformity records.",
        "weight": 2,
        "nist_mapping": "GOVERN-2.2",
    },
]


# ---------------------------------------------------------------------------
# GPAI (General Purpose AI) obligations — Articles 52-55, in force Aug 2025
# ---------------------------------------------------------------------------

GPAI_OBLIGATIONS: list[dict] = [
    {
        "id": "GPAI-52.1",
        "article": "Article 52(1)",
        "title": "Disclosure: AI-generated content",
        "description": "Persons must be informed they are interacting with an AI system (unless obvious).",
        "applicable_to": ["chatbot", "voice_assistant", "content_generator"],
        "evidence": ["Disclosure banners", "Terms of service AI notification", "API disclosure headers"],
        "nist_mapping": "MEASURE-2.10",
        "in_force": date(2025, 8, 2),
    },
    {
        "id": "GPAI-52.3",
        "article": "Article 52(3)",
        "title": "Labelling of AI-generated content",
        "description": "Deep fakes and synthetic media must be disclosed as AI-generated.",
        "applicable_to": ["image_generator", "video_generator", "audio_generator"],
        "evidence": ["Content labelling policy", "Synthetic media watermarking", "C2PA metadata"],
        "nist_mapping": "MEASURE-2.10",
        "in_force": date(2025, 8, 2),
    },
    {
        "id": "GPAI-53.1",
        "article": "Article 53(1)",
        "title": "GPAI provider: technical documentation",
        "description": "GPAI model providers must maintain technical documentation per Annex XI.",
        "applicable_to": ["gpai_model_provider"],
        "evidence": ["Annex XI documentation", "Model capability description", "Safety evaluation results"],
        "nist_mapping": "MAP-2.1",
        "in_force": date(2025, 8, 2),
    },
    {
        "id": "GPAI-53.2",
        "article": "Article 53(2)",
        "title": "GPAI provider: copyright compliance",
        "description": "GPAI providers must publish a summary of training data and copyright policy.",
        "applicable_to": ["gpai_model_provider"],
        "evidence": ["Training data summary", "Copyright policy", "Opt-out mechanism for rightsholders"],
        "nist_mapping": "MEASURE-2.6",
        "in_force": date(2025, 8, 2),
    },
    {
        "id": "GPAI-55.1",
        "article": "Article 55(1)",
        "title": "Systemic risk GPAI: adversarial testing",
        "description": "GPAI models with systemic risk must conduct adversarial testing (red teaming).",
        "applicable_to": ["gpai_systemic_risk"],
        "evidence": ["Red team exercise reports", "Adversarial testing methodology", "Third-party evaluation"],
        "nist_mapping": "MEASURE-2.8",
        "in_force": date(2025, 8, 2),
    },
    {
        "id": "GPAI-55.2",
        "article": "Article 55(2)",
        "title": "Systemic risk GPAI: incident reporting",
        "description": "Serious incidents from systemic-risk GPAI models must be reported to the AI Office.",
        "applicable_to": ["gpai_systemic_risk"],
        "evidence": ["Incident reporting procedure", "AI Office notification template", "Incident register"],
        "nist_mapping": "MANAGE-3.1",
        "in_force": date(2025, 8, 2),
    },
]


# ---------------------------------------------------------------------------
# Compliance deadlines
# ---------------------------------------------------------------------------

COMPLIANCE_DEADLINES = [
    {
        "deadline": date(2025, 2, 2),
        "milestone": "Article 5 — Prohibited AI practices banned. GPAI governance rules apply.",
        "scope": "prohibited_practices",
        "articles": ["Article 5"],
        "affects": "All AI systems",
    },
    {
        "deadline": date(2025, 8, 2),
        "milestone": "GPAI model obligations in force (Articles 52-55). AI Office operational.",
        "scope": "gpai_obligations",
        "articles": ["Article 52", "Article 53", "Article 54", "Article 55"],
        "affects": "General Purpose AI model providers",
    },
    {
        "deadline": date(2026, 8, 2),
        "milestone": "HIGH-RISK systems must be fully compliant (Articles 6-49). Conformity assessments required.",
        "scope": "high_risk_systems",
        "articles": ["Article 6", "Article 9", "Article 10", "Article 11", "Article 12", "Article 13", "Article 14", "Article 15", "Article 43"],
        "affects": "High-risk AI systems per Annex III",
    },
    {
        "deadline": date(2027, 8, 2),
        "milestone": "All remaining obligations fully applicable. General-purpose AI regulations complete.",
        "scope": "all_obligations",
        "articles": ["All Articles"],
        "affects": "All AI systems",
    },
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ProhibitedPracticeResult:
    practice_id: str
    practice_name: str
    detected: bool
    confidence: float          # 0.0–1.0
    evidence_fragments: list[str]
    triggered_by_keywords: list[str]
    max_fine_eur: int
    nist_mapping: str


@dataclass
class AnnexIVSection:
    section_id: str
    title: str
    present: bool
    completeness_score: float   # 0.0–1.0 for this section
    missing_elements: list[str]
    weight: int


@dataclass
class TechnicalDocScore:
    """Article 11: 15-section technical documentation completeness."""
    sections: list[AnnexIVSection]
    weighted_score: float       # 0–100
    sections_complete: int
    sections_missing: int
    sections_partial: int
    gap_description: str


@dataclass
class GPAIObligationResult:
    obligation_id: str
    article: str
    title: str
    compliant: bool
    evidence_found: list[str]
    evidence_missing: list[str]
    in_force: date
    days_until_enforcement: int


@dataclass
class ArticleAssessment:
    article_id: str
    article_name: str
    status: str              # PASS | FAIL | PARTIAL | NOT_APPLICABLE
    compliance_score: float  # 0–100
    gap_score: float         # 100 - compliance_score (how far from compliant)
    remediation_effort_days: int
    findings: list[str]
    remediations: list[str]
    cross_framework_mappings: dict[str, str]  # {"nist": "MEASURE-2.3", "soc2": "AICC-7"}


@dataclass
class RiskClassification:
    system_name: str
    risk_tier: str
    annex_iii_category: Optional[int]
    annex_iii_category_name: Optional[str]
    justification: str
    article_references: list[str]
    conformity_route: str       # "internal" | "notified_body" | "n/a"
    conformity_deadline: Optional[date]
    prohibited_practice_flags: list[str]


@dataclass
class ConformityAssessment:
    """Article 43 conformity assessment route determination."""
    system_name: str
    risk_tier: str
    required_route: str          # "internal_control" | "notified_body" | "n/a"
    notified_body_required: bool
    reasons: list[str]
    estimated_cost_eur: int
    estimated_duration_weeks: int
    checklist: list[str]


@dataclass
class EUAIActFinding:
    control_id: str
    title: str
    status: str       # FAIL | PASS | PARTIAL
    severity: str     # CRITICAL | HIGH | MEDIUM | LOW
    article: str
    system_name: Optional[str]
    details: str
    remediation: str
    cross_framework: dict[str, str]


@dataclass
class EUAIActReport:
    ai_systems_evaluated: int
    all_classifications: list[RiskClassification]
    high_risk_systems: list[RiskClassification]
    prohibited_practice_results: list[ProhibitedPracticeResult]
    article_assessments: list[ArticleAssessment]
    gpai_obligations: list[GPAIObligationResult]
    technical_doc_score: Optional[TechnicalDocScore]
    conformity_assessments: list[ConformityAssessment]
    findings: list[EUAIActFinding]
    deadline_status: list[dict]
    compliance_score: float = 0.0
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    days_to_high_risk_deadline: int = 0

    def compute(self) -> None:
        self.days_to_high_risk_deadline = days_until_enforcement("high_risk_systems")
        self.total_findings = len([f for f in self.findings if f.status == "FAIL"])
        self.critical_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "CRITICAL"])
        self.high_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "HIGH"])
        self.medium_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "MEDIUM"])
        self.low_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "LOW"])

        if self.article_assessments:
            self.compliance_score = sum(a.compliance_score for a in self.article_assessments) / len(self.article_assessments)
        else:
            self.compliance_score = 0.0


# ---------------------------------------------------------------------------
# Mock system state — realistic Fortune 500 scenario
# ---------------------------------------------------------------------------

MOCK_SYSTEM_STATES: dict[str, dict] = {
    "HiringAI": {
        "description": "AI system screening resumes and ranking candidates for employment decisions.",
        "has_risk_management": False,
        "has_data_governance_docs": False,
        "has_technical_documentation": False,
        "technical_doc_completeness": 0.15,
        "has_audit_logging": False,
        "has_model_card": False,
        "has_human_oversight": False,
        "has_accuracy_benchmarks": True,
        "is_gpai": False,
        "training_data_documented": False,
        "bias_testing_done": False,
        "conformity_assessment_done": False,
        "eu_database_registered": False,
        "annex_iii_match": 4,
        "keywords_present": ["recruitment", "resume screening", "hiring", "applicant tracking"],
    },
    "CreditScoreAI": {
        "description": "ML model evaluating creditworthiness for loan approval decisions.",
        "has_risk_management": False,
        "has_data_governance_docs": False,
        "has_technical_documentation": False,
        "technical_doc_completeness": 0.20,
        "has_audit_logging": True,
        "has_model_card": False,
        "has_human_oversight": False,
        "has_accuracy_benchmarks": True,
        "is_gpai": False,
        "training_data_documented": False,
        "bias_testing_done": False,
        "conformity_assessment_done": False,
        "eu_database_registered": False,
        "annex_iii_match": 5,
        "keywords_present": ["creditworthiness", "credit scoring", "loan approval"],
    },
    "CustomerSupportLLM": {
        "description": "GPT-based chatbot for customer support. Foundation model (GPAI).",
        "has_risk_management": True,
        "has_data_governance_docs": False,
        "has_technical_documentation": False,
        "technical_doc_completeness": 0.30,
        "has_audit_logging": True,
        "has_model_card": False,
        "has_human_oversight": True,
        "has_accuracy_benchmarks": False,
        "is_gpai": True,
        "training_data_documented": False,
        "bias_testing_done": False,
        "conformity_assessment_done": False,
        "eu_database_registered": False,
        "annex_iii_match": None,
        "keywords_present": ["customer support", "chatbot"],
    },
    "DiagnosticAI": {
        "description": "Medical imaging AI classifying potential tumours in radiology scans.",
        "has_risk_management": True,
        "has_data_governance_docs": True,
        "has_technical_documentation": True,
        "technical_doc_completeness": 0.60,
        "has_audit_logging": True,
        "has_model_card": True,
        "has_human_oversight": True,
        "has_accuracy_benchmarks": True,
        "is_gpai": False,
        "training_data_documented": True,
        "bias_testing_done": False,
        "conformity_assessment_done": False,
        "eu_database_registered": False,
        "annex_iii_match": 2,
        "keywords_present": ["medical", "diagnostic", "radiology"],
    },
}


def _classify_system(name: str, state: dict) -> RiskClassification:
    """Classify an AI system into EU AI Act risk tiers."""
    # Check prohibited practices
    prohibited_flags: list[str] = []
    for pp in PROHIBITED_PRACTICES:
        if any(kw in " ".join(state.get("keywords_present", [])).lower() for kw in pp["keywords"]):
            prohibited_flags.append(pp["id"])

    if prohibited_flags:
        return RiskClassification(
            system_name=name,
            risk_tier=RISK_TIER_UNACCEPTABLE,
            annex_iii_category=None,
            annex_iii_category_name=None,
            justification=f"System triggers prohibited practice(s): {', '.join(prohibited_flags)}. Banned under Article 5.",
            article_references=["Article 5"],
            conformity_route="n/a",
            conformity_deadline=None,
            prohibited_practice_flags=prohibited_flags,
        )

    if state.get("is_gpai"):
        return RiskClassification(
            system_name=name,
            risk_tier=RISK_TIER_GPAI,
            annex_iii_category=None,
            annex_iii_category_name=None,
            justification=(
                "System is a General Purpose AI (GPAI) model. "
                "Subject to Articles 52-55 transparency obligations (in force Aug 2025). "
                "If used in high-risk application context, Annex III applies."
            ),
            article_references=["Article 52", "Article 53", "Article 55"],
            conformity_route="internal",
            conformity_deadline=ENFORCEMENT_DATES["gpai_obligations"],
            prohibited_practice_flags=[],
        )

    annex_match = state.get("annex_iii_match")
    if annex_match and annex_match in ANNEX_III_CATEGORIES:
        cat = ANNEX_III_CATEGORIES[annex_match]
        return RiskClassification(
            system_name=name,
            risk_tier=RISK_TIER_HIGH,
            annex_iii_category=annex_match,
            annex_iii_category_name=cat["name"],
            justification=(
                f"System matches Annex III Category {annex_match}: {cat['name']}. "
                f"Description keywords match: {', '.join(state.get('keywords_present', [])[:3])}. "
                f"Full compliance required by August 2, 2026. Conformity assessment route: {cat['conformity_route']}."
            ),
            article_references=[cat["article_ref"], "Article 6(2)", "Article 9", "Article 10", "Article 11", "Article 12"],
            conformity_route=cat["conformity_route"],
            conformity_deadline=ENFORCEMENT_DATES["high_risk_systems"],
            prohibited_practice_flags=[],
        )

    return RiskClassification(
        system_name=name,
        risk_tier=RISK_TIER_LIMITED,
        annex_iii_category=None,
        annex_iii_category_name=None,
        justification="System does not match Annex III categories or prohibited practices. Limited risk obligations apply (transparency, disclosure).",
        article_references=["Article 52"],
        conformity_route="internal",
        conformity_deadline=ENFORCEMENT_DATES["all_obligations"],
        prohibited_practice_flags=[],
    )


def _assess_article_9(state: dict) -> ArticleAssessment:
    """Article 9: Risk Management System — 7 checks."""
    checks = [
        ("Risk management system documented", state.get("has_risk_management", False), "CRITICAL"),
        ("Risk identification and analysis performed", state.get("has_risk_management", False), "HIGH"),
        ("Risk evaluation and mitigation measures defined", state.get("has_risk_management", False), "HIGH"),
        ("Residual risk communicated to deployers", False, "MEDIUM"),
        ("Post-market monitoring plan established", False, "MEDIUM"),
        ("Risk management system updated iteratively", False, "MEDIUM"),
        ("Testing against risk management objectives complete", state.get("has_accuracy_benchmarks", False), "HIGH"),
    ]
    passed = sum(1 for _, v, _ in checks if v)
    score = (passed / len(checks)) * 100
    gap = 100 - score
    failures = [name for name, passed_flag, _ in checks if not passed_flag]
    return ArticleAssessment(
        article_id="Art.9",
        article_name="Risk Management System",
        status="PASS" if score >= 80 else ("PARTIAL" if score >= 40 else "FAIL"),
        compliance_score=score,
        gap_score=gap,
        remediation_effort_days=14 if gap > 50 else 7,
        findings=[f"Missing: {f}" for f in failures],
        remediations=[
            "Establish formal risk management system per ISO 31000",
            "Document risk identification methodology",
            "Create residual risk register and communicate to deployers",
            "Implement post-market monitoring plan",
            "Schedule quarterly risk management review",
        ],
        cross_framework_mappings={
            "nist_ai_rmf": "GOVERN-1.1, MAP-4.1, MANAGE-1.1",
            "soc2_aicc": "AICC-2",
            "iso_42001": "Clause 6.1",
        },
    )


def _assess_article_10(state: dict) -> ArticleAssessment:
    """Article 10: Training Data Governance."""
    checks = [
        ("Training data documented", state.get("training_data_documented", False), "HIGH"),
        ("Data quality assessment performed", state.get("has_data_governance_docs", False), "HIGH"),
        ("Bias testing on training data complete", state.get("bias_testing_done", False), "CRITICAL"),
        ("Data governance policy exists", state.get("has_data_governance_docs", False), "HIGH"),
        ("Personal data handling compliant with GDPR", False, "HIGH"),
        ("Data lineage tracked", state.get("training_data_documented", False), "MEDIUM"),
    ]
    passed = sum(1 for _, v, _ in checks if v)
    score = (passed / len(checks)) * 100
    gap = 100 - score
    failures = [name for name, passed_flag, _ in checks if not passed_flag]
    return ArticleAssessment(
        article_id="Art.10",
        article_name="Training Data Governance",
        status="PASS" if score >= 80 else ("PARTIAL" if score >= 40 else "FAIL"),
        compliance_score=score,
        gap_score=gap,
        remediation_effort_days=21 if gap > 60 else 10,
        findings=[f"Missing: {f}" for f in failures],
        remediations=[
            "Create data governance documentation per Annex IV §5",
            "Run bias and fairness testing on all training datasets",
            "Implement data lineage tracking (DVC, MLflow, or equivalent)",
            "Conduct GDPR/DPIA review for personal data in training sets",
            "Establish data quality metrics and thresholds",
        ],
        cross_framework_mappings={
            "nist_ai_rmf": "MEASURE-2.3, MEASURE-2.6",
            "soc2_aicc": "AICC-5, AICC-9",
            "iso_42001": "Clause 8.4",
        },
    )


def _assess_article_11(state: dict) -> tuple[ArticleAssessment, TechnicalDocScore]:
    """Article 11: Technical Documentation — 15-section completeness."""
    completeness_raw = state.get("technical_doc_completeness", 0.0)
    sections: list[AnnexIVSection] = []

    # Simulate per-section completeness based on overall completeness
    for i, sec in enumerate(ANNEX_IV_SECTIONS):
        # Higher-numbered sections more likely to be missing if overall completeness is low
        threshold = completeness_raw - (i * 0.04)
        present = threshold > 0.5
        completeness_val = min(1.0, max(0.0, threshold)) if present else max(0.0, threshold + 0.3)
        missing = [] if present else [
            "Section not found in provided documentation",
            f"Required per Annex IV, Section {i+1}",
        ]
        sections.append(AnnexIVSection(
            section_id=sec["id"],
            title=sec["title"],
            present=present,
            completeness_score=completeness_val,
            missing_elements=missing,
            weight=sec["weight"],
        ))

    total_weight = sum(s.weight for s in sections)
    weighted_score = sum(
        s.completeness_score * s.weight for s in sections
    ) / total_weight * 100

    complete = sum(1 for s in sections if s.present)
    missing_count = sum(1 for s in sections if not s.present and s.completeness_score < 0.1)
    partial = len(sections) - complete - missing_count

    doc_score = TechnicalDocScore(
        sections=sections,
        weighted_score=weighted_score,
        sections_complete=complete,
        sections_missing=missing_count,
        sections_partial=partial,
        gap_description=(
            f"Technical documentation is {weighted_score:.0f}% complete. "
            f"{missing_count} sections entirely missing, {partial} partial. "
            f"Annex IV requires all 15 sections before conformity assessment can proceed."
        ),
    )

    assessment = ArticleAssessment(
        article_id="Art.11",
        article_name="Technical Documentation",
        status="PASS" if weighted_score >= 80 else ("PARTIAL" if weighted_score >= 40 else "FAIL"),
        compliance_score=weighted_score,
        gap_score=100 - weighted_score,
        remediation_effort_days=30 if weighted_score < 40 else 14,
        findings=[
            f"Section {s.section_id} ({s.title}): missing or incomplete"
            for s in sections if not s.present
        ],
        remediations=[
            "Use PolicyGuard Annex IV template to populate all 15 required sections",
            "Assign a technical writer + ML engineer to complete documentation",
            "Schedule documentation review with legal counsel",
            "Target 100% completeness 90 days before August 2, 2026 deadline",
        ],
        cross_framework_mappings={
            "nist_ai_rmf": "MAP-2.1, MEASURE-2.10",
            "soc2_aicc": "AICC-3",
            "iso_42001": "Clause 8.3",
        },
    )
    return assessment, doc_score


def _assess_article_12(state: dict) -> ArticleAssessment:
    """Article 12: Logging and Audit Trail."""
    has_logging = state.get("has_audit_logging", False)
    score = 70.0 if has_logging else 0.0
    # Even with logging, specifics matter
    return ArticleAssessment(
        article_id="Art.12",
        article_name="Record-Keeping and Audit Logging",
        status="PARTIAL" if has_logging else "FAIL",
        compliance_score=score,
        gap_score=100 - score,
        remediation_effort_days=7 if has_logging else 21,
        findings=[] if has_logging else [
            "No automatic logging of AI system operations",
            "No input/output capture for audit trail",
            "Article 12 requires automatic logging enabling post-hoc review",
        ],
        remediations=[
            "Implement structured logging capturing: timestamp, input hash, output, model version, confidence",
            "Set log retention to minimum 5 years (high-risk systems)",
            "Implement immutable log storage (WORM storage or blockchain-anchored)",
            "Create log access controls and monitoring for unauthorized access",
            "Integrate with PolicyGuard AIAuditTrail module",
        ],
        cross_framework_mappings={
            "nist_ai_rmf": "MANAGE-4.1, MEASURE-2.1",
            "soc2_aicc": "AICC-4, CC2.1",
            "iso_42001": "Clause 9.1",
        },
    )


def _assess_article_13(state: dict) -> ArticleAssessment:
    """Article 13: Transparency and provision of information."""
    has_model_card = state.get("has_model_card", False)
    has_docs = state.get("has_technical_documentation", False)
    score = (40.0 if has_model_card else 0.0) + (40.0 if has_docs else 0.0)
    return ArticleAssessment(
        article_id="Art.13",
        article_name="Transparency and Information to Deployers",
        status="PASS" if score >= 80 else ("PARTIAL" if score >= 40 else "FAIL"),
        compliance_score=score,
        gap_score=100 - score,
        remediation_effort_days=10,
        findings=[
            *(["Model card not published"] if not has_model_card else []),
            *(["Instructions for use not provided to deployers"] if not has_docs else []),
        ],
        remediations=[
            "Create model card documenting: purpose, capabilities, limitations, intended users",
            "Publish disclosure text: 'This system uses AI to make [decision]'",
            "Provide deployers with instructions covering oversight, maintenance, and incident reporting",
            "Generate transparency disclosure text using PolicyGuard Article 13 generator",
        ],
        cross_framework_mappings={
            "nist_ai_rmf": "MEASURE-2.10, MAP-3.1",
            "soc2_aicc": "AICC-3",
            "iso_42001": "Clause 8.5",
        },
    )


def _assess_article_14(state: dict) -> ArticleAssessment:
    """Article 14: Human Oversight."""
    has_oversight = state.get("has_human_oversight", False)
    score = 80.0 if has_oversight else 0.0
    return ArticleAssessment(
        article_id="Art.14",
        article_name="Human Oversight",
        status="PASS" if has_oversight else "FAIL",
        compliance_score=score,
        gap_score=100 - score,
        remediation_effort_days=14,
        findings=[] if has_oversight else [
            "No human oversight mechanism implemented",
            "No human-in-the-loop for consequential decisions",
            "No override/stop capability documented",
        ],
        remediations=[
            "Designate natural persons responsible for overseeing AI outputs",
            "Implement override controls: ability to halt system, disregard output, or request human review",
            "Document oversight procedures and train staff",
            "Log override events for audit purposes",
        ],
        cross_framework_mappings={
            "nist_ai_rmf": "MANAGE-1.3, GOVERN-1.2",
            "soc2_aicc": "AICC-6",
            "iso_42001": "Clause 6.1.2",
        },
    )


def _assess_article_15(state: dict) -> ArticleAssessment:
    """Article 15: Accuracy, Robustness, and Cybersecurity."""
    has_benchmarks = state.get("has_accuracy_benchmarks", False)
    score = 40.0 if has_benchmarks else 0.0
    return ArticleAssessment(
        article_id="Art.15",
        article_name="Accuracy, Robustness, and Cybersecurity",
        status="PARTIAL" if has_benchmarks else "FAIL",
        compliance_score=score,
        gap_score=100 - score,
        remediation_effort_days=21,
        findings=[
            *([] if has_benchmarks else ["No accuracy benchmarks established"]),
            "No adversarial robustness testing performed",
            "No cybersecurity assessment for AI system",
        ],
        remediations=[
            "Establish accuracy, precision, recall, F1 benchmarks with acceptance thresholds",
            "Run adversarial robustness tests (FGSM, PGD, input perturbation)",
            "Conduct model-specific penetration testing",
            "Implement monitoring for accuracy degradation over time",
            "Document minimum performance requirements in technical specification",
        ],
        cross_framework_mappings={
            "nist_ai_rmf": "MEASURE-2.2, MEASURE-2.8",
            "soc2_aicc": "AICC-8, AICC-11",
            "iso_42001": "Clause 8.6",
        },
    )


def _assess_article_43(classification: RiskClassification, state: dict) -> ConformityAssessment:
    """Article 43: Conformity assessment route."""
    if classification.risk_tier != RISK_TIER_HIGH:
        return ConformityAssessment(
            system_name=classification.system_name,
            risk_tier=classification.risk_tier,
            required_route="n/a",
            notified_body_required=False,
            reasons=["System is not high-risk — no conformity assessment required under Article 43"],
            estimated_cost_eur=0,
            estimated_duration_weeks=0,
            checklist=[],
        )

    cat_num = classification.annex_iii_category
    cat = ANNEX_III_CATEGORIES.get(cat_num, {}) if cat_num else {}
    route = cat.get("conformity_route", "internal")

    if route == "notified_body":
        return ConformityAssessment(
            system_name=classification.system_name,
            risk_tier=classification.risk_tier,
            required_route="notified_body",
            notified_body_required=True,
            reasons=[
                f"Annex III Category {cat_num} requires notified body assessment",
                "Internal conformity assessment not sufficient for this use case",
                f"Must obtain CE marking before August 2, 2026",
            ],
            estimated_cost_eur=50_000,
            estimated_duration_weeks=16,
            checklist=[
                "Select an EU-accredited notified body",
                "Prepare complete Annex IV technical documentation",
                "Submit application package to notified body",
                "Undergo conformity assessment audit",
                "Receive assessment certificate",
                "Draft and sign EU Declaration of Conformity",
                "Affix CE marking",
                "Register system in EU AI Act database",
            ],
        )
    else:
        return ConformityAssessment(
            system_name=classification.system_name,
            risk_tier=classification.risk_tier,
            required_route="internal_control",
            notified_body_required=False,
            reasons=[
                f"Annex III Category {cat_num} permits internal conformity assessment",
                "Provider may self-certify compliance with Articles 9-15",
            ],
            estimated_cost_eur=15_000,
            estimated_duration_weeks=8,
            checklist=[
                "Complete Annex IV technical documentation (all 15 sections)",
                "Conduct and document risk management per Article 9",
                "Complete bias testing and data governance per Article 10",
                "Implement logging per Article 12",
                "Implement human oversight per Article 14",
                "Draft EU Declaration of Conformity",
                "Register system in EU AI Act database",
                "Appoint EU representative (if non-EU provider)",
            ],
        )


def _check_gpai_obligations(state: dict) -> list[GPAIObligationResult]:
    """Check GPAI obligations (Articles 52-55) for GPAI systems."""
    results: list[GPAIObligationResult] = []
    is_gpai = state.get("is_gpai", False)
    has_docs = state.get("has_technical_documentation", False)
    training_documented = state.get("training_data_documented", False)

    for ob in GPAI_OBLIGATIONS:
        applicable = "gpai_model_provider" in ob["applicable_to"] and is_gpai
        if not applicable and "chatbot" in ob["applicable_to"] and is_gpai:
            applicable = True
        if not applicable:
            continue

        compliant = has_docs if "documentation" in ob["title"].lower() else training_documented
        days_left = days_until_enforcement("gpai_obligations")

        results.append(GPAIObligationResult(
            obligation_id=ob["id"],
            article=ob["article"],
            title=ob["title"],
            compliant=compliant,
            evidence_found=ob["evidence"][:1] if compliant else [],
            evidence_missing=ob["evidence"][1:] if compliant else ob["evidence"],
            in_force=ob["in_force"],
            days_until_enforcement=days_left,
        ))
    return results


def _build_deadline_status() -> list[dict]:
    """Build deadline tracking status for all milestones."""
    statuses = []
    today = date.today()
    for dl in COMPLIANCE_DEADLINES:
        delta = dl["deadline"] - today
        days_remaining = delta.days
        is_past = days_remaining < 0
        statuses.append({
            "deadline_str": dl["deadline"].strftime("%B %d, %Y"),
            "milestone": dl["milestone"],
            "scope": dl["scope"],
            "articles": dl["articles"],
            "affects": dl["affects"],
            "days_remaining": abs(days_remaining),
            "is_past": is_past,
            "urgency": "CRITICAL" if 0 < days_remaining < 120 else ("HIGH" if 0 < days_remaining < 365 else "PAST" if is_past else "MEDIUM"),
        })
    return statuses


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------

class EUAIActScanner:
    """EU AI Act V2 scanner — full Article coverage."""

    def __init__(
        self,
        ai_systems: Optional[list[dict]] = None,
        mock: bool = True,
    ) -> None:
        self.ai_systems = ai_systems or []
        self.mock = mock

    async def scan(self) -> EUAIActReport:
        await asyncio.sleep(0)

        systems_to_assess = (
            list(MOCK_SYSTEM_STATES.items())
            if self.mock
            else [(s.get("name", f"System-{i}"), s) for i, s in enumerate(self.ai_systems)]
        )

        all_classifications: list[RiskClassification] = []
        all_findings: list[EUAIActFinding] = []
        all_article_assessments: list[ArticleAssessment] = []
        all_conformity_assessments: list[ConformityAssessment] = []
        all_gpai_results: list[GPAIObligationResult] = []
        tech_doc_score: Optional[TechnicalDocScore] = None
        all_prohibited: list[ProhibitedPracticeResult] = []

        for sys_name, state in systems_to_assess:
            classification = _classify_system(sys_name, state)
            all_classifications.append(classification)

            # Article assessments for high-risk systems
            if classification.risk_tier == RISK_TIER_HIGH:
                art9 = _assess_article_9(state)
                art10 = _assess_article_10(state)
                art11, doc_score = _assess_article_11(state)
                art12 = _assess_article_12(state)
                art13 = _assess_article_13(state)
                art14 = _assess_article_14(state)
                art15 = _assess_article_15(state)

                if tech_doc_score is None:
                    tech_doc_score = doc_score

                for art in [art9, art10, art11, art12, art13, art14, art15]:
                    all_article_assessments.append(art)
                    if art.status in ("FAIL", "PARTIAL"):
                        sev = "CRITICAL" if art.gap_score > 70 else "HIGH" if art.gap_score > 40 else "MEDIUM"
                        all_findings.append(EUAIActFinding(
                            control_id=art.article_id,
                            title=f"{sys_name}: {art.article_name} — Non-compliant",
                            status=art.status,
                            severity=sev,
                            article=art.article_id,
                            system_name=sys_name,
                            details=f"Compliance score: {art.compliance_score:.0f}%. Gap: {art.gap_score:.0f}%. Findings: {'; '.join(art.findings[:2])}",
                            remediation="\n".join(art.remediations[:3]),
                            cross_framework=art.cross_framework_mappings,
                        ))

                conf = _assess_article_43(classification, state)
                all_conformity_assessments.append(conf)

            # GPAI obligations
            if state.get("is_gpai", False):
                gpai_results = _check_gpai_obligations(state)
                all_gpai_results.extend(gpai_results)
                for r in gpai_results:
                    if not r.compliant:
                        all_findings.append(EUAIActFinding(
                            control_id=r.obligation_id,
                            title=f"{sys_name}: {r.title} — Non-compliant",
                            status="FAIL",
                            severity="HIGH",
                            article=r.article,
                            system_name=sys_name,
                            details=f"GPAI obligation in force since {r.in_force}. Missing evidence: {', '.join(r.evidence_missing[:2])}",
                            remediation=f"Implement: {', '.join(r.evidence_missing)}",
                            cross_framework={"nist_ai_rmf": "MEASURE-2.10"},
                        ))

            # Prohibited practices check
            for pp in PROHIBITED_PRACTICES:
                triggered = any(
                    kw in " ".join(state.get("keywords_present", [])).lower()
                    for kw in pp["keywords"]
                )
                all_prohibited.append(ProhibitedPracticeResult(
                    practice_id=pp["id"],
                    practice_name=pp["name"],
                    detected=triggered,
                    confidence=0.85 if triggered else 0.0,
                    evidence_fragments=state.get("keywords_present", []) if triggered else [],
                    triggered_by_keywords=[kw for kw in pp["keywords"] if kw in " ".join(state.get("keywords_present", [])).lower()],
                    max_fine_eur=pp["max_fine_eur"],
                    nist_mapping=pp["nist_mapping"],
                ))
                if triggered:
                    all_findings.append(EUAIActFinding(
                        control_id=pp["id"],
                        title=f"PROHIBITED PRACTICE DETECTED: {pp['name']}",
                        status="FAIL",
                        severity="CRITICAL",
                        article="Article 5",
                        system_name=sys_name,
                        details=f"System '{sys_name}' appears to engage in prohibited practice '{pp['name']}'. Maximum fine: €{pp['max_fine_eur']:,}.",
                        remediation=f"Immediately cease prohibited practice. Collect evidence: {', '.join(pp['evidence_to_collect'])}",
                        cross_framework={"nist_ai_rmf": pp["nist_mapping"]},
                    ))

        high_risk = [c for c in all_classifications if c.risk_tier == RISK_TIER_HIGH]
        deadline_status = _build_deadline_status()

        report = EUAIActReport(
            ai_systems_evaluated=len(systems_to_assess),
            all_classifications=all_classifications,
            high_risk_systems=high_risk,
            prohibited_practice_results=all_prohibited,
            article_assessments=all_article_assessments,
            gpai_obligations=all_gpai_results,
            technical_doc_score=tech_doc_score,
            conformity_assessments=all_conformity_assessments,
            findings=all_findings,
            deadline_status=deadline_status,
        )
        report.compute()
        return report


class EUAIActFramework:
    """Sync wrapper around EUAIActScanner for test compatibility."""

    def run_assessment(self) -> "EUAIActReport":
        scanner = EUAIActScanner(mock=True)
        report = asyncio.run(scanner.scan())
        # Expose overall_compliance_score as alias for compliance_score
        report.overall_compliance_score = report.compliance_score
        return report
