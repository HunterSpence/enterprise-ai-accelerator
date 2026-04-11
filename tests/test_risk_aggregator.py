"""
Tests for risk_aggregator.py (repo root)
"""
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from risk_aggregator import (
    WorkloadRiskAggregator,
    RiskInput,
    RiskScore,
    DimensionScore,
    DIMENSION_WEIGHTS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def aggregator():
    return WorkloadRiskAggregator()


@pytest.fixture
def high_risk_input():
    return RiskInput(
        policy_score=20.0,
        policy_critical_findings=5,
        policy_high_findings=10,
        finops_waste_pct=55.0,
        finops_anomaly_count=8,
        finops_monthly_waste_usd=45000.0,
        migration_risk_score=85.0,
        migration_critical_workloads=3,
        migration_has_circular_deps=True,
        audit_trail_present=False,
        eu_ai_act_gap_count=10,
        ai_systems_count=3,
        high_risk_ai_systems=2,
    )


@pytest.fixture
def low_risk_input():
    return RiskInput(
        policy_score=92.0,
        policy_critical_findings=0,
        policy_high_findings=0,
        finops_waste_pct=5.0,
        finops_anomaly_count=0,
        migration_risk_score=15.0,
        migration_critical_workloads=0,
        audit_trail_present=True,
        audit_chain_verified=True,
        eu_ai_act_gap_count=0,
        ai_systems_count=1,
        high_risk_ai_systems=0,
    )


@pytest.fixture
def all_zeros_input():
    return RiskInput()


@pytest.fixture
def all_maxed_input():
    return RiskInput(
        policy_score=0.0,
        policy_critical_findings=100,
        policy_high_findings=100,
        finops_waste_pct=100.0,
        finops_anomaly_count=50,
        finops_monthly_waste_usd=999999.0,
        migration_risk_score=100.0,
        migration_critical_workloads=50,
        migration_has_circular_deps=True,
        migration_oracle_dependency=True,
        audit_trail_present=False,
        eu_ai_act_gap_count=20,
        ai_systems_count=10,
        high_risk_ai_systems=10,
    )


# ---------------------------------------------------------------------------
# Overall score ordering: high risk > low risk
# ---------------------------------------------------------------------------

class TestOverallScoreOrdering:

    def test_high_risk_score_greater_than_low_risk(self, aggregator, high_risk_input, low_risk_input):
        high = aggregator.compute(high_risk_input)
        low = aggregator.compute(low_risk_input)
        assert high.overall_score > low.overall_score

    def test_high_risk_score_above_60(self, aggregator, high_risk_input):
        score = aggregator.compute(high_risk_input)
        assert score.overall_score > 60

    def test_low_risk_score_below_40(self, aggregator, low_risk_input):
        score = aggregator.compute(low_risk_input)
        assert score.overall_score < 40

    def test_score_bounded_0_to_100(self, aggregator, all_maxed_input):
        score = aggregator.compute(all_maxed_input)
        assert 0.0 <= score.overall_score <= 100.0

    def test_score_never_negative(self, aggregator, all_zeros_input):
        score = aggregator.compute(all_zeros_input)
        assert score.overall_score >= 0.0


# ---------------------------------------------------------------------------
# Dimension scores present
# ---------------------------------------------------------------------------

class TestDimensionScores:

    def test_all_four_dimensions_present(self, aggregator, high_risk_input):
        score = aggregator.compute(high_risk_input)
        dim_names = {d.dimension for d in score.dimensions}
        assert "security_compliance" in dim_names
        assert "financial_waste" in dim_names
        assert "migration_complexity" in dim_names
        assert "ai_governance" in dim_names

    def test_dimension_has_required_fields(self, aggregator, high_risk_input):
        score = aggregator.compute(high_risk_input)
        for dim in score.dimensions:
            assert isinstance(dim.raw_score, float)
            assert isinstance(dim.weighted_score, float)
            assert isinstance(dim.drivers, list)
            assert isinstance(dim.weight, float)
            assert isinstance(dim.dimension, str)

    def test_dimension_weighted_score_equals_raw_times_weight(self, aggregator, low_risk_input):
        score = aggregator.compute(low_risk_input)
        for dim in score.dimensions:
            expected = round(dim.raw_score * dim.weight, 2)
            assert abs(dim.weighted_score - expected) < 0.1, (
                f"{dim.dimension}: weighted_score={dim.weighted_score}, expected={expected}"
            )

    def test_dimension_raw_score_bounded(self, aggregator, all_maxed_input):
        score = aggregator.compute(all_maxed_input)
        for dim in score.dimensions:
            assert 0.0 <= dim.raw_score <= 100.0

    def test_dimensions_have_drivers(self, aggregator, high_risk_input):
        score = aggregator.compute(high_risk_input)
        for dim in score.dimensions:
            assert len(dim.drivers) >= 1

    def test_security_dimension_weight_matches_constant(self, aggregator, high_risk_input):
        score = aggregator.compute(high_risk_input)
        sec_dim = next(d for d in score.dimensions if d.dimension == "security_compliance")
        assert sec_dim.weight == DIMENSION_WEIGHTS["security_compliance"]


# ---------------------------------------------------------------------------
# Risk tier values
# ---------------------------------------------------------------------------

class TestRiskTiers:

    def test_high_risk_tier_is_critical_or_high(self, aggregator, high_risk_input):
        score = aggregator.compute(high_risk_input)
        assert score.risk_tier in ("Critical", "High")

    def test_low_risk_tier_is_low_or_healthy(self, aggregator, low_risk_input):
        score = aggregator.compute(low_risk_input)
        assert score.risk_tier in ("Healthy", "Low", "Medium")

    def test_score_80_plus_is_critical(self, aggregator):
        inp = RiskInput(
            policy_score=0.0,
            policy_critical_findings=20,
            finops_waste_pct=80.0,
            finops_anomaly_count=20,
            audit_trail_present=False,
            high_risk_ai_systems=5,
            eu_ai_act_gap_count=15,
            ai_systems_count=5,
        )
        score = aggregator.compute(inp)
        if score.overall_score >= 80:
            assert score.risk_tier == "Critical"

    def test_all_valid_tiers(self, aggregator):
        valid_tiers = {"Healthy", "Low", "Medium", "High", "Critical"}
        for score_val in [10, 25, 45, 65, 85]:
            tier = WorkloadRiskAggregator._classify_tier(float(score_val))
            assert tier in valid_tiers

    def test_classify_tier_boundaries(self):
        assert WorkloadRiskAggregator._classify_tier(80.0) == "Critical"
        assert WorkloadRiskAggregator._classify_tier(79.9) == "High"
        assert WorkloadRiskAggregator._classify_tier(60.0) == "High"
        assert WorkloadRiskAggregator._classify_tier(59.9) == "Medium"
        assert WorkloadRiskAggregator._classify_tier(40.0) == "Medium"
        assert WorkloadRiskAggregator._classify_tier(39.9) == "Low"
        assert WorkloadRiskAggregator._classify_tier(20.0) == "Low"
        assert WorkloadRiskAggregator._classify_tier(19.9) == "Healthy"

    def test_risk_tier_color_returns_string(self, aggregator, high_risk_input):
        score = aggregator.compute(high_risk_input)
        assert isinstance(score.risk_tier_color, str)

    def test_all_tiers_have_colors(self):
        valid_tiers = ["Critical", "High", "Medium", "Low", "Healthy"]
        score = RiskScore(overall_score=50.0, risk_tier="Medium", confidence="Low")
        for tier in valid_tiers:
            score.risk_tier = tier
            assert score.risk_tier_color != "white" or tier == "unknown"


# ---------------------------------------------------------------------------
# Edge cases: all zeros
# ---------------------------------------------------------------------------

class TestAllZerosInput:

    def test_all_zeros_returns_risk_score(self, aggregator, all_zeros_input):
        score = aggregator.compute(all_zeros_input)
        assert isinstance(score, RiskScore)

    def test_all_zeros_confidence_is_low(self, aggregator, all_zeros_input):
        score = aggregator.compute(all_zeros_input)
        assert score.confidence == "Low"

    def test_all_zeros_no_data_dimensions_have_default_scores(self, aggregator, all_zeros_input):
        score = aggregator.compute(all_zeros_input)
        for dim in score.dimensions:
            assert dim.data_available is False or dim.raw_score >= 0


# ---------------------------------------------------------------------------
# Edge cases: all maxed out
# ---------------------------------------------------------------------------

class TestAllMaxedInput:

    def test_all_maxed_score_is_high(self, aggregator, all_maxed_input):
        score = aggregator.compute(all_maxed_input)
        assert score.overall_score >= 60

    def test_all_maxed_confidence_is_high(self, aggregator, all_maxed_input):
        score = aggregator.compute(all_maxed_input)
        assert score.confidence in ("High", "Medium")

    def test_all_maxed_has_priority_actions(self, aggregator, all_maxed_input):
        score = aggregator.compute(all_maxed_input)
        assert len(score.priority_actions) >= 1

    def test_all_maxed_top_risk_driver_present(self, aggregator, all_maxed_input):
        score = aggregator.compute(all_maxed_input)
        assert len(score.top_risk_driver) > 0


# ---------------------------------------------------------------------------
# Compound penalty
# ---------------------------------------------------------------------------

class TestCompoundPenalty:

    def test_critical_security_plus_high_finops_scores_higher(self, aggregator):
        base = RiskInput(
            policy_score=30.0,
            policy_critical_findings=1,
            finops_waste_pct=45.0,  # triggers compound penalty
        )
        no_compound = RiskInput(
            policy_score=30.0,
            policy_critical_findings=1,
            finops_waste_pct=10.0,  # no compound penalty
        )
        score_compound = aggregator.compute(base)
        score_no_compound = aggregator.compute(no_compound)
        assert score_compound.overall_score >= score_no_compound.overall_score


# ---------------------------------------------------------------------------
# Return type and structure
# ---------------------------------------------------------------------------

class TestReturnStructure:

    def test_compute_returns_risk_score(self, aggregator, low_risk_input):
        result = aggregator.compute(low_risk_input)
        assert isinstance(result, RiskScore)

    def test_risk_score_has_executive_narrative(self, aggregator, high_risk_input):
        score = aggregator.compute(high_risk_input)
        assert isinstance(score.executive_narrative, str)
        assert len(score.executive_narrative) > 20

    def test_risk_score_input_summary(self, aggregator, high_risk_input):
        score = aggregator.compute(high_risk_input)
        assert isinstance(score.input_summary, dict)
        assert "modules_with_data" in score.input_summary

    def test_risk_score_computed_at_populated(self, aggregator, low_risk_input):
        score = aggregator.compute(low_risk_input)
        assert score.computed_at.endswith("Z")

    def test_risk_drivers_list(self, aggregator, high_risk_input):
        score = aggregator.compute(high_risk_input)
        assert isinstance(score.risk_drivers, list)
        assert len(score.risk_drivers) >= 1
