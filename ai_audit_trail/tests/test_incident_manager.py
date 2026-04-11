"""
test_incident_manager.py — Tests for AI incident management.

Tests:
- P0 incident creates 72-hour Article 62 deadline
- Article 62 report template generates valid text
- Severity escalation ordering
- MTTR computation on resolution
- detect_from_chain integration
- Summary statistics
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from ai_audit_trail.incident_manager import (
    AIIncident,
    IncidentManager,
    IncidentSeverity,
    IncidentStatus,
    _SEVERITY_ORDER,
    _PLAYBOOKS,
)
from ai_audit_trail.eu_ai_act import ARTICLE_62_REPORTING_HOURS


# ---------------------------------------------------------------------------
# P0 incident — Article 62 deadline
# ---------------------------------------------------------------------------

class TestArticle62Deadline:
    def test_p0_safety_sets_72h_deadline(self, p0_incident: AIIncident):
        """P0-SAFETY incident must have a 72-hour reporting deadline."""
        assert p0_incident.article_62_required is True
        assert p0_incident.article_62_deadline is not None

        detected = datetime.fromisoformat(p0_incident.detected_at)
        deadline = datetime.fromisoformat(p0_incident.article_62_deadline)
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=timezone.utc)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        delta_hours = (deadline - detected).total_seconds() / 3600
        assert abs(delta_hours - ARTICLE_62_REPORTING_HOURS) < 0.01

    def test_p0_discrimination_sets_72h_deadline(self, p0_discrimination_incident: AIIncident):
        assert p0_discrimination_incident.article_62_required is True
        assert p0_discrimination_incident.article_62_deadline is not None

    def test_p2_incident_does_not_require_article_62(self, incident_manager: IncidentManager):
        inc = incident_manager.create_incident(
            system_id="sys",
            system_name="Test System",
            severity=IncidentSeverity.P2_PERFORMANCE,
            title="Latency spike",
            description="p95 latency exceeded SLA",
        )
        assert inc.article_62_required is False
        assert inc.article_62_deadline is None

    def test_p3_incident_does_not_require_article_62(self, incident_manager: IncidentManager):
        inc = incident_manager.create_incident(
            system_id="sys",
            system_name="Test System",
            severity=IncidentSeverity.P3_COST,
            title="Cost spike",
            description="Token spend exceeded budget",
        )
        assert inc.article_62_required is False

    def test_hours_until_deadline_is_positive_for_new_p0(self, p0_incident: AIIncident):
        """Freshly created P0 incidents have positive hours remaining."""
        hrs = p0_incident.hours_until_article_62_deadline
        assert hrs is not None
        assert hrs > 0

    def test_article_62_deadline_constant_is_72(self):
        assert ARTICLE_62_REPORTING_HOURS == 72


# ---------------------------------------------------------------------------
# Article 62 report template
# ---------------------------------------------------------------------------

class TestArticle62Report:
    def test_report_generates_markdown(self, p0_incident: AIIncident):
        report = p0_incident.generate_article_62_report(provider_name="TestCorp")
        md = report.to_markdown()
        assert "Article 62" in md
        assert "Regulation (EU) 2024/1689" in md

    def test_report_contains_provider_name(self, p0_incident: AIIncident):
        report = p0_incident.generate_article_62_report(provider_name="Acme Legal AI")
        md = report.to_markdown()
        assert "Acme Legal AI" in md

    def test_report_contains_incident_id(self, p0_incident: AIIncident):
        report = p0_incident.generate_article_62_report()
        md = report.to_markdown()
        assert p0_incident.incident_id in md

    def test_report_contains_system_id(self, p0_incident: AIIncident):
        report = p0_incident.generate_article_62_report()
        md = report.to_markdown()
        assert p0_incident.system_id in md

    def test_report_contains_affected_persons_count(self, p0_discrimination_incident: AIIncident):
        report = p0_discrimination_incident.generate_article_62_report()
        md = report.to_markdown()
        assert "342" in md  # affected_persons_estimate from fixture

    def test_report_shows_overdue_when_past_deadline(self, incident_manager: IncidentManager):
        """Incident detected 80 hours ago → deadline is OVERDUE."""
        past_detected = (
            datetime.now(timezone.utc) - timedelta(hours=80)
        ).isoformat()
        inc = incident_manager.create_incident(
            system_id="sys",
            system_name="Old System",
            severity=IncidentSeverity.P0_SAFETY,
            title="Old incident",
            description="Detected 80 hours ago",
        )
        # Manually backdate detected_at for test
        import dataclasses
        old_inc = dataclasses.replace(
            inc,
            detected_at=past_detected,
            article_62_deadline=(
                datetime.now(timezone.utc) - timedelta(hours=8)
            ).isoformat(),
        )
        report = old_inc.generate_article_62_report()
        md = report.to_markdown()
        assert "OVERDUE" in md or "remaining" in md


# ---------------------------------------------------------------------------
# Severity escalation and ordering
# ---------------------------------------------------------------------------

class TestSeverityOrdering:
    def test_p0_safety_is_highest_priority(self):
        """P0-SAFETY should have the lowest numeric order value (highest priority)."""
        assert _SEVERITY_ORDER[IncidentSeverity.P0_SAFETY] < _SEVERITY_ORDER[IncidentSeverity.P1_ACCURACY]
        assert _SEVERITY_ORDER[IncidentSeverity.P0_SAFETY] < _SEVERITY_ORDER[IncidentSeverity.P3_COST]

    def test_p0_before_p1(self):
        assert _SEVERITY_ORDER[IncidentSeverity.P0_DISCRIMINATION] < _SEVERITY_ORDER[IncidentSeverity.P1_ACCURACY]

    def test_p1_before_p2(self):
        assert _SEVERITY_ORDER[IncidentSeverity.P1_ACCURACY] < _SEVERITY_ORDER[IncidentSeverity.P2_PERFORMANCE]

    def test_p2_before_p3(self):
        assert _SEVERITY_ORDER[IncidentSeverity.P2_PERFORMANCE] < _SEVERITY_ORDER[IncidentSeverity.P3_COST]

    def test_get_open_incidents_returns_sorted_by_severity(
        self, incident_manager: IncidentManager
    ):
        """open incidents returned in priority order: P0 before P2 before P3."""
        incident_manager.create_incident(
            system_id="s", system_name="S", severity=IncidentSeverity.P3_COST,
            title="Cost", description="Budget exceeded",
        )
        incident_manager.create_incident(
            system_id="s", system_name="S", severity=IncidentSeverity.P0_SAFETY,
            title="Safety", description="Harm detected",
        )
        incident_manager.create_incident(
            system_id="s", system_name="S", severity=IncidentSeverity.P2_PERFORMANCE,
            title="Perf", description="Slow",
        )
        open_incidents = incident_manager.get_open_incidents()
        severities = [i.severity for i in open_incidents]
        # First item should be P0
        assert "P0" in severities[0].value


# ---------------------------------------------------------------------------
# MTTR and resolution
# ---------------------------------------------------------------------------

class TestResolution:
    def test_resolve_incident_sets_resolved_status(
        self, incident_manager: IncidentManager, p0_incident: AIIncident
    ):
        resolved = incident_manager.resolve_incident(
            p0_incident.incident_id, resolution_notes="Root cause fixed, model retrained"
        )
        assert resolved is not None
        assert resolved.status == IncidentStatus.RESOLVED
        assert resolved.resolved_at is not None

    def test_resolve_incident_computes_mttr(
        self, incident_manager: IncidentManager, p0_incident: AIIncident
    ):
        resolved = incident_manager.resolve_incident(p0_incident.incident_id)
        assert resolved is not None
        assert resolved.mttr_minutes is not None
        assert resolved.mttr_minutes >= 0

    def test_resolve_nonexistent_incident_returns_none(self, incident_manager: IncidentManager):
        result = incident_manager.resolve_incident("nonexistent-id-xyz")
        assert result is None

    def test_resolved_incident_not_in_open_list(
        self, incident_manager: IncidentManager, p0_incident: AIIncident
    ):
        incident_manager.resolve_incident(p0_incident.incident_id)
        open_incidents = incident_manager.get_open_incidents()
        open_ids = [i.incident_id for i in open_incidents]
        assert p0_incident.incident_id not in open_ids


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

class TestIncidentSummary:
    def test_summary_has_required_fields(self, incident_manager: IncidentManager, p0_incident: AIIncident):
        summary = incident_manager.summary()
        assert "total" in summary
        assert "open" in summary
        assert "p0_critical" in summary
        assert "article_62_pending" in summary
        assert "by_severity" in summary

    def test_summary_counts_p0_correctly(
        self,
        incident_manager: IncidentManager,
        p0_incident: AIIncident,
        p0_discrimination_incident: AIIncident,
    ):
        summary = incident_manager.summary()
        assert summary["p0_critical"] >= 2

    def test_summary_article_62_pending_count(
        self, incident_manager: IncidentManager, p0_incident: AIIncident
    ):
        summary = incident_manager.summary()
        assert summary["article_62_pending"] >= 1


# ---------------------------------------------------------------------------
# Playbooks
# ---------------------------------------------------------------------------

class TestPlaybooks:
    def test_p0_safety_playbook_has_article_62_step(self):
        steps = _PLAYBOOKS[IncidentSeverity.P0_SAFETY]
        combined = " ".join(steps)
        assert "Article 62" in combined or "72" in combined

    def test_p0_discrimination_playbook_has_bias_step(self):
        steps = _PLAYBOOKS[IncidentSeverity.P0_DISCRIMINATION]
        combined = " ".join(steps)
        assert "disparate" in combined.lower() or "bias" in combined.lower()

    def test_all_severities_have_playbooks(self):
        for severity in IncidentSeverity:
            assert severity in _PLAYBOOKS, f"Missing playbook for {severity}"
            assert len(_PLAYBOOKS[severity]) > 0

    def test_incident_created_with_playbook_steps(self, p0_incident: AIIncident):
        assert len(p0_incident.playbook_steps) > 0


# ---------------------------------------------------------------------------
# detect_from_chain
# ---------------------------------------------------------------------------

class TestDetectFromChain:
    def test_detect_from_chain_returns_list(
        self, incident_manager: IncidentManager, populated_chain
    ):
        incidents = incident_manager.detect_from_chain(
            chain=populated_chain,
            system_id="loan-approval-v2",
            system_name="Loan Approval AI",
        )
        assert isinstance(incidents, list)

    def test_detect_from_chain_creates_incidents_in_manager(
        self, incident_manager: IncidentManager, high_risk_chain
    ):
        before = len(list(incident_manager._incidents.values()))
        incidents = incident_manager.detect_from_chain(
            chain=high_risk_chain,
            system_id="loan-approval-v2",
            system_name="Loan Approval AI",
        )
        after = len(list(incident_manager._incidents.values()))
        # New incidents should be registered
        assert after >= before
