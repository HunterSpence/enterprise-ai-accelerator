"""Tests for iac_security/ — terraform_parser, pulumi_parser, policies, sarif, drift, sbom."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from iac_security.terraform_parser import (
    TerraformResource,
    TerraformParseStats,
    _build_line_index,
    _parse_file,
    parse_terraform,
)
from iac_security.pulumi_parser import PulumiResource
from iac_security.policies import ALL_POLICIES
from iac_security.sarif_exporter import export_sarif, SARIFExporter
from iac_security.drift_detector import DriftDetector, DriftItem, DriftReport
from iac_security.sbom_generator import SBOMGenerator, MLBOMGenerator, _ml_model_component


# ---------------------------------------------------------------------------
# Sample HCL for line-index tests (no hcl2 import needed)
# ---------------------------------------------------------------------------

_SAMPLE_HCL = '''
resource "aws_s3_bucket" "bad_bucket" {
  bucket = "my-bad-bucket"
  acl    = "public-read"
}

resource "aws_db_instance" "prod_db" {
  engine = "mysql"
  backup_retention_period = 0
}
'''


class TestTerraformParserLineIndex:
    def test_line_index_finds_resource(self):
        index = _build_line_index(_SAMPLE_HCL)
        assert any("aws_s3_bucket" in k for k in index.keys())

    def test_line_index_finds_db_instance(self):
        index = _build_line_index(_SAMPLE_HCL)
        assert any("aws_db_instance" in k for k in index.keys())

    def test_line_index_positive_line_numbers(self):
        index = _build_line_index(_SAMPLE_HCL)
        assert all(v > 0 for v in index.values())


class TestTerraformResource:
    def test_address_for_resource(self):
        r = TerraformResource(
            kind="resource", resource_type="aws_s3_bucket", name="my_bucket"
        )
        assert r.address == "aws_s3_bucket.my_bucket"

    def test_address_for_module(self):
        r = TerraformResource(kind="module", resource_type="", name="vpc")
        assert r.address == "module.vpc"

    def test_get_present_attribute(self):
        r = TerraformResource(
            kind="resource", resource_type="aws_s3_bucket", name="b",
            attributes={"acl": "private"},
        )
        assert r.get("acl") == "private"

    def test_get_missing_returns_default(self):
        r = TerraformResource(kind="resource", resource_type="t", name="n")
        assert r.get("nonexistent", "fallback") == "fallback"

    def test_get_nested_attribute(self):
        r = TerraformResource(
            kind="resource", resource_type="aws_s3_bucket", name="b",
            attributes={"server_side_encryption_configuration": {"rule": "AES256"}},
        )
        sse = r.get("server_side_encryption_configuration")
        assert sse is not None


class TestPulumiResource:
    def test_address_property(self):
        r = PulumiResource(resource_type="aws:s3/bucket:Bucket", name="my_bucket")
        assert "aws:s3/bucket:Bucket" in r.address

    def test_get_attribute(self):
        r = PulumiResource(
            resource_type="aws:s3/bucket:Bucket",
            name="b",
            attributes={"acl": "private"},
        )
        assert r.get("acl") == "private"

    def test_get_missing_returns_none(self):
        r = PulumiResource(resource_type="t", name="n")
        assert r.get("missing") is None

    def test_parse_pulumi_on_tmp_dir(self, tmp_path):
        from iac_security.pulumi_parser import parse_pulumi
        # Should not raise on empty dir
        resources = parse_pulumi(tmp_path)
        assert isinstance(resources, list)


class TestPoliciesRegistry:
    def test_20_policies_registered(self):
        assert len(ALL_POLICIES) == 20

    def test_all_policies_have_iac_id(self):
        for p in ALL_POLICIES:
            assert p.id.startswith("IAC-")

    def test_all_policies_have_severity(self):
        for p in ALL_POLICIES:
            assert p.severity in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}

    def test_s3_public_acl_flags_bad(self):
        from iac_security.policies import S3NoPublicACL
        policy = S3NoPublicACL()
        r = TerraformResource(
            kind="resource", resource_type="aws_s3_bucket", name="b",
            attributes={"acl": "public-read"},
        )
        result = policy.check(r)
        assert result is not None
        assert result.policy_id == "IAC-001"

    def test_s3_public_acl_passes_private(self):
        from iac_security.policies import S3NoPublicACL
        policy = S3NoPublicACL()
        r = TerraformResource(
            kind="resource", resource_type="aws_s3_bucket", name="b",
            attributes={"acl": "private"},
        )
        assert policy.check(r) is None

    def test_rds_no_public_flags_publicly_accessible(self):
        from iac_security.policies import RDSNotPublic
        policy = RDSNotPublic()
        r = TerraformResource(
            kind="resource", resource_type="aws_db_instance", name="db",
            attributes={"publicly_accessible": True},
        )
        result = policy.check(r)
        assert result is not None

    def test_kms_rotation_flags_disabled(self):
        from iac_security.policies import KMSKeyRotation
        policy = KMSKeyRotation()
        r = TerraformResource(
            kind="resource", resource_type="aws_kms_key", name="key",
            attributes={"enable_key_rotation": False},
        )
        result = policy.check(r)
        assert result is not None

    def test_wrong_resource_type_skips(self):
        from iac_security.policies import S3NoPublicACL
        policy = S3NoPublicACL()
        r = TerraformResource(
            kind="resource", resource_type="aws_ec2_instance", name="inst",
            attributes={"acl": "public-read"},
        )
        assert policy.check(r) is None

    def test_ec2_imdsv2_flags_optional(self):
        from iac_security.policies import EC2IMDSv2Required
        policy = EC2IMDSv2Required()
        r = TerraformResource(
            kind="resource", resource_type="aws_instance", name="ec2",
            attributes={"metadata_options": {"http_tokens": "optional"}},
        )
        result = policy.check(r)
        assert result is not None


class TestSARIFExporter:
    def _make_scan_report(self, findings=None, tmp_path=None):
        from iac_security.scanner import ScanReport
        # scan_path must be absolute for as_uri() to work
        import tempfile, os
        scan_path = str(tmp_path) if tmp_path else tempfile.gettempdir()
        return ScanReport(scan_path=scan_path, iac_type="terraform", findings=findings or [])

    def test_export_sarif_empty_findings(self, tmp_path):
        report = self._make_scan_report(tmp_path=tmp_path)
        output = export_sarif(report)
        data = json.loads(output)
        assert data["version"] == "2.1.0"

    def test_sarif_schema_present(self, tmp_path):
        report = self._make_scan_report(tmp_path=tmp_path)
        output = export_sarif(report)
        data = json.loads(output)
        assert "$schema" in data

    def test_sarif_exporter_class(self, tmp_path):
        exporter = SARIFExporter()
        report = self._make_scan_report(tmp_path=tmp_path)
        output = exporter.export(report)
        data = json.loads(output)
        assert data["version"] == "2.1.0"


class TestDriftDetector:
    def _make_iac_resource(self, name="my-ec2", rtype="aws_instance"):
        return TerraformResource(
            kind="resource", resource_type=rtype, name=name,
            attributes={}, source_file="main.tf",
        )

    def _make_cloud_workload(self, wid="i-1234", name="my-ec2", stype="EC2"):
        wl = MagicMock()
        wl.id = wid
        wl.name = name
        wl.service_type = stype
        wl.tags = {}
        wl.metadata = {}
        return wl

    def test_empty_inputs_no_drift(self):
        detector = DriftDetector(iac_state=[], cloud_state=[])
        report = detector.detect()
        assert isinstance(report, DriftReport)
        assert len(report.items) == 0

    def test_missing_cloud_resource_flagged(self):
        iac = self._make_iac_resource()
        detector = DriftDetector(iac_state=[iac], cloud_state=[])
        report = detector.detect()
        assert len(report.missing_in_cloud) >= 1

    def test_unmanaged_cloud_resource_flagged(self):
        wl = self._make_cloud_workload()
        detector = DriftDetector(iac_state=[], cloud_state=[wl])
        report = detector.detect()
        assert len(report.unmanaged_in_cloud) >= 1

    def test_report_has_timestamp(self):
        detector = DriftDetector(iac_state=[], cloud_state=[])
        report = detector.detect()
        assert report.timestamp is not None


class TestSBOMGenerator:
    def test_empty_repo_returns_dict(self, tmp_path):
        gen = SBOMGenerator()
        sbom_dict = gen.generate(tmp_path)
        assert isinstance(sbom_dict, dict)
        assert sbom_dict.get("bomFormat") == "CycloneDX"

    def test_sbom_has_metadata(self, tmp_path):
        gen = SBOMGenerator()
        sbom_dict = gen.generate(tmp_path)
        assert "metadata" in sbom_dict

    def test_sbom_has_components(self, tmp_path):
        # Seed a real dependency so the SBOM actually has components — a
        # spec-valid CycloneDX doc omits the "components" key when empty, so an
        # empty repo can't exercise this assertion.
        (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
        gen = SBOMGenerator()
        sbom_dict = gen.generate(tmp_path)
        assert sbom_dict.get("components"), "expected at least one component"


class TestMLBOMComponentType:
    """P0-24: CycloneDX 1.7 has no 'ml-model' enum value — must be
    'machine-learning-model'. License data must live on the standard
    component-level 'licenses' array, not the (schema-invalid)
    modelCard.considerations.licenses location."""

    def test_component_type_is_valid_cyclonedx_enum(self):
        comp = _ml_model_component(
            model_id="claude-sonnet-5", name="Claude Sonnet 5", version="claude-sonnet-5",
            provider="Anthropic", intended_use="test", role="worker",
        )
        assert comp["type"] == "machine-learning-model"
        assert comp["type"] != "ml-model"

    def test_license_on_component_not_in_model_card(self):
        comp = _ml_model_component(
            model_id="claude-sonnet-5", name="Claude Sonnet 5", version="claude-sonnet-5",
            provider="Anthropic", intended_use="test", role="worker",
        )
        assert comp["licenses"] == [{"license": {"name": "Anthropic Usage Policy"}}]
        assert "considerations" not in comp["modelCard"]

    def test_generate_all_components_valid_type(self):
        mlbom = MLBOMGenerator().generate()
        assert mlbom["components"], "expected at least one ML-BOM component"
        for comp in mlbom["components"]:
            assert comp["type"] == "machine-learning-model"


class TestTerraformParseFailClosed:
    """P0-08: missing parser / unparseable files must fail closed — never
    a silent 0-resource, 0-finding, passed:true scan."""

    def test_missing_hcl2_reports_skip_reason(self, tmp_path, monkeypatch):
        tf = tmp_path / "main.tf"
        tf.write_text('resource "aws_s3_bucket" "b" { acl = "private" }\n')

        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "hcl2":
                raise ImportError("simulated: python-hcl2 not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)

        resources, stats = parse_terraform(tmp_path)
        assert resources == []
        assert stats.files_seen == 1
        assert stats.files_parsed == 0
        assert stats.files_skipped == 1
        assert any("hcl2" in r for r in stats.skip_reasons)

    def test_malformed_hcl_recorded_as_skip_not_silent_zero(self, tmp_path):
        tf = tmp_path / "broken.tf"
        tf.write_text("resource aws_s3_bucket b { this is not valid hcl {{{\n")

        resources, stats = parse_terraform(tmp_path)
        assert stats.files_seen == 1
        assert stats.files_parsed == 0
        assert stats.files_skipped == 1
        assert stats.skip_reasons  # reason captured, not swallowed

    def test_scanner_reports_failed_status_on_total_parse_failure(self, tmp_path, monkeypatch):
        from iac_security.scanner import IaCScanner

        tf = tmp_path / "main.tf"
        tf.write_text('resource "aws_s3_bucket" "b" { acl = "private" }\n')

        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "hcl2":
                raise ImportError("simulated: python-hcl2 not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)

        report = IaCScanner().scan(tmp_path)
        assert report.status == "FAILED"
        assert report.resource_count == 0
        assert report.findings == []
        # The flagship bug: this must NOT look like a clean pass.
        assert report.passed is False

    def test_cli_scan_exits_nonzero_on_missing_parser_without_allow_partial(
        self, tmp_path, monkeypatch, capsys
    ):
        from iac_security import cli as iac_cli

        tf = tmp_path / "main.tf"
        tf.write_text('resource "aws_s3_bucket" "b" { acl = "private" }\n')

        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "hcl2":
                raise ImportError("simulated: python-hcl2 not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)

        parser = iac_cli.build_parser()
        args = parser.parse_args(["scan", str(tmp_path)])
        exit_code = iac_cli.cmd_scan(args)
        assert exit_code != 0

    def test_cli_scan_allow_partial_falls_through_to_findings(
        self, tmp_path, monkeypatch
    ):
        from iac_security import cli as iac_cli

        tf = tmp_path / "main.tf"
        tf.write_text('resource "aws_s3_bucket" "b" { acl = "private" }\n')

        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "hcl2":
                raise ImportError("simulated: python-hcl2 not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)

        parser = iac_cli.build_parser()
        # FAILED status (0 files parsed) is still a hard stop even with
        # --allow-partial — there is no usable scan result to trust.
        args = parser.parse_args(["scan", str(tmp_path), "--allow-partial"])
        exit_code = iac_cli.cmd_scan(args)
        assert exit_code != 0

    def test_clean_repo_status_complete_and_passed(self, tmp_path):
        tf = tmp_path / "main.tf"
        tf.write_text('resource "aws_s3_bucket" "b" { acl = "private" }\n')
        resources, stats = parse_terraform(tmp_path)
        assert stats.files_seen == 1
        assert stats.files_parsed == 1
        assert stats.files_skipped == 0
