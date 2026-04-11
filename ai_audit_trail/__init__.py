"""
AIAuditTrail V2 — Immutable AI decision logging for EU AI Act compliance.

EU AI Act enforcement for HIGH-RISK AI systems: August 2, 2026.
IBM OpenPages: $500K/yr. Credo AI: $180K/yr. This: $0.

V2 additions:
- SHA-256 Merkle tree (O(log n) proof verification)
- Article 62 serious incident detection + 72h reporting
- NIST AI RMF 1.0 dual-framework mapping (GOVERN/MAP/MEASURE/MANAGE)
- Incident manager with P0-P3 severity classification
- FastAPI REST API (api.py) with OpenAPI docs
- Rich terminal dashboard (dashboard.py)
- 5 SDK integrations: Anthropic, OpenAI, LangChain, LlamaIndex, CrewAI

Core usage::

    from ai_audit_trail import AuditChain, DecisionType, RiskTier
    from ai_audit_trail.decorators import audit_llm_call

    chain = AuditChain("audit.db")

    @audit_llm_call(chain=chain, decision_type=DecisionType.CLASSIFICATION,
                    risk_tier=RiskTier.HIGH, system_id="loan-review-v3")
    def my_llm_function(prompt: str) -> str:
        return call_your_llm(prompt)

Drop-in integrations::

    # Anthropic
    from ai_audit_trail.integrations.anthropic_sdk import AuditedAnthropic
    client = AuditedAnthropic(audit_chain=chain, system_id="my-system")

    # OpenAI
    from ai_audit_trail.integrations.openai_sdk import AuditedOpenAI
    client = AuditedOpenAI(audit_chain=chain, system_id="my-system")

    # LangChain
    from ai_audit_trail.integrations.langchain import AuditTrailCallback
    callback = AuditTrailCallback(audit_chain=chain, system_id="my-system")

    # LlamaIndex
    from ai_audit_trail.integrations.llamaindex import AuditTrailLlamaIndexCallback
    callback = AuditTrailLlamaIndexCallback(audit_chain=chain)

    # CrewAI
    from ai_audit_trail.integrations.crewai import AuditTrailCrewCallback
    callback = AuditTrailCrewCallback(audit_chain=chain, crew_name="my-crew")

Incident management::

    from ai_audit_trail import IncidentManager, IncidentSeverity
    mgr = IncidentManager(chain)
    incidents = mgr.detect_from_chain(chain, "loan-v3", "Loan AI")

NIST AI RMF::

    from ai_audit_trail import assess_nist_rmf
    assessment = assess_nist_rmf(chain, system_id="loan-v3", system_name="Loan AI")
    print(assessment.overall_score)  # 1.0-5.0

Run the demo::

    python -m ai_audit_trail.demo

Start the API server::

    uvicorn ai_audit_trail.api:app --port 8000

Start the dashboard::

    python -m ai_audit_trail.dashboard audit.db
"""

from ai_audit_trail.chain import AuditChain, DecisionType, LogEntry, RiskTier, TamperReport, MerkleTree
from ai_audit_trail.config import settings
from ai_audit_trail.decorators import AuditContext, audit_llm_call
from ai_audit_trail.eu_ai_act import (
    Article12Check,
    Article62Report,
    GPAIComplianceCheck,
    check_article_12_compliance,
    classify_risk_tier,
    days_until_enforcement,
    detect_article_62_incidents,
    enforcement_status,
    generate_article_11_technical_doc,
    generate_article_13_transparency_report,
    check_gpai_obligations,
)
from ai_audit_trail.incident_manager import (
    AIIncident,
    IncidentManager,
    IncidentSeverity,
)
from ai_audit_trail.nist_rmf import (
    RMFAssessment,
    assess_nist_rmf,
)
from ai_audit_trail.query import QueryEngine
from ai_audit_trail.reporter import AuditReport, ReportGenerator

__version__ = "2.0.0"
__author__ = "Hunter Spence"

__all__ = [
    # Core chain
    "AuditChain",
    "LogEntry",
    "DecisionType",
    "RiskTier",
    "TamperReport",
    "MerkleTree",
    # Config
    "settings",
    # Decorators
    "audit_llm_call",
    "AuditContext",
    # EU AI Act
    "classify_risk_tier",
    "check_article_12_compliance",
    "Article12Check",
    "Article62Report",
    "GPAIComplianceCheck",
    "generate_article_13_transparency_report",
    "generate_article_11_technical_doc",
    "days_until_enforcement",
    "enforcement_status",
    "detect_article_62_incidents",
    "check_gpai_obligations",
    # Incident management
    "AIIncident",
    "IncidentManager",
    "IncidentSeverity",
    # NIST AI RMF
    "RMFAssessment",
    "assess_nist_rmf",
    # Query
    "QueryEngine",
    # Reports
    "ReportGenerator",
    "AuditReport",
]
