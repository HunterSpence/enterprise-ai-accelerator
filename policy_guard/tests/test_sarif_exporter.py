"""
Tests for policy_guard/sarif_exporter.py
"""
import json
import os
import sys
import tempfile
from types import SimpleNamespace

import pytest

# Ensure repo root is on path
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from policy_guard.sarif_exporter import (
    SARIFExporter,
    SARIFRule,
    SARIFResult,
    _SARIF_VERSION,
    _SARIF_SCHEMA,
    _SEVERITY_TO_SARIF_LEVEL,
    _SEVERITY_TO_SECURITY_SCORE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_finding(control_id, title, severity, status="FAIL", details="", remediation="", resource=""):
    return SimpleNamespace(
        control_id=control_id,
        title=title,
        severity=severity,
        status=status,
        details=details,
        remediation=remediation,
        resource=resource,
    )


def _make_fw_report(findings):
    return SimpleNamespace(findings=findings)


def _make_report(cis_aws=None, eu_ai_act=None, nist_ai_rmf=None, soc2=None, hipaa=None,
                 scan_id="test-scan-001", overall_score=72, risk_rating="Medium"):
    report = SimpleNamespace(
        scan_id=scan_id,
        overall_score=overall_score,
        risk_rating=risk_rating,
        cis_aws=cis_aws,
        eu_ai_act=eu_ai_act,
        nist_ai_rmf=nist_ai_rmf,
        soc2=soc2,
        hipaa=hipaa,
    )
    return report


@pytest.fixture
def report_with_findings():
    cis_findings = [
        _make_finding("1.4", "No root access keys", "CRITICAL", details="Root account has active access keys", remediation="Delete root access keys"),
        _make_finding("2.1", "CloudTrail enabled", "HIGH", resource="aws_cloudtrail"),
        _make_finding("2.2", "Log file validation", "MEDIUM"),
        _make_finding("3.1", "S3 public access blocked", "LOW"),
        _make_finding("4.0", "SG rule compliant", "INFO", status="PASS"),  # PASS — should be excluded
    ]
    eu_findings = [
        _make_finding("ART-12", "Audit logging required", "HIGH", details="AI system lacks audit trail"),
    ]
    return _make_report(
        cis_aws=_make_fw_report(cis_findings),
        eu_ai_act=_make_fw_report(eu_findings),
    )


@pytest.fixture
def empty_report():
    return _make_report(
        cis_aws=_make_fw_report([]),
        eu_ai_act=_make_fw_report([]),
    )


@pytest.fixture
def report_no_frameworks():
    return _make_report()


# ---------------------------------------------------------------------------
# SARIF structure tests
# ---------------------------------------------------------------------------

class TestSARIFStructure:

    def test_sarif_version_field(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        sarif = exporter.to_dict()
        assert sarif["version"] == "2.1.0"

    def test_sarif_schema_field(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        sarif = exporter.to_dict()
        assert "$schema" in sarif
        assert "sarif-schema-2.1.0" in sarif["$schema"]

    def test_sarif_has_runs(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        sarif = exporter.to_dict()
        assert "runs" in sarif
        assert isinstance(sarif["runs"], list)
        assert len(sarif["runs"]) == 1

    def test_run_has_tool_and_results(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        run = exporter.to_dict()["runs"][0]
        assert "tool" in run
        assert "results" in run
        assert "driver" in run["tool"]

    def test_tool_driver_metadata(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        driver = exporter.to_dict()["runs"][0]["tool"]["driver"]
        assert driver["name"] == "PolicyGuard"
        assert "version" in driver
        assert "rules" in driver

    def test_run_has_automation_details(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        run = exporter.to_dict()["runs"][0]
        assert "automationDetails" in run
        assert "id" in run["automationDetails"]


# ---------------------------------------------------------------------------
# Finding → result conversion
# ---------------------------------------------------------------------------

class TestFindingConversion:

    def test_fail_findings_are_exported(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        sarif = exporter.to_dict()
        results = sarif["runs"][0]["results"]
        # 4 FAIL findings (1.4 CRITICAL, 2.1 HIGH, 2.2 MEDIUM, 3.1 LOW from cis + ART-12 from eu)
        assert len(results) == 5

    def test_pass_findings_excluded(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        sarif = exporter.to_dict()
        results = sarif["runs"][0]["results"]
        rule_ids = [r["ruleId"] for r in results]
        # "4.0" was a PASS — should not appear
        assert not any("4.0" in rid for rid in rule_ids)

    def test_rule_id_format(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        sarif = exporter.to_dict()
        results = sarif["runs"][0]["results"]
        for result in results:
            assert result["ruleId"].startswith("PG-")

    def test_result_has_message(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        results = exporter.to_dict()["runs"][0]["results"]
        for result in results:
            assert "message" in result
            assert "text" in result["message"]

    def test_result_has_locations(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        results = exporter.to_dict()["runs"][0]["results"]
        for result in results:
            assert "locations" in result
            assert len(result["locations"]) >= 1

    def test_rules_list_populated(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        rules = exporter.to_dict()["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) > 0
        for rule in rules:
            assert "id" in rule
            assert "shortDescription" in rule
            assert "defaultConfiguration" in rule

    def test_multi_framework_results(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        results = exporter.to_dict()["runs"][0]["results"]
        frameworks = {r["properties"]["policyguard-framework"] for r in results}
        assert "cis_aws" in frameworks
        assert "eu_ai_act" in frameworks


# ---------------------------------------------------------------------------
# Severity mapping
# ---------------------------------------------------------------------------

class TestSeverityMapping:

    @pytest.mark.parametrize("severity,expected_level", [
        ("CRITICAL", "error"),
        ("HIGH", "error"),
        ("MEDIUM", "warning"),
        ("LOW", "note"),
        ("INFO", "none"),
    ])
    def test_severity_to_sarif_level(self, severity, expected_level):
        assert _SEVERITY_TO_SARIF_LEVEL[severity] == expected_level

    def test_critical_result_level_is_error(self):
        report = _make_report(cis_aws=_make_fw_report([
            _make_finding("1.4", "Root keys", "CRITICAL")
        ]))
        exporter = SARIFExporter(report)
        results = exporter.to_dict()["runs"][0]["results"]
        assert results[0]["level"] == "error"

    def test_medium_result_level_is_warning(self):
        report = _make_report(cis_aws=_make_fw_report([
            _make_finding("2.2", "Log validation", "MEDIUM")
        ]))
        exporter = SARIFExporter(report)
        results = exporter.to_dict()["runs"][0]["results"]
        assert results[0]["level"] == "warning"

    def test_low_result_level_is_note(self):
        report = _make_report(cis_aws=_make_fw_report([
            _make_finding("3.1", "Low severity finding", "LOW")
        ]))
        exporter = SARIFExporter(report)
        results = exporter.to_dict()["runs"][0]["results"]
        assert results[0]["level"] == "note"

    def test_severity_security_scores_ordered(self):
        assert _SEVERITY_TO_SECURITY_SCORE["CRITICAL"] > _SEVERITY_TO_SECURITY_SCORE["HIGH"]
        assert _SEVERITY_TO_SECURITY_SCORE["HIGH"] > _SEVERITY_TO_SECURITY_SCORE["MEDIUM"]
        assert _SEVERITY_TO_SECURITY_SCORE["MEDIUM"] > _SEVERITY_TO_SECURITY_SCORE["LOW"]

    def test_rule_properties_contain_severity(self):
        report = _make_report(cis_aws=_make_fw_report([
            _make_finding("1.4", "Root keys", "CRITICAL")
        ]))
        exporter = SARIFExporter(report)
        rules = exporter.to_dict()["runs"][0]["tool"]["driver"]["rules"]
        rule = rules[0]
        assert rule["properties"]["policyguard-severity"] == "CRITICAL"
        assert rule["properties"]["security-severity"] == "9.5"


# ---------------------------------------------------------------------------
# Export to file / to_dict / to_json
# ---------------------------------------------------------------------------

class TestExportMethods:

    def test_to_json_returns_string(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        result = exporter.to_json()
        assert isinstance(result, str)

    def test_to_json_is_valid_json(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        parsed = json.loads(exporter.to_json())
        assert parsed["version"] == "2.1.0"

    def test_export_writes_file(self, report_with_findings):
        with tempfile.TemporaryDirectory() as tmp:
            exporter = SARIFExporter(report_with_findings)
            path = exporter.export(tmp)
            assert os.path.exists(path)
            assert path.endswith(".sarif")

    def test_export_file_is_valid_sarif(self, report_with_findings):
        with tempfile.TemporaryDirectory() as tmp:
            exporter = SARIFExporter(report_with_findings)
            path = exporter.export(tmp)
            with open(path) as f:
                content = json.load(f)
            assert content["version"] == "2.1.0"
            assert "runs" in content

    def test_export_creates_directory(self, report_with_findings):
        with tempfile.TemporaryDirectory() as tmp:
            nested = os.path.join(tmp, "subdir", "nested")
            exporter = SARIFExporter(report_with_findings)
            path = exporter.export(nested)
            assert os.path.exists(path)

    def test_export_filename_contains_scan_id(self, report_with_findings):
        with tempfile.TemporaryDirectory() as tmp:
            exporter = SARIFExporter(report_with_findings)
            path = exporter.export(tmp)
            assert "test-scan-001" in os.path.basename(path)


# ---------------------------------------------------------------------------
# Empty report (0 findings)
# ---------------------------------------------------------------------------

class TestEmptyReport:

    def test_empty_report_zero_results(self, empty_report):
        exporter = SARIFExporter(empty_report)
        results = exporter.to_dict()["runs"][0]["results"]
        assert results == []

    def test_empty_report_zero_rules(self, empty_report):
        exporter = SARIFExporter(empty_report)
        rules = exporter.to_dict()["runs"][0]["tool"]["driver"]["rules"]
        assert rules == []

    def test_empty_report_still_valid_sarif(self, empty_report):
        exporter = SARIFExporter(empty_report)
        sarif = exporter.to_dict()
        assert sarif["version"] == "2.1.0"
        assert len(sarif["runs"]) == 1

    def test_no_frameworks_zero_results(self, report_no_frameworks):
        exporter = SARIFExporter(report_no_frameworks)
        results = exporter.to_dict()["runs"][0]["results"]
        assert results == []


# ---------------------------------------------------------------------------
# Summary method
# ---------------------------------------------------------------------------

class TestSummaryMethod:

    def test_summary_returns_dict(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        s = exporter.summary()
        assert isinstance(s, dict)

    def test_summary_total_findings(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        s = exporter.summary()
        assert s["total_findings_exported"] == 5

    def test_summary_by_severity_keys(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        s = exporter.summary()
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            assert sev in s["by_severity"]

    def test_summary_by_severity_critical_count(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        s = exporter.summary()
        assert s["by_severity"]["CRITICAL"] == 1

    def test_summary_by_framework(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        s = exporter.summary()
        assert "cis_aws" in s["by_framework"]
        assert "eu_ai_act" in s["by_framework"]

    def test_summary_unique_rules(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        s = exporter.summary()
        assert s["unique_rules"] >= 1

    def test_summary_empty_report(self, empty_report):
        exporter = SARIFExporter(empty_report)
        s = exporter.summary()
        assert s["total_findings_exported"] == 0
        assert s["unique_rules"] == 0

    def test_summary_has_github_command(self, report_with_findings):
        exporter = SARIFExporter(report_with_findings)
        s = exporter.summary()
        assert "github_upload_command" in s
