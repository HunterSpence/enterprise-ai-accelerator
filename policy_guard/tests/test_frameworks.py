"""
PolicyGuard V2 — Framework unit tests
Tests the three compliance frameworks without any external dependencies.
"""
import pytest
import sys
import os

# Ensure policy_guard package is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestEUAIAct:
    def test_days_until_enforcement_returns_int(self):
        from frameworks.eu_ai_act import days_until_enforcement
        days = days_until_enforcement("high_risk_enforcement")
        assert isinstance(days, int)

    def test_prohibited_practices_count(self):
        from frameworks.eu_ai_act import PROHIBITED_PRACTICES
        assert len(PROHIBITED_PRACTICES) >= 6, "EU AI Act must define at least 6 prohibited practices"

    def test_annex_iv_sections(self):
        from frameworks.eu_ai_act import ANNEX_IV_SECTIONS
        assert len(ANNEX_IV_SECTIONS) >= 10

    def test_eu_ai_act_report_runs(self):
        from frameworks.eu_ai_act import EUAIActFramework
        fw = EUAIActFramework()
        report = fw.run_assessment()
        assert report is not None
        assert hasattr(report, "overall_compliance_score")
        assert 0 <= report.overall_compliance_score <= 100

    def test_gpai_obligations_present(self):
        from frameworks.eu_ai_act import GPAI_OBLIGATIONS
        assert len(GPAI_OBLIGATIONS) >= 4


class TestNISTAIRMF:
    def test_72_subcategories(self):
        from frameworks.nist_ai_rmf import NISTAIRMFFramework
        fw = NISTAIRMFFramework()
        report = fw.run_assessment()
        assert report.subcategories_total >= 72

    def test_five_level_maturity(self):
        from frameworks.nist_ai_rmf import _maturity_from_score
        assert _maturity_from_score(0) == "Initial"
        assert _maturity_from_score(40) == "Developing"
        assert _maturity_from_score(65) == "Defined"
        assert _maturity_from_score(82) == "Managed"
        assert _maturity_from_score(95) == "Optimizing"

    def test_cross_framework_gaps_present(self):
        from frameworks.nist_ai_rmf import NISTAIRMFFramework
        fw = NISTAIRMFFramework()
        report = fw.run_assessment()
        assert len(report.cross_framework_gaps) > 0

    def test_four_functions_present(self):
        from frameworks.nist_ai_rmf import NISTAIRMFFramework
        fw = NISTAIRMFFramework()
        report = fw.run_assessment()
        function_keys = {c.function for c in report.subcategory_results}
        assert {"GOVERN", "MAP", "MEASURE", "MANAGE"}.issubset(function_keys)


class TestSOC2:
    def test_50_controls(self):
        from frameworks.soc2 import SOC2Framework
        fw = SOC2Framework()
        report = fw.run_assessment()
        assert report.total_controls >= 50

    def test_aicc_controls_present(self):
        from frameworks.soc2 import AI_SPECIFIC_CONTROLS
        aicc_ids = [c["id"] for c in AI_SPECIFIC_CONTROLS]
        for i in range(1, 13):
            assert f"AICC-{i}" in aicc_ids, f"AICC-{i} missing from SOC2 controls"

    def test_aicc_score_field(self):
        from frameworks.soc2 import SOC2Framework
        fw = SOC2Framework()
        report = fw.run_assessment()
        assert hasattr(report, "aicc_score")
        assert 0 <= report.aicc_score <= 100

    def test_evidence_templates_for_key_controls(self):
        from frameworks.soc2 import EVIDENCE_TEMPLATES
        for control_id in ("AICC-1", "AICC-4", "AICC-7", "AICC-12"):
            assert control_id in EVIDENCE_TEMPLATES, f"Evidence template missing for {control_id}"


class TestBiasDetector:
    def test_bias_detector_runs(self):
        from bias_detector import BiasDetector
        detector = BiasDetector()
        report = detector.run()
        assert report is not None
        assert hasattr(report, "overall_bias_risk")

    def test_all_five_metrics_present(self):
        from bias_detector import BiasDetector
        detector = BiasDetector()
        report = detector.run()
        metrics = {m.metric_name for m in report.metrics}
        expected = {
            "Demographic Parity Difference",
            "Disparate Impact Ratio (EEOC 4/5ths)",
            "Equalized Odds",
            "Individual Fairness",
            "Counterfactual Fairness",
        }
        assert expected.issubset(metrics), f"Missing metrics: {expected - metrics}"

    def test_eu_ai_act_article_10_flag(self):
        from bias_detector import BiasDetector
        detector = BiasDetector()
        report = detector.run()
        assert hasattr(report, "eu_ai_act_article_10_compliant")
        assert isinstance(report.eu_ai_act_article_10_compliant, bool)

    def test_mitigation_strategies_present(self):
        from bias_detector import MITIGATION_STRATEGIES
        assert len(MITIGATION_STRATEGIES) >= 4


class TestIncidentResponse:
    def test_severity_levels(self):
        from incident_response import IncidentSeverity
        assert hasattr(IncidentSeverity, "P0")
        assert hasattr(IncidentSeverity, "P1")
        assert hasattr(IncidentSeverity, "P2")
        assert hasattr(IncidentSeverity, "P3")

    def test_classifier_runs(self):
        from incident_response import IncidentClassifier
        clf = IncidentClassifier()
        result = clf.classify(
            title="Model producing biased hiring recommendations",
            affected_users=500,
            accuracy_drop=0.12,
        )
        assert result is not None

    def test_article_62_notification_generated(self):
        from incident_response import generate_article_62_notification
        text = generate_article_62_notification(
            incident_id="TEST-001",
            system_name="HiringAI",
            description="Bias detected",
            severity="P1",
        )
        assert "Article 62" in text or "serious incident" in text.lower()

    def test_demo_incidents_defined(self):
        from incident_response import DEMO_INCIDENTS
        assert len(DEMO_INCIDENTS) >= 3
        severities = {i["severity"] for i in DEMO_INCIDENTS}
        assert "P0" in severities


class TestScanner:
    def test_scanner_imports(self):
        """Smoke test: scanner module imports without errors."""
        import scanner  # noqa: F401

    def test_scanner_has_run_method(self):
        from scanner import PolicyGuardScanner
        assert hasattr(PolicyGuardScanner, "run") or hasattr(PolicyGuardScanner, "scan")


class TestReporter:
    def test_reporter_imports(self):
        import reporter  # noqa: F401

    def test_radar_svg_generation(self):
        from reporter import PolicyGuardReporter
        # Verify the reporter can instantiate and has the SVG method
        r = PolicyGuardReporter.__new__(PolicyGuardReporter)
        assert hasattr(r, "_build_radar_svg") or hasattr(PolicyGuardReporter, "_build_radar_svg")
