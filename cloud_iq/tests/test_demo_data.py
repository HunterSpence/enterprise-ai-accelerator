"""
Smoke tests for demo data module.

Validates that the mock data is self-consistent and has the expected
financial figures so demo scenes render correctly.
"""

from __future__ import annotations

import pytest

from cloud_iq.demo_data import MOCK_COST_REPORT, MOCK_RECOMMENDATIONS, MOCK_SNAPSHOT


class TestMockSnapshot:
    def test_account_id_set(self) -> None:
        assert MOCK_SNAPSHOT.account_id == "123456789012"

    def test_has_ec2_instances(self) -> None:
        assert len(MOCK_SNAPSHOT.ec2_instances) >= 4

    def test_has_rds_instances(self) -> None:
        assert len(MOCK_SNAPSHOT.rds_instances) >= 2

    def test_has_unattached_ebs(self) -> None:
        unattached = [v for v in MOCK_SNAPSHOT.ebs_volumes if v.attached_instance is None]
        assert len(unattached) >= 2

    def test_has_idle_eips(self) -> None:
        idle = [e for e in MOCK_SNAPSHOT.elastic_ips if e.is_idle]
        assert len(idle) >= 1

    def test_total_cost_plausible(self) -> None:
        assert 100_000 <= MOCK_SNAPSHOT.total_estimated_monthly_cost <= 500_000


class TestMockCostReport:
    def test_has_waste_items(self) -> None:
        assert len(MOCK_COST_REPORT.waste_items) >= 5

    def test_waste_items_sorted_descending(self) -> None:
        costs = [w.estimated_monthly_waste for w in MOCK_COST_REPORT.waste_items]
        assert costs == sorted(costs, reverse=True), "Waste items should be sorted descending"

    def test_total_waste_matches_sum(self) -> None:
        expected = sum(w.estimated_monthly_waste for w in MOCK_COST_REPORT.waste_items)
        assert abs(MOCK_COST_REPORT.total_identified_waste - expected) < 0.01

    def test_has_rightsizing_recommendations(self) -> None:
        assert len(MOCK_COST_REPORT.rightsizing_recommendations) >= 1

    def test_critical_findings_exist(self) -> None:
        critical = [w for w in MOCK_COST_REPORT.waste_items if w.severity == "critical"]
        assert len(critical) >= 2

    def test_annual_savings_is_12x_monthly(self) -> None:
        monthly = MOCK_COST_REPORT.total_monthly_savings_opportunity
        annual = MOCK_COST_REPORT.annual_savings_opportunity
        assert abs(annual - monthly * 12) < 1.0


class TestMockRecommendations:
    def test_recommendations_built(self) -> None:
        assert len(MOCK_RECOMMENDATIONS) >= 5

    def test_all_have_ids(self) -> None:
        for rec in MOCK_RECOMMENDATIONS:
            assert rec.id, f"Recommendation missing id: {rec}"

    def test_all_have_positive_waste(self) -> None:
        for rec in MOCK_RECOMMENDATIONS:
            assert rec.monthly_waste_usd > 0, f"Zero waste for {rec.resource_id}"

    def test_annual_is_12x_monthly(self) -> None:
        for rec in MOCK_RECOMMENDATIONS:
            assert abs(rec.annual_waste_usd - rec.monthly_waste_usd * 12) < 0.01
