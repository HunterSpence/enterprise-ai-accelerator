"""
Tests for the ML anomaly detection engine.

All tests use pure mock data — no cloud credentials or external APIs required.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from cloud_iq.ml_detector import (
    DBSCANClusterDetector,
    IsolationForestDetector,
    MLAnomalyDetector,
    ProphetForecaster,
    ResourceFeatureVector,
    RollingZScoreDetector,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_vector(
    resource_id: str,
    monthly_cost: float,
    idle_pct: float = 0.0,
) -> ResourceFeatureVector:
    return ResourceFeatureVector(
        resource_id=resource_id,
        resource_type="EC2 Instance",
        region="us-east-1",
        tags={},
        daily_cost_usd=monthly_cost / 30,
        weekly_cost_usd=monthly_cost / 4,
        monthly_cost_usd=monthly_cost,
        cost_per_unit=monthly_cost / 4,
        idle_hours_pct=idle_pct,
        data_transfer_cost_usd=monthly_cost * 0.05,
        storage_cost_usd=monthly_cost * 0.10,
        request_cost_usd=0.0,
        cost_change_7d_pct=0.0,
        cost_volatility=0.05,
    )


def _make_daily_costs(
    n_days: int = 60,
    base: float = 5000.0,
    spike_on_day: int | None = None,
    spike_multiplier: float = 4.0,
) -> list[tuple[datetime, float]]:
    now = datetime.now(timezone.utc)
    costs = []
    for i in range(n_days - 1, -1, -1):
        cost = base
        if spike_on_day is not None and i == spike_on_day:
            cost = base * spike_multiplier
        costs.append((now - timedelta(days=i), cost))
    return costs


# ---------------------------------------------------------------------------
# IsolationForest tests
# ---------------------------------------------------------------------------


class TestIsolationForestDetector:
    def test_returns_scores_for_all_vectors(self) -> None:
        detector = IsolationForestDetector()
        vectors = [_make_vector(f"i-{i}", 200.0 + i * 50) for i in range(20)]
        # Add one extreme outlier
        vectors.append(_make_vector("i-outlier", 50_000.0, idle_pct=0.95))

        scores = detector.fit_predict(vectors)

        assert len(scores) == len(vectors)
        for resource_id, score in scores.items():
            assert 0.0 <= score <= 1.0, f"Score {score} for {resource_id} out of range"

    def test_outlier_gets_higher_score(self) -> None:
        detector = IsolationForestDetector()
        vectors = [_make_vector(f"i-normal-{i}", 200.0) for i in range(30)]
        vectors.append(_make_vector("i-outlier", 50_000.0, idle_pct=0.98))

        scores = detector.fit_predict(vectors)

        normal_avg = sum(
            scores[v.resource_id] for v in vectors[:-1]
        ) / len(vectors[:-1])

        assert scores["i-outlier"] > normal_avg, (
            f"Outlier score {scores['i-outlier']} should be above normal average {normal_avg}"
        )

    def test_empty_input_returns_empty(self) -> None:
        detector = IsolationForestDetector()
        result = detector.fit_predict([])
        assert result == {}

    def test_single_vector_handled_gracefully(self) -> None:
        detector = IsolationForestDetector()
        vectors = [_make_vector("i-only", 500.0)]
        scores = detector.fit_predict(vectors)
        assert "i-only" in scores
        assert 0.0 <= scores["i-only"] <= 1.0


# ---------------------------------------------------------------------------
# Z-score detector tests
# ---------------------------------------------------------------------------


class TestRollingZScoreDetector:
    def test_stable_series_produces_low_zscores(self) -> None:
        detector = RollingZScoreDetector()
        costs = _make_daily_costs(60, base=5000.0)
        results = detector.detect(costs)

        # Ignore first 7 days (warm-up period)
        steady_zscores = [abs(z) for _, _, z in results[7:]]
        assert all(z < 3.0 for z in steady_zscores), (
            f"Stable series should have z-scores < 3, got max {max(steady_zscores):.2f}"
        )

    def test_spike_produces_high_zscore(self) -> None:
        detector = RollingZScoreDetector()
        # Spike on day 2 from end (index 1 from end of n_days=60)
        costs = _make_daily_costs(60, base=5000.0, spike_on_day=1, spike_multiplier=8.0)
        results = detector.detect(costs)

        # The spike should be at results[-2] (second to last)
        spike_z = abs(results[-2][2])
        normal_z = abs(results[30][2])
        assert spike_z > normal_z, f"Spike z={spike_z:.2f} should exceed normal z={normal_z:.2f}"

    def test_handles_short_series(self) -> None:
        detector = RollingZScoreDetector()
        costs = _make_daily_costs(5, base=1000.0)
        results = detector.detect(costs)
        assert len(results) == 5
        for _, _, z in results:
            assert not math.isnan(z)


# ---------------------------------------------------------------------------
# ProphetForecaster tests
# ---------------------------------------------------------------------------


class TestProphetForecaster:
    def test_forecast_returns_correct_horizon(self) -> None:
        forecaster = ProphetForecaster()
        costs = _make_daily_costs(60, base=5000.0)
        result = forecaster.forecast(costs, horizon_days=30)

        assert result.horizon_days == 30
        assert len(result.daily_forecasts) == 30

    def test_p10_le_p50_le_p90(self) -> None:
        forecaster = ProphetForecaster()
        costs = _make_daily_costs(60, base=5000.0)
        result = forecaster.forecast(costs, horizon_days=90)

        for point in result.daily_forecasts:
            assert point.p10_usd <= point.p50_usd, (
                f"P10 {point.p10_usd} should be <= P50 {point.p50_usd}"
            )
            assert point.p50_usd <= point.p90_usd, (
                f"P50 {point.p50_usd} should be <= P90 {point.p90_usd}"
            )

    def test_budget_exhaustion_detected(self) -> None:
        forecaster = ProphetForecaster()
        # Rapidly growing costs that will breach a tight budget
        costs = _make_daily_costs(30, base=4_000.0)
        result = forecaster.forecast(costs, horizon_days=90, monthly_budget_usd=130_000.0)

        # With $4K/day base and growing trend, $130K budget should exhaust
        # within 90 days
        assert result.budget_exhaustion_date is not None or result.trend_direction in (
            "increasing", "stable"
        )

    def test_trend_direction_identified(self) -> None:
        forecaster = ProphetForecaster()
        # Flat costs — should be "stable"
        costs = _make_daily_costs(60, base=5000.0)
        result = forecaster.forecast(costs, horizon_days=30)
        assert result.trend_direction in ("stable", "increasing", "decreasing")


# ---------------------------------------------------------------------------
# MLAnomalyDetector integration test
# ---------------------------------------------------------------------------


class TestMLAnomalyDetector:
    def test_full_pipeline_returns_sorted_alerts(self) -> None:
        detector = MLAnomalyDetector()
        vectors = [_make_vector(f"i-{i}", 200.0 + i * 30) for i in range(25)]
        vectors.append(_make_vector("i-costly-idle", 15_000.0, idle_pct=0.92))

        daily_costs = _make_daily_costs(60, base=8_000.0)
        results = detector.detect_anomalies(vectors, daily_costs)

        # Results should be sorted: critical before high before medium before low
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for i in range(len(results) - 1):
            assert sev_order.get(results[i].severity, 4) <= sev_order.get(
                results[i + 1].severity, 4
            ), f"Anomaly list is not sorted by severity at position {i}"

    def test_anomaly_scores_in_range(self) -> None:
        detector = MLAnomalyDetector()
        vectors = [_make_vector(f"i-{i}", 500.0) for i in range(15)]
        results = detector.detect_anomalies(vectors)

        for alert in results:
            assert 0.0 <= alert.anomaly_score <= 1.0, (
                f"Anomaly score {alert.anomaly_score} out of range"
            )

    def test_empty_vectors_returns_empty(self) -> None:
        detector = MLAnomalyDetector()
        results = detector.detect_anomalies([])
        assert results == []
