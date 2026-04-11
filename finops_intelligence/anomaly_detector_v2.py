"""
anomaly_detector_v2.py — Ensemble anomaly detection for FinOps Intelligence V2.

Three-method ensemble:
  1. Isolation Forest (multivariate, service-level)
  2. Rolling Z-score with exponential moving average baseline (time-series aware)
  3. LSTM autoencoder (optional, lazy-loaded — improves seasonal pattern detection)

New in V2:
  - Root cause attribution: "driven by 847 new spot instances in us-east-1"
  - Correlation detection: co-moving services flagged as related
  - Suppression rules: known events do not re-alert
  - PagerDuty-ready alert payload generation
  - Weighted ensemble voting with calibrated confidence
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .cost_tracker import SpendData


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class AnomalySeverity(str, Enum):
    CRITICAL = "CRITICAL"    # > 3 sigma or > 200% spike
    HIGH = "HIGH"            # 2-3 sigma or 100-200% spike
    MEDIUM = "MEDIUM"        # 1.5-2 sigma or 50-100% spike
    LOW = "LOW"              # < 1.5 sigma, informational


@dataclass
class RootCauseAttribution:
    """Root cause signals derived from co-occurring data."""
    primary_driver: str
    contributing_factors: list[str]
    correlated_services: list[str]
    confidence: float


@dataclass
class Anomaly:
    """A detected cost anomaly — V2 enriched."""
    detected_at: date
    service: str
    amount: float
    baseline: float
    delta: float
    delta_pct: float
    severity: AnomalySeverity
    confidence: float
    isolation_score: float
    zscore: float
    ema_baseline: float = 0.0
    ensemble_votes: int = 0
    root_cause: RootCauseAttribution | None = None
    explanation: str = ""
    method: str = "combined"
    acknowledged: bool = False
    acknowledged_by: str = ""
    pagerduty_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_spike(self) -> bool:
        return self.delta > 0

    @property
    def formatted_delta(self) -> str:
        sign = "+" if self.delta >= 0 else ""
        return f"{sign}${self.delta:,.0f} ({sign}{self.delta_pct:.1f}%)"

    @property
    def anomaly_id(self) -> str:
        """Stable ID for acknowledgement tracking."""
        raw = f"{self.detected_at}|{self.service}|{self.delta:.0f}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]


@dataclass
class SuppressionRule:
    """Rule to suppress alerts for known events."""
    rule_id: str
    service_pattern: str
    date_start: date
    date_end: date
    reason: str
    created_by: str = "system"


# ---------------------------------------------------------------------------
# AnomalyDetector V2
# ---------------------------------------------------------------------------

class AnomalyDetectorV2:
    """
    Ensemble anomaly detector:
      - Isolation Forest (multivariate)
      - EMA-based rolling Z-score (time-series aware)
      - LSTM autoencoder (optional, lazy-loaded)

    V2 improvements:
      - Root cause attribution via co-movement analysis
      - Suppression rules for known events
      - PagerDuty-ready payload generation
      - Weighted ensemble voting
    """

    WEIGHTS = {
        "isolation_forest": 0.35,
        "ema_zscore": 0.45,
        "lstm": 0.20,
    }

    def __init__(
        self,
        anthropic_api_key: str | None = None,
        zscore_threshold: float = 2.0,
        isolation_contamination: float = 0.05,
        rolling_window: int = 14,
        ema_span: int = 7,
        explain_top_n: int = 5,
        use_lstm: bool = False,
        suppression_rules: list[SuppressionRule] | None = None,
    ) -> None:
        self.api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.zscore_threshold = zscore_threshold
        self.isolation_contamination = isolation_contamination
        self.rolling_window = rolling_window
        self.ema_span = ema_span
        self.explain_top_n = explain_top_n
        self.use_lstm = use_lstm
        self._suppression_rules: list[SuppressionRule] = suppression_rules or []
        self._acknowledged_ids: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, spend_data: SpendData) -> list[Anomaly]:
        """Run ensemble anomaly detection. Returns sorted anomalies."""
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

            if len(daily) < 7:
                continue

            svc_anomalies = self._detect_service(daily, service)
            all_anomalies.extend(svc_anomalies)

        all_anomalies = [a for a in all_anomalies if not self._is_suppressed(a)]
        all_anomalies = self._attribute_root_causes(all_anomalies, spend_data)

        for a in all_anomalies:
            if a.severity in (AnomalySeverity.CRITICAL, AnomalySeverity.HIGH):
                a.pagerduty_payload = self._build_pagerduty_payload(a)

        severity_order = {
            AnomalySeverity.CRITICAL: 0,
            AnomalySeverity.HIGH: 1,
            AnomalySeverity.MEDIUM: 2,
            AnomalySeverity.LOW: 3,
        }
        all_anomalies.sort(key=lambda a: (severity_order[a.severity], -abs(a.delta)))
        return all_anomalies

    def detect_and_explain(
        self,
        spend_data: SpendData,
        top_n: int | None = None,
    ) -> list[Anomaly]:
        anomalies = self.detect(spend_data)
        n = top_n if top_n is not None else self.explain_top_n
        if self.api_key:
            explained = self.explain_all(anomalies[:n], spend_data)
            return explained + anomalies[n:]
        return anomalies

    def acknowledge(self, anomaly_id: str, acknowledged_by: str = "user") -> bool:
        self._acknowledged_ids.add(anomaly_id)
        return True

    def add_suppression_rule(self, rule: SuppressionRule) -> None:
        self._suppression_rules.append(rule)

    # ------------------------------------------------------------------
    # Per-service ensemble detection
    # ------------------------------------------------------------------

    def _detect_service(self, daily: pd.Series, service: str) -> list[Anomaly]:
        ema = daily.ewm(span=self.ema_span, adjust=False).mean()
        rolling_std = daily.rolling(window=self.rolling_window, min_periods=3).std()
        iso_scores = self._run_isolation_forest(daily)

        lstm_scores: np.ndarray | None = None
        if self.use_lstm and len(daily) >= 30:
            lstm_scores = self._run_lstm(daily)

        anomalies: list[Anomaly] = []
        for i, (ts, amount) in enumerate(daily.items()):
            if i < self.rolling_window:
                continue

            ema_val = float(ema.iloc[i])
            std_val = float(rolling_std.iloc[i]) if not pd.isna(rolling_std.iloc[i]) else 0.0
            iso_score = iso_scores[i]

            if ema_val <= 0 or std_val <= 0:
                continue

            zscore = (amount - ema_val) / std_val

            votes = 0
            if abs(zscore) >= self.zscore_threshold:
                votes += 1
            if iso_score < -0.1:
                votes += 1
            if lstm_scores is not None and lstm_scores[i] > 0.5:
                votes += 1

            if votes == 0:
                continue

            delta = amount - ema_val
            delta_pct = (delta / ema_val * 100) if ema_val > 0 else 0

            if abs(delta) < 10 and abs(delta_pct) < 20:
                continue

            severity = self._classify_severity(zscore, delta_pct)
            confidence = self._compute_ensemble_confidence(zscore, iso_score, votes, lstm_scores, i)

            anomalies.append(Anomaly(
                detected_at=ts.date() if hasattr(ts, "date") else ts,
                service=service,
                amount=round(float(amount), 2),
                baseline=round(float(ema_val), 2),
                delta=round(float(delta), 2),
                delta_pct=round(float(delta_pct), 1),
                severity=severity,
                confidence=round(confidence, 3),
                isolation_score=round(float(iso_score), 4),
                zscore=round(float(zscore), 3),
                ema_baseline=round(float(ema_val), 2),
                ensemble_votes=votes,
                method="ensemble",
            ))

        return anomalies

    def _run_isolation_forest(self, daily: pd.Series) -> np.ndarray:
        values = daily.values
        n = len(values)

        lag1 = np.concatenate([[values[0]], values[:-1]])
        lag2 = np.concatenate([[values[0]] * 2, values[:-2]])
        lag7 = np.concatenate(
            [[float(np.mean(values[:min(7, n)]))] * min(7, n), values[:max(0, n - 7)]]
        )
        rolling7 = pd.Series(values).rolling(7, min_periods=1).mean().values

        features = np.column_stack([values, lag1, lag2, lag7, rolling7])
        scaler = StandardScaler()
        scaled = scaler.fit_transform(features)

        iso = IsolationForest(
            contamination=self.isolation_contamination,
            random_state=42,
            n_estimators=150,
        )
        iso.fit(scaled)
        return iso.decision_function(scaled)

    def _run_lstm(self, daily: pd.Series) -> np.ndarray | None:
        """Optional LSTM autoencoder — lazy-loaded, returns None if torch missing."""
        try:
            import torch
            import torch.nn as nn

            values = daily.values.astype(np.float32)
            mean_v, std_v = float(values.mean()), float(values.std())
            if std_v == 0:
                return None
            norm = (values - mean_v) / std_v

            seq_len = 7
            n = len(norm)
            if n <= seq_len:
                return None

            sequences = np.array([norm[i:i + seq_len] for i in range(n - seq_len)])
            X = torch.tensor(sequences, dtype=torch.float32).unsqueeze(-1)

            class LSTMAuto(nn.Module):
                def __init__(self) -> None:
                    super().__init__()
                    self.enc = nn.LSTM(1, 16, batch_first=True)
                    self.dec = nn.LSTM(16, 1, batch_first=True)

                def forward(self, x: torch.Tensor) -> torch.Tensor:
                    _, (h, _) = self.enc(x)
                    repeated = h.permute(1, 0, 2).repeat(1, x.size(1), 1)
                    out, _ = self.dec(repeated)
                    return out

            model = LSTMAuto()
            optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
            criterion = nn.MSELoss()

            model.train()
            for _ in range(20):
                pred = model(X)
                loss = criterion(pred, X)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            model.eval()
            with torch.no_grad():
                recon = model(X).squeeze(-1).numpy()

            errors = np.abs(sequences[:, -1] - recon[:, -1])
            padded = np.concatenate([np.zeros(seq_len), errors])
            max_err = float(padded.max())
            if max_err > 0:
                padded = padded / max_err
            return padded

        except (ImportError, Exception):
            return None

    # ------------------------------------------------------------------
    # Root cause attribution
    # ------------------------------------------------------------------

    def _attribute_root_causes(
        self,
        anomalies: list[Anomaly],
        spend_data: SpendData,
    ) -> list[Anomaly]:
        if spend_data.df is None:
            return anomalies

        df = spend_data.df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date

        for anomaly in anomalies:
            same_day = df[df["date"] == anomaly.detected_at]
            if same_day.empty:
                continue

            day_totals = same_day.groupby("service")["amount"].sum()
            ratios: dict[str, float] = {}

            for svc, amount in day_totals.items():
                prior_data = df[
                    (df["service"] == svc) &
                    (df["date"] >= anomaly.detected_at - timedelta(days=8)) &
                    (df["date"] < anomaly.detected_at)
                ]["amount"]
                prior_mean = float(prior_data.mean()) if not prior_data.empty else 1.0
                ratios[str(svc)] = float(amount) / max(prior_mean, 1.0)

            correlated = [
                svc for svc, ratio in ratios.items()
                if ratio > 2.0 and svc != anomaly.service
            ][:3]

            primary = self._infer_primary_driver(anomaly, correlated)
            contributing = [
                f"{svc} also elevated {ratios.get(svc, 1.0):.1f}x normal"
                for svc in correlated
            ]

            anomaly.root_cause = RootCauseAttribution(
                primary_driver=primary,
                contributing_factors=contributing,
                correlated_services=correlated,
                confidence=0.70 if correlated else 0.40,
            )

        return anomalies

    def _infer_primary_driver(self, anomaly: Anomaly, correlated: list[str]) -> str:
        service = anomaly.service.lower()

        if "data transfer" in service or "nat" in service:
            if any("lambda" in s.lower() for s in correlated):
                return f"Lambda retry loop generating excessive NAT Gateway traffic — ${anomaly.delta:,.0f} projected overage"
            if any("ecs" in s.lower() for s in correlated):
                return "ECS task scale-out driving cross-AZ data transfer spike"
            return f"Unexpected data transfer surge — check VPC Flow Logs for {anomaly.detected_at}"

        if "ec2" in service:
            if anomaly.delta_pct > 200:
                est_instances = max(1, int(anomaly.delta / 100))
                return f"Auto Scaling Group expanded aggressively — estimated {est_instances} new instances"
            return f"EC2 spend elevated {anomaly.delta_pct:.0f}% — check ASG activity history"

        if "lambda" in service:
            return f"Lambda function in retry loop — check invocation count spike and error rate on {anomaly.detected_at}"

        if "rds" in service:
            return "RDS cost spike — possible new instance provisioning or storage auto-scale event"

        return (
            f"Unexpected {anomaly.delta_pct:.0f}% cost increase — "
            f"investigate CloudWatch events on {anomaly.detected_at}"
        )

    # ------------------------------------------------------------------
    # Suppression
    # ------------------------------------------------------------------

    def _is_suppressed(self, anomaly: Anomaly) -> bool:
        if anomaly.anomaly_id in self._acknowledged_ids:
            return True
        for rule in self._suppression_rules:
            if (
                rule.service_pattern.lower() in anomaly.service.lower()
                and rule.date_start <= anomaly.detected_at <= rule.date_end
            ):
                return True
        return False

    # ------------------------------------------------------------------
    # PagerDuty payload
    # ------------------------------------------------------------------

    def _build_pagerduty_payload(self, anomaly: Anomaly) -> dict[str, Any]:
        """PagerDuty Events API v2 payload — POST to https://events.pagerduty.com/v2/enqueue"""
        return {
            "routing_key": "${PAGERDUTY_INTEGRATION_KEY}",
            "event_action": "trigger",
            "dedup_key": f"finops-anomaly-{anomaly.anomaly_id}",
            "payload": {
                "summary": (
                    f"[FinOps] {anomaly.severity.value}: {anomaly.service} "
                    f"spiked {anomaly.delta_pct:+.0f}% on {anomaly.detected_at} "
                    f"({anomaly.formatted_delta})"
                ),
                "severity": anomaly.severity.value.lower(),
                "source": "finops-intelligence",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "custom_details": {
                    "service": anomaly.service,
                    "anomaly_date": str(anomaly.detected_at),
                    "actual_amount": anomaly.amount,
                    "baseline_amount": anomaly.baseline,
                    "delta": anomaly.delta,
                    "delta_pct": anomaly.delta_pct,
                    "z_score": anomaly.zscore,
                    "confidence": anomaly.confidence,
                    "method": anomaly.method,
                    "ensemble_votes": anomaly.ensemble_votes,
                    "root_cause": (
                        anomaly.root_cause.primary_driver
                        if anomaly.root_cause else "Pending analysis"
                    ),
                    "correlated_services": (
                        anomaly.root_cause.correlated_services
                        if anomaly.root_cause else []
                    ),
                    "anomaly_id": anomaly.anomaly_id,
                    "acknowledge_url": f"POST /anomalies/{anomaly.anomaly_id}/acknowledge",
                },
            },
        }

    # ------------------------------------------------------------------
    # Severity + confidence
    # ------------------------------------------------------------------

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

    def _compute_ensemble_confidence(
        self,
        zscore: float,
        iso_score: float,
        votes: int,
        lstm_scores: np.ndarray | None,
        idx: int,
    ) -> float:
        z_conf = min(abs(zscore) / 5.0, 1.0)
        iso_conf = max(0.0, min(1.0, -iso_score / 0.5))
        lstm_conf = float(lstm_scores[idx]) if lstm_scores is not None else 0.0

        base = (
            z_conf * self.WEIGHTS["ema_zscore"] +
            iso_conf * self.WEIGHTS["isolation_forest"] +
            lstm_conf * self.WEIGHTS["lstm"]
        )
        agreement_bonus = (votes - 1) * 0.1
        return min(1.0, base + agreement_bonus)

    # ------------------------------------------------------------------
    # Claude explanations
    # ------------------------------------------------------------------

    def explain_all(
        self,
        anomalies: list[Anomaly],
        spend_data: SpendData,
    ) -> list[Anomaly]:
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

        for anomaly in anomalies:
            context = self._build_anomaly_context(anomaly, spend_data)
            try:
                response = client.messages.create(
                    model="claude-haiku-4-5",
                    max_tokens=450,
                    system=(
                        "You are a senior FinOps engineer analyzing AWS cost anomalies. "
                        "Provide concise root cause analysis in 2-4 sentences using specific "
                        "AWS service names and metrics. If correlated services are shown, "
                        "explain the causal relationship. End with one specific CLI command or console action."
                    ),
                    messages=[{"role": "user", "content": context}],
                )
                anomaly.explanation = response.content[0].text.strip()
            except Exception:
                anomaly.explanation = self._fallback_explanation(anomaly)

        return anomalies

    def _build_anomaly_context(self, anomaly: Anomaly, spend_data: SpendData) -> str:
        window_start = anomaly.detected_at - timedelta(days=3)
        window_end = anomaly.detected_at + timedelta(days=3)
        nearby = [
            r for r in spend_data.daily_rows
            if r.service == anomaly.service and window_start <= r.date <= window_end
        ]
        window_data = {str(r.date): f"${r.amount:,.2f}" for r in nearby}

        lines = [
            f"Service: {anomaly.service}",
            f"Anomaly date: {anomaly.detected_at}",
            f"Actual: ${anomaly.amount:,.2f}  |  EMA baseline: ${anomaly.ema_baseline:,.2f}",
            f"Delta: {anomaly.formatted_delta}",
            f"Z-score: {anomaly.zscore:.2f}  |  Ensemble votes: {anomaly.ensemble_votes}/3",
            f"Severity: {anomaly.severity.value}  |  Confidence: {anomaly.confidence:.0%}",
            "",
            "7-day cost context:",
        ]
        for d, v in sorted(window_data.items()):
            marker = " <<<< ANOMALY" if d == str(anomaly.detected_at) else ""
            lines.append(f"  {d}: {v}{marker}")

        if anomaly.root_cause and anomaly.root_cause.correlated_services:
            lines.append(
                f"\nCorrelated services spiked on same day: "
                f"{', '.join(anomaly.root_cause.correlated_services)}"
            )
            lines.append(f"Preliminary root cause: {anomaly.root_cause.primary_driver}")

        same_day = sorted(
            [r for r in spend_data.daily_rows if r.date == anomaly.detected_at and r.service != anomaly.service],
            key=lambda r: r.amount,
            reverse=True,
        )
        if same_day:
            lines.append(f"\nOther top services on {anomaly.detected_at}:")
            for r in same_day[:5]:
                lines.append(f"  {r.service}: ${r.amount:,.2f}")

        lines.append("\nQuestion: Explain this anomaly and recommend one specific action.")
        return "\n".join(lines)

    def _fallback_explanation(self, anomaly: Anomaly) -> str:
        direction = "spike" if anomaly.is_spike else "drop"
        rc = (
            f" Root cause signal: {anomaly.root_cause.primary_driver}."
            if anomaly.root_cause else ""
        )
        templates = {
            "AWS Data Transfer": (
                f"Data Transfer costs {direction}d {anomaly.formatted_delta}.{rc} "
                "Likely a Lambda retry loop or cross-AZ replication job generating excess NAT Gateway traffic. "
                "Action: aws cloudwatch get-metric-statistics --metric-name Errors --namespace AWS/Lambda"
            ),
            "Amazon EC2": (
                f"EC2 costs {direction}d {anomaly.formatted_delta}.{rc} "
                "Auto Scaling Group scale-out triggered by traffic spike or CPU alarm. "
                "Action: aws autoscaling describe-scaling-activities --auto-scaling-group-name <asg>"
            ),
            "Amazon RDS": (
                f"RDS costs {direction}d {anomaly.formatted_delta}.{rc} "
                "Possible new instance or storage auto-expansion. "
                "Action: aws rds describe-events --duration 1440"
            ),
            "AWS Lambda": (
                f"Lambda costs {direction}d {anomaly.formatted_delta}.{rc} "
                "Invocation loop or abnormal concurrency from misconfigured event source. "
                "Action: Check Lambda Insights for top functions by invocation count."
            ),
        }
        for keyword, template in templates.items():
            if keyword in anomaly.service:
                return template

        return (
            f"{anomaly.service} costs {direction}d {anomaly.formatted_delta} "
            f"(z-score: {anomaly.zscore:.1f}, confidence: {anomaly.confidence:.0%}, "
            f"ensemble votes: {anomaly.ensemble_votes}/3).{rc} "
            f"Review CloudWatch events around {anomaly.detected_at}."
        )
