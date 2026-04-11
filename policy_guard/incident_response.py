"""
PolicyGuard — AI Incident Response Playbook
===========================================
V2: Automated AI incident classification, response triggers, and reporting.

Severity tiers:
  P0 — Safety-critical: immediate model rollback + regulatory notification
  P1 — Bias/discrimination: output throttling + human review queue
  P2 — Accuracy degradation: investigation trigger + enhanced monitoring
  P3 — Performance degradation: monitoring alert + SLA review

Alignments:
  - NIST AI RMF: RESPOND function (MANAGE-1.2, MANAGE-3.1)
  - EU AI Act: Article 62 (serious incident reporting)
  - SOC2: AICC-12 (AI incident response)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Incident severity classification
# ---------------------------------------------------------------------------

class IncidentSeverity:
    P0 = "P0"  # Safety-critical — immediate halt required
    P1 = "P1"  # Bias/discrimination — output throttling
    P2 = "P2"  # Accuracy degradation — investigation
    P3 = "P3"  # Performance — monitoring/SLA


SEVERITY_DEFINITIONS: dict[str, dict] = {
    IncidentSeverity.P0: {
        "name": "Safety-Critical",
        "description": "AI system producing outputs that cause or could cause physical harm, unlawful discrimination, or violate EU AI Act Article 5 prohibited practices.",
        "examples": [
            "Medical AI recommending dangerous dosage",
            "Safety system producing false negatives for critical alerts",
            "Prohibited practice detected in production",
            "AI system used in manner inconsistent with approved use case",
        ],
        "max_response_time_minutes": 15,
        "requires_rollback": True,
        "requires_regulatory_notification": True,
        "eu_ai_act_article": "Article 62 — Serious incident reporting",
        "nist_mapping": "MANAGE-1.2",
        "soc2_mapping": "AICC-12",
        "regulatory_notification_hours": 72,
    },
    IncidentSeverity.P1: {
        "name": "Bias / Discrimination",
        "description": "AI system demonstrating systematic bias against protected groups, violating fairness thresholds, or producing discriminatory outputs.",
        "examples": [
            "Demographic parity difference > 0.10 detected in production",
            "Disparate impact ratio drops below 0.70",
            "Protected characteristic correlation detected in outputs",
            "User complaint alleging discriminatory AI decision",
        ],
        "max_response_time_minutes": 60,
        "requires_rollback": False,
        "requires_regulatory_notification": False,
        "eu_ai_act_article": "Article 10 — Training data and bias",
        "nist_mapping": "MANAGE-1.3",
        "soc2_mapping": "AICC-7",
        "regulatory_notification_hours": None,
    },
    IncidentSeverity.P2: {
        "name": "Accuracy Degradation",
        "description": "AI system accuracy, precision, or recall has degraded below defined acceptance thresholds. May indicate model drift, data pipeline issues, or adversarial interference.",
        "examples": [
            "Model accuracy drops > 5% from baseline",
            "Prediction confidence scores systematically low",
            "Out-of-distribution inputs detected at high volume",
            "Model outputs showing unexpected distribution shift",
        ],
        "max_response_time_minutes": 240,
        "requires_rollback": False,
        "requires_regulatory_notification": False,
        "eu_ai_act_article": "Article 15 — Accuracy and robustness",
        "nist_mapping": "MANAGE-2.4",
        "soc2_mapping": "AICC-9",
        "regulatory_notification_hours": None,
    },
    IncidentSeverity.P3: {
        "name": "Performance Degradation",
        "description": "AI system experiencing latency, throughput, or availability issues without direct accuracy or fairness impact.",
        "examples": [
            "Inference latency > 2x baseline",
            "API error rate > 1%",
            "Model serving pod crashes and restarts",
            "Feature pipeline delays causing stale inputs",
        ],
        "max_response_time_minutes": 480,
        "requires_rollback": False,
        "requires_regulatory_notification": False,
        "eu_ai_act_article": None,
        "nist_mapping": "MANAGE-2.4",
        "soc2_mapping": "CC7.1",
        "regulatory_notification_hours": None,
    },
}


# ---------------------------------------------------------------------------
# Response playbooks
# ---------------------------------------------------------------------------

RESPONSE_PLAYBOOKS: dict[str, list[dict]] = {
    IncidentSeverity.P0: [
        {
            "step": 1,
            "action": "IMMEDIATE: Halt AI system outputs",
            "owner": "On-call ML Engineer",
            "timeframe": "T+0 to T+15min",
            "details": "Route all AI decisions to human reviewers. Disable automated decision-making. Activate fallback rule-based system if available.",
            "automated": True,
        },
        {
            "step": 2,
            "action": "Page CISO, CTO, and Legal",
            "owner": "On-call Incident Commander",
            "timeframe": "T+5min",
            "details": "Activate P0 incident bridge call. Include CISO, CTO, General Counsel, and AI governance lead.",
            "automated": True,
        },
        {
            "step": 3,
            "action": "Rollback to last known-good model version",
            "owner": "ML Platform Team",
            "timeframe": "T+15min",
            "details": "Identify last clean model checkpoint. Execute rollback via MLOps pipeline. Validate rollback with smoke tests before re-enabling.",
            "automated": False,
        },
        {
            "step": 4,
            "action": "Preserve all evidence for regulatory investigation",
            "owner": "Legal + ML Engineering",
            "timeframe": "T+30min",
            "details": "Archive: input logs, output logs, model version, feature pipeline state, deployment configuration at time of incident.",
            "automated": False,
        },
        {
            "step": 5,
            "action": "Draft Article 62 serious incident notification",
            "owner": "Legal + Compliance",
            "timeframe": "T+24h",
            "details": "EU AI Act Article 62 requires notification to national supervisory authority within 72 hours. Use PolicyGuard Article 62 template.",
            "automated": False,
        },
        {
            "step": 6,
            "action": "Root cause analysis and remediation plan",
            "owner": "AI Governance Team",
            "timeframe": "T+7 days",
            "details": "Full RCA including: timeline reconstruction, contributing factors, technical root cause, control failures, and remediation roadmap.",
            "automated": False,
        },
        {
            "step": 7,
            "action": "Post-incident review and policy update",
            "owner": "CISO + AI Governance",
            "timeframe": "T+30 days",
            "details": "Update AI risk management policy, add new controls to prevent recurrence, update risk register.",
            "automated": False,
        },
    ],
    IncidentSeverity.P1: [
        {
            "step": 1,
            "action": "Throttle AI outputs — route borderline decisions to human queue",
            "owner": "ML Platform Team",
            "timeframe": "T+0 to T+60min",
            "details": "Reduce AI system confidence threshold. Decisions with confidence < 0.85 route to human review queue. Do not halt system.",
            "automated": True,
        },
        {
            "step": 2,
            "action": "Notify AI Governance Lead and Privacy Counsel",
            "owner": "On-call Engineer",
            "timeframe": "T+30min",
            "details": "Bias incident may constitute EU AI Act Article 10 violation. Loop in privacy counsel for potential GDPR implications.",
            "automated": True,
        },
        {
            "step": 3,
            "action": "Run full bias detection suite",
            "owner": "Data Science Team",
            "timeframe": "T+2h",
            "details": "Execute PolicyGuard BiasDetector across all protected attributes. Document demographic parity, equalized odds, disparate impact results.",
            "automated": False,
        },
        {
            "step": 4,
            "action": "Investigate root cause — identify bias source",
            "owner": "ML Engineering",
            "timeframe": "T+24h",
            "details": "Analyze: training data distribution shifts, model drift, feature proxy issues, recent model changes. Use SHAP analysis.",
            "automated": False,
        },
        {
            "step": 5,
            "action": "Implement bias mitigation and re-validate",
            "owner": "ML Engineering + Legal",
            "timeframe": "T+7 days",
            "details": "Apply calibrated threshold adjustment or resampling. Re-run full bias test suite. Obtain legal sign-off before re-enabling automated decisions.",
            "automated": False,
        },
        {
            "step": 6,
            "action": "Document incident for regulatory inquiries",
            "owner": "Legal + Compliance",
            "timeframe": "T+14 days",
            "details": "Prepare incident report documenting: detection, scope, root cause, remediation, validation. Retain for minimum 5 years.",
            "automated": False,
        },
    ],
    IncidentSeverity.P2: [
        {
            "step": 1,
            "action": "Enable enhanced monitoring — increase sampling frequency",
            "owner": "ML Platform Team",
            "timeframe": "T+0 to T+4h",
            "details": "Increase output sampling from 5% to 100% for manual quality review. Enable detailed logging.",
            "automated": True,
        },
        {
            "step": 2,
            "action": "Investigate accuracy degradation source",
            "owner": "Data Science Team",
            "timeframe": "T+4h",
            "details": "Check: input data distribution drift, feature pipeline integrity, model serving infrastructure, recent deployment changes.",
            "automated": False,
        },
        {
            "step": 3,
            "action": "Evaluate impact and determine if rollback is warranted",
            "owner": "AI Governance + Product",
            "timeframe": "T+8h",
            "details": "Quantify business and regulatory impact of degraded performance. Determine if accuracy breach triggers Article 15 concern.",
            "automated": False,
        },
        {
            "step": 4,
            "action": "Remediate and re-validate performance",
            "owner": "ML Engineering",
            "timeframe": "T+48h",
            "details": "Retrain/fine-tune model if needed. Validate against acceptance thresholds before restoring normal operation.",
            "automated": False,
        },
    ],
    IncidentSeverity.P3: [
        {
            "step": 1,
            "action": "Alert on-call team and begin investigation",
            "owner": "Platform Engineer",
            "timeframe": "T+0 to T+8h",
            "details": "Check infrastructure metrics: CPU, memory, GPU utilization, network latency, pod health.",
            "automated": True,
        },
        {
            "step": 2,
            "action": "Scale infrastructure or implement caching",
            "owner": "Platform Engineering",
            "timeframe": "T+2h",
            "details": "Scale model serving infrastructure. Check for runaway processes. Review recent infrastructure changes.",
            "automated": False,
        },
        {
            "step": 3,
            "action": "Validate SLA compliance and communicate to stakeholders",
            "owner": "Product Manager",
            "timeframe": "T+4h",
            "details": "Assess SLA breach status. Notify affected stakeholders if SLA thresholds exceeded.",
            "automated": False,
        },
    ],
}


# ---------------------------------------------------------------------------
# Article 62 notification template
# ---------------------------------------------------------------------------

def generate_article_62_notification(
    incident_id: str,
    system_name: str,
    incident_summary: str,
    affected_persons_estimate: int,
    provider_name: str = "[ORGANIZATION NAME]",
    country: str = "[MEMBER STATE]",
    detected_at: Optional[datetime] = None,
) -> str:
    """Generate EU AI Act Article 62 serious incident notification template."""
    if detected_at is None:
        detected_at = datetime.utcnow()

    return f"""
