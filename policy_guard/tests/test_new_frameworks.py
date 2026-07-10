"""
Tests for Colorado SB 26-189 and Texas TRAIGA framework scanners.

P0-23: both frameworks are quarantined — they previously fabricated
statutory citations (and, for Texas, a nonexistent registry URL) and
returned those as if they were a real assessment. scan() now always raises
NotImplementedError in both mock and live mode; these tests assert the
quarantine holds, not that a report comes back.

Offline only — no external dependencies, no API calls.
"""
from __future__ import annotations

import asyncio
import sys
import os

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
# Colorado SB 26-189 — quarantined
# ---------------------------------------------------------------------------

class TestColoradoSB26189Quarantined:
    """ColoradoSB26189Scanner is quarantined (P0-23) — scan() must always raise."""

    def test_import(self):
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner, ColoradoSB26189Report
        assert ColoradoSB26189Scanner is not None
        assert ColoradoSB26189Report is not None

    def test_mock_scan_raises_not_implemented(self):
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["loan-approval-v2"], mock=True)
        with pytest.raises(NotImplementedError):
            run(scanner.scan())

    def test_live_scan_raises_not_implemented(self):
        """Live mode must never silently fall back to fabricated mock data."""
        from frameworks.colorado_sb26189 import ColoradoSB26189Scanner
        scanner = ColoradoSB26189Scanner(ai_systems=["loan-approval-v2"], mock=False)
        with pytest.raises(NotImplementedError):
            run(scanner.scan())

    def test_no_fake_url_or_live_scan_path(self):
        """The module must not contain the fabricated txag-style claims or a
        working mock-scan implementation to fall back to."""
        import frameworks.colorado_sb26189 as mod
        assert not hasattr(mod.ColoradoSB26189Scanner, "_mock_scan")
        assert not hasattr(mod.ColoradoSB26189Scanner, "_live_scan")

    def test_control_sections_scrubbed(self):
        """Fabricated statutory citations must be removed, not merely unused."""
        from frameworks.colorado_sb26189 import ALL_CONTROLS
        for ctrl in ALL_CONTROLS.values():
            assert ctrl["section"] == "UNVERIFIED"


# ---------------------------------------------------------------------------
# Texas TRAIGA — quarantined
# ---------------------------------------------------------------------------

class TestTexasTRAIGAQuarantined:
    """TexasTRAIGAScanner is quarantined (P0-23) — scan() must always raise."""

    def test_import(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner, TexasTRAIGAReport
        assert TexasTRAIGAScanner is not None
        assert TexasTRAIGAReport is not None

    def test_mock_scan_raises_not_implemented(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=["fraud-detection-v3"], mock=True)
        with pytest.raises(NotImplementedError):
            run(scanner.scan())

    def test_live_scan_raises_not_implemented(self):
        from frameworks.texas_traiga import TexasTRAIGAScanner
        scanner = TexasTRAIGAScanner(ai_systems=["fraud-detection-v3"], mock=False)
        with pytest.raises(NotImplementedError):
            run(scanner.scan())

    def test_no_fake_url_or_live_scan_path(self):
        import frameworks.texas_traiga as mod
        assert not hasattr(mod.TexasTRAIGAScanner, "_mock_scan")
        assert not hasattr(mod.TexasTRAIGAScanner, "_live_scan")

    def test_no_registry_url_in_source(self):
        """The fabricated txag.gov/AI-registry URL must be gone entirely."""
        import inspect
        import frameworks.texas_traiga as mod
        source = inspect.getsource(mod)
        assert "txag.gov" not in source

    def test_control_sections_scrubbed(self):
        from frameworks.texas_traiga import ALL_CONTROLS
        for ctrl in ALL_CONTROLS.values():
            assert ctrl["section"] == "UNVERIFIED"


# ---------------------------------------------------------------------------
# Scanner integration — both frameworks registered but off by default
# ---------------------------------------------------------------------------

class TestScannerIntegration:
    """Verify Colorado SB 26-189 + Texas TRAIGA are wired into the main
    scanner but quarantined (disabled by default, non-fatal if forced on)."""

    def _load_scanner_module(self):
        import importlib.util
        scanner_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, scanner_dir)
        import policy_guard.scanner as sc
        return sc

    def test_scan_config_new_frameworks_off_by_default(self):
        """P0-23: quarantined frameworks must not run in a routine scan."""
        sc = self._load_scanner_module()
        cfg = sc.ScanConfig()
        assert hasattr(cfg, "run_colorado_sb26189")
        assert hasattr(cfg, "run_texas_traiga")
        assert cfg.run_colorado_sb26189 is False
        assert cfg.run_texas_traiga is False

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

    def test_default_scan_completes_without_quarantined_frameworks(self):
        """A routine scan must succeed even though these two are wired in."""
        sc = self._load_scanner_module()
        report = run(sc.ComplianceScanner(sc.ScanConfig()).scan())
        assert report.colorado_sb26189 is None
        assert report.texas_traiga is None
        assert report.overall_score > 0

    def test_forcing_quarantined_frameworks_on_does_not_crash_scan(self):
        """If an operator explicitly re-enables a quarantined framework, the
        scan must not blow up — it just comes back absent from the report."""
        sc = self._load_scanner_module()
        cfg = sc.ScanConfig(run_colorado_sb26189=True, run_texas_traiga=True)
        report = run(sc.ComplianceScanner(cfg).scan())
        assert report.colorado_sb26189 is None
        assert report.texas_traiga is None
