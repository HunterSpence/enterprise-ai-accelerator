"""
unit_economics.py — Unit Economics Engine for FinOps Intelligence V2.

Calculates cost-per-X metrics (per user, per API call, per transaction, per GB).
Identifies efficiency trends and benchmarks against industry medians.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any

from .cost_tracker import SpendData


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class EfficiencyTrend(str, Enum):
    IMPROVING = "IMPROVING"      # cost/unit decreasing
    STABLE = "STABLE"
    DEGRADING = "DEGRADING"      # cost/unit increasing (bad)
    UNKNOWN = "UNKNOWN"


@dataclass
class UnitMetric:
    """A single cost-per-X measurement."""
    metric_name: str            # e.g. "cost_per_user", "cost_per_api_call"
    display_name: str           # e.g. "Cost per Active User"
    current_value: float        # dollars per unit
    previous_value: float | None  # prior period for trend
    unit: str                   # e.g. "$/user/month", "$/1000 API calls"
    trend: EfficiencyTrend
    trend_pct: float            # % change vs prior period
    industry_benchmark: float | None  # industry median
    benchmark_multiple: float | None  # current / benchmark (1.0 = at benchmark)
    benchmark_label: str = ""   # e.g. "4x above industry median"
    responsible_services: list[str] = field(default_factory=list)
    period_start: date = field(default_factory=date.today)
    period_end: date = field(default_factory=date.today)


@dataclass
class UnitEconomicsReport:
    """Full unit economics analysis."""
    generated_at: date
    account_name: str
    metrics: list[UnitMetric]
    total_monthly_spend: float
    key_finding: str            # One-line headline finding
    degrading_metrics: list[str]  # metric names that are getting worse
    maturity_score: float       # 0–1, how well unit economics are tracked


@dataclass
class ServiceCostAttribution:
    """Showback/chargeback data for a team or service."""
    team: str
    services: list[str]
    monthly_cost: float
    cost_per_user: float | None
    cost_per_transaction: float | None
    pct_of_total: float


# Industry benchmark medians (SaaS companies $1M–$10M ARR)
INDUSTRY_BENCHMARKS: dict[str, tuple[float, str]] = {
    "cost_per_user":          (2.50,   "$/user/month — SaaS median"),
    "cost_per_api_call":      (0.003,  "$/1000 API calls — API-first median"),
    "cost_per_transaction":   (0.008,  "$/transaction — fintech/ecomm median"),
    "cost_per_gb_processed":  (0.02,   "$/GB processed — data pipeline median"),
    "cost_per_engineer":      (1_200,  "$/engineer/month — platform team median"),
}


# ---------------------------------------------------------------------------
# UnitEconomicsEngine
# ---------------------------------------------------------------------------

class UnitEconomicsEngine:
    """
    Calculates and trends unit economics metrics.

    Usage:
        engine = UnitEconomicsEngine()
        report = engine.analyze(
            spend_data=data,
            active_users=12_400,
            monthly_transactions=3_200_000,
            monthly_api_calls=48_000_000,
            monthly_gb_processed=84_000,
            engineers=47,
        )
        print(report.key_finding)
    """

    def __init__(self) -> None:
        self._history: list[dict[str, float]] = []  # rolling metric history

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def analyze(
        self,
        spend_data: SpendData,
        active_users: int = 0,
        monthly_transactions: int = 0,
        monthly_api_calls: int = 0,
        monthly_gb_processed: float = 0.0,
        engineers: int = 0,
        prior_period_spend: float | None = None,
        prior_period_users: int = 0,
        prior_period_transactions: int = 0,
    ) -> UnitEconomicsReport:
        """
        Compute full unit economics report.

        Parameters
        ----------
        spend_data: SpendData from CostTracker
        active_users: monthly active users
        monthly_transactions: processed transactions (orders, payments, events)
        monthly_api_calls: total API calls to your services
        monthly_gb_processed: GB of data processed (ETL, streaming, analytics)
        engineers: number of engineering headcount
        prior_period_spend: previous month total (for trend)
        """
        # Use projected monthly as the current month figure
        monthly_spend = spend_data.projected_monthly or (
            spend_data.total_spend / max(1, (spend_data.query_end - spend_data.query_start).days) * 30
        )

        metrics: list[UnitMetric] = []
        degrading: list[str] = []

        # --- Cost per user ---
        if active_users > 0:
            m = self._metric_cost_per_user(
                monthly_spend, active_users,
                prior_spend=prior_period_spend,
                prior_users=prior_period_users,
                period_start=spend_data.query_start,
                period_end=spend_data.query_end,
            )
            metrics.append(m)
            if m.trend == EfficiencyTrend.DEGRADING:
                degrading.append(m.metric_name)

        # --- Cost per API call ---
        if monthly_api_calls > 0:
            m = self._metric_cost_per_api_call(
                monthly_spend, monthly_api_calls,
                spend_data=spend_data,
                period_start=spend_data.query_start,
                period_end=spend_data.query_end,
            )
            metrics.append(m)
            if m.trend == EfficiencyTrend.DEGRADING:
                degrading.append(m.metric_name)

        # --- Cost per transaction ---
        if monthly_transactions > 0:
            m = self._metric_cost_per_transaction(
                monthly_spend, monthly_transactions,
                prior_spend=prior_period_spend,
                prior_transactions=prior_period_transactions,
                period_start=spend_data.query_start,
                period_end=spend_data.query_end,
            )
            metrics.append(m)
            if m.trend == EfficiencyTrend.DEGRADING:
                degrading.append(m.metric_name)

        # --- Cost per GB processed ---
        if monthly_gb_processed > 0:
            m = self._metric_cost_per_gb(
                monthly_spend, monthly_gb_processed,
                spend_data=spend_data,
                period_start=spend_data.query_start,
                period_end=spend_data.query_end,
            )
            metrics.append(m)
            if m.trend == EfficiencyTrend.DEGRADING:
                degrading.append(m.metric_name)

        # --- Cost per engineer ---
        if engineers > 0:
            m = self._metric_cost_per_engineer(
                monthly_spend, engineers,
                period_start=spend_data.query_start,
                period_end=spend_data.query_end,
            )
            metrics.append(m)

        # Maturity: how many business drivers are tracked
        tracked = sum([
            active_users > 0,
            monthly_api_calls > 0,
            monthly_transactions > 0,
            monthly_gb_processed > 0,
            engineers > 0,
        ])
        maturity_score = min(1.0, tracked / 4)

        # Key finding (first degrading or best benchmark finding)
        key_finding = self._generate_key_finding(metrics, monthly_spend, degrading)

        return UnitEconomicsReport(
            generated_at=date.today(),
            account_name=spend_data.account_name,
            metrics=metrics,
            total_monthly_spend=round(monthly_spend, 2),
            key_finding=key_finding,
            degrading_metrics=degrading,
            maturity_score=round(maturity_score, 2),
        )

    def compute_service_attribution(
        self,
        spend_data: SpendData,
        team_service_map: dict[str, list[str]],
        active_users: int = 0,
        monthly_transactions: int = 0,
    ) -> list[ServiceCostAttribution]:
        """
        Showback/chargeback report: attribute costs to teams by service ownership.

        team_service_map: {"platform": ["Amazon EC2", "Amazon EKS"], "data": ["Amazon RDS", ...]}
        """
        monthly_spend = spend_data.projected_monthly or spend_data.total_spend / 30 * 30
        results: list[ServiceCostAttribution] = []

        for team, services in team_service_map.items():
            team_cost = sum(
                spend_data.services[s].total / max(1, (spend_data.query_end - spend_data.query_start).days) * 30
                for s in services
                if s in spend_data.services
            )
            cpu = team_cost / active_users if active_users > 0 else None
            cpt = team_cost / monthly_transactions if monthly_transactions > 0 else None

            results.append(ServiceCostAttribution(
                team=team,
                services=services,
                monthly_cost=round(team_cost, 2),
                cost_per_user=round(cpu, 4) if cpu is not None else None,
                cost_per_transaction=round(cpt, 6) if cpt is not None else None,
                pct_of_total=round(team_cost / monthly_spend * 100 if monthly_spend > 0 else 0, 1),
            ))

        results.sort(key=lambda x: x.monthly_cost, reverse=True)
        return results

    def finops_maturity_unit_economics(self, report: UnitEconomicsReport) -> dict[str, Any]:
        """
        FinOps Foundation Unit Economics capability maturity:
        Crawl / Walk / Run
        """
        score = report.maturity_score
        tracked_count = len(report.metrics)

        if score >= 0.75 and tracked_count >= 4:
            level = "RUN"
            description = "Unit economics fully instrumented. Costs allocated to products, features, and user cohorts."
        elif score >= 0.40 or tracked_count >= 2:
            level = "WALK"
            description = "Key unit metrics tracked. Gap: missing per-feature or cohort-level attribution."
        else:
            level = "CRAWL"
            description = "Unit economics not yet established. Only aggregate spend tracked."

        next_steps = []
        if not any(m.metric_name == "cost_per_user" for m in report.metrics):
            next_steps.append("Instrument active user count and compute cost-per-user monthly")
        if not any(m.metric_name == "cost_per_transaction" for m in report.metrics):
            next_steps.append("Add transaction counter to your application metrics pipeline")
        if len(report.metrics) < 3:
            next_steps.append("Track at minimum: cost/user, cost/transaction, cost/GB processed")

        return {"level": level, "description": description, "next_steps": next_steps, "score": score}

    # ------------------------------------------------------------------
    # Individual metric builders
    # ------------------------------------------------------------------

    def _metric_cost_per_user(
        self,
        monthly_spend: float,
        users: int,
        prior_spend: float | None,
        prior_users: int,
        period_start: date,
        period_end: date,
    ) -> UnitMetric:
        current = monthly_spend / users
        previous: float | None = None
        if prior_spend and prior_users > 0:
            previous = prior_spend / prior_users

        trend, trend_pct = self._compute_trend(current, previous)
        bench, bench_mult, bench_label = self._benchmark("cost_per_user", current)

        # Which services drive user compute cost most?
        responsible = ["Amazon EC2", "Amazon EKS", "AWS Lambda"]

        return UnitMetric(
            metric_name="cost_per_user",
            display_name="Cost per Active User",
            current_value=round(current, 4),
            previous_value=round(previous, 4) if previous else None,
            unit="$/user/month",
            trend=trend,
            trend_pct=round(trend_pct, 1),
            industry_benchmark=bench,
            benchmark_multiple=bench_mult,
            benchmark_label=bench_label,
            responsible_services=responsible,
            period_start=period_start,
            period_end=period_end,
        )

    def _metric_cost_per_api_call(
        self,
        monthly_spend: float,
        api_calls: int,
        spend_data: SpendData,
        period_start: date,
        period_end: date,
    ) -> UnitMetric:
        # Cost per 1000 API calls
        current = (monthly_spend / api_calls) * 1000
        bench, bench_mult, bench_label = self._benchmark("cost_per_api_call", current)

        # Lambda + API Gateway are primary drivers
        lambda_spend = sum(
            s.total for name, s in spend_data.services.items()
            if "lambda" in name.lower() or "api gateway" in name.lower()
        )
        responsible = ["AWS Lambda", "Amazon API Gateway", "Amazon CloudFront"]

        return UnitMetric(
            metric_name="cost_per_api_call",
            display_name="Cost per 1,000 API Calls",
            current_value=round(current, 5),
            previous_value=None,
            unit="$/1,000 calls",
            trend=EfficiencyTrend.UNKNOWN,
            trend_pct=0.0,
            industry_benchmark=bench,
            benchmark_multiple=bench_mult,
            benchmark_label=bench_label,
            responsible_services=responsible,
            period_start=period_start,
            period_end=period_end,
        )

    def _metric_cost_per_transaction(
        self,
        monthly_spend: float,
        transactions: int,
        prior_spend: float | None,
        prior_transactions: int,
        period_start: date,
        period_end: date,
    ) -> UnitMetric:
        current = monthly_spend / transactions
        previous: float | None = None
        if prior_spend and prior_transactions > 0:
            previous = prior_spend / prior_transactions

        trend, trend_pct = self._compute_trend(current, previous)
        bench, bench_mult, bench_label = self._benchmark("cost_per_transaction", current)

        return UnitMetric(
            metric_name="cost_per_transaction",
            display_name="Cost per Transaction",
            current_value=round(current, 6),
            previous_value=round(previous, 6) if previous else None,
            unit="$/transaction",
            trend=trend,
            trend_pct=round(trend_pct, 1),
            industry_benchmark=bench,
            benchmark_multiple=bench_mult,
            benchmark_label=bench_label,
            responsible_services=["Amazon RDS", "Amazon DynamoDB", "Amazon SQS"],
            period_start=period_start,
            period_end=period_end,
        )

    def _metric_cost_per_gb(
        self,
        monthly_spend: float,
        gb_processed: float,
        spend_data: SpendData,
        period_start: date,
        period_end: date,
    ) -> UnitMetric:
        current = monthly_spend / gb_processed
        bench, bench_mult, bench_label = self._benchmark("cost_per_gb_processed", current)

        return UnitMetric(
            metric_name="cost_per_gb_processed",
            display_name="Cost per GB Processed",
            current_value=round(current, 5),
            previous_value=None,
            unit="$/GB",
            trend=EfficiencyTrend.UNKNOWN,
            trend_pct=0.0,
            industry_benchmark=bench,
            benchmark_multiple=bench_mult,
            benchmark_label=bench_label,
            responsible_services=["Amazon S3", "AWS Data Transfer", "Amazon Redshift", "AWS Glue"],
            period_start=period_start,
            period_end=period_end,
        )

    def _metric_cost_per_engineer(
        self,
        monthly_spend: float,
        engineers: int,
        period_start: date,
        period_end: date,
    ) -> UnitMetric:
        current = monthly_spend / engineers
        bench, bench_mult, bench_label = self._benchmark("cost_per_engineer", current)

        return UnitMetric(
            metric_name="cost_per_engineer",
            display_name="Cloud Spend per Engineer",
            current_value=round(current, 2),
            previous_value=None,
            unit="$/engineer/month",
            trend=EfficiencyTrend.UNKNOWN,
            trend_pct=0.0,
            industry_benchmark=bench,
            benchmark_multiple=bench_mult,
            benchmark_label=bench_label,
            responsible_services=[],
            period_start=period_start,
            period_end=period_end,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_trend(
        self,
        current: float,
        previous: float | None,
    ) -> tuple[EfficiencyTrend, float]:
        if previous is None or previous == 0:
            return EfficiencyTrend.UNKNOWN, 0.0
        pct_change = (current - previous) / previous * 100
        if pct_change < -5:
            return EfficiencyTrend.IMPROVING, pct_change
        elif pct_change > 5:
            return EfficiencyTrend.DEGRADING, pct_change
        return EfficiencyTrend.STABLE, pct_change

    def _benchmark(
        self,
        metric_name: str,
        current: float,
    ) -> tuple[float | None, float | None, str]:
        if metric_name not in INDUSTRY_BENCHMARKS:
            return None, None, ""
        bench_val, bench_desc = INDUSTRY_BENCHMARKS[metric_name]
        multiple = current / bench_val if bench_val > 0 else None
        if multiple is None:
            label = ""
        elif multiple <= 0.8:
            label = f"{1/multiple:.1f}x below industry median (excellent)"
        elif multiple <= 1.2:
            label = f"at industry median ({bench_desc})"
        elif multiple <= 2.0:
            label = f"{multiple:.1f}x above industry median — optimization opportunity"
        else:
            label = f"{multiple:.1f}x above industry median — significant overspend vs peers"
        return bench_val, round(multiple, 2) if multiple else None, label

    def _generate_key_finding(
        self,
        metrics: list[UnitMetric],
        monthly_spend: float,
        degrading: list[str],
    ) -> str:
        if not metrics:
            return f"Total monthly cloud spend: ${monthly_spend:,.0f}. Enable unit metrics for per-user/per-transaction analysis."

        # Find most egregious benchmark deviation
        worst: UnitMetric | None = None
        worst_multiple = 1.0
        for m in metrics:
            if m.benchmark_multiple and m.benchmark_multiple > worst_multiple:
                worst = m
                worst_multiple = m.benchmark_multiple

        if worst and worst_multiple > 2.0:
            return (
                f"{worst.display_name} is ${worst.current_value:.4f} — "
                f"{worst.benchmark_multiple:.1f}x above industry median "
                f"(${worst.industry_benchmark:.4f}). "
                f"Drivers: {', '.join(worst.responsible_services[:2])}."
            )

        if degrading:
            m_name = degrading[0]
            m = next((m for m in metrics if m.metric_name == m_name), None)
            if m:
                return (
                    f"{m.display_name} degraded {m.trend_pct:+.1f}% vs last period "
                    f"(${m.previous_value:.4f} → ${m.current_value:.4f}). "
                    "Efficiency is declining — investigate service cost growth."
                )

        best = min(metrics, key=lambda m: m.benchmark_multiple or 999)
        if best.benchmark_multiple and best.benchmark_multiple <= 1.0:
            return f"Unit economics healthy: {best.display_name} ${best.current_value:.4f} at or below industry median."

        return f"Monthly cloud spend ${monthly_spend:,.0f} across {len(metrics)} tracked unit metrics."