EU AI ACT — SERIOUS INCIDENT NOTIFICATION
Article 62, Regulation (EU) 2024/1689
==========================================

NOTIFICATION REF: {incident_id}
DATE OF NOTIFICATION: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
INCIDENT DETECTED: {detected_at.strftime('%Y-%m-%d %H:%M UTC')}
NOTIFYING AUTHORITY: National supervisory authority of {country}

--- SECTION 1: PROVIDER INFORMATION ---
Provider Name: {provider_name}
AI System Name: {system_name}
EU Database Registration Number: [PENDING / NUMBER]
EU Representative (if applicable): [NAME AND CONTACT]
Contact for this notification: [NAME, EMAIL, PHONE]

--- SECTION 2: INCIDENT DESCRIPTION ---
Incident Reference: {incident_id}
Severity Classification: P0 — Safety-Critical / Serious Incident (Article 62)

Brief Description:
{incident_summary}

Estimated Number of Persons Affected: {affected_persons_estimate:,}
Geographic Scope: [MEMBER STATES AFFECTED]
Affected Use Case: [DESCRIBE AI SYSTEM FUNCTION AND DEPLOYMENT CONTEXT]

--- SECTION 3: TIMELINE ---
T+0:   Incident detected via [monitoring system / user report]
T+15m: AI system outputs halted; on-call team engaged
T+1h:  Initial investigation begun; legal counsel notified
T+24h: Preliminary root cause assessment
T+72h: This notification filed with supervisory authority

