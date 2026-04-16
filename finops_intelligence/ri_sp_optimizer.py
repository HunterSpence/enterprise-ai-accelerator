"""
finops_intelligence/ri_sp_optimizer.py
=======================================

RISPOptimizer — Reserved Instance and Savings Plan recommendation engine.

Analyses EC2, RDS, and ElastiCache on-demand usage from a CURIngestor,
identifies steady-state baselines, and produces prioritised commitment
recommendations that cover up to 80% of baseline usage (leaving headroom
for fluctuation).

Commitment types modelled:
  ri_1y_no_upfront      — 1-year RI, no upfront (lowest breakeven risk)
  ri_3y_all_upfront     — 3-year RI, all upfront (maximum savings)
  savings_plan_compute_1y — Compute Savings Plan 1-year (most flexible)
  savings_plan_ec2_3y   — EC2 Instance Savings Plan 3-year (highest EC2 discount)

Pricing is approximate (2025-Q1 us-east-1 discount rates) and is intended
as directional guidance; customers should validate against the AWS Pricing API
before purchasing.

No new dependencies — uses duckdb, pandas, numpy (all in requirements.txt).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

from .cur_ingestor import CURIngestor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Commitment discount rates vs on-demand (approximate 2025-Q1 averages)
# These are blended across instance families; real rates vary by type.
# ---------------------------------------------------------------------------

_DISCOUNT_RATES: dict[str, float] = {
    "ri_1y_no_upfront": 0.36,        # ~36% off on-demand
    "ri_3y_all_upfront": 0.60,        # ~60% off on-demand
    "savings_plan_compute_1y": 0.34,  # ~34% off on-demand (flexible, any family)
    "savings_plan_ec2_3y": 0.57,      # ~57% off on-demand (EC2-specific, 3yr)
}

# Upfront cost multipliers (months of effective commitment at discounted rate)
_UPFRONT_MONTHS: dict[str, float] = {
    "ri_1y_no_upfront": 0.0,
    "ri_3y_all_upfront": 36.0,
    "savings_plan_compute_1y": 0.0,
    "savings_plan_ec2_3y": 36.0,
}

# Services eligible for RI/SP analysis
_RI_ELIGIBLE_SERVICES = {"Amazon EC2", "Amazon RDS", "Amazon ElastiCache", "AmazonEC2"}
_SP_ELIGIBLE_SERVICES = {"Amazon EC2", "AWS Lambda", "AWS Fargate", "AmazonEC2"}

# Maximum commitment coverage to avoid over-commitment risk
_MAX_COVERAGE = 0.80


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    """A single RI or Savings Plan commitment recommendation."""

    resource_group: str
    """Human-readable group label, e.g. 'm6i.xlarge / us-east-1 / Linux'."""

    service: str
    instance_family: str
    region: str
    operating_system: str
    commitment_type: str

    current_monthly_cost: float
    """Current on-demand monthly spend for this resource group (USD)."""

    recommended_commitment: float
    """Recommended hourly commitment rate to purchase ($/hr or normalised units)."""

    projected_savings_monthly: float
    """Estimated monthly savings vs staying on-demand (USD)."""

    upfront_cost: float
    """One-time upfront payment required (0 for no-upfront options)."""

    breakeven_months: float
    """Months until cumulative savings exceed upfront cost (0 if no upfront)."""

    coverage_pct: float
    """Percentage of on-demand usage this commitment covers (target <=80%)."""

    utilization_risk: str
    """'low' | 'medium' | 'high' — risk of unused committed capacity."""

    confidence: float
    """0-1 score based on data consistency over the lookback window."""

    baseline_hourly_usage: float
    """10th-percentile hourly usage (vCPU-hours or normalised units) over lookback."""

    lookback_days: int

    lookback_data_points: int
    """Number of hourly data points used to compute baseline."""


@dataclass
class RISPAnalysis:
    """Full output from RISPOptimizer.recommend()."""

    recommendations: list[Recommendation] = field(default_factory=list)
    total_current_monthly_cost: float = 0.0
    total_projected_savings_monthly: float = 0.0
    total_upfront_cost: float = 0.0
    analysis_date: str = ""
    lookback_days: int = 90
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

class RISPOptimizer:
    """Analyses CUR data to produce RI / Savings Plan purchase recommendations.

    Usage::

        async with CURIngestor() as cur:
            await cur.ingest_from_local(Path("cur_data/"))
            optimizer = RISPOptimizer()
            analysis = optimizer.recommend(cur, lookback_days=90)
            for rec in analysis.recommendations:
                print(rec.resource_group, rec.projected_savings_monthly)
    """

    def recommend(
        self,
        cur: CURIngestor,
        lookback_days: int = 90,
    ) -> RISPAnalysis:
        """Generate RI/SP recommendations from loaded CUR data.

        Args:
            cur: Populated CURIngestor with cost_records loaded.
            lookback_days: Number of days of historical usage to analyse.
                           Minimum recommended is 30; 90 gives better baselines.

        Returns:
            RISPAnalysis with all recommendations sorted by savings desc.
        """
        analysis = RISPAnalysis(
            lookback_days=lookback_days,
            analysis_date=datetime.now(timezone.utc).isoformat(),
        )
        if cur.row_count() == 0:
            analysis.warnings.append("cost_records is empty — ingest CUR data first")
            return analysis

        # ------------------------------------------------------------------
        # Step 1: aggregate hourly on-demand usage by (service, family, region, os)
        # ------------------------------------------------------------------
        hourly_df = self._aggregate_hourly_usage(cur, lookback_days)
        if hourly_df.empty:
            analysis.warnings.append(
                "No on-demand usage found for RI/SP eligible services in the lookback window."
            )
            return analysis

        # ------------------------------------------------------------------
        # Step 2: compute baseline per group
        # ------------------------------------------------------------------
        groups = hourly_df.groupby(["service", "instance_family", "region", "operating_system"])
        recs: list[Recommendation] = []
        for group_key, group_df in groups:
            service, instance_family, region, os_name = group_key
            group_recs = self._analyse_group(
                service=service,
                instance_family=str(instance_family),
                region=str(region),
                operating_system=str(os_name),
                group_df=group_df,
                lookback_days=lookback_days,
            )
            recs.extend(group_recs)

        # ------------------------------------------------------------------
        # Step 3: sort by projected monthly savings descending
        # ------------------------------------------------------------------
        recs.sort(key=lambda r: r.projected_savings_monthly, reverse=True)
        analysis.recommendations = recs
        analysis.total_current_monthly_cost = sum(r.current_monthly_cost for r in recs)
        analysis.total_projected_savings_monthly = sum(r.projected_savings_monthly for r in recs)
        analysis.total_upfront_cost = sum(r.upfront_cost for r in recs)
        logger.info(
            "RISPOptimizer: %d recommendations, $%.0f/mo projected savings",
            len(recs), analysis.total_projected_savings_monthly,
        )
        return analysis

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _aggregate_hourly_usage(self, cur: CURIngestor, lookback_days: int) -> pd.DataFrame:
        """Pull hourly on-demand costs aggregated by resource group."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        service_list = ", ".join(f"'{s}'" for s in _RI_ELIGIBLE_SERVICES | _SP_ELIGIBLE_SERVICES)
        sql = f"""
            SELECT
                service,
                COALESCE(instance_family, regexp_extract(instance_type, '^([a-z][0-9]+[a-z]*)', 1), 'unknown') AS instance_family,
                COALESCE(region, 'unknown') AS region,
                COALESCE(operating_system, 'Linux') AS operating_system,
                DATE_TRUNC('hour', usage_start) AS usage_hour,
                SUM(usage_amount) AS hourly_usage,
                SUM(unblended_cost) AS hourly_cost
            FROM cost_records
            WHERE usage_start >= '{cutoff}'
              AND service IN ({service_list})
              AND line_item_type = 'Usage'
              AND (pricing_term = 'OnDemand' OR pricing_term IS NULL)
              AND instance_family IS NOT NULL
              AND instance_family != ''
              AND instance_family != 'unknown'
            GROUP BY 1, 2, 3, 4, 5
            ORDER BY 1, 2, 3, 4, 5
        """
        try:
            return cur.query(sql)
        except Exception as exc:
            logger.warning("Hourly usage aggregation failed: %s", exc)
            return pd.DataFrame()

    def _analyse_group(
        self,
        service: str,
        instance_family: str,
        region: str,
        operating_system: str,
        group_df: pd.DataFrame,
        lookback_days: int,
    ) -> list[Recommendation]:
        """Produce RI/SP recommendations for a single resource group."""
        if len(group_df) < 7 * 24:  # Need at least 7 days of hourly data
            return []

        hourly_usage = group_df["hourly_usage"].values
        hourly_cost = group_df["hourly_cost"].values

        # 10th-percentile = steady-state baseline (conservative commitment anchor)
        baseline_usage = float(np.percentile(hourly_usage, 10))
        if baseline_usage <= 0:
            return []

        # Current on-demand monthly cost (extrapolated from lookback)
        avg_hourly_cost = float(np.mean(hourly_cost))
        current_monthly_cost = avg_hourly_cost * 730  # 730 hours/month

        if current_monthly_cost < 50:
            # Not worth recommending for tiny workloads
            return []

        # Coverage cap: commit to at most 80% of baseline
        commitment_usage = baseline_usage * _MAX_COVERAGE

        # Confidence: low variance over the period = high confidence
        cv = float(np.std(hourly_usage) / (np.mean(hourly_usage) + 1e-9))  # coefficient of variation
        confidence = max(0.0, min(1.0, 1.0 - cv))

        # Utilization risk based on variance
        if cv < 0.2:
            util_risk = "low"
        elif cv < 0.5:
            util_risk = "medium"
        else:
            util_risk = "high"

        # Effective on-demand hourly rate for this group
        effective_od_rate = avg_hourly_cost / (np.mean(hourly_usage) + 1e-9)
        committed_hourly_cost = commitment_usage * effective_od_rate
        committed_monthly_cost = committed_hourly_cost * 730

        recs: list[Recommendation] = []
        group_label = f"{instance_family} / {region} / {operating_system}"

        for commitment_type, discount_rate in _DISCOUNT_RATES.items():
            # Skip SP for non-EC2 services (RDS/ElastiCache only support RIs)
            if "savings_plan" in commitment_type and service not in _SP_ELIGIBLE_SERVICES:
                continue
            if "ri_" in commitment_type and service not in _RI_ELIGIBLE_SERVICES:
                continue

            discounted_monthly = committed_monthly_cost * (1 - discount_rate)
            savings_monthly = committed_monthly_cost - discounted_monthly

            # Upfront cost
            upfront_months = _UPFRONT_MONTHS[commitment_type]
            upfront_cost = discounted_monthly * upfront_months if upfront_months > 0 else 0.0

            # Breakeven in months
            if upfront_cost > 0 and savings_monthly > 0:
                breakeven = upfront_cost / savings_monthly
            else:
                breakeven = 0.0

            coverage_pct = (commitment_usage / (np.mean(hourly_usage) + 1e-9)) * 100
            coverage_pct = min(coverage_pct, _MAX_COVERAGE * 100)

            recs.append(Recommendation(
                resource_group=group_label,
                service=service,
                instance_family=instance_family,
                region=region,
                operating_system=operating_system,
                commitment_type=commitment_type,
                current_monthly_cost=round(current_monthly_cost, 2),
                recommended_commitment=round(committed_hourly_cost, 4),
                projected_savings_monthly=round(savings_monthly, 2),
                upfront_cost=round(upfront_cost, 2),
                breakeven_months=round(breakeven, 1),
                coverage_pct=round(coverage_pct, 1),
                utilization_risk=util_risk,
                confidence=round(confidence, 3),
                baseline_hourly_usage=round(baseline_usage, 4),
                lookback_days=lookback_days,
                lookback_data_points=len(group_df),
            ))

        # Sort within group: best savings-per-risk first
        recs.sort(key=lambda r: (r.utilization_risk, -r.projected_savings_monthly))
        return recs

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def to_dataframe(analysis: RISPAnalysis) -> pd.DataFrame:
        """Convert recommendations list to a pandas DataFrame for reporting."""
        if not analysis.recommendations:
            return pd.DataFrame()
        rows = [
            {
                "resource_group": r.resource_group,
                "service": r.service,
                "commitment_type": r.commitment_type,
                "current_monthly_usd": r.current_monthly_cost,
                "projected_savings_monthly_usd": r.projected_savings_monthly,
                "upfront_cost_usd": r.upfront_cost,
                "breakeven_months": r.breakeven_months,
                "coverage_pct": r.coverage_pct,
                "utilization_risk": r.utilization_risk,
                "confidence": r.confidence,
            }
            for r in analysis.recommendations
        ]
        return pd.DataFrame(rows)
