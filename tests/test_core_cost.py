"""Tests for core/cost_estimator.py — per-model rates, cache/batch math, CostBreakdown render."""

import pytest
from core.cost_estimator import CostBreakdown, CostEstimator, TokenUsageSummary
from core.models import MODEL_HAIKU_4_5, MODEL_OPUS_4_7, MODEL_SONNET_4_6


@pytest.fixture
def est():
    return CostEstimator()


class TestCostEstimatorSingleCall:
    def test_opus_more_expensive_than_sonnet(self, est):
        opus = est.estimate(MODEL_OPUS_4_7, input_tokens=1000, output_tokens=200)
        sonnet = est.estimate(MODEL_SONNET_4_6, input_tokens=1000, output_tokens=200)
        assert opus > sonnet

    def test_sonnet_more_expensive_than_haiku(self, est):
        sonnet = est.estimate(MODEL_SONNET_4_6, input_tokens=1000, output_tokens=200)
        haiku = est.estimate(MODEL_HAIKU_4_5, input_tokens=1000, output_tokens=200)
        assert sonnet > haiku

    def test_zero_tokens_zero_cost(self, est):
        cost = est.estimate(MODEL_HAIKU_4_5, input_tokens=0, output_tokens=0)
        assert cost == 0.0

    def test_batch_discount_reduces_cost(self, est):
        regular = est.estimate(MODEL_HAIKU_4_5, input_tokens=1000, output_tokens=200)
        batched = est.estimate(MODEL_HAIKU_4_5, input_tokens=1000, output_tokens=200, via_batch=True)
        assert batched < regular

    def test_batch_discount_is_50_percent(self, est):
        regular = est.estimate(MODEL_HAIKU_4_5, input_tokens=1_000_000, output_tokens=0)
        batched = est.estimate(MODEL_HAIKU_4_5, input_tokens=1_000_000, output_tokens=0, via_batch=True)
        assert abs(batched - regular * 0.5) < 1e-9

    def test_cache_read_cheaper_than_input(self, est):
        cache_cost = est.estimate(MODEL_OPUS_4_7, input_tokens=0, output_tokens=0, cache_read=1_000_000)
        input_cost = est.estimate(MODEL_OPUS_4_7, input_tokens=1_000_000, output_tokens=0)
        assert cache_cost < input_cost

    def test_unknown_model_falls_back_to_sonnet(self, est):
        cost_unknown = est.estimate("unknown-model", input_tokens=1000, output_tokens=200)
        cost_sonnet = est.estimate(MODEL_SONNET_4_6, input_tokens=1000, output_tokens=200)
        assert cost_unknown == cost_sonnet


class TestTokenUsageSummary:
    def test_add_and_count(self):
        usage = TokenUsageSummary()
        usage.add(model=MODEL_HAIKU_4_5, input_tokens=500, output_tokens=100)
        assert usage.total_calls() == 1

    def test_multiple_adds(self):
        usage = TokenUsageSummary()
        for _ in range(5):
            usage.add(model=MODEL_SONNET_4_6, input_tokens=100, output_tokens=50)
        assert usage.total_calls() == 5


class TestCostBreakdown:
    def test_summary_returns_breakdown(self):
        est = CostEstimator()
        usage = TokenUsageSummary()
        usage.add(model=MODEL_HAIKU_4_5, input_tokens=1000, output_tokens=300)
        usage.add(model=MODEL_OPUS_4_7, input_tokens=500, output_tokens=100)
        breakdown = est.summary(usage)
        assert isinstance(breakdown, CostBreakdown)
        assert breakdown.total_usd > 0

    def test_summary_per_model_present(self):
        est = CostEstimator()
        usage = TokenUsageSummary()
        usage.add(model=MODEL_HAIKU_4_5, input_tokens=1000, output_tokens=200)
        breakdown = est.summary(usage)
        assert MODEL_HAIKU_4_5 in breakdown.per_model
        assert breakdown.per_model[MODEL_HAIKU_4_5]["calls"] == 1

    def test_render_markdown_contains_header(self):
        est = CostEstimator()
        usage = TokenUsageSummary()
        usage.add(model=MODEL_SONNET_4_6, input_tokens=100, output_tokens=50)
        breakdown = est.summary(usage)
        md = breakdown.render_markdown()
        assert "## Cost Estimate" in md
        assert "Total:" in md

    def test_render_markdown_contains_savings_section(self):
        est = CostEstimator()
        usage = TokenUsageSummary()
        usage.add(model=MODEL_HAIKU_4_5, input_tokens=100, output_tokens=50, cache_read=200)
        breakdown = est.summary(usage)
        md = breakdown.render_markdown()
        assert "Savings" in md

    def test_render_text_short_form(self):
        est = CostEstimator()
        usage = TokenUsageSummary()
        usage.add(model=MODEL_HAIKU_4_5, input_tokens=500, output_tokens=100)
        breakdown = est.summary(usage)
        text = breakdown.render_text()
        assert "Cost:" in text

    def test_batch_savings_positive(self):
        est = CostEstimator()
        usage = TokenUsageSummary()
        usage.add(model=MODEL_SONNET_4_6, input_tokens=1000, output_tokens=200, via_batch=True)
        breakdown = est.summary(usage)
        assert breakdown.savings_vs_no_batch_usd > 0
