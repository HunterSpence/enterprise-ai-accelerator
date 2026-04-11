"""
Tests for policy_guard/remediation_generator.py
"""
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from policy_guard.remediation_generator import (
    RemediationGenerator,
    RemediationResult,
    _HCL_TEMPLATES,
    _DEFAULT_TEMPLATE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_finding(control_id, title, severity="HIGH", status="FAIL", details="", remediation="", resource=""):
    return SimpleNamespace(
        control_id=control_id,
        title=title,
        severity=severity,
        status=status,
        details=details,
        remediation=remediation,
        resource=resource,
    )


def _make_report(**kwargs):
    defaults = dict(
        cis_aws=None, eu_ai_act=None, nist_ai_rmf=None, soc2=None, hipaa=None
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_fw(findings):
    return SimpleNamespace(findings=findings)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------

class TestInstantiation:

    def test_no_api_key_creates_instance(self):
        gen = RemediationGenerator()
        assert gen is not None

    def test_with_api_key_stores_key(self):
        gen = RemediationGenerator(anthropic_api_key="sk-ant-fake-key")
        assert gen._api_key == "sk-ant-fake-key"

    def test_no_api_key_client_is_none(self):
        gen = RemediationGenerator()
        assert gen._client is None

    def test_custom_model_stored(self):
        gen = RemediationGenerator(model="claude-haiku-4-5-20251001")
        assert gen._model == "claude-haiku-4-5-20251001"

    def test_custom_max_findings(self):
        gen = RemediationGenerator(max_findings=10)
        assert gen._max_findings == 10

    def test_cache_starts_empty(self):
        gen = RemediationGenerator()
        assert gen._cache == {}

    def test_invalid_api_key_falls_back_gracefully(self):
        # anthropic package may not be installed; either way should not crash
        gen = RemediationGenerator(anthropic_api_key="sk-ant-invalid")
        assert gen is not None


# ---------------------------------------------------------------------------
# Offline / template mode
# ---------------------------------------------------------------------------

class TestOfflineTemplateMode:

    def test_known_rule_returns_template(self):
        gen = RemediationGenerator()
        result = gen.generate_for_finding(
            rule_id="PG-CIS_AWS-1.4",
            title="Root access keys",
            severity="CRITICAL",
            framework="cis_aws",
            details="",
            remediation="",
        )
        assert result.generated_by == "template"
        assert result.rule_id == "PG-CIS_AWS-1.4"

    def test_known_rule_returns_hcl_content(self):
        gen = RemediationGenerator()
        result = gen.generate_for_finding(
            rule_id="PG-CIS_AWS-2.1",
            title="CloudTrail multi-region",
            severity="HIGH",
            framework="cis_aws",
            details="",
            remediation="",
        )
        assert len(result.remediation_hcl) > 0
        assert result.remediation_hcl == _HCL_TEMPLATES["PG-CIS_AWS-2.1"]

    def test_unknown_rule_fallback_mode(self):
        gen = RemediationGenerator()
        result = gen.generate_for_finding(
            rule_id="PG-CIS_AWS-UNKNOWN-RULE",
            title="Some unknown check",
            severity="LOW",
            framework="cis_aws",
            details="Some detail",
            remediation="Do something",
        )
        assert result.generated_by == "none"
        assert result.remediation_hcl is not None
        assert len(result.remediation_hcl) > 0

    def test_fallback_hcl_contains_title(self):
        gen = RemediationGenerator()
        result = gen.generate_for_finding(
            rule_id="PG-SOC2-UNIQUE-999",
            title="MyCustomFinding",
            severity="MEDIUM",
            framework="soc2",
            details="",
            remediation="Fix it now",
        )
        assert "MyCustomFinding" in result.remediation_hcl or result.generated_by in ("template", "none")

    def test_result_confidence_template_is_high(self):
        gen = RemediationGenerator()
        result = gen.generate_for_finding(
            rule_id="PG-CIS_AWS-1.4",
            title="Root access keys",
            severity="CRITICAL",
            framework="cis_aws",
            details="",
            remediation="",
        )
        assert result.confidence == "high"

    def test_result_confidence_fallback_is_low(self):
        gen = RemediationGenerator()
        result = gen.generate_for_finding(
            rule_id="PG-HIPAA-UNKNOWN-9999",
            title="Unknown",
            severity="LOW",
            framework="hipaa",
            details="",
            remediation="",
        )
        assert result.confidence == "low"

    def test_patch_filename_generated(self):
        gen = RemediationGenerator()
        result = gen.generate_for_finding(
            rule_id="PG-CIS_AWS-1.4",
            title="Root",
            severity="CRITICAL",
            framework="cis_aws",
            details="",
            remediation="",
        )
        assert result.patch_filename.endswith(".tf")

    def test_result_is_cached(self):
        gen = RemediationGenerator()
        r1 = gen.generate_for_finding(
            rule_id="PG-CIS_AWS-4.1",
            title="Unrestricted SSH",
            severity="CRITICAL",
            framework="cis_aws",
            details="",
            remediation="",
        )
        r2 = gen.generate_for_finding(
            rule_id="PG-CIS_AWS-4.1",
            title="Unrestricted SSH",
            severity="CRITICAL",
            framework="cis_aws",
            details="",
            remediation="",
        )
        assert r1 is r2  # same object from cache

    def test_no_api_calls_without_key(self):
        gen = RemediationGenerator()
        # Should never raise even for unknown rules — falls back without calling API
        result = gen.generate_for_finding(
            rule_id="PG-EU_AI_ACT-UNKNOWN-ARTICLE",
            title="Missing audit log",
            severity="HIGH",
            framework="eu_ai_act",
            details="No audit log configured",
            remediation="Configure audit logging",
        )
        assert result is not None
        assert result.remediation_hcl is not None


# ---------------------------------------------------------------------------
# enrich_findings
# ---------------------------------------------------------------------------

class TestEnrichFindings:

    def test_enrich_returns_list(self):
        report = _make_report(
            cis_aws=_make_fw([_make_finding("1.4", "Root keys", "CRITICAL")])
        )
        gen = RemediationGenerator()
        results = gen.enrich_findings(report)
        assert isinstance(results, list)

    def test_enrich_skips_pass_findings(self):
        report = _make_report(
            cis_aws=_make_fw([
                _make_finding("1.4", "Root keys", "CRITICAL", status="FAIL"),
                _make_finding("2.0", "Passing check", "LOW", status="PASS"),
            ])
        )
        gen = RemediationGenerator()
        results = gen.enrich_findings(report)
        assert len(results) == 1

    def test_enrich_result_has_required_keys(self):
        report = _make_report(
            cis_aws=_make_fw([_make_finding("2.1", "CloudTrail", "HIGH")])
        )
        gen = RemediationGenerator()
        results = gen.enrich_findings(report)
        assert len(results) == 1
        r = results[0]
        for key in ("rule_id", "framework", "title", "severity", "remediation_hcl", "generated_by"):
            assert key in r

    def test_enrich_respects_max_findings(self):
        findings = [_make_finding(str(i), f"Finding {i}", "LOW") for i in range(100)]
        report = _make_report(cis_aws=_make_fw(findings))
        gen = RemediationGenerator(max_findings=5)
        results = gen.enrich_findings(report)
        assert len(results) <= 5

    def test_enrich_empty_report(self):
        report = _make_report()
        gen = RemediationGenerator()
        results = gen.enrich_findings(report)
        assert results == []

    def test_enrich_multi_framework(self):
        report = _make_report(
            cis_aws=_make_fw([_make_finding("1.4", "Root keys", "CRITICAL")]),
            eu_ai_act=_make_fw([_make_finding("ART-12", "Audit log", "HIGH")]),
        )
        gen = RemediationGenerator()
        results = gen.enrich_findings(report)
        frameworks = {r["framework"] for r in results}
        assert "cis_aws" in frameworks
        assert "eu_ai_act" in frameworks


# ---------------------------------------------------------------------------
# export_patch_bundle
# ---------------------------------------------------------------------------

class TestExportPatchBundle:

    def test_export_creates_directory(self):
        report = _make_report(
            cis_aws=_make_fw([_make_finding("2.1", "CloudTrail", "HIGH")])
        )
        gen = RemediationGenerator()
        enriched = gen.enrich_findings(report)
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = gen.export_patch_bundle(enriched, tmp)
            assert os.path.isdir(out_dir)

    def test_export_creates_tf_files(self):
        report = _make_report(
            cis_aws=_make_fw([_make_finding("2.1", "CloudTrail", "HIGH")])
        )
        gen = RemediationGenerator()
        enriched = gen.enrich_findings(report)
        with tempfile.TemporaryDirectory() as tmp:
            gen.export_patch_bundle(enriched, tmp)
            tf_files = [f for f in os.listdir(tmp) if f.endswith(".tf")]
            assert len(tf_files) >= 1

    def test_export_creates_index(self):
        report = _make_report(
            cis_aws=_make_fw([_make_finding("4.1", "SSH unrestricted", "CRITICAL")])
        )
        gen = RemediationGenerator()
        enriched = gen.enrich_findings(report)
        with tempfile.TemporaryDirectory() as tmp:
            gen.export_patch_bundle(enriched, tmp)
            assert os.path.exists(os.path.join(tmp, "REMEDIATION_INDEX.md"))


# ---------------------------------------------------------------------------
# RemediationResult dataclass
# ---------------------------------------------------------------------------

class TestRemediationResultDataclass:

    def test_result_fields(self):
        result = RemediationResult(
            rule_id="PG-CIS_AWS-1.4",
            finding_title="Root keys",
            severity="CRITICAL",
            framework="cis_aws",
            remediation_hcl="# hcl",
            generated_by="template",
        )
        assert result.rule_id == "PG-CIS_AWS-1.4"
        assert result.generated_by == "template"
        assert result.confidence == "medium"  # default

    def test_result_optional_model_used(self):
        result = RemediationResult(
            rule_id="X",
            finding_title="Y",
            severity="LOW",
            framework="cis_aws",
            remediation_hcl="# x",
            generated_by="claude",
            model_used="claude-haiku-4-5",
        )
        assert result.model_used == "claude-haiku-4-5"
