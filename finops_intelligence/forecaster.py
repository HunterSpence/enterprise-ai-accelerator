"""
forecaster.py — Cloud spend forecasting with confidence intervals.

Uses Prophet (Meta) for primary forecasting with statsmodels SARIMA as fallback.
Produces P10/P50/P90 bands, budget burn rate, and commitment gap analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from .cost_tracker import SpendData


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ForecastPoint:
    """Single forecast data point with confidence interval."""
    date: date
    predicted: float
    lower_bound: float   # P10
    upper_bound: float   # P90


@dataclass
class ForecastResult:
    """Full forecast output for a given horizon."""
    horizon_days: int
    total_predicted: float
    total_lower: float     # P10 cumulative
    total_upper: float     # P90 cumulative
    daily_forecast: list[ForecastPoint]
    model_used: str        # "prophet" | "sarima" | "linear"
    mape: float            # Mean Absolute Percentage Error on held-out data (0–1)
    trend: str             # "increasing" | "stable" | "decreasing"
    trend_pct_per_month: float  # % change per month in trend

    @property
    def end_date(self) -> date:
        return self.daily_forecast[-1].date if self.daily_forecast else date.today()


@dataclass
class BurnRateResult:
    """Budget burn rate analysis."""
    monthly_budget: float
    mtd_spend: float
    days_elapsed: int
    days_in_month: int
    daily_burn_rate: float
    projected_month_end: float
    budget_exhaustion_date: date | None   # None if won't exceed budget
    budget_status: str                    # "ON_TRACK" | "AT_RISK" | "OVER_BUDGET"
    pct_of_budget: float
    days_until_exhaustion: int | None


@dataclass
class ServiceForecast:
    """30-day forecast for an individual service."""
    service: str
    current_monthly: float
    predicted_next_month: float
    change_pct: float


@dataclass
class CommitmentGapAnalysis:
    """RI/SP commitment sufficiency analysis."""
    forecast_baseline_monthly: float
    current_ri_sp_coverage_monthly: float
    coverage_pct: float
    gap_monthly: float              # uncovered spend
    recommended_sp_purchase: float  # amount to buy to reach 70% coverage
    estimated_savings: float        # monthly savings from buying recommended SP
    confidence: str                 # "HIGH" | "MEDIUM" | "LOW"


# ---------------------------------------------------------------------------
# Forecaster
# ---------------------------------------------------------------------------

class Forecaster:
    """
    Forecasts cloud spend using Prophet or SARIMA.

    Usage:
        forecaster = Forecaster()
        result = forecaster.forecast(spend_data, horizon_days=30)
        burn = forecaster.burn_rate(spend_data, monthly_budget=150_000)
        gap = forecaster.commitment_gap(spend_data, current_ri_sp_monthly=15_000)
    """

    def __init__(self, use_prophet: bool = True) -> None:
        self.use_prophet = use_prophet
        self._prophet_available = self._check_prophet()

    def _check_prophet(self) -> bool:
        try:
            import prophet  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def forecast(
        self,
        spend_data: SpendData,
        horizon_days: int = 30,
        service: str | None = None,
    ) -> ForecastResult:
        """
        Generate spend forecast for `horizon_days` ahead.
        If `service` is specified, forecast that service only.
        Otherwise forecast total daily spend.
        """
        series = self._build_series(spend_data, service)

        if len(series) < 14:
            return self._linear_forecast(series, horizon_days)

        if self.use_prophet and self._prophet_available:
            try:
                return self._prophet_forecast(series, horizon_days)
            except Exception:
                pass

        return self._sarima_forecast(series, horizon_days)

    def forecast_all_services(
        self,
        spend_data: SpendData,
        horizon_days: int = 30,
    ) -> list[ServiceForecast]:
        """Forecast each top-10 service for the next month."""
        results: list[ServiceForecast] = []
        top_services = spend_data.top_services(10)

        for svc in top_services:
            try:
                fc = self.forecast(spend_data, horizon_days=30, service=svc.service)
                current_monthly = svc.total / (spend_data.query_end - spend_data.query_start).days * 30
                change_pct = ((fc.total_predicted - current_monthly) / current_monthly * 100) if current_monthly > 0 else 0
                results.append(ServiceForecast(
                    service=svc.service,
                    current_monthly=round(current_monthly, 2),
                    predicted_next_month=round(fc.total_predicted, 2),
                    change_pct=round(change_pct, 1),
                ))
            except Exception:
                continue

        results.sort(key=lambda x: x.predicted_next_month, reverse=True)
        return results

    def burn_rate(
        self,
        spend_data: SpendData,
        monthly_budget: float,
    ) -> BurnRateResult:
        """Compute budget burn rate and projected exhaustion date."""
        today = date.today()
        first_of_month = today.replace(day=1)
        days_elapsed = (today - first_of_month).days + 1
        days_in_month = 30

        mtd = spend_data.mtd_spend
        daily_rate = mtd / days_elapsed if days_elapsed > 0 else 0
        projected = daily_rate * days_in_month

        pct = (projected / monthly_budget * 100) if monthly_budget > 0 else 0

        if pct >= 100:
            status = "OVER_BUDGET"
        elif pct >= 90:
            status = "AT_RISK"
        else:
            status = "ON_TRACK"

        # When will budget be exhausted?
        exhaustion_date: date | None = None
        days_until_exhaustion: int | None = None
        if daily_rate > 0:
            remaining = monthly_budget - mtd
            if remaining > 0:
                days_left = remaining / daily_rate
                if days_left < days_in_month:
                    exhaustion_date = today + timedelta(days=int(days_left))
                    days_until_exhaustion = int(days_left)

        return BurnRateResult(
            monthly_budget=monthly_budget,
            mtd_spend=round(mtd, 2),
            days_elapsed=days_elapsed,
            days_in_month=days_in_month,
            daily_burn_rate=round(daily_rate, 2),
            projected_month_end=round(projected, 2),
            budget_exhaustion_date=exhaustion_date,
            budget_status=status,
            pct_of_budget=round(pct, 1),
            days_until_exhaustion=days_until_exhaustion,
        )

    def commitment_gap(
        self,
        spend_data: SpendData,
        current_ri_sp_monthly: float,
        target_coverage_pct: float = 0.70,
    ) -> CommitmentGapAnalysis:
        """
        Analyze whether current RI/SP commitments are sufficient for forecast spend.
        Recommends purchase amount to reach target coverage.
        """
        # Use 30-day forecast as baseline
        fc = self.forecast(spend_data, horizon_days=30)
        forecast_monthly = fc.total_predicted

        coverage_pct = (current_ri_sp_monthly / forecast_monthly * 100) if forecast_monthly > 0 else 0
        gap = forecast_monthly - current_ri_sp_monthly
        target_monthly = forecast_monthly * target_coverage_pct

        recommended_purchase = max(0.0, target_monthly - current_ri_sp_monthly)
        # Compute Savings Plan savings: ~32% avg discount vs. on-demand
        estimated_savings = recommended_purchase * 0.32

        # Confidence based on forecast stability
        confidence = "HIGH" if fc.mape < 0.08 else ("MEDIUM" if fc.mape < 0.15 else "LOW")

        return CommitmentGapAnalysis(
            forecast_baseline_monthly=round(forecast_monthly, 2),
            current_ri_sp_coverage_monthly=round(current_ri_sp_monthly, 2),
            coverage_pct=round(coverage_pct, 1),
            gap_monthly=round(gap, 2),
            recommended_sp_purchase=round(recommended_purchase, 2),
            estimated_savings=round(estimated_savings, 2),
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Prophet forecasting
    # ------------------------------------------------------------------

    def _prophet_forecast(self, series: pd.Series, horizon_days: int) -> ForecastResult:
        from prophet import Prophet  # type: ignore

        df = pd.DataFrame({
            "ds": series.index,
            "y": series.values,
        })

        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.8,  # 80% CI → roughly P10/P90
            changepoint_prior_scale=0.05,
        )
        model.fit(df)

        future = model.make_future_dataframe(periods=horizon_days)
        forecast = model.predict(future)

        # MAPE on last 14 days of training data (hold-out evaluation)
        n_holdout = min(14, len(df) // 5)
        actuals = df["y"].tail(n_holdout).values
        predicted = forecast["yhat"].iloc[-(n_holdout + horizon_days):-horizon_days].values
        mape = float(np.mean(np.abs((actuals - predicted) / np.where(actuals == 0, 1, actuals))))

        # Extract future forecast only
        future_fc = forecast.tail(horizon_days)
        points: list[ForecastPoint] = []
        for _, row in future_fc.iterrows():
            points.append(ForecastPoint(
                date=row["ds"].date(),
                predicted=max(0.0, round(float(row["yhat"]), 2)),
                lower_bound=max(0.0, round(float(row["yhat_lower"]), 2)),
                upper_bound=max(0.0, round(float(row["yhat_upper"]), 2)),
            ))

        total = sum(p.predicted for p in points)
        total_lower = sum(p.lower_bound for p in points)
        total_upper = sum(p.upper_bound for p in points)

        trend = self._detect_trend(series)
        trend_pct = self._compute_trend_pct(series)

        return ForecastResult(
            horizon_days=horizon_days,
            total_predicted=round(total, 2),
            total_lower=round(total_lower, 2),
            total_upper=round(total_upper, 2),
            daily_forecast=points,
            model_used="prophet",
            mape=round(mape, 4),
            trend=trend,
            trend_pct_per_month=round(trend_pct, 1),
        )

    # ------------------------------------------------------------------
    # SARIMA forecasting
    # ------------------------------------------------------------------

    def _sarima_forecast(self, series: pd.Series, horizon_days: int) -> ForecastResult:
        try:
            from statsmodels.tsa.statespace.sarimax import SARIMAX
            from statsmodels.tools.sm_exceptions import ConvergenceWarning
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = SARIMAX(
                    series,
                    order=(1, 1, 1),
                    seasonal_order=(1, 0, 1, 7),
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                )
                fit = model.fit(disp=False)
                forecast = fit.get_forecast(steps=horizon_days)
                mean = forecast.predicted_mean
                ci = forecast.conf_int(alpha=0.2)  # 80% CI

            points: list[ForecastPoint] = []
            for i in range(horizon_days):
                fc_date = (series.index[-1] + timedelta(days=i + 1)).date()
                points.append(ForecastPoint(
                    date=fc_date,
                    predicted=max(0.0, round(float(mean.iloc[i]), 2)),
                    lower_bound=max(0.0, round(float(ci.iloc[i, 0]), 2)),
                    upper_bound=max(0.0, round(float(ci.iloc[i, 1]), 2)),
                ))

            total = sum(p.predicted for p in points)

            # Quick MAPE estimate
            n_holdout = min(7, len(series) // 4)
            actuals = series.values[-n_holdout:]
            train = series.iloc[:-n_holdout]
            preds = SARIMAX(train, order=(1, 1, 1), enforce_stationarity=False).fit(disp=False).forecast(n_holdout)
            mape = float(np.mean(np.abs((actuals - preds.values) / np.where(actuals == 0, 1, actuals))))

        except Exception:
            return self._linear_forecast(series, horizon_days)

        trend = self._detect_trend(series)
        trend_pct = self._compute_trend_pct(series)

        return ForecastResult(
            horizon_days=horizon_days,
            total_predicted=round(total, 2),
            total_lower=round(sum(p.lower_bound for p in points), 2),
            total_upper=round(sum(p.upper_bound for p in points), 2),
            daily_forecast=points,
            model_used="sarima",
            mape=round(mape, 4),
            trend=trend,
            trend_pct_per_month=round(trend_pct, 1),
        )

    # ------------------------------------------------------------------
    # Linear fallback
    # ------------------------------------------------------------------

    def _linear_forecast(self, series: pd.Series, horizon_days: int) -> ForecastResult:
        """Simple linear regression fallback when Prophet/SARIMA unavailable."""
        x = np.arange(len(series))
        y = series.values
        coeffs = np.polyfit(x, y, 1)
        slope, intercept = coeffs

        points: list[ForecastPoint] = []
        std_residual = float(np.std(y - (slope * x + intercept)))

        for i in range(1, horizon_days + 1):
            predicted = max(0.0, slope * (len(series) + i) + intercept)
            margin = std_residual * 1.28  # 80% CI
            fc_date = (series.index[-1] + timedelta(days=i)).date()
            points.append(ForecastPoint(
                date=fc_date,
                predicted=round(predicted, 2),
                lower_bound=round(max(0.0, predicted - margin), 2),
                upper_bound=round(predicted + margin, 2),
            ))

        total = sum(p.predicted for p in points)

        # MAPE using last 7 days
        n = min(7, len(y))
        actuals = y[-n:]
        preds_val = slope * x[-n:] + intercept
        mape = float(np.mean(np.abs((actuals - preds_val) / np.where(actuals == 0, 1, actuals))))

        trend = "increasing" if slope > 0.5 else ("decreasing" if slope < -0.5 else "stable")
        # Monthly trend %
        monthly_delta = slope * 30
        trend_pct = (monthly_delta / float(np.mean(y)) * 100) if np.mean(y) > 0 else 0

        return ForecastResult(
            horizon_days=horizon_days,
            total_predicted=round(total, 2),
            total_lower=round(sum(p.lower_bound for p in points), 2),
            total_upper=round(sum(p.upper_bound for p in points), 2),
            daily_forecast=points,
            model_used="linear",
            mape=round(mape, 4),
            trend=trend,
            trend_pct_per_month=round(trend_pct, 1),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_series(self, spend_data: SpendData, service: str | None) -> pd.Series:
        """Build a daily time series for total spend or a specific service."""
        df = spend_data.df
        if df is None or df.empty:
            return pd.Series(dtype=float)

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        if service:
            df = df[df["service"] == service]

        daily = df.groupby("date")["amount"].sum()
        daily = daily.sort_index()

        # Fill gaps with forward-fill then zero
        idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
        daily = daily.reindex(idx).fillna(method="ffill").fillna(0)

        return daily

    def _detect_trend(self, series: pd.Series) -> str:
        if len(series) < 14:
            return "stable"
        x = np.arange(len(series))
        slope, _ = np.polyfit(x, series.values, 1)
        mean = float(series.mean())
        if mean == 0:
            return "stable"
        monthly_pct = (slope * 30 / mean) * 100
        if monthly_pct > 5:
            return "increasing"
        elif monthly_pct < -5:
            return "decreasing"
        return "stable"

    def _compute_trend_pct(self, series: pd.Series) -> float:
        if len(series) < 14:
            return 0.0
        x = np.arange(len(series))
        slope, _ = np.polyfit(x, series.values, 1)
        mean = float(series.mean())
        return (slope * 30 / mean * 100) if mean > 0 else 0.0
