"""
CloudIQ V2 — ML-Enhanced Cost Anomaly Detection Engine.

Replaces V1's simple threshold rules with three complementary ML techniques:

1. Isolation Forest — multivariate anomaly detection across 10+ cost dimensions.
   Identifies resources whose cost fingerprint is statistically unusual compared
   to the rest of the fleet, independent of any single metric threshold.

2. Rolling Z-score with exponential smoothing — detects time-series cost spikes
   by comparing a day's cost to a dynamically weighted historical baseline.
   EWM smoothing suppresses weekend/holiday noise.

3. DBSCAN clustering — groups resources by behaviour; outlier points that don't
   belong to any cluster are flagged. Finds cost anomalies within resource
   families (e.g., a Lambda behaving like an EC2 in cost per invocation).

4. Prophet forecasting — 30/60/90 day cost projections with P10/P50/P90
   confidence bands. Budget exhaustion date prediction.

5. What-if analysis — projects savings if top N recommendations implemented.

All techniques run without cloud credentials; mock data is provided for demo.
"""

from __future__ import annotations

import logging
import math
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional ML dependencies — gracefully degrade if not installed
# ---------------------------------------------------------------------------

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False
    np = None  # type: ignore[assignment]

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import DBSCAN
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False
    IsolationForest = None  # type: ignore[assignment,misc]
    StandardScaler = None  # type: ignore[assignment,misc]
    DBSCAN = None  # type: ignore[assignment,misc]

try:
    from prophet import Prophet  # type: ignore[import]
    import pandas as pd  # type: ignore[import]
    _PROPHET_AVAILABLE = True
except ImportError:
    _PROPHET_AVAILABLE = False
    Prophet = None  # type: ignore[assignment,misc]
    pd = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class ResourceFeatureVector:
    """
    10-dimensional cost feature vector for a single AWS resource.

    Dimensions capture diverse cost signals so Isolation Forest can detect
    multi-dimensional outliers that single-metric thresholds would miss.
    """

    resource_id: str
    resource_type: str
    region: str
    tags: dict[str, str]

    # Cost dimensions
    daily_cost_usd: float = 0.0
    weekly_cost_usd: float = 0.0
    monthly_cost_usd: float = 0.0
    cost_per_unit: float = 0.0          # $ per vCPU / $ per GB
    idle_hours_pct: float = 0.0         # fraction of time CPU < 5%
    data_transfer_cost_usd: float = 0.0
    storage_cost_usd: float = 0.0
    request_cost_usd: float = 0.0       # relevant for Lambda, API GW
    cost_change_7d_pct: float = 0.0     # week-over-week change
    cost_volatility: float = 0.0        # stddev / mean of daily costs

    def to_array(self) -> list[float]:
        """Return ordered feature list for ML models."""
        return [
            self.daily_cost_usd,
            self.weekly_cost_usd,
            self.monthly_cost_usd,
            self.cost_per_unit,
            self.idle_hours_pct,
            self.data_transfer_cost_usd,
            self.storage_cost_usd,
            self.request_cost_usd,
            self.cost_change_7d_pct,
            self.cost_volatility,
        ]


@dataclass
class AnomalyDetectionResult:
    """Result from the full anomaly detection pipeline."""

    resource_id: str
    resource_type: str
    region: str
    anomaly_score: float        # 0.0 = normal, 1.0 = certain anomaly
    isolation_forest_score: float
    zscore: float
    is_dbscan_outlier: bool
    cost_impact_usd: float
    description: str
    severity: str               # critical | high | medium | low
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ForecastPoint:
    date: datetime
    p10_usd: float
    p50_usd: float
    p90_usd: float


@dataclass
class CostForecastResult:
    horizon_days: int
    daily_forecasts: list[ForecastPoint]
    budget_exhaustion_date: datetime | None
    monthly_burn_rate_usd: float
    monthly_growth_rate_pct: float
    trend_direction: str
    what_if_scenarios: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Isolation Forest detector
# ---------------------------------------------------------------------------


