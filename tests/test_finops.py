"""Tests for finops_intelligence/ — carbon_tracker, ri_sp_optimizer, right_sizer, savings_reporter."""

# finops_intelligence/__init__.py imports duckdb which may not be installed.
# Stub out the parent package before importing submodules directly.
import sys
import types

if "finops_intelligence" not in sys.modules:
    _pkg = types.ModuleType("finops_intelligence")
    _pkg.__path__ = ["finops_intelligence"]  # type: ignore[assignment]
    _pkg.__package__ = "finops_intelligence"
    sys.modules["finops_intelligence"] = _pkg

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures — minimal workload objects
# ---------------------------------------------------------------------------

def _workload(resource_id="i-001", instance_type="m5.large", region="us-east-1", vcpu=2, ram_gb=8.0):
    wl = MagicMock()
    wl.resource_id = resource_id
    wl.instance_type = instance_type
    wl.region = region
    wl.vcpu = vcpu
    wl.ram_gb = ram_gb
    wl.monthly_hours = 730.0
    return wl


class TestCarbonTracker:
    def test_empty_workloads_returns_zero_emissions(self):
        from finops_intelligence.carbon_tracker import CarbonTracker
        tracker = CarbonTracker(cloud="AWS")
        report = tracker.estimate([])
        assert report.total_monthly_kgco2e == 0.0

    def test_single_workload_positive_emissions(self):
        from finops_intelligence.carbon_tracker import CarbonTracker
        tracker = CarbonTracker(cloud="AWS")
        wl = _workload()
        report = tracker.estimate([wl])
        assert report.total_monthly_kgco2e > 0

    def test_emissions_scales_with_vcpu(self):
        from finops_intelligence.carbon_tracker import CarbonTracker
        tracker = CarbonTracker(cloud="AWS")
        small = _workload("i-1", "t3.medium", vcpu=1)
        large = _workload("i-2", "m5.16xlarge", vcpu=32)
        r_small = tracker.estimate([small])
        r_large = tracker.estimate([large])
        assert r_large.total_monthly_kgco2e > r_small.total_monthly_kgco2e

    def test_report_has_per_workload(self):
        from finops_intelligence.carbon_tracker import CarbonTracker
        tracker = CarbonTracker(cloud="AWS")
        report = tracker.estimate([_workload()])
        assert len(report.per_workload) == 1

    def test_to_dict_keys(self):
        from finops_intelligence.carbon_tracker import CarbonTracker
        tracker = CarbonTracker(cloud="AWS")
        report = tracker.estimate([_workload()])
        d = report.to_dict()
        assert "total_monthly_kgco2e" in d
        assert "workload_count" in d

    def test_monthly_tco2e_property(self):
        from finops_intelligence.carbon_tracker import CarbonTracker
        tracker = CarbonTracker(cloud="AWS")
        report = tracker.estimate([_workload()])
        assert report.monthly_tco2e == report.total_monthly_tonnes_co2e

    def test_multiple_regions_aggregated(self):
        from finops_intelligence.carbon_tracker import CarbonTracker
        tracker = CarbonTracker(cloud="AWS")
        wl1 = _workload("i-1", region="us-east-1")
        wl2 = _workload("i-2", region="eu-west-1")
        report = tracker.estimate([wl1, wl2])
        assert len(report.per_workload) == 2


