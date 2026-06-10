"""
Tests for Colorado SB 26-189 and Texas TRAIGA framework scanners.
Offline only — no external dependencies, no API calls.
"""
from __future__ import annotations

import asyncio
import sys
import os
from datetime import date

import pytest

# Ensure policy_guard package root is on sys.path (mirrors test_frameworks.py pattern)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run an async coroutine from sync test code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Colorado SB 26-189
# ---------------------------------------------------------------------------

class TestColoradoSB26189:
    """Unit tests for the Colorado SB 26-189 framework scanner."""

    def test_import(self):
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner, ColoradoSB26189Report
        assert ColoradoSB26189Scanner is not None
        assert ColoradoSB26189Report is not None

    def test_mock_scan_returns_report(self):
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["loan-approval-v2"], mock=True)
        report = run(scanner.scan())
        assert report is not None

    def test_report_has_expected_fields(self):
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["test-system"], mock=True)
        report = run(scanner.scan())
        assert hasattr(report, "compliance_score")
        assert hasattr(report, "total_findings")
        assert hasattr(report, "findings")
        assert hasattr(report, "days_until_effective")

    def test_compliance_score_in_range(self):
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["test-system"], mock=True)
        report = run(scanner.scan())
        assert 0.0 <= report.compliance_score <= 100.0

    def test_findings_list_has_15_items(self):
        """findings list covers all 15 controls regardless of total_findings computation."""
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["test-system"], mock=True)
        report = run(scanner.scan())
        assert len(report.findings) == 15

    def test_severity_count_fields_exist(self):
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["test-system"], mock=True)
        report = run(scanner.scan())
        assert hasattr(report, "critical_count")
        assert hasattr(report, "high_count")
        assert hasattr(report, "medium_count")
        assert hasattr(report, "low_count")

    def test_severity_counts_non_negative(self):
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["test-system"], mock=True)
        report = run(scanner.scan())
        assert report.critical_count >= 0
        assert report.high_count >= 0
        assert report.medium_count >= 0
        assert report.low_count >= 0

    def test_days_until_effective_positive_before_2027(self):
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=[], mock=True)
        report = run(scanner.scan())
        effective = date(2027, 1, 1)
        today = date.today()
        if today < effective:
            assert report.days_until_effective > 0
        else:
            assert report.days_until_effective <= 0

    def test_15_controls_in_findings_list(self):
        """Spec requires 15 controls across the 4 groups."""
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["s1"], mock=True)
        report = run(scanner.scan())
        assert len(report.findings) == 15

    def test_finding_is_dataclass_with_expected_attrs(self):
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["s1"], mock=True)
        report = run(scanner.scan())
        for finding in report.findings:
            assert hasattr(finding, "control_id")
            assert hasattr(finding, "title")
            assert hasattr(finding, "status")
            assert finding.status in ("PASS", "FAIL", "WARN", "NA")

    def test_no_sb24205_in_control_ids(self):
        """Control IDs must not reference the repealed SB 24-205."""
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["s1"], mock=True)
        report = run(scanner.scan())
        for finding in report.findings:
            assert "24205" not in finding.control_id
            assert "24_205" not in finding.control_id

    def test_control_ids_use_sb26189_prefix(self):
        """All control IDs should reference the 26-189 framework."""
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["s1"], mock=True)
        report = run(scanner.scan())
        for finding in report.findings:
            assert "26189" in finding.control_id or "SB26" in finding.control_id, (
                f"Unexpected control_id: {finding.control_id}"
            )

    def test_multiple_ai_systems(self):
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(
            ai_systems=["system-a", "system-b", "system-c"], mock=True
        )
        report = run(scanner.scan())
        assert report is not None
        assert report.compliance_score >= 0


# ---------------------------------------------------------------------------
# Texas TRAIGA
# ---------------------------------------------------------------------------