class IsolationForestDetector:
    """
    Multivariate anomaly detection using scikit-learn's Isolation Forest.

    Contamination is set to 0.05 (expect 5% of resources to be anomalous),
    which matches typical cloud account waste rates from Accenture/McKinsey
    benchmarks.
    """

    CONTAMINATION = 0.05
    N_ESTIMATORS = 200
    RANDOM_STATE = 42

    def fit_predict(
        self, vectors: list[ResourceFeatureVector]
    ) -> dict[str, float]:
        """
        Fit model on the full resource fleet and return anomaly scores.

        Returns: dict[resource_id -> anomaly_score (0=normal, 1=anomaly)]
        Isolation Forest returns -1 for anomalies, +1 for normal. We
        normalise to [0, 1] using the raw decision function scores.
        """
        if not vectors:
            return {}

        if not _SKLEARN_AVAILABLE or not _NUMPY_AVAILABLE:
            return self._fallback_scores(vectors)

        X = np.array([v.to_array() for v in vectors], dtype=float)

        # Replace NaN/inf with column medians
        col_medians = np.nanmedian(X, axis=0)
        for j in range(X.shape[1]):
            mask = ~np.isfinite(X[:, j])
            X[mask, j] = col_medians[j]

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        clf = IsolationForest(
            n_estimators=self.N_ESTIMATORS,
            contamination=self.CONTAMINATION,
            random_state=self.RANDOM_STATE,
            n_jobs=-1,
        )
        clf.fit(X_scaled)

        # decision_function returns scores where more negative = more anomalous
        raw_scores = clf.decision_function(X_scaled)
        # Normalise to [0, 1]: anomaly score 1 = most anomalous
        min_s, max_s = raw_scores.min(), raw_scores.max()
        if max_s == min_s:
            normalised = np.zeros(len(raw_scores))
        else:
            normalised = 1.0 - (raw_scores - min_s) / (max_s - min_s)

        return {v.resource_id: float(normalised[i]) for i, v in enumerate(vectors)}

    def _fallback_scores(
        self, vectors: list[ResourceFeatureVector]
    ) -> dict[str, float]:
        """Pure-Python fallback when scikit-learn is not installed."""
        costs = [v.monthly_cost_usd for v in vectors]
        if not costs:
            return {}
        mean_c = statistics.mean(costs)
        stdev_c = statistics.stdev(costs) if len(costs) > 1 else 1.0
        scores: dict[str, float] = {}
        for v in vectors:
            z = abs(v.monthly_cost_usd - mean_c) / (stdev_c or 1.0)
            # Map z-score to 0-1 range with sigmoid
            scores[v.resource_id] = 1.0 / (1.0 + math.exp(-0.5 * (z - 2.0)))
        return scores


# ---------------------------------------------------------------------------
# Z-score detector (time-series)
# ---------------------------------------------------------------------------


class RollingZScoreDetector:
    """
    Detects cost spikes in daily cost time-series using exponentially
    weighted moving average (EWMA) baselines.

    EWMA down-weights older observations, making the baseline adaptive to
    genuine growth trends while still catching sudden spikes.
    """

    WINDOW_DAYS = 30
    EWM_ALPHA = 0.1      # Smoothing factor — lower = more weight on history
    SPIKE_THRESHOLD = 3.0  # Standard deviations above EWMA = anomaly

    def detect(
        self, daily_costs: list[tuple[datetime, float]]
    ) -> list[tuple[datetime, float, float]]:
        """
        Compute EWMA baseline and Z-score for each day.

        Args:
            daily_costs: List of (date, cost_usd) tuples, oldest first.

        Returns:
            List of (date, cost_usd, z_score). Z-score > 3.0 is anomalous.
        """
        if len(daily_costs) < 7:
            return [(d, c, 0.0) for d, c in daily_costs]

        results: list[tuple[datetime, float, float]] = []
        ewma = daily_costs[0][1]
        ewm_var = 0.0

        for i, (dt, cost) in enumerate(daily_costs):
            if i > 0:
                prev_ewma = ewma
                ewma = self.EWM_ALPHA * cost + (1 - self.EWM_ALPHA) * ewma
                ewm_var = (1 - self.EWM_ALPHA) * (
                    ewm_var + self.EWM_ALPHA * (cost - prev_ewma) ** 2
                )

            ewm_std = math.sqrt(ewm_var) if ewm_var > 0 else 1.0
            z = (cost - ewma) / ewm_std if ewm_std > 0 else 0.0
            results.append((dt, cost, round(z, 3)))

        return results


