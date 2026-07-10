"""
incident_manager.py — AI Incident Management for EU AI Act Article 73 compliance.

NEW in V2. Classifies, tracks, and responds to AI system incidents with
automated playbooks and Article 73 report generation.

Incident classification (P0 → P3 severity):
- P0-SAFETY:          Output caused or could cause physical harm
- P0-DISCRIMINATION:  Protected class disparate impact detected
- P1-ACCURACY:        Model accuracy degraded beyond threshold
- P1-INTEGRITY:       Hash chain tamper detected
- P2-PERFORMANCE:     Latency/throughput SLA breach
- P3-COST:            Token spend exceeded budget

EU AI Act Article 73: Serious incidents (P0) must be reported to the national
market surveillance authority within a deadline TIERED by incident type (see
ARTICLE_73_REPORTING_HOURS in eu_ai_act.py) — not a flat window. The severity
-> tier mapping below is an engineering approximation, not legal advice;
verify against the primary source and qualified counsel before relying on it.

Stdlib only — zero mandatory dependencies.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional

from ai_audit_trail.chain import AuditChain
from ai_audit_trail.eu_ai_act import Article73Report, ARTICLE_73_REPORTING_HOURS


# ---------------------------------------------------------------------------
# Incident classification
# ---------------------------------------------------------------------------

class IncidentSeverity(str, Enum):
    P0_SAFETY = "P0-SAFETY"
    P0_DISCRIMINATION = "P0-DISCRIMINATION"
    P1_ACCURACY = "P1-ACCURACY"
    P1_INTEGRITY = "P1-INTEGRITY"
    P2_PERFORMANCE = "P2-PERFORMANCE"
    P3_COST = "P3-COST"


class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


_SEVERITY_REQUIRES_ARTICLE_73 = {
    IncidentSeverity.P0_SAFETY,
    IncidentSeverity.P0_DISCRIMINATION,
}

# Best-effort mapping from our internal severity taxonomy to an Article 73
# incident-type tier (see ARTICLE_73_REPORTING_HOURS). P0-SAFETY may involve
# physical/health harm -> the faster tier; P0-DISCRIMINATION is treated as a
# potential widespread fundamental-rights infringement -> the faster tier.
# Everything else required falls back to the "default" (slowest) tier.
_SEVERITY_TO_ARTICLE_73_TIER = {
    IncidentSeverity.P0_SAFETY: "serious_harm_or_widespread_infringement",
    IncidentSeverity.P0_DISCRIMINATION: "serious_harm_or_widespread_infringement",
}


def _article_73_deadline_hours(severity: "IncidentSeverity") -> int:
    tier = _SEVERITY_TO_ARTICLE_73_TIER.get(severity, "default")
    return ARTICLE_73_REPORTING_HOURS.get(tier, ARTICLE_73_REPORTING_HOURS["default"])

_SEVERITY_ORDER = {
    IncidentSeverity.P0_SAFETY: 0,
    IncidentSeverity.P0_DISCRIMINATION: 1,
    IncidentSeverity.P1_ACCURACY: 2,
    IncidentSeverity.P1_INTEGRITY: 3,
    IncidentSeverity.P2_PERFORMANCE: 4,
    IncidentSeverity.P3_COST: 5,
}


# ---------------------------------------------------------------------------
# Playbooks
# ---------------------------------------------------------------------------

_PLAYBOOKS: dict[IncidentSeverity, list[str]] = {
    IncidentSeverity.P0_SAFETY: [
        "IMMEDIATE: Halt AI system output for affected use case",
        "IMMEDIATE: Notify safety officer and legal counsel",
        "NOTIFY EU Article 73: File incident report to national authority per the "
        "tiered deadline on this incident record (see article_73_deadline)",
        "INVESTIGATE: Identify affected outputs from audit trail",
        "REMEDIATE: Human review of all impacted decisions",
        "VALIDATE: Retrain or rollback model before re-enabling",
        "POST-MORTEM: Update risk assessment (Article 9)",
    ],
    IncidentSeverity.P0_DISCRIMINATION: [
        "IMMEDIATE: Throttle output for affected demographic segment",
        "IMMEDIATE: Activate human review queue for pending decisions",
        "NOTIFY EU Article 73: File incident report per the tiered deadline on "
        "this incident record (see article_73_deadline)",
        "INVESTIGATE: Run disparate impact analysis (80% rule) across audit log",
        "REMEDIATE: Suspend automated decision-making for affected group",
        "VALIDATE: Bias testing before re-enabling (per Article 10.2)",
        "DOCUMENT: Update Annex IV technical documentation with bias test results",
    ],
    IncidentSeverity.P1_ACCURACY: [
        "ALERT: Notify ML engineering team",
        "INVESTIGATE: Compare accuracy metrics against baseline audit log window",
        "REMEDIATE: Route affected decisions to human review",
        "VALIDATE: A/B test candidate fix before full rollout",
        "MONITOR: Watch error rate over next 24h after remediation",
    ],
    IncidentSeverity.P1_INTEGRITY: [
        "CRITICAL: Pause all log writes to prevent further corruption",
        "INVESTIGATE: Run verify_chain() to identify tampered entries",
        "PRESERVE: Export current chain state as evidence",
        "NOTIFY: Inform legal and compliance teams — regulatory impact likely",
        "RECOVER: Restore from last verified checkpoint if backup available",
        "DOCUMENT: Article 73 report may be required (review with counsel)",
    ],
    IncidentSeverity.P2_PERFORMANCE: [
        "ALERT: Notify infrastructure and ML ops teams",
        "INVESTIGATE: Identify latency spike source (model, network, DB)",
        "REMEDIATE: Scale compute or fallback to faster model tier",
        "MONITOR: Track p50/p95 latency in dashboard for 2 hours",
    ],
    IncidentSeverity.P3_COST: [
        "ALERT: Notify team lead and product owner",
        "INVESTIGATE: Identify token usage spike by session/model in audit log",
        "REMEDIATE: Implement request throttling or model downgrade",
        "REVIEW: Update cost budget thresholds if justified",
    ],
}


# ---------------------------------------------------------------------------
# Incident dataclass
# ---------------------------------------------------------------------------

@dataclass
class AIIncident:
    """A single AI system incident record."""
    incident_id: str
    system_id: str
    system_name: str
    severity: IncidentSeverity
    status: IncidentStatus
    title: str
    description: str
    detected_at: str
    detected_by: str              # "automated" | "human" | "user_report"
    evidence_entry_ids: list[str]
    affected_persons_estimate: int
    playbook_steps: list[str]
    article_73_required: bool
    article_73_deadline: Optional[str]  # ISO 8601 UTC, detected_at + tiered Article 73 hours
    resolved_at: Optional[str] = None
    resolution_notes: str = ""
    mttr_minutes: Optional[float] = None  # Mean time to resolution
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.article_73_required = self.severity in _SEVERITY_REQUIRES_ARTICLE_73
        if self.article_73_required and not self.article_73_deadline:
            detected = datetime.fromisoformat(self.detected_at)
            deadline = detected + timedelta(hours=_article_73_deadline_hours(self.severity))
            self.article_73_deadline = deadline.isoformat()

    @property
    def hours_until_article_73_deadline(self) -> Optional[float]:
        if not self.article_73_deadline:
            return None
        deadline = datetime.fromisoformat(self.article_73_deadline)
        now = datetime.now(timezone.utc)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return (deadline - now).total_seconds() / 3600.0

    @property
    def is_overdue_article_73(self) -> bool:
        hrs = self.hours_until_article_73_deadline
        return hrs is not None and hrs < 0 and self.status != IncidentStatus.CLOSED

    def to_dict(self) -> dict[str, Any]:
        d = {
            "incident_id": self.incident_id,
            "system_id": self.system_id,
            "system_name": self.system_name,
            "severity": self.severity.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "detected_at": self.detected_at,
            "detected_by": self.detected_by,
            "evidence_entry_ids": self.evidence_entry_ids,
            "affected_persons_estimate": self.affected_persons_estimate,
            "article_73_required": self.article_73_required,
            "article_73_deadline": self.article_73_deadline,
            "resolved_at": self.resolved_at,
            "mttr_minutes": self.mttr_minutes,
        }
        return d

    def generate_article_73_report(self, provider_name: str = "[Organization]") -> Article73Report:
        """Generate EU AI Act Article 73 serious incident report for submission."""
        return Article73Report(
            incident_id=self.incident_id,
            system_id=self.system_id,
            system_name=self.system_name,
            incident_type=self.severity.value,
            detected_at=self.detected_at,
            reporting_deadline=self.article_73_deadline or "",
            hours_remaining=self.hours_until_article_73_deadline or 0.0,
            description=self.description,
            affected_persons_estimate=self.affected_persons_estimate,
            severity=self.severity.value,
            evidence_entry_ids=self.evidence_entry_ids,
            immediate_actions_taken=self.playbook_steps[:3],  # First 3 steps as immediate actions
            provider_name=provider_name,
        )


# ---------------------------------------------------------------------------
# Incident Manager
# ---------------------------------------------------------------------------

class IncidentManager:
    """
    Manages AI system incidents with automated detection, classification,
    playbook execution, and Article 73 report generation.

    Usage::

        im = IncidentManager()
        incident = im.create_incident(
            system_id="loan-approval-v2",
            system_name="AcmeBank Loan Approval AI",
            severity=IncidentSeverity.P0_DISCRIMINATION,
            title="Disparate impact detected in Q3 approval rates",
            description="Approval rate for zip codes 30xxx is 0.61 vs baseline 1.0",
            evidence_entry_ids=["entry-uuid-1", ...],
            affected_persons_estimate=1250,
        )
        report = incident.generate_article_73_report()
        print(report.to_markdown())
    """

    def __init__(self) -> None:
        self._incidents: dict[str, AIIncident] = {}

    def create_incident(
        self,
        system_id: str,
        system_name: str,
        severity: IncidentSeverity,
        title: str,
        description: str,
        evidence_entry_ids: list[str] | None = None,
        affected_persons_estimate: int = 0,
        detected_by: str = "automated",
        tags: list[str] | None = None,
    ) -> AIIncident:
        """Create and register a new incident."""
        incident_id = str(uuid.uuid4())
        incident = AIIncident(
            incident_id=incident_id,
            system_id=system_id,
            system_name=system_name,
            severity=severity,
            status=IncidentStatus.OPEN,
            title=title,
            description=description,
            detected_at=datetime.now(timezone.utc).isoformat(),
            detected_by=detected_by,
            evidence_entry_ids=evidence_entry_ids or [],
            affected_persons_estimate=affected_persons_estimate,
            playbook_steps=_PLAYBOOKS.get(severity, []),
            article_73_required=False,  # set by __post_init__
            article_73_deadline=None,   # set by __post_init__
            tags=tags or [],
        )
        # Trigger __post_init__ to compute article_73 fields
        # (already called by dataclass, but we need to re-trigger after assignment)
        object.__setattr__(incident, "article_73_required",
                           severity in _SEVERITY_REQUIRES_ARTICLE_73)
        if incident.article_73_required:
            detected = datetime.fromisoformat(incident.detected_at)
            deadline = detected + timedelta(hours=_article_73_deadline_hours(severity))
            object.__setattr__(incident, "article_73_deadline", deadline.isoformat())

        self._incidents[incident_id] = incident
        return incident

    def resolve_incident(
        self,
        incident_id: str,
        resolution_notes: str = "",
    ) -> Optional[AIIncident]:
        """Mark an incident as resolved and compute MTTR."""
        incident = self._incidents.get(incident_id)
        if not incident:
            return None

        now = datetime.now(timezone.utc)
        object.__setattr__(incident, "resolved_at", now.isoformat())
        object.__setattr__(incident, "status", IncidentStatus.RESOLVED)
        object.__setattr__(incident, "resolution_notes", resolution_notes)

        detected = datetime.fromisoformat(incident.detected_at)
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=timezone.utc)
        mttr_minutes = (now - detected).total_seconds() / 60.0
        object.__setattr__(incident, "mttr_minutes", round(mttr_minutes, 1))

        return incident

    def get_open_incidents(self, severity_filter: list[IncidentSeverity] | None = None) -> list[AIIncident]:
        """Return open incidents, optionally filtered by severity."""
        incidents = [
            i for i in self._incidents.values()
            if i.status in (IncidentStatus.OPEN, IncidentStatus.INVESTIGATING)
        ]
        if severity_filter:
            incidents = [i for i in incidents if i.severity in severity_filter]
        return sorted(incidents, key=lambda x: _SEVERITY_ORDER.get(x.severity, 99))

    def get_article_73_pending(self) -> list[AIIncident]:
        """Return P0 incidents requiring Article 73 submission."""
        return [
            i for i in self._incidents.values()
            if i.article_73_required and i.status != IncidentStatus.CLOSED
        ]

    def summary(self) -> dict[str, Any]:
        """Return incident summary statistics."""
        all_incidents = list(self._incidents.values())
        open_incidents = self.get_open_incidents()
        p0_incidents = [i for i in all_incidents if "P0" in i.severity.value]
        overdue = [i for i in all_incidents if i.is_overdue_article_73]

        resolved = [i for i in all_incidents if i.mttr_minutes is not None]
        avg_mttr = (
            sum(i.mttr_minutes for i in resolved) / len(resolved)  # type: ignore[arg-type]
            if resolved else None
        )

        by_severity: dict[str, int] = {}
        for i in all_incidents:
            by_severity[i.severity.value] = by_severity.get(i.severity.value, 0) + 1

        return {
            "total": len(all_incidents),
            "open": len(open_incidents),
            "p0_critical": len(p0_incidents),
            "article_73_pending": len(self.get_article_73_pending()),
            "article_73_overdue": len(overdue),
            "avg_mttr_minutes": round(avg_mttr, 1) if avg_mttr else None,
            "by_severity": by_severity,
        }

    def detect_from_chain(
        self,
        chain: AuditChain,
        system_id: str,
        system_name: str,
    ) -> list[AIIncident]:
        """
        Auto-detect incidents from audit log patterns and create incident records.
        Wraps eu_ai_act.detect_article_73_incidents() with full incident creation.
        """
        from ai_audit_trail.eu_ai_act import detect_article_73_incidents
        raw_incidents = detect_article_73_incidents(chain, system_id)

        created: list[AIIncident] = []
        for raw in raw_incidents:
            severity_map = {
                "P0-SAFETY": IncidentSeverity.P0_SAFETY,
                "P0-DISCRIMINATION": IncidentSeverity.P0_DISCRIMINATION,
                "P1-ACCURACY": IncidentSeverity.P1_ACCURACY,
                "P1-INTEGRITY": IncidentSeverity.P1_INTEGRITY,
                "P2-PERFORMANCE": IncidentSeverity.P2_PERFORMANCE,
                "P3-COST": IncidentSeverity.P3_COST,
            }
            severity_str = raw.get("severity", "P2-PERFORMANCE")
            severity = severity_map.get(severity_str, IncidentSeverity.P2_PERFORMANCE)

            incident = self.create_incident(
                system_id=system_id,
                system_name=system_name,
                severity=severity,
                title=f"Auto-detected: {severity_str}",
                description=raw.get("description", "Automated detection"),
                evidence_entry_ids=raw.get("evidence_entry_ids", []),
                affected_persons_estimate=raw.get("affected_persons_estimate", 0),
                detected_by="automated",
                tags=["auto-detected"],
            )
            created.append(incident)

        return created
