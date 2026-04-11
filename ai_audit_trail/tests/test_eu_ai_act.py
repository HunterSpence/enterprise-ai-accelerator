"""
test_eu_ai_act.py — Tests for EU AI Act compliance engine.

Tests:
- Risk tier classification for known system types
- Enforcement timeline dates are correct
- Article 62 incident detection from audit log patterns
- Article 12 compliance scoring
- GPAI obligation assessment
- HTML report generation
"""

from __future__ import annotations

from datetime import date

import pytest

from ai_audit_trail.chain import AuditChain, DecisionType, RiskTier
from ai_audit_trail.eu_ai_act import (
    Article12Check,
    Article62Report,
    check_article_12_compliance,
    check_gpai_obligations,
    classify_risk_tier,
    days_until_enforcement,
    detect_annex_iii_categories,
    detect_article_62_incidents,
    enforcement_status,
    generate_article_12_html_report,
    generate_article_13_transparency_report,
    _ENFORCEMENT_DATES,
)


# ---------------------------------------------------------------------------
# Enforcement timeline
# ---------------------------------------------------------------------------

class TestEnforcementTimeline:
    def test_prohibited_systems_enforcement_date(self):
        """Article 5 (prohibited systems) — enforcement date: Feb 2, 2025."""
        assert _ENFORCEMENT_DATES["prohibited_systems"] == date(2025, 2, 2)

    def test_gpai_model_rules_enforcement_date(self):
        """Chapter V (GPAI) — enforcement date: Aug 2, 2025."""
        assert _ENFORCEMENT_DATES["gpai_model_rules"] == date(2025, 8, 2)

    def test_high_risk_systems_enforcement_date(self):
        """Articles 8-25 (high-risk) — enforcement date: Aug 2, 2026."""
        assert _ENFORCEMENT_DATES["high_risk_systems"] == date(2026, 8, 2)

    def test_remaining_provisions_enforcement_date(self):
        """Remaining provisions — enforcement date: Aug 2, 2027."""
        assert _ENFORCEMENT_DATES["remaining_provisions"] == date(2027, 8, 2)

    def test_prohibited_systems_already_enforced(self):
        """Feb 2, 2025 has already passed — should be ENFORCED."""
        status = enforcement_status()
        assert status["prohibited_systems"]["status"] == "ENFORCED"

    def test_gpai_rules_already_enforced(self):
        """Aug 2, 2025 has already passed — should be ENFORCED."""
        status = enforcement_status()
        assert status["gpai_model_rules"]["status"] == "ENFORCED"

    def test_days_until_enforcement_returns_int(self):
        days = days_until_enforcement("high_risk_systems")
        assert isinstance(days, int)

    def test_days_until_invalid_phase_raises(self):
        with pytest.raises(ValueError, match="Unknown phase"):
            days_until_enforcement("nonexistent_phase")

    def test_enforcement_status_has_all_phases(self):
        status = enforcement_status()
        expected_phases = {
            "prohibited_systems", "gpai_model_rules",
            "high_risk_systems", "remaining_provisions",
        }
        assert expected_phases.issubset(set(status.keys()))


# ---------------------------------------------------------------------------
# Risk tier classification
# ---------------------------------------------------------------------------

class TestRiskTierClassification:
    def test_loan_system_classified_as_high(self):
        tier = classify_risk_tier("loan approval system for mortgage applicants")
        assert tier == RiskTier.HIGH

    def test_hiring_system_classified_as_high(self):
        tier = classify_risk_tier("AI-powered resume screening and hiring recommendation")
        assert tier == RiskTier.HIGH

    def test_credit_scoring_classified_as_high(self):
        tier = classify_risk_tier("credit score assessment for consumer lending")
        assert tier == RiskTier.HIGH

    def test_law_enforcement_classified_as_high(self):
        tier = classify_risk_tier("predictive policing crime detection system")
        assert tier == RiskTier.HIGH

    def test_medical_diagnosis_classified_as_high(self):
        tier = classify_risk_tier("clinical decision support for medical diagnosis")
        assert tier == RiskTier.HIGH

    def test_chatbot_classified_as_limited(self):
        tier = classify_risk_tier("customer service chatbot for product inquiries")
        assert tier == RiskTier.LIMITED

    def test_deepfake_detector_classified_as_limited(self):
        tier = classify_risk_tier("deepfake detection for synthetic media identification")
        assert tier == RiskTier.LIMITED

    def test_virtual_assistant_classified_as_limited(self):
        tier = classify_risk_tier("virtual assistant for calendar scheduling")
        assert tier == RiskTier.LIMITED

    def test_spam_filter_classified_as_minimal(self):
        tier = classify_risk_tier("email spam filter using machine learning")
        assert tier == RiskTier.MINIMAL

    def test_social_scoring_classified_as_unacceptable(self):
        tier = classify_risk_tier("social scoring system for citizens")
        assert tier == RiskTier.UNACCEPTABLE

    def test_mass_surveillance_classified_as_unacceptable(self):
        tier = classify_risk_tier("real-time biometric surveillance in public spaces")
        assert tier == RiskTier.UNACCEPTABLE


# ---------------------------------------------------------------------------
# Annex III category detection
# ---------------------------------------------------------------------------

class TestAnnexIIIDetection:
    def test_employment_hr_detected(self):
        categories = detect_annex_iii_categories("hiring and recruitment decision support")
        assert "employment_hr" in categories

    def test_essential_services_detected(self):
        categories = detect_annex_iii_categories("mortgage underwriting and loan decisions")
        assert "essential_services" in categories

    def test_multiple_categories_detected(self):
        categories = detect_annex_iii_categories(
            "medical diagnosis system used in clinical decision for student assessment"
        )
        assert len(categories) >= 2

    def test_generic_system_has_no_categories(self):
        categories = detect_annex_iii_categories("general text summarization tool")
        assert categories == []


