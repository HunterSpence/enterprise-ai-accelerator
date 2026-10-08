"""Acceptance tests for the Haiku 5.5 migration.

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


# --- Call sites that go through AIClient.thinking(): Haiku 5.5 thinks adaptively and
# --- thinking tokens share max_tokens. At effort high with a small cap the reply can be
# --- thinking-only (empty text), so these requests must be low effort with room for text.

def _thinking_then_text(text):
    usage = SimpleNamespace(
        input_tokens=10, output_tokens=10, cache_read_input_tokens=0,
        cache_creation_input_tokens=0, iterations=None,
    )
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        stop_reason="end_turn", stop_details=None, model=HAIKU_5_5, usage=usage,
    )


def _stub_ai_client(text):
    from unittest.mock import AsyncMock, MagicMock

    from core.ai_client import AIClient

    raw = MagicMock()
    raw.messages.create = AsyncMock(return_value=_thinking_then_text(text))
    return AIClient(client=raw, default_model=HAIKU_5_5, enable_fallbacks=False), raw


def test_remediation_generator_requests_low_effort_with_room_for_text():
    from policy_guard.remediation_generator import RemediationGenerator

    hcl = 'resource "aws_s3_bucket" "b" {}'
    gen = RemediationGenerator(rate_limit_delay=0)
    gen._client, raw = _stub_ai_client(hcl)
    result = gen.generate_for_finding("PG-NO-TEMPLATE-1", "t", "HIGH", "cis_aws", "d", "r")
    kwargs = raw.messages.create.call_args.kwargs
    assert kwargs["output_config"] == {"effort": "low"}
    assert kwargs["max_tokens"] == 1024
    assert (result.generated_by, result.remediation_hcl) == ("claude", hcl)


async def test_nl_query_requests_low_effort_with_room_for_text():
    from datetime import datetime, timezone

    from cloud_iq.nl_query import NLQueryEngine
    from cloud_iq.scanner import InfrastructureSnapshot

    snap = InfrastructureSnapshot(
        account_id="123456789012", regions=["us-east-1"], scanned_at=datetime.now(timezone.utc)
    )
    engine = NLQueryEngine(snap, anthropic_api_key="test-key")
    engine._client, raw = _stub_ai_client("There are no instances.")
    result = await engine.query("How many instances?")
    kwargs = raw.messages.create.call_args.kwargs
    assert kwargs["output_config"] == {"effort": "low"}
    assert kwargs["max_tokens"] == 1024
    assert result.answer == "There are no instances."