--- SECTION 4: IMMEDIATE ACTIONS TAKEN ---
[ ] AI system outputs halted or routed to human review
[ ] Model rollback executed to version: [VERSION]
[ ] Evidence preserved for regulatory review
[ ] Affected individuals to be notified (if required)
[ ] Internal investigation initiated

--- SECTION 5: RISK AND HARM ASSESSMENT ---
Nature of Harm: [DESCRIBE ACTUAL OR POTENTIAL HARM]
Causal Link to AI System: [DESCRIBE HOW AI SYSTEM CAUSED OR CONTRIBUTED TO HARM]
Vulnerability Exploited: [KNOWN / UNKNOWN]

--- SECTION 6: CORRECTIVE MEASURES ---
Immediate Measures: [DESCRIBE WHAT WAS DONE TO STOP HARM]
Investigation Plan: [ROOT CAUSE ANALYSIS TIMELINE]
Preventive Measures: [WHAT WILL BE DONE TO PREVENT RECURRENCE]
Estimated Timeline for Full Resolution: [DAYS]

--- SECTION 7: FOLLOW-UP COMMITMENT ---
The provider commits to submitting a follow-up report with full root cause analysis
and corrective action plan within 30 days of this notification.

Signed: ___________________________
Name: [RESPONSIBLE PERSON]
Title: [CISO / DPO / LEGAL COUNSEL]
Date: {datetime.utcnow().strftime('%Y-%m-%d')}