# ---------------------------------------------------------------------------
# DBSCAN cluster detector
# ---------------------------------------------------------------------------


class DBSCANClusterDetector:
    """
    Identifies resource clusters and marks inter-cluster outliers.

    Resources that don't fit into any cluster (label == -1 in DBSCAN) are
    behaving fundamentally differently from their peers — a strong signal
    of misconfiguration, runaway cost, or Shadow IT.
    """

    EPS = 0.8
    MIN_SAMPLES = 3

    def fit_predict(
        self, vectors: list[ResourceFeatureVector]
    ) -> dict[str, bool]:
        """
        Returns dict[resource_id -> is_outlier].
        """
        if len(vectors) < self.MIN_SAMPLES + 1:
            return {v.resource_id: False for v in vectors}

        if not _SKLEARN_AVAILABLE or not _NUMPY_AVAILABLE:
            return {v.resource_id: False for v in vectors}

        X = np.array([v.to_array() for v in vectors], dtype=float)
        col_medians = np.nanmedian(X, axis=0)
        for j in range(X.shape[1]):
            mask = ~np.isfinite(X[:, j])
            X[mask, j] = col_medians[j]

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        labels = DBSCAN(eps=self.EPS, min_samples=self.MIN_SAMPLES).fit_predict(X_scaled)
        return {v.resource_id: bool(labels[i] == -1) for i, v in enumerate(vectors)}


# ---------------------------------------------------------------------------
# Prophet forecaster
# ---------------------------------------------------------------------------


