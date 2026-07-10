"""
Tests for finops_intelligence/anomaly_detector_v2.py — P0-04 AIClient routing.

Regression coverage: explain_all() must go through core.ai_client.AIClient
(governed refusal handling + fallback chain) rather than constructing a bare
anthropic.Anthropic() client directly.

Run with:
  python -m pytest finops_intelligence/tests/test_anomaly_detector_ai_routing.py -q
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("sklearn")
pytest.importorskip("anthropic")

from finops_intelligence.anomaly_detector_v2 import (
    Anomaly,
    AnomalyDetectorV2,
    AnomalySeverity,
)
from finops_intelligence.cost_tracker import DailySpend, SpendData


def _spend_data() -> SpendData:
    rows = [DailySpend(date=date(2026, 7, 1), service="Amazon EC2", amount=100.0)]
    return SpendData(
        account_id="123",
        account_name="test",
        query_start=date(2026, 7, 1),
        query_end=date(2026, 7, 1),
        currency="USD",
        daily_rows=rows,
    )


def _anomaly() -> Anomaly:
    return Anomaly(
        detected_at=date(2026, 7, 1),
        service="Amazon EC2",
        amount=1000.0,
        baseline=100.0,
        delta=900.0,
        delta_pct=900.0,
        severity=AnomalySeverity.CRITICAL,
        confidence=0.9,
        isolation_score=-0.6,
        zscore=4.0,
    )


class TestExplainAllRoutesThroughAIClient:
    def test_no_api_key_uses_fallback_without_touching_ai_client(self, monkeypatch):
        # The constructor falls back to ANTHROPIC_API_KEY from the environment,
        # so a genuine "no key" test must clear it (CI sets a dummy key).
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        detector = AnomalyDetectorV2(anthropic_api_key="")
        anomalies = [_anomaly()]
        with patch("core.ai_client.AIClient") as mock_cls:
            result = detector.explain_all(anomalies, _spend_data())
        mock_cls.assert_not_called()
        assert result[0].explanation  # fallback text populated

    def test_explanation_populated_via_ai_client_thinking(self):
        detector = AnomalyDetectorV2(anthropic_api_key="test-key")
        anomalies = [_anomaly()]

        mock_response = type("R", (), {"text": "EC2 spend spiked due to new spot fleet."})()
        mock_instance = AsyncMock()
        mock_instance.thinking = AsyncMock(return_value=mock_response)

        with patch("core.ai_client.AIClient", return_value=mock_instance) as mock_cls:
            result = detector.explain_all(anomalies, _spend_data())

        mock_cls.assert_called_once()
        # default_model kwarg must be passed — proves routing through the
        # governed client, not a bare anthropic.Anthropic().messages.create()
        assert "default_model" in mock_cls.call_args.kwargs
        mock_instance.thinking.assert_awaited_once()
        assert result[0].explanation == "EC2 spend spiked due to new spot fleet."

    def test_ai_client_failure_falls_back_gracefully(self):
        detector = AnomalyDetectorV2(anthropic_api_key="test-key")
        anomalies = [_anomaly()]

        mock_instance = AsyncMock()
        mock_instance.thinking = AsyncMock(side_effect=RuntimeError("refusal"))

        with patch("core.ai_client.AIClient", return_value=mock_instance):
            result = detector.explain_all(anomalies, _spend_data())

        assert result[0].explanation  # fell back to the deterministic explanation
        assert "spike" in result[0].explanation.lower() or "$" in result[0].explanation