class TestTexasTRAIGA:
    """Unit tests for the Texas TRAIGA framework scanner."""

    def test_import(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner, TexasTRAIGAReport
        assert TexasTRAIGAScanner is not None
        assert TexasTRAIGAReport is not None

    def test_mock_scan_returns_report(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=["fraud-detection-v3"], mock=True)
        report = run(scanner.scan())
        assert report is not None

    def test_report_has_expected_fields(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=["test-system"], mock=True)
        report = run(scanner.scan())
        assert hasattr(report, "compliance_score")
        assert hasattr(report, "total_findings")
        assert hasattr(report, "findings")
        assert hasattr(report, "penalty_range")

    def test_penalty_range_contains_dollar_amounts(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=[], mock=True)
        report = run(scanner.scan())
        pr = report.penalty_range
        assert "10,000" in pr or "10K" in pr.upper() or "$10" in pr
        assert "200,000" in pr or "200K" in pr.upper() or "200" in pr

    def test_compliance_score_in_range(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=["test-system"], mock=True)
        report = run(scanner.scan())
        assert 0.0 <= report.compliance_score <= 100.0

    def test_findings_list_has_15_items(self):
        """findings list covers all 15 controls."""
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=["test-system"], mock=True)
        report = run(scanner.scan())
        assert len(report.findings) == 15

    def test_severity_count_fields_exist(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=["test-system"], mock=True)
        report = run(scanner.scan())
        assert hasattr(report, "critical_count")
        assert hasattr(report, "high_count")
        assert hasattr(report, "medium_count")
        assert hasattr(report, "low_count")

    def test_severity_counts_non_negative(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=["test-system"], mock=True)
        report = run(scanner.scan())
        assert report.critical_count >= 0
        assert report.high_count >= 0
        assert report.medium_count >= 0
        assert report.low_count >= 0

    def test_is_in_effect(self):
        """TRAIGA is effective Jan 1, 2026 — must return True today."""
        from frameworks.texas_traiga import is_in_effect
        assert is_in_effect() is True

    def test_government_controls_marked_na_for_private_deployer(self):
        """Government AI controls (2506_*) must be NA for private deployers."""
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=["private-ai"], mock=True)
        report = run(scanner.scan())
        gov_findings = [
            f for f in report.findings
            if "2506" in f.control_id
        ]
        assert len(gov_findings) > 0, "Expected at least one 2506 government AI control"
        for gf in gov_findings:
            assert gf.status == "NA", (
                f"Government control {gf.control_id} should be NA for private deployer, got {gf.status}"
            )

    def test_finding_is_dataclass_with_expected_attrs(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=["s1"], mock=True)
        report = run(scanner.scan())
        for finding in report.findings:
            assert hasattr(finding, "control_id")
            assert hasattr(finding, "title")
            assert hasattr(finding, "status")
            assert finding.status in ("PASS", "FAIL", "WARN", "NA")

    def test_control_ids_use_traiga_prefix(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=["s1"], mock=True)
        report = run(scanner.scan())
        for finding in report.findings:
            assert "TRAIGA" in finding.control_id or "TX" in finding.control_id, (
                f"Unexpected control_id: {finding.control_id}"
            )


# ---------------------------------------------------------------------------
# Scanner integration — both frameworks register in PolicyGuard scanner
# ---------------------------------------------------------------------------

class TestScannerIntegration:
    """Verify Colorado SB 26-189 + Texas TRAIGA are wired into the main scanner."""

    def _load_scanner_module(self):
        import importlib.util
        scanner_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, scanner_dir)
        import policy_guard.scanner as sc
        return sc

    def test_scan_config_has_new_framework_flags(self):
        sc = self._load_scanner_module()
        cfg = sc.ScanConfig()
        assert hasattr(cfg, "run_colorado_sb26189")
        assert hasattr(cfg, "run_texas_traiga")
        assert cfg.run_colorado_sb26189 is True
        assert cfg.run_texas_traiga is True

    def test_compliance_report_has_new_framework_fields(self):
        sc = self._load_scanner_module()
        fields = set(sc.ComplianceReport.__dataclass_fields__.keys())
        assert "colorado_sb26189" in fields
        assert "texas_traiga" in fields

    def test_framework_weights_sum_to_one(self):
        sc = self._load_scanner_module()
        total = sum(sc.FRAMEWORK_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"FRAMEWORK_WEIGHTS sum={total}, expected 1.0"

    def test_eleven_frameworks_registered(self):
        sc = self._load_scanner_module()
        assert len(sc.FRAMEWORK_WEIGHTS) == 11

    def test_new_frameworks_in_framework_weights(self):
        sc = self._load_scanner_module()
        assert "colorado_sb26189" in sc.FRAMEWORK_WEIGHTS
        assert "texas_traiga" in sc.FRAMEWORK_WEIGHTS