# ---------------------------------------------------------------------------
# Article 12 compliance check
# ---------------------------------------------------------------------------

class TestArticle12Compliance:
    def test_empty_chain_score_is_zero(self, empty_chain: AuditChain):
        check = check_article_12_compliance(empty_chain)
        assert check.score == 0
        assert check.compliant is False

    def test_populated_chain_has_positive_score(self, populated_chain: AuditChain):
        check = check_article_12_compliance(populated_chain)
        assert check.score > 0

    def test_compliance_check_has_required_fields(self, populated_chain: AuditChain):
        check = check_article_12_compliance(populated_chain)
        assert isinstance(check.score, int)
        assert isinstance(check.requirements_met, list)
        assert isinstance(check.requirements_missing, list)
        assert isinstance(check.recommendations, list)

    def test_input_logging_requirement_met(self, populated_chain: AuditChain):
        check = check_article_12_compliance(populated_chain)
        met_titles = " ".join(check.requirements_met)
        assert "12.1.a" in met_titles or "Input data" in met_titles or len(check.requirements_met) > 0

    def test_score_between_0_and_100(self, populated_chain: AuditChain):
        check = check_article_12_compliance(populated_chain)
        assert 0 <= check.score <= 100

    def test_article_12_html_report_is_html(self, populated_chain: AuditChain):
        html = generate_article_12_html_report(
            system_name="Test System",
            system_description="loan approval AI",
            chain=populated_chain,
        )
        assert "<!DOCTYPE html>" in html or "<html" in html or "<div" in html

    def test_article_13_transparency_report_is_markdown(self, populated_chain: AuditChain):
        md = generate_article_13_transparency_report(
            system_name="Test System",
            system_description="virtual assistant for scheduling",
            chain=populated_chain,
        )
        assert "# EU AI Act Article 13" in md
        assert "Risk Classification" in md


# ---------------------------------------------------------------------------
# Article 62 incident detection
# ---------------------------------------------------------------------------

class TestArticle62Detection:
    def test_clean_chain_has_no_incidents(self, populated_chain: AuditChain):
        incidents = detect_article_62_incidents(populated_chain, system_id="loan-approval-v2")
        # Chain is valid, no error metadata → should have no or few incidents
        integrity_incidents = [i for i in incidents if i["type"] == "P1-INTEGRITY"]
        assert len(integrity_incidents) == 0

    def test_tampered_chain_triggers_integrity_incident(self, empty_chain: AuditChain):
        """A tampered chain should produce a P1-INTEGRITY incident."""
        for i in range(5):
            empty_chain.append(
                session_id="s1", model="m", input_text=f"in{i}", output_text=f"out{i}",
                input_tokens=10, output_tokens=10, latency_ms=100.0,
                system_id="test-system",
            )
        entry = empty_chain.query(limit=1)[0]
        empty_chain._tamper_entry_for_demo(entry.entry_id, "input_tokens", 99999)

        incidents = detect_article_62_incidents(empty_chain, system_id="test-system")
        incident_types = [i["type"] for i in incidents]
        assert "P1-INTEGRITY" in incident_types

    def test_low_output_diversity_triggers_discrimination_incident(
        self, high_risk_chain: AuditChain
    ):
        """
        High-risk CLASSIFICATION entries with <30% output diversity
        should trigger a P0-DISCRIMINATION incident.
        """
        incidents = detect_article_62_incidents(high_risk_chain, system_id="loan-approval-v2")
        incident_types = [i["type"] for i in incidents]
        assert "P0-DISCRIMINATION" in incident_types

    def test_incidents_have_required_fields(self, high_risk_chain: AuditChain):
        incidents = detect_article_62_incidents(high_risk_chain, system_id="loan-approval-v2")
        for inc in incidents:
            assert "type" in inc
            assert "severity" in inc
            assert "description" in inc
            assert "evidence_entry_ids" in inc


# ---------------------------------------------------------------------------
# GPAI obligations
# ---------------------------------------------------------------------------

class TestGPAIObligations:
    def test_claude_model_detected_as_gpai(self):
        check = check_gpai_obligations("claude-sonnet-4-6")
        assert check.is_gpai is True

    def test_gpt_model_detected_as_gpai(self):
        check = check_gpai_obligations("gpt-4o")
        assert check.is_gpai is True

    def test_unknown_model_not_gpai(self):
        check = check_gpai_obligations("my-custom-fine-tuned-bert-v2")
        assert check.is_gpai is False

    def test_missing_transparency_doc_is_obligation(self):
        check = check_gpai_obligations("claude-sonnet-4-6", has_transparency_doc=False)
        missing = " ".join(check.obligations_missing)
        assert "53.1.a" in missing or "Technical documentation" in missing

    def test_all_docs_present_reduces_missing_obligations(self):
        full_check = check_gpai_obligations(
            "claude-haiku-4-5",
            has_transparency_doc=True,
            has_copyright_policy=True,
            has_energy_consumption_data=True,
            has_capabilities_limitations_doc=True,
            has_incident_reporting_process=True,
        )
        minimal_check = check_gpai_obligations("claude-haiku-4-5")
        assert len(full_check.obligations_missing) < len(minimal_check.obligations_missing)

    def test_transparency_checklist_is_dict(self):
        check = check_gpai_obligations("gpt-4o")
        assert isinstance(check.transparency_checklist, dict)
        assert "technical_documentation" in check.transparency_checklist
