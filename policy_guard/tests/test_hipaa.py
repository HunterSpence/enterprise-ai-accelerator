"""
Tests for policy_guard/frameworks/hipaa.py

P0-22: HIPAAScanner(mock=False) with no evidence must never report every
control as PASS (was: state.get(control_id, True) — missing evidence
defaulted to compliant, so an empty scan silently scored 100%). Missing
evidence in live mode must produce NOT_ASSESSED, never PASS.

Offline only — no external dependencies, no API calls.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestHIPAAFailClosed:
    def test_live_empty_evidence_is_not_assessed_not_pass(self):
        from frameworks.hipaa import HIPAAScanner
        scanner = HIPAAScanner(mock=False)
        report = run(scanner.scan())
        statuses = {f.status for f in report.findings}
        # Every control has no evidence in live mode with an empty state —
        # none of them may be silently marked PASS.
        assert "PASS" not in statuses
        assert statuses == {"NOT_ASSESSED"}

    def test_live_empty_evidence_never_scores_100_percent(self):
        from frameworks.hipaa import HIPAAScanner
        scanner = HIPAAScanner(mock=False)
        report = run(scanner.scan())
        assert report.compliance_score < 100.0

    def test_live_empty_evidence_scores_zero(self):
        """No evidence at all -> 0% readiness, not the old silent 100%."""
        from frameworks.hipaa import HIPAAScanner
        scanner = HIPAAScanner(mock=False)
        report = run(scanner.scan())
        assert report.compliance_score == 0.0

    def test_not_assessed_controls_not_counted_as_findings(self):
        """NOT_ASSESSED is a control-mapping gap, distinct from a FAIL finding."""
        from frameworks.hipaa import HIPAAScanner
        scanner = HIPAAScanner(mock=False)
        report = run(scanner.scan())
        assert report.total_findings == 0
        assert report.not_assessed_count == len(report.findings)

    def test_mock_mode_unaffected(self):
        """Mock mode still uses the explicit demo state dict (unchanged behavior)."""
        from frameworks.hipaa import HIPAAScanner, MOCK_HIPAA_STATE
        scanner = HIPAAScanner(mock=True)
        report = run(scanner.scan())
        expected_fail = sum(1 for v in MOCK_HIPAA_STATE.values() if not v)
        assert report.total_findings == expected_fail
        assert report.compliance_score < 100.0

    def test_finding_status_is_one_of_three_valid_values(self):
        """Documents the three-way status contract: PASS / FAIL / NOT_ASSESSED."""
        from frameworks.hipaa import HIPAAScanner
        scanner = HIPAAScanner(mock=False)
        report = run(scanner.scan())
        for f in report.findings:
            assert f.status in ("PASS", "FAIL", "NOT_ASSESSED")
