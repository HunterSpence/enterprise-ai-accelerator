"""
anomaly_detector.py — ML anomaly detection for cloud cost data.

Two-layer detection:
  1. Isolation Forest (scikit-learn) — point anomalies per service
  2. Rolling z-score — time-series drift detection
  3. Claude (Haiku) — plain-English root cause explanation for each anomaly
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .cost_tracker import SpendData


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class AnomalySeverity(str, Enum):
    CRITICAL = "CRITICAL"   # > 3σ or > 200% spike
    HIGH = "HIGH"           # 2–3σ or 100–200% spike
    MEDIUM = "MEDIUM"       # 1.5–2σ or 50–100% spike
    LOW = "LOW"             # < 1.5σ, informational


@dataclass
class Anomaly:
    """A detected cost anomaly."""
    detected_at: date
    service: str
    amount: float           # actual spend that day
    baseline: float         # expected spend (rolling mean)
    delta: float            # amount - baseline
    delta_pct: float        # % change vs. baseline
    severity: AnomalySeverity
    confidence: float       # 0.0–1.0
    isolation_score: float  # raw Isolation Forest score (-1 to 0, lower = more anomalous)
    zscore: float           # rolling z-score
    explanation: str = ""   # Claude-generated explanation (populated on demand)
    method: str = "combined"  # "isolation_forest" | "zscore" | "combined"

    @property
    def is_spike(self) -> bool:
        return self.delta > 0

    @property
    def formatted_delta(self) -> str:
        sign = "+" if self.delta >= 0 else ""
        return f"{sign}${self.delta:,.0f} ({sign}{self.delta_pct:.1f}%)"


# ---------------------------------------------------------------------------
# AnomalyDetector
# ---------------------------------------------------------------------------

class AnomalyDetector:
    """
    Detects cost anomalies using:
    - Isolation Forest for point anomalies (service-level daily spend)
    - Rolling z-score for time series drift

    Usage:
        detector = AnomalyDetector(anthropic_api_key="sk-ant-...")
        anomalies = detector.detect(spend_data)
        explained = detector.explain_all(anomalies, spend_data)
    """

    def __init__(
        self,
        anthropic_api_key: str | None = None,
        zscore_threshold: float = 2.0,
        isolation_contamination: float = 0.05,
        rolling_window: int = 14,
        explain_top_n: int = 5,
    ) -> None:
        self.api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.zscore_threshold = zscore_threshold
        self.isolation_contamination = isolation_contamination
        self.rolling_window = rolling_window
        self.explain_top_n = explain_top_n

    # ------------------------------------------------------------------
    # Main detection pipeline
    # ------------------------------------------------------------------

    def detect(self, spend_data: SpendData) -> list[Anomaly]:
        """
        Run full anomaly detection pipeline.
        Returns anomalies sorted by severity (highest first) then delta (largest first).
        """
        if spend_data.df is None or spend_data.df.empty:
            return []

        df = spend_data.df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        all_anomalies: list[Anomaly] = []

        for service in df["service"].unique():
            svc_df = df[df["service"] == service].copy()
            svc_df = svc_df.sort_values("date").set_index("date")
            daily = svc_df["amount"].resample("D").sum().fillna(0)

            if len(daily) < 7:  # not enough data
                continue

            svc_anomalies = self._detect_service_anomalies(daily, service)
            all_anomalies.extend(svc_anomalies)

        # Sort: CRITICAL first, then by absolute delta
        severity_order = {
            AnomalySeverity.CRITICAL: 0,
            AnomalySeverity.HIGH: 1,
            AnomalySeverity.MEDIUM: 2,
            AnomalySeverity.LOW: 3,
        }
        all_anomalies.sort(
            key=lambda a: (severity_order[a.severity], -abs(a.delta))
        )

        return all_anomalies

    def detect_and_explain(
        self,
        spend_data: SpendData,
        top_n: int | None = None,
    ) -> list[Anomaly]:
        """
        Detect anomalies and explain the top-N with Claude.
        Convenient one-call API for demo use.
        """
        anomalies = self.detect(spend_data)
        n = top_n if top_n is not None else self.explain_top_n
        if self.api_key:
            explained = self.explain_all(anomalies[:n], spend_data)
            return explained + anomalies[n:]
        return anomalies

    # ------------------------------------------------------------------
    # Service-level detection
    # ------------------------------------------------------------------

    def _detect_service_anomalies(
        self,
        daily: pd.Series,
        service: str,
    ) -> list[Anomaly]:
        """Run both detectors on a single service's daily spend series."""
        anomalies: list[Anomaly] = []

        # Rolling statistics
        rolling_mean = daily.rolling(window=self.rolling_window, min_periods=3).mean()
        rolling_std = daily.rolling(window=self.rolling_window, min_periods=3).std()

        # Isolation Forest — train on all data, score each day
        iso_scores = self._run_isolation_forest(daily)

        for i, (ts, amount) in enumerate(daily.items()):
            # Skip first `rolling_window` days — insufficient baseline
            if i < self.rolling_window:
                continue

            baseline = rolling_mean.iloc[i]
            std = rolling_std.iloc[i]
            if baseline <= 0 or std <= 0:
                continue

            zscore = (amount - baseline) / std
            iso_score = iso_scores[i]

            # Anomaly if either detector fires
            is_zscore_anomaly = abs(zscore) >= self.zscore_threshold
            is_iso_anomaly = iso_score < -0.1  # negative = more anomalous

            if not (is_zscore_anomaly or is_iso_anomaly):
                continue

            delta = amount - baseline
            delta_pct = (delta / baseline * 100) if baseline > 0 else 0

            # Only flag meaningful dollar changes (> $10 or > 20%)
            if abs(delta) < 10 and abs(delta_pct) < 20:
                continue

            severity = self._classify_severity(zscore, delta_pct)
            confidence = self._compute_confidence(zscore, iso_score)
            method = "combined" if (is_zscore_anomaly and is_iso_anomaly) else (
                "zscore" if is_zscore_anomaly else "isolation_forest"
            )

            anomalies.append(Anomaly(
                detected_at=ts.date() if hasattr(ts, "date") else ts,
                service=service,
                amount=round(float(amount), 2),
                baseline=round(float(baseline), 2),
                delta=round(float(delta), 2),
                delta_pct=round(float(delta_pct), 1),
                severity=severity,
                confidence=round(confidence, 3),
                isolation_score=round(float(iso_score), 4),
                zscore=round(float(zscore), 3),
                method=method,
            ))

        return anomalies

    def _run_isolation_forest(self, daily: pd.Series) -> np.ndarray:
        """Fit Isolation Forest and return anomaly scores for each day."""
        values = daily.values.reshape(-1, 1)
        scaler = StandardScaler()
        scaled = scaler.fit_transform(values)

        iso = IsolationForest(
            contamination=self.isolation_contamination,
            random_state=42,
            n_estimators=100,
        )
        iso.fit(scaled)
        # decision_function: negative = more anomalous
        scores = iso.decision_function(scaled)
        return scores

    def _classify_severity(self, zscore: float, delta_pct: float) -> AnomalySeverity:
        abs_z = abs(zscore)
        abs_pct = abs(delta_pct)
        if abs_z >= 3.0 or abs_pct >= 200:
            return AnomalySeverity.CRITICAL
        elif abs_z >= 2.0 or abs_pct >= 100:
            return AnomalySeverity.HIGH
        elif abs_z >= 1.5 or abs_pct >= 50:
            return AnomalySeverity.MEDIUM
        return AnomalySeverity.LOW

    def _compute_confidence(self, zscore: float, iso_score: float) -> float:
        """Combine z-score and Isolation Forest into a 0–1 confidence score."""
        # Normalize z-score to 0–1 (cap at 5σ)
        z_confidence = min(abs(zscore) / 5.0, 1.0)
        # Normalize iso score: more negative = more anomalous
        iso_confidence = max(0.0, min(1.0, -iso_score / 0.5))
        # Weighted average (z-score slightly more reliable for billing data)
        return z_confidence * 0.6 + iso_confidence * 0.4

    # ------------------------------------------------------------------
    # Claude explanations
    # ------------------------------------------------------------------

    def explain_all(
        self,
        anomalies: list[Anomaly],
        spend_data: SpendData,
    ) -> list[Anomaly]:
        """Generate Claude explanations for each anomaly. Returns annotated list."""
        if not self.api_key:
            for a in anomalies:
                a.explanation = self._fallback_explanation(a)
            return anomalies

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            for a in anomalies:
                a.explanation = self._fallback_explanation(a)
            return anomalies

        explained: list[Anomaly] = []
        for anomaly in anomalies:
            context = self._build_anomaly_context(anomaly, spend_data)
            try:
                response = client.messages.create(
                    model="claude-haiku-4-5",
                    max_tokens=400,
                    system=(
                        "You are a senior FinOps engineer analyzing AWS cost anomalies. "
                        "Provide concise, specific root cause analysis in 2-4 sentences. "
                        "Name specific AWS services, deployment events, or resource patterns. "
                        "Always end with a concrete recommended action."
                    ),
                    messages=[
                        {
                            "role": "user",
                            "content": f"Explain this AWS cost anomaly and its likely root cause:\n\n{context}",
                        }
                    ],
                )
                anomaly.explanation = response.content[0].text.strip()
            except Exception as exc:
                anomaly.explanation = self._fallback_explanation(anomaly)
            explained.append(anomaly)

        return explained

    def _build_anomaly_context(self, anomaly: Anomaly, spend_data: SpendData) -> str:
        """Build structured context string for Claude."""
        # Get surrounding 7-day window for context
        window_start = anomaly.detected_at - timedelta(days=3)
        window_end = anomaly.detected_at + timedelta(days=3)

        nearby_rows = [
            r for r in spend_data.daily_rows
            if r.service == anomaly.service
            and window_start <= r.date <= window_end
        ]
        window_data = {str(r.date): f"${r.amount:,.2f}" for r in nearby_rows}

        lines = [
            f"Service: {anomaly.service}",
            f"Anomaly date: {anomaly.detected_at}",
            f"Actual spend: ${anomaly.amount:,.2f}",
            f"Expected baseline: ${anomaly.baseline:,.2f}",
            f"Delta: {anomaly.formatted_delta}",
            f"Z-score: {anomaly.zscore:.2f}",
            f"Severity: {anomaly.severity.value}",
            f"Confidence: {anomaly.confidence:.0%}",
            f"",
            f"7-day context window (service daily spend):",
        ]
        for d, v in sorted(window_data.items()):
            marker = " <<< ANOMALY" if d == str(anomaly.detected_at) else ""
            lines.append(f"  {d}: {v}{marker}")

        # Top co-spending services on anomaly day
        same_day = [
            r for r in spend_data.daily_rows
            if r.date == anomaly.detected_at and r.service != anomaly.service
        ]
        same_day.sort(key=lambda r: r.amount, reverse=True)
        if same_day:
            lines.append(f"\nOther top services on {anomaly.detected_at}:")
            for r in same_day[:5]:
                lines.append(f"  {r.service}: ${r.amount:,.2f}")

        return "\n".join(lines)

    def _fallback_explanation(self, anomaly: Anomaly) -> str:
        """Rule-based fallback when Claude API is unavailable."""
        direction = "spike" if anomaly.is_spike else "drop"
        templates = {
            "AWS Data Transfer": (
                f"Data Transfer costs {direction}d {anomaly.formatted_delta}. "
                "Likely cause: Lambda function in a retry loop generating excessive cross-AZ or "
                "internet-bound traffic, or a new cross-region replication job. "
                "Check CloudWatch Lambda error metrics and VPC Flow Logs for the anomaly window. "
                "Action: identify the top NAT Gateway consumer in the VPC."
            ),
            "Amazon EC2": (
                f"EC2 costs {direction}d {anomaly.formatted_delta}. "
                "Likely cause: Auto Scaling Group scaled out unexpectedly due to a spike in "
                "application traffic or a runaway process causing high CPU. "
                "Check EC2 Auto Scaling activity history for the anomaly date. "
                "Action: review scaling policies and set max instance count guardrail."
            ),
            "Amazon RDS": (
                f"RDS costs {direction}d {anomaly.formatted_delta}. "
                "Likely cause: a new RDS instance was provisioned, or an existing instance "
                "was upgraded to a larger class without corresponding termination of the old. "
                "Action: audit active RDS instances and terminate any idle ones (CPU < 5% for 7 days)."
            ),
            "AWS Lambda": (
                f"Lambda costs {direction}d {anomaly.formatted_delta}. "
                "Likely cause: a function entered a retry loop or was invoked at abnormally "
                "high concurrency due to an upstream event source misconfiguration. "
                "Action: check Lambda Insights for top functions by invocation count and duration."
            ),
        }
        for keyword, template in templates.items():
            if keyword in anomaly.service:
                return template

        return (
            f"{anomaly.service} costs {direction}d {anomaly.formatted_delta} "
            f"(z-score: {anomaly.zscore:.1f}, confidence: {anomaly.confidence:.0%}). "
            "Review CloudWatch metrics, deployment events, and Auto Scaling activity "
            f"around {anomaly.detected_at} to identify the root cause. "
            "Action: check if any new resources were launched or deployments occurred on this date."
        )
