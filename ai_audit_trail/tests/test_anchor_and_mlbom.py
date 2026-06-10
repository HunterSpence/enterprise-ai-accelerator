"""
Tests for:
  - FileAnchor (fsync'd append-only file)
  - WebhookAnchor (HTTP POST with retry, mocked)
  - MLBOMGenerator (CycloneDX 1.7 schema sanity)
"""
from __future__ import annotations

import json
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from ai_audit_trail.chain import (
    AuditChain,
    AnchorBackend,
    FileAnchor,
    WebhookAnchor,
    DecisionType,
    RiskTier,
)


# ---------------------------------------------------------------------------
# FileAnchor
# ---------------------------------------------------------------------------

class TestFileAnchor:
    """FileAnchor writes valid JSON records and fsync's them."""

    def test_creates_file_on_first_anchor(self, tmp_path):
        anchor_file = tmp_path / "anchors.log"
        backend = FileAnchor(anchor_file)
        assert not anchor_file.exists()
        backend.anchor("deadbeef" * 8, 10, "/db/path.db")
        assert anchor_file.exists()

    def test_record_is_valid_json(self, tmp_path):
        anchor_file = tmp_path / "anchors.log"
        backend = FileAnchor(anchor_file)
        root = "a" * 64
        backend.anchor(root, 42, "/db/test.db")
        line = anchor_file.read_text().strip()
        record = json.loads(line)
        assert record["merkle_root"] == root
        assert record["entry_count"] == 42
        assert record["db_path"] == "/db/test.db"
        assert record["anchor_type"] == "file"
        assert "timestamp" in record

    def test_appends_multiple_records(self, tmp_path):
        anchor_file = tmp_path / "anchors.log"
        backend = FileAnchor(anchor_file)
        for i in range(5):
            backend.anchor(f"root{i:060d}", i * 10, "/db/path.db")
        lines = [l for l in anchor_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 5
        records = [json.loads(l) for l in lines]
        assert records[0]["entry_count"] == 0
        assert records[4]["entry_count"] == 40

    def test_concurrent_writes_all_survive(self, tmp_path):
        """Multiple threads writing to the same FileAnchor must not corrupt records."""
        anchor_file = tmp_path / "concurrent.log"
        backend = FileAnchor(anchor_file)
        errors: list[Exception] = []

        def write(i: int) -> None:
            try:
                backend.anchor(f"root{i:060d}", i, "/db/concurrent.db")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=write, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Anchor errors: {errors}"
        lines = [l for l in anchor_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 20

    def test_satisfies_anchor_backend_protocol(self):
        fa = FileAnchor("/tmp/x.log")
        assert isinstance(fa, AnchorBackend)

    def test_auditchain_records_file_anchor_type(self, tmp_path):
        """When AuditChain uses FileAnchor, hourly checkpoint writes anchor_type='file'."""
        anchor_file = tmp_path / "anchors.log"
        backend = FileAnchor(anchor_file)
        chain = AuditChain(":memory:", anchor_backend=backend)
        # Seed an entry then force anchor
        chain.append(
            session_id="s1", model="claude-haiku-4-5-20251001",
            input_text="x", output_text="y",
            input_tokens=10, output_tokens=5, latency_ms=100.0,
            decision_type=DecisionType.GENERATION, risk_tier=RiskTier.MINIMAL,
            system_id="test", cost_usd=0.0001,
        )
        # Manually call to simulate hourly trigger
        chain._last_anchor_hour = -1
        chain._maybe_anchor_hourly()
        chain.close()
        # File anchor should have recorded the root
        assert anchor_file.exists()
        content = anchor_file.read_text().strip()
        assert content  # non-empty
        record = json.loads(content.splitlines()[-1])
        assert record["anchor_type"] == "file"


# ---------------------------------------------------------------------------
# WebhookAnchor
# ---------------------------------------------------------------------------

class TestWebhookAnchor:
    """WebhookAnchor POSTs valid JSON and retries on failure."""

    def test_satisfies_anchor_backend_protocol(self):
        wa = WebhookAnchor("https://example.com/anchor")
        assert isinstance(wa, AnchorBackend)

    def test_posts_correct_payload(self):
        """Successful 200 response — no retry needed."""
        root = "b" * 64
        captured: list[dict] = []

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        def fake_urlopen(req, timeout=None):
            body = json.loads(req.data.decode("utf-8"))
            captured.append(body)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            wa = WebhookAnchor("https://example.com/anchor", retries=1)
            wa.anchor(root, 99, "/db/hook.db")

        assert len(captured) == 1
        payload = captured[0]
        assert payload["merkle_root"] == root
        assert payload["entry_count"] == 99
        assert payload["anchor_type"] == "webhook"
        assert "timestamp" in payload

    def test_retries_on_network_error(self):
        """URLError triggers retry; succeeds on third attempt."""
        attempt_count = [0]
        root = "c" * 64

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        def fake_urlopen(req, timeout=None):
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise urllib.error.URLError("connection refused")
            return mock_response

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with patch("time.sleep"):  # skip actual sleep
                wa = WebhookAnchor("https://example.com/anchor", retries=3)
                wa.anchor(root, 1, "/db/hook.db")

        assert attempt_count[0] == 3

    def test_raises_after_exhausting_retries(self):
        """All retries fail → RuntimeError is raised."""
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with patch("time.sleep"):
                wa = WebhookAnchor("https://example.com/anchor", retries=2)
                with pytest.raises(RuntimeError, match="failed after 2 attempts"):
                    wa.anchor("x" * 64, 0, "/db/hook.db")

    def test_raises_on_non_2xx_response(self):
        """HTTP 500 after exhausting retries should raise RuntimeError."""
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch("time.sleep"):
                wa = WebhookAnchor("https://example.com/anchor", retries=1)
                with pytest.raises(RuntimeError):
                    wa.anchor("x" * 64, 0, "/db/hook.db")


# ---------------------------------------------------------------------------
# AuditChain — anchor_backend integration (no-backend path)
# ---------------------------------------------------------------------------

class TestAuditChainAnchorIntegration:
    """Verify AuditChain still works with no anchor_backend (default None)."""

    def test_default_no_backend_no_output(self, capsys):
        chain = AuditChain(":memory:")
        chain.append(
            session_id="s1", model="claude-haiku-4-5-20251001",
            input_text="hello", output_text="world",
            input_tokens=5, output_tokens=5, latency_ms=50.0,
            decision_type=DecisionType.GENERATION, risk_tier=RiskTier.MINIMAL,
            system_id="test", cost_usd=0.0,
        )
        chain._last_anchor_hour = -1
        chain._maybe_anchor_hourly()
        chain.close()
        captured = capsys.readouterr()
        # Old stdout placeholder must be gone
        assert "AIAuditTrail:ANCHOR" not in captured.out
        assert "stdout_placeholder" not in captured.out
        assert "ethereum" not in captured.out.lower()

    def test_public_api_unchanged(self):
        """Ensure the public chain API is not broken by anchor changes."""
        chain = AuditChain(":memory:")
        entry = chain.append(
            session_id="s1", model="claude-sonnet-4-6",
            input_text="a", output_text="b",
            input_tokens=1, output_tokens=1, latency_ms=10.0,
            decision_type=DecisionType.CLASSIFICATION, risk_tier=RiskTier.HIGH,
            system_id="sys", cost_usd=0.001,
        )
        eid = entry.entry_id  # append() returns LogEntry, not a raw string
        assert chain.count() == 1
        assert chain.get_entry(eid) is not None
        assert chain.get_merkle_root() != ""
        proof = chain.get_entry_proof(eid)
        assert proof is not None
        report = chain.verify_chain()
        assert report.is_valid
        chain.close()

    def test_file_anchor_backend_constructor_param(self, tmp_path):
        """AuditChain accepts anchor_backend kwarg without breaking."""
        backend = FileAnchor(tmp_path / "test.log")
        chain = AuditChain(":memory:", anchor_backend=backend)
        assert chain._anchor_backend is backend
        chain.close()


# ---------------------------------------------------------------------------
# MLBOMGenerator
# ---------------------------------------------------------------------------

class TestMLBOMGenerator:
    """CycloneDX 1.7 ML-BOM schema sanity checks — offline, no API calls."""

    def _gen(self) -> dict[str, Any]:
        from iac_security.sbom_generator import MLBOMGenerator
        return MLBOMGenerator().generate()

    def test_generates_valid_json_structure(self):
        mlbom = self._gen()
        # Must be serialisable
        raw = json.dumps(mlbom)
        parsed = json.loads(raw)
        assert parsed == mlbom

    def test_cyclonedx_17_spec_version(self):
        mlbom = self._gen()
        assert mlbom["bomFormat"] == "CycloneDX"
        assert mlbom["specVersion"] == "1.7"

    def test_has_serial_number(self):
        mlbom = self._gen()
        sn = mlbom.get("serialNumber", "")
        assert sn.startswith("urn:uuid:")

    def test_three_ml_model_components(self):
        mlbom = self._gen()
        components = mlbom.get("components", [])
        assert len(components) == 3

    def test_all_components_type_ml_model(self):
        mlbom = self._gen()
        for comp in mlbom["components"]:
            assert comp["type"] == "ml-model", (
                f"Component {comp.get('name')} has type {comp['type']!r}, expected 'ml-model'"
            )

    def test_all_components_have_purl(self):
        mlbom = self._gen()
        for comp in mlbom["components"]:
            purl = comp.get("purl", "")
            assert purl.startswith("pkg:mlmodel/"), (
                f"Component {comp.get('name')} has invalid PURL: {purl!r}"
            )

    def test_all_components_have_model_card(self):
        mlbom = self._gen()
        for comp in mlbom["components"]:
            assert "modelCard" in comp, f"Component {comp.get('name')} missing modelCard"

    def test_anthropic_models_present(self):
        mlbom = self._gen()
        names = {c["name"] for c in mlbom["components"]}
        assert any("Fable" in n or "fable" in n for n in names), (
            f"Expected Fable 5 in components, got: {names}"
        )
        assert any("Sonnet" in n or "sonnet" in n for n in names)
        assert any("Haiku" in n or "haiku" in n for n in names)

    def test_metadata_has_regulatory_properties(self):
        mlbom = self._gen()
        props = {p["name"]: p["value"] for p in mlbom["metadata"].get("properties", [])}
        assert "eaa:regulatory-basis" in props
        assert "EU AI Act" in props["eaa:regulatory-basis"]
        assert "eaa:nist-control" in props
        assert "GOVERN 5.2" in props["eaa:nist-control"]

    def test_each_component_has_intended_use_property(self):
        mlbom = self._gen()
        for comp in mlbom["components"]:
            prop_names = {p["name"] for p in comp.get("properties", [])}
            assert "ai:intended-use" in prop_names, (
                f"Component {comp.get('name')} missing ai:intended-use property"
            )
            assert "ai:role" in prop_names

    def test_no_duplicate_model_ids(self):
        mlbom = self._gen()
        purls = [c["purl"] for c in mlbom["components"]]
        assert len(purls) == len(set(purls)), "Duplicate PURLs in ML-BOM"

    def test_cli_mlbom_command(self, tmp_path):
        """End-to-end: python -m iac_security mlbom --output writes valid CycloneDX 1.7."""
        import sys
        sys.argv = ["python -m iac_security", "mlbom", "--output", str(tmp_path / "out.json")]
        from iac_security.cli import cmd_mlbom
        import argparse
        args = argparse.Namespace(output=str(tmp_path / "out.json"))
        rc = cmd_mlbom(args)
        assert rc == 0
        out = json.loads((tmp_path / "out.json").read_text())
        assert out["specVersion"] == "1.7"
        assert len(out["components"]) == 3