--- PolicyGuard Auto-Generated Template ---
Generated by PolicyGuard v2.0 | EU AI Act Article 62 Compliance Module
Complete and have qualified legal counsel review before filing.
""".strip()


# ---------------------------------------------------------------------------
# Incident data models
# ---------------------------------------------------------------------------

@dataclass
class AIIncident:
    incident_id: str
    system_name: str
    detected_at: datetime
    severity: str
    title: str
    description: str
    triggered_by: str  # "monitoring_alert" | "user_report" | "audit" | "manual"
    metrics_at_detection: dict


@dataclass
class IncidentResponse:
    incident: AIIncident
    severity_definition: dict
    playbook_steps: list[dict]
    article_62_required: bool
    article_62_notification: Optional[str]
    timeline_reconstruction: list[dict]
    nist_rmf_function: str  # RESPOND
    estimated_resolution_hours: int


@dataclass
class IncidentReport:
    incidents: list[AIIncident]
    responses: list[IncidentResponse]
    p0_count: int
    p1_count: int
    p2_count: int
    p3_count: int
    total_incidents: int
    regulatory_notifications_required: int


# ---------------------------------------------------------------------------
# Incident classifier
# ---------------------------------------------------------------------------

class IncidentClassifier:
    """Classify AI incidents and generate response playbooks."""

    @staticmethod
    def classify(
        system_name: str,
        description: str,
        metrics: Optional[dict] = None,
    ) -> str:
        """
        Classify an incident based on description keywords and metrics.
        Returns severity string (P0, P1, P2, P3).
        """
        desc_lower = description.lower()
        metrics = metrics or {}

        # P0 triggers
        p0_keywords = [
            "safety", "physical harm", "prohibited", "banned practice",
            "medical decision", "life-threatening", "illegal", "regulatory breach",
        ]
        if any(kw in desc_lower for kw in p0_keywords):
            return IncidentSeverity.P0

        # P1 triggers
        p1_keywords = [
            "bias", "discrimination", "disparate", "fairness", "demographic",
            "protected attribute", "disparate impact", "equalized odds",
        ]
        demographic_parity_diff = metrics.get("demographic_parity_diff", 0)
        if any(kw in desc_lower for kw in p1_keywords) or demographic_parity_diff > 0.10:
            return IncidentSeverity.P1

        # P2 triggers
        p2_keywords = [
            "accuracy", "degradation", "drift", "performance drop", "f1 score",
            "precision", "recall", "out-of-distribution",
        ]
        accuracy_drop = metrics.get("accuracy_drop_pct", 0)
        if any(kw in desc_lower for kw in p2_keywords) or accuracy_drop > 5:
            return IncidentSeverity.P2

        return IncidentSeverity.P3

    @staticmethod
    def generate_response(
        incident: AIIncident,
        affected_persons_estimate: int = 0,
        provider_name: str = "[ORGANIZATION]",
    ) -> IncidentResponse:
        """Generate full incident response playbook for a classified incident."""
        sev_def = SEVERITY_DEFINITIONS[incident.severity]
        playbook = RESPONSE_PLAYBOOKS[incident.severity]

        # Article 62 notification required for P0
        article_62 = None
        if incident.severity == IncidentSeverity.P0:
            article_62 = generate_article_62_notification(
                incident_id=incident.incident_id,
                system_name=incident.system_name,
                incident_summary=incident.description,
                affected_persons_estimate=affected_persons_estimate,
                provider_name=provider_name,
                detected_at=incident.detected_at,
            )

        # Timeline reconstruction
        base_time = incident.detected_at
        timeline = []
        for step in playbook:
            timeline.append({
                "step": step["step"],
                "action": step["action"],
                "owner": step["owner"],
                "target_time": step["timeframe"],
                "status": "PENDING",
            })

        est_hours = {
            IncidentSeverity.P0: 168,   # 1 week full resolution
            IncidentSeverity.P1: 120,   # 5 days
            IncidentSeverity.P2: 48,    # 2 days
            IncidentSeverity.P3: 8,     # 8 hours
        }.get(incident.severity, 24)

        return IncidentResponse(
            incident=incident,
            severity_definition=sev_def,
            playbook_steps=playbook,
            article_62_required=incident.severity == IncidentSeverity.P0,
            article_62_notification=article_62,
            timeline_reconstruction=timeline,
            nist_rmf_function="RESPOND — MANAGE-1.2, MANAGE-3.1",
            estimated_resolution_hours=est_hours,
        )


# ---------------------------------------------------------------------------
# Demo incident scenarios
# ---------------------------------------------------------------------------

DEMO_INCIDENTS: list[dict] = [
    {
        "system_name": "HiringAI",
        "title": "Demographic parity violation detected in production",
        "description": "Bias monitoring alert: demographic parity difference for 'race' attribute spiked to 0.17 over the past 24 hours. Female candidates approved at 41% vs male at 73%.",
        "triggered_by": "monitoring_alert",
        "severity": "P1",
        "metrics": {
            "demographic_parity_diff": 0.17,
            "disparate_impact_ratio": 0.56,
            "accuracy_drop_pct": 0,
        },
    },
    {
        "system_name": "DiagnosticAI",
        "title": "Critical: Medical AI recommending incorrect dosage ranges",
        "description": "User reports indicate AI diagnostic system recommended dosage 3x safe threshold for pediatric patients. Safety-critical incident. Physical harm potential.",
        "triggered_by": "user_report",
        "severity": "P0",
        "metrics": {
            "safety_critical": True,
            "affected_patients": 47,
        },
    },
    {
        "system_name": "CreditScoreAI",
        "title": "Accuracy degradation: model drift detected post Q1 data",
        "description": "Model monitoring detected precision drop from 0.88 to 0.71 following Q1 economic data update. Out-of-distribution inputs increasing at 23% daily rate.",
        "triggered_by": "monitoring_alert",
        "severity": "P2",
        "metrics": {
            "accuracy_drop_pct": 17,
            "precision_current": 0.71,
            "precision_baseline": 0.88,
        },
    },
]


class IncidentResponseEngine:
    """Generate and manage AI incident responses."""

    def run_demo(self) -> IncidentReport:
        """Run demo incident response scenarios."""
        incidents: list[AIIncident] = []
        responses: list[IncidentResponse] = []

        for i, demo in enumerate(DEMO_INCIDENTS):
            severity = IncidentClassifier.classify(
                system_name=demo["system_name"],
                description=demo["description"],
                metrics=demo.get("metrics", {}),
            )

            incident_id = f"INC-2026-{1001 + i:04d}"
            incident = AIIncident(
                incident_id=incident_id,
                system_name=demo["system_name"],
                detected_at=datetime.utcnow() - timedelta(hours=i * 3),
                severity=severity,
                title=demo["title"],
                description=demo["description"],
                triggered_by=demo["triggered_by"],
                metrics_at_detection=demo.get("metrics", {}),
            )
            incidents.append(incident)

            response = IncidentClassifier.generate_response(
                incident=incident,
                affected_persons_estimate=demo.get("metrics", {}).get("affected_patients", 1200),
            )
            responses.append(response)

        return IncidentReport(
            incidents=incidents,
            responses=responses,
            p0_count=sum(1 for i in incidents if i.severity == IncidentSeverity.P0),
            p1_count=sum(1 for i in incidents if i.severity == IncidentSeverity.P1),
            p2_count=sum(1 for i in incidents if i.severity == IncidentSeverity.P2),
            p3_count=sum(1 for i in incidents if i.severity == IncidentSeverity.P3),
            total_incidents=len(incidents),
            regulatory_notifications_required=sum(
                1 for r in responses if r.article_62_required
            ),
        )