class TestRightSizerClassifications:
    def _make_rec(self, classification, cpu_p95=20.0):
        from finops_intelligence.right_sizer import RightSizingRec, MetricsSnapshot
        snap = MetricsSnapshot(
            resource_id="i-001", instance_type="m5.large", region="us-east-1",
            cpu_avg=15.0, cpu_p95=cpu_p95, idle_days=0, data_points=336,
        )
        return RightSizingRec(
            resource_id="i-001",
            current_type="m5.large",
            recommended_type="t3.medium",
            current_monthly_cost_usd=70.0,
            recommended_monthly_cost_usd=35.0,
            projected_monthly_savings=35.0,
            savings_pct=50.0,
            risk="low",
            classification=classification,
            region="us-east-1",
            metrics_snapshot=snap,
        )

    def test_over_provisioned_classification(self):
        rec = self._make_rec("over_provisioned", cpu_p95=20.0)
        assert rec.classification == "over_provisioned"
        assert rec.projected_monthly_savings > 0

    def test_under_provisioned_classification(self):
        rec = self._make_rec("under_provisioned", cpu_p95=90.0)
        assert rec.classification == "under_provisioned"

    def test_idle_classification(self):
        rec = self._make_rec("idle", cpu_p95=2.0)
        assert rec.classification == "idle"

    def test_to_dict_has_required_keys(self):
        rec = self._make_rec("over_provisioned")
        d = rec.to_dict()
        assert "resource_id" in d
        assert "classification" in d
        assert "projected_monthly_savings" in d


class TestInstanceCatalog:
    def test_catalog_loads(self):
        from finops_intelligence.right_sizer import _InstanceCatalog
        catalog = _InstanceCatalog.load()
        assert len(catalog) > 0

    def test_m5_large_in_catalog(self):
        from finops_intelligence.right_sizer import _InstanceCatalog
        inst = _InstanceCatalog.get("m5.large")
        assert inst is not None
        assert "vcpu" in inst

    def test_monthly_cost_positive(self):
        from finops_intelligence.right_sizer import _InstanceCatalog
        cost = _InstanceCatalog.monthly_cost("m5.large")
        assert cost > 0


class TestSavingsReporter:
    def test_reporter_instantiates(self):
        from finops_intelligence.savings_reporter import SavingsReporter
        reporter = SavingsReporter()
        assert reporter is not None

    def test_savings_opportunity_dataclass(self):
        from finops_intelligence.savings_reporter import SavingsOpportunity
        opp = SavingsOpportunity(
            opportunity_id="op-1",
            category="ri_sp",
            resource_group="m5.large/us-east-1",
            description="Switch to 1-year RI",
            monthly_savings_usd=100.0,
            upfront_cost_usd=0.0,
            effort_level="low",
            risk="low",
            breakeven_months=0.0,
            priority_score=10.0,
        )
        assert opp.monthly_savings_usd == 100.0
        assert opp.category == "ri_sp"

    def test_executive_report_dataclass(self):
        from finops_intelligence.savings_reporter import ExecutiveSavingsReport
        report = ExecutiveSavingsReport(
            report_date="2026-04-16",
            current_monthly_spend_usd=10_000.0,
            total_achievable_savings_usd=2_000.0,
            savings_pct=20.0,
            co2e_reduction_kg_monthly=50.0,
        )
        assert report.savings_pct == 20.0


class TestRISPOptimizer:
    def test_discount_rates_defined(self):
        from finops_intelligence.ri_sp_optimizer import _DISCOUNT_RATES, _MAX_COVERAGE
        assert "ri_1y_no_upfront" in _DISCOUNT_RATES
        assert _DISCOUNT_RATES["ri_1y_no_upfront"] > 0
        assert _MAX_COVERAGE <= 1.0

    def test_recommendation_dataclass(self):
        from finops_intelligence.ri_sp_optimizer import Recommendation
        rec = Recommendation(
            resource_group="m5.large/us-east-1",
            service="Amazon EC2",
            instance_family="m5",
            region="us-east-1",
            operating_system="Linux",
            commitment_type="ri_1y_no_upfront",
            current_monthly_cost=1000.0,
            recommended_commitment=800.0,
            projected_savings_monthly=288.0,
            upfront_cost=0.0,
            breakeven_months=0.0,
            coverage_pct=0.80,
            utilization_risk="low",
            confidence=0.9,
            baseline_hourly_usage=1.1,
            lookback_days=90,
            lookback_data_points=2160,
        )
        assert rec.projected_savings_monthly == 288.0
        assert rec.coverage_pct == 0.80