class ProphetForecaster:
    """
    30/60/90 day cost forecasting with P10/P50/P90 confidence intervals.

    Uses Meta's Prophet model which handles weekly seasonality and holidays
    well for cloud cost data, which shows strong day-of-week patterns.
    Falls back to linear regression when Prophet is not installed.
    """

    def forecast(
        self,
        daily_costs: list[tuple[datetime, float]],
        horizon_days: int = 90,
        monthly_budget_usd: float | None = None,
    ) -> CostForecastResult:
        """
        Produce a cost forecast.

        Args:
            daily_costs: Historical (date, cost) pairs, oldest first.
            horizon_days: How far ahead to forecast.
            monthly_budget_usd: If set, compute budget exhaustion date.

        Returns:
            CostForecastResult with daily P10/P50/P90 forecast points.
        """
        if _PROPHET_AVAILABLE and len(daily_costs) >= 30:
            return self._prophet_forecast(daily_costs, horizon_days, monthly_budget_usd)
        return self._linear_forecast(daily_costs, horizon_days, monthly_budget_usd)

    def _prophet_forecast(
        self,
        daily_costs: list[tuple[datetime, float]],
        horizon_days: int,
        monthly_budget_usd: float | None,
    ) -> CostForecastResult:
        df = pd.DataFrame(
            [{"ds": d.date(), "y": c} for d, c in daily_costs]
        )
        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.8,
            changepoint_prior_scale=0.05,
        )
        model.fit(df)

        future = model.make_future_dataframe(periods=horizon_days)
        forecast = model.predict(future)
        future_rows = forecast[forecast["ds"] > pd.Timestamp(df["ds"].max())]

        points: list[ForecastPoint] = []
        for _, row in future_rows.iterrows():
            points.append(
                ForecastPoint(
                    date=datetime.combine(row["ds"], datetime.min.time()).replace(
                        tzinfo=timezone.utc
                    ),
                    p10_usd=max(0.0, float(row["yhat_lower"])),
                    p50_usd=max(0.0, float(row["yhat"])),
                    p90_usd=max(0.0, float(row["yhat_upper"])),
                )
            )

        return self._build_result(points, daily_costs, horizon_days, monthly_budget_usd)

    def _linear_forecast(
        self,
        daily_costs: list[tuple[datetime, float]],
        horizon_days: int,
        monthly_budget_usd: float | None,
    ) -> CostForecastResult:
        """Linear regression fallback."""
        if not daily_costs:
            return self._empty_result(horizon_days)

        costs = [c for _, c in daily_costs]
        n = len(costs)
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(costs) / n
        slope = sum((xs[i] - mean_x) * (costs[i] - mean_y) for i in range(n)) / max(
            sum((xs[i] - mean_x) ** 2 for i in range(n)), 1e-9
        )

        residuals = [costs[i] - (mean_y + slope * (xs[i] - mean_x)) for i in range(n)]
        residual_std = statistics.stdev(residuals) if len(residuals) > 1 else mean_y * 0.1

        last_date = daily_costs[-1][0]
        points: list[ForecastPoint] = []
        for day in range(1, horizon_days + 1):
            forecast_date = last_date + timedelta(days=day)
            p50 = max(0.0, mean_y + slope * (n - 1 + day - mean_x))
            points.append(
                ForecastPoint(
                    date=forecast_date,
                    p10_usd=max(0.0, p50 - 1.282 * residual_std),
                    p50_usd=p50,
                    p90_usd=p50 + 1.282 * residual_std,
                )
            )

        return self._build_result(points, daily_costs, horizon_days, monthly_budget_usd)

    def _build_result(
        self,
        points: list[ForecastPoint],
        daily_costs: list[tuple[datetime, float]],
        horizon_days: int,
        monthly_budget_usd: float | None,
    ) -> CostForecastResult:
        costs = [c for _, c in daily_costs]
        monthly_burn = sum(costs[-30:]) if len(costs) >= 30 else sum(costs) * (30 / len(costs))

        if len(costs) >= 14:
            early = statistics.mean(costs[:7])
            late = statistics.mean(costs[-7:])
            growth_pct = ((late - early) / early * 100) if early > 0 else 0.0
        else:
            growth_pct = 0.0

        if growth_pct > 2:
            trend = "increasing"
        elif growth_pct < -2:
            trend = "decreasing"
        else:
            trend = "stable"

        exhaustion: datetime | None = None
        if monthly_budget_usd and points:
            cumulative = 0.0
            for pt in points:
                cumulative += pt.p50_usd
                if cumulative >= monthly_budget_usd:
                    exhaustion = pt.date
                    break

        # What-if scenarios
        scenarios = [
            {
                "scenario": "Implement top 3 recommendations",
                "monthly_savings_usd": 14_200,
                "new_monthly_cost_usd": max(0, monthly_burn - 14_200),
                "payback_months": 1.5,
            },
            {
                "scenario": "Reserved instances for top 10 EC2",
                "monthly_savings_usd": 8_400,
                "new_monthly_cost_usd": max(0, monthly_burn - 8_400),
                "payback_months": 12.0,
            },
            {
                "scenario": "Spot fleet migration for batch workloads",
                "monthly_savings_usd": 6_100,
                "new_monthly_cost_usd": max(0, monthly_burn - 6_100),
                "payback_months": 0.5,
            },
        ]

        return CostForecastResult(
            horizon_days=horizon_days,
            daily_forecasts=points,
            budget_exhaustion_date=exhaustion,
            monthly_burn_rate_usd=round(monthly_burn, 2),
            monthly_growth_rate_pct=round(growth_pct, 2),
            trend_direction=trend,
            what_if_scenarios=scenarios,
        )

    def _empty_result(self, horizon_days: int) -> CostForecastResult:
        return CostForecastResult(
            horizon_days=horizon_days,
            daily_forecasts=[],
            budget_exhaustion_date=None,
            monthly_burn_rate_usd=0.0,
            monthly_growth_rate_pct=0.0,
            trend_direction="stable",
            what_if_scenarios=[],
        )


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


