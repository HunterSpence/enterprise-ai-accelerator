"""Acceptance tests for the Haiku 4.5 -> 5.5 migration.

Four independent tests. Each imports inside the function so each one fails on
the pre-migration code for its own reason (no shared ImportError).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

HAIKU_5_5 = "claude-haiku-5-5"


def test_describe_model_haiku_5_5_capabilities():
    from core.models import describe_model

    caps = describe_model(HAIKU_5_5)
    assert caps["family"] == "haiku"
    assert caps["context_window"] == 1_000_000
    assert caps["max_output_tokens"] == 128_000
    # Adaptive thinking + effort are what keep budget_tokens (a 400) from being sent.
    assert caps["supports_adaptive_thinking"] is True
    assert caps["supports_effort"] is True


def test_router_cheap_path_is_haiku_5_5_low():
    from core.model_router import ModelRouter, RoutingTask

    decision = ModelRouter().route_decision(
        RoutingTask(kind="classification", token_count_estimate=500)
    )
    assert (decision.model, decision.effort) == (HAIKU_5_5, "low")


def test_response_text_skips_thinking_blocks():
    from core.ai_client import response_text

    blocks = [{"type": "thinking", "thinking": "", "signature": "s"}, {"type": "text", "text": "x"}]
    assert response_text(blocks) == "x"
    # SDK objects, and a full message wrapping the blocks
    objs = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text="x")]
    assert response_text(objs) == "x"
    assert response_text(SimpleNamespace(content=objs)) == "x"
    assert response_text({"content": blocks}) == "x"
    assert response_text(SimpleNamespace(content=[])) == ""


def test_cost_estimator_tiers_each_request():
    from core.cost_estimator import CostEstimator, TokenUsageSummary

    est = CostEstimator()
    short = est.estimate(HAIKU_5_5, input_tokens=50_000, output_tokens=10_000)
    long_ = est.estimate(HAIKU_5_5, input_tokens=200_000, output_tokens=10_000)
    assert short == pytest.approx(0.01)
    assert long_ == pytest.approx(0.125)

    usage = TokenUsageSummary()
    usage.add(model=HAIKU_5_5, input_tokens=50_000, output_tokens=10_000)
    usage.add_from_response(
        SimpleNamespace(
            model=HAIKU_5_5, input_tokens=200_000, output_tokens=10_000,
            cache_read_tokens=0, cache_creation_tokens=0,
        )
    )
    assert est.summary(usage).total_usd == pytest.approx(short + long_)

    # The tier follows each request's prompt, never the summed tokens:
    # two 60K prompts (120K total) are both on the cheap tier.
    pair = TokenUsageSummary()
    for _ in range(2):
        pair.add(model=HAIKU_5_5, input_tokens=60_000, output_tokens=0)
    assert est.summary(pair).total_usd == pytest.approx(0.012)
    # Cached tokens count toward the prompt; the boundary itself is the cheap tier.
    assert est.estimate(HAIKU_5_5, input_tokens=100_000, output_tokens=0) == pytest.approx(0.01)
    assert est.estimate(
        HAIKU_5_5, input_tokens=50_000, output_tokens=0, cache_read=60_000
    ) == pytest.approx(50_000 * 0.50 / 1e6 + 60_000 * 0.05 / 1e6)