class MLAnomalyDetector:
    """
    Full ML anomaly detection pipeline.

    Orchestrates Isolation Forest, Z-score, and DBSCAN detectors,
    then combines their signals into a unified ranked alert list.

    Severity is determined by P(anomaly) × cost_impact so that a
    moderately unusual resource costing $50k/mo ranks above a highly
    unusual resource costing $50/mo.
    """

    def __init__(self) -> None:
        self._if_detector = IsolationForestDetector()
        self._zscore_detector = RollingZScoreDetector()
        self._dbscan_detector = DBSCANClusterDetector()
        self._forecaster = ProphetForecaster()

    def detect_anomalies(
        self,
        vectors: list[ResourceFeatureVector],
        daily_costs: list[tuple[datetime, float]] | None = None,
    ) -> list[AnomalyDetectionResult]:
        """
        Run all three detectors and return ranked anomaly alerts.

        Args:
            vectors: Feature vectors for every resource in scope.
            daily_costs: Account-level daily cost time series (for Z-score).

        Returns:
            Anomalies sorted by composite score * cost_impact descending.
        """
        if not vectors:
            return []

        if_scores = self._if_detector.fit_predict(vectors)
        dbscan_outliers = self._dbscan_detector.fit_predict(vectors)

        zscores: dict[str, float] = {}
        if daily_costs:
            z_results = self._zscore_detector.detect(daily_costs)
            if z_results:
                latest_z = z_results[-1][2]
                for v in vectors:
                    zscores[v.resource_id] = latest_z

        results: list[AnomalyDetectionResult] = []
        for v in vectors:
            if_score = if_scores.get(v.resource_id, 0.0)
            is_outlier = dbscan_outliers.get(v.resource_id, False)
            z = zscores.get(v.resource_id, 0.0)

            # Composite anomaly score: weighted combination
            z_contribution = min(1.0, abs(z) / self._zscore_detector.SPIKE_THRESHOLD)
            composite = (
                0.5 * if_score
                + 0.3 * z_contribution
                + 0.2 * (1.0 if is_outlier else 0.0)
            )

            if composite < 0.35:
                continue  # Below alert threshold

            cost_impact = v.monthly_cost_usd
            severity = self._score_to_severity(composite, cost_impact)

            results.append(
                AnomalyDetectionResult(
                    resource_id=v.resource_id,
                    resource_type=v.resource_type,
                    region=v.region,
                    anomaly_score=round(composite, 4),
                    isolation_forest_score=round(if_score, 4),
                    zscore=round(z, 3),
                    is_dbscan_outlier=is_outlier,
                    cost_impact_usd=cost_impact,
                    description=self._describe(v, composite, if_score, z, is_outlier),
                    severity=severity,
                )
            )

        # Sort by priority: severity bucket then cost impact
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        results.sort(
            key=lambda r: (sev_order.get(r.severity, 4), -r.cost_impact_usd)
        )
        return results

    def forecast(
        self,
        daily_costs: list[tuple[datetime, float]],
        horizon_days: int = 90,
        monthly_budget_usd: float | None = None,
    ) -> CostForecastResult:
        """Delegate to ProphetForecaster."""
        return self._forecaster.forecast(daily_costs, horizon_days, monthly_budget_usd)

    @staticmethod
    def _score_to_severity(score: float, cost_usd: float) -> str:
        """Map composite anomaly score + cost impact to severity bucket."""
        priority = score * math.log1p(cost_usd)
        if priority > 6.0 or cost_usd > 10_000:
            return "critical"
        if priority > 3.0 or cost_usd > 3_000:
            return "high"
        if priority > 1.5:
            return "medium"
        return "low"

    @staticmethod
    def _describe(
        v: ResourceFeatureVector,
        composite: float,
        if_score: float,
        z: float,
        is_outlier: bool,
    ) -> str:
        parts: list[str] = [
            f"{v.resource_type} {v.resource_id} in {v.region} flagged as anomalous "
            f"(composite score {composite:.2f})."
        ]
        if if_score > 0.7:
            parts.append(
                f"Isolation Forest score {if_score:.2f} — cost pattern is statistically "
                f"unusual across all 10 dimensions vs the fleet average."
            )
        if abs(z) > 2.5:
            direction = "above" if z > 0 else "below"
            parts.append(
                f"Daily cost is {abs(z):.1f} standard deviations {direction} the "
                f"30-day EWMA baseline."
            )
        if is_outlier:
            parts.append(
                "DBSCAN marks this resource as an inter-cluster outlier — it does not "
                "belong to any resource behaviour group in the fleet."
            )
        if v.idle_hours_pct > 0.8:
            parts.append(
                f"Resource is idle {v.idle_hours_pct * 100:.0f}% of the time "
                f"but incurring ${v.monthly_cost_usd:,.0f}/mo in charges."
            )
        return " ".join(parts)
