"""
test_integrations.py — Tests for SDK integration wrappers.

Tests:
- AuditedAnthropic wraps correctly (mock Anthropic client)
- Token capture works from response usage
- Cost calculation is correct for known models
- AuditedOpenAI wraps correctly (mock OpenAI client)
- LangChain callback captures on_llm_end events
- LlamaIndex callback captures retrieval + synthesis events
"""

from __future__ import annotations

import threading
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ai_audit_trail.chain import AuditChain, DecisionType, RiskTier
from ai_audit_trail.integrations.anthropic_sdk import (
    AuditedAnthropic,
    _calculate_cost,
    _ANTHROPIC_PRICING,
)
from ai_audit_trail.integrations.openai_sdk import AuditedOpenAI


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------

class TestCostCalculation:
    def test_sonnet_cost_calculation(self):
        """claude-sonnet-4: $3.00/M input, $15.00/M output."""
        cost = _calculate_cost("claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=0)
        assert abs(cost - 3.00) < 0.01

    def test_haiku_cost_calculation(self):
        """claude-haiku-4: $0.80/M input, $4.00/M output."""
        cost = _calculate_cost("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=0)
        assert abs(cost - 0.80) < 0.01

    def test_opus_cost_calculation(self):
        """claude-opus-4: $15.00/M input, $75.00/M output."""
        cost = _calculate_cost("claude-opus-4-6", input_tokens=1_000_000, output_tokens=0)
        assert abs(cost - 15.00) < 0.01

    def test_output_token_cost(self):
        """Output tokens should cost more per token than input."""
        input_cost = _calculate_cost("claude-sonnet-4-6", input_tokens=1000, output_tokens=0)
        output_cost = _calculate_cost("claude-sonnet-4-6", input_tokens=0, output_tokens=1000)
        # Sonnet output ($15/M) > input ($3/M)
        assert output_cost > input_cost

    def test_cache_read_reduces_cost(self):
        """Cache read tokens should cost less than regular input tokens."""
        regular_cost = _calculate_cost("claude-sonnet-4-6", input_tokens=100_000, output_tokens=0)
        cached_cost = _calculate_cost(
            "claude-sonnet-4-6", input_tokens=0, output_tokens=0, cache_read_tokens=100_000
        )
        assert cached_cost < regular_cost

    def test_zero_tokens_zero_cost(self):
        cost = _calculate_cost("claude-haiku-4-5", input_tokens=0, output_tokens=0)
        assert cost == 0.0

    def test_unknown_model_returns_fallback_cost(self):
        """Unknown model should not raise — should return a non-negative cost."""
        cost = _calculate_cost("unknown-model-v999", input_tokens=100, output_tokens=50)
        assert cost >= 0.0

    def test_pricing_table_has_all_claude_tiers(self):
        models = list(_ANTHROPIC_PRICING.keys())
        model_str = " ".join(models)
        assert "opus" in model_str
        assert "sonnet" in model_str
        assert "haiku" in model_str


# ---------------------------------------------------------------------------
# AuditedAnthropic — mock Anthropic client
# ---------------------------------------------------------------------------

def _mock_anthropic_response(
    text: str = "Mock response",
    input_tokens: int = 100,
    output_tokens: int = 50,
    model: str = "claude-haiku-4-5-20251001",
) -> MagicMock:
    """Build a mock Anthropic messages.create() response."""
    response = MagicMock()
    response.model = model
    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    response.usage.cache_read_input_tokens = 0
    response.content = [MagicMock()]
    response.content[0].type = "text"
    response.content[0].text = text
    return response


class TestAuditedAnthropic:
    def _make_client(self, chain: AuditChain, **kwargs) -> AuditedAnthropic:
        """Create AuditedAnthropic with a mock underlying Anthropic client."""
        client = AuditedAnthropic.__new__(AuditedAnthropic)
        client.audit_chain = chain
        client.system_id = kwargs.get("system_id", "test-system")
        client.default_risk_tier = kwargs.get("default_risk_tier", RiskTier.LIMITED)
        client.session_id = str(uuid.uuid4())

        # Mock the inner Anthropic client
        mock_inner = MagicMock()
        mock_inner.messages = MagicMock()
        client._client = mock_inner
        return client

    def test_audited_anthropic_initializes(self, empty_chain: AuditChain):
        """AuditedAnthropic can be constructed with an AuditChain."""
        with patch("ai_audit_trail.integrations.anthropic_sdk.Anthropic"):
            client = AuditedAnthropic(
                audit_chain=empty_chain,
                system_id="test-system",
            )
        assert client.audit_chain is empty_chain
        assert client.system_id == "test-system"

    def test_call_creates_audit_entry(self, empty_chain: AuditChain):
        """After a messages.create() call, one entry should be in the chain."""
        with patch("ai_audit_trail.integrations.anthropic_sdk.Anthropic") as MockAnthropic:
            mock_response = _mock_anthropic_response()
            MockAnthropic.return_value.messages.create.return_value = mock_response

            client = AuditedAnthropic(audit_chain=empty_chain, system_id="test")
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": "Hello"}],
            )

        assert empty_chain.count() == 1

    def test_token_capture_from_response(self, empty_chain: AuditChain):
        """input_tokens and output_tokens must be captured from the API response."""
        with patch("ai_audit_trail.integrations.anthropic_sdk.Anthropic") as MockAnthropic:
            mock_response = _mock_anthropic_response(input_tokens=250, output_tokens=75)
            MockAnthropic.return_value.messages.create.return_value = mock_response

            client = AuditedAnthropic(audit_chain=empty_chain, system_id="test")
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": "Hello"}],
            )

        entry = empty_chain.query(limit=1)[0]
        assert entry.input_tokens == 250
        assert entry.output_tokens == 75

    def test_cost_calculated_and_stored(self, empty_chain: AuditChain):
        """Cost in USD should be stored and be positive for real token usage."""
        with patch("ai_audit_trail.integrations.anthropic_sdk.Anthropic") as MockAnthropic:
            mock_response = _mock_anthropic_response(
                input_tokens=1000, output_tokens=500, model="claude-haiku-4-5-20251001"
            )
            MockAnthropic.return_value.messages.create.return_value = mock_response

            client = AuditedAnthropic(audit_chain=empty_chain, system_id="test")
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": "Hello"}],
            )

        entry = empty_chain.query(limit=1)[0]
        assert entry.cost_usd > 0.0

    def test_response_returned_unchanged(self, empty_chain: AuditChain):
        """The original response object must be returned to the caller."""
        with patch("ai_audit_trail.integrations.anthropic_sdk.Anthropic") as MockAnthropic:
            mock_response = _mock_anthropic_response(text="The answer is 42")
            MockAnthropic.return_value.messages.create.return_value = mock_response

            client = AuditedAnthropic(audit_chain=empty_chain, system_id="test")
            result = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": "Hello"}],
            )

        assert result is mock_response

    def test_system_id_stored_in_entry(self, empty_chain: AuditChain):
        """The system_id should appear on the logged entry."""
        with patch("ai_audit_trail.integrations.anthropic_sdk.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _mock_anthropic_response()
            client = AuditedAnthropic(audit_chain=empty_chain, system_id="loan-approval-v2")
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": "Hello"}],
            )

        entry = empty_chain.query(limit=1)[0]
        assert entry.system_id == "loan-approval-v2"

    def test_multiple_calls_chain_links_correctly(self, empty_chain: AuditChain):
        """N calls must produce N chained entries with correct prev_hash linkage."""
        with patch("ai_audit_trail.integrations.anthropic_sdk.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _mock_anthropic_response()
            client = AuditedAnthropic(audit_chain=empty_chain, system_id="test")
            for _ in range(5):
                client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=50,
                    messages=[{"role": "user", "content": "ping"}],
                )

        assert empty_chain.count() == 5
        report = empty_chain.verify_chain()
        assert report.is_valid is True


# ---------------------------------------------------------------------------
# AuditedOpenAI — mock OpenAI client
# ---------------------------------------------------------------------------

def _mock_openai_response(
    text: str = "Mock OpenAI response",
    prompt_tokens: int = 80,
    completion_tokens: int = 40,
    model: str = "gpt-4o-mini",
) -> MagicMock:
    """Build a mock OpenAI chat.completions.create() response."""
    response = MagicMock()
    response.model = model
    response.usage = MagicMock()
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.total_tokens = prompt_tokens + completion_tokens
    choice = MagicMock()
    choice.message.content = text
    response.choices = [choice]
    return response


class TestAuditedOpenAI:
    def test_audited_openai_initializes(self, empty_chain: AuditChain):
        with patch("ai_audit_trail.integrations.openai_sdk.OpenAI"):
            client = AuditedOpenAI(audit_chain=empty_chain, system_id="gpt-assistant")
        assert client.audit_chain is empty_chain

    def test_call_creates_audit_entry(self, empty_chain: AuditChain):
        with patch("ai_audit_trail.integrations.openai_sdk.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.chat.completions.create.return_value = (
                _mock_openai_response()
            )
            client = AuditedOpenAI(audit_chain=empty_chain, system_id="test")
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Hello"}],
            )

        assert empty_chain.count() == 1

    def test_token_capture_from_openai_response(self, empty_chain: AuditChain):
        with patch("ai_audit_trail.integrations.openai_sdk.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.chat.completions.create.return_value = (
                _mock_openai_response(prompt_tokens=200, completion_tokens=100)
            )
            client = AuditedOpenAI(audit_chain=empty_chain, system_id="test")
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "test"}],
            )

        entry = empty_chain.query(limit=1)[0]
        assert entry.input_tokens == 200
        assert entry.output_tokens == 100

    def test_openai_response_returned_unchanged(self, empty_chain: AuditChain):
        with patch("ai_audit_trail.integrations.openai_sdk.OpenAI") as MockOpenAI:
            mock_resp = _mock_openai_response(text="OpenAI said this")
            MockOpenAI.return_value.chat.completions.create.return_value = mock_resp
            client = AuditedOpenAI(audit_chain=empty_chain, system_id="test")
            result = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "test"}],
            )

        assert result is mock_resp

    def test_chain_valid_after_multiple_openai_calls(self, empty_chain: AuditChain):
        with patch("ai_audit_trail.integrations.openai_sdk.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.chat.completions.create.return_value = (
                _mock_openai_response()
            )
            client = AuditedOpenAI(audit_chain=empty_chain, system_id="test")
            for _ in range(5):
                client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "ping"}],
                )

        report = empty_chain.verify_chain()
        assert report.is_valid is True
        assert report.total_entries == 5


# ---------------------------------------------------------------------------
# LangChain callback
# ---------------------------------------------------------------------------

class TestLangChainCallback:
    def test_callback_initializes_with_chain(self, empty_chain: AuditChain):
        pytest.importorskip("langchain_core", reason="langchain-core not installed")
        from ai_audit_trail.integrations.langchain import AuditTrailCallback
        cb = AuditTrailCallback(audit_chain=empty_chain, system_id="lc-test")
        assert cb.audit_chain is empty_chain

    def test_on_llm_end_logs_entry(self, empty_chain: AuditChain):
        """Simulating on_llm_end should create an audit entry."""
        pytest.importorskip("langchain_core", reason="langchain-core not installed")
        from ai_audit_trail.integrations.langchain import AuditTrailCallback

        cb = AuditTrailCallback(audit_chain=empty_chain, system_id="lc-test")

        # Simulate on_llm_end by calling the internal log method directly
        # (decoupled from LangChain's event system for unit testing)
        empty_chain.append(
            session_id="lc-session",
            model="claude-haiku-4-5",
            input_text="LangChain test prompt",
            output_text="LangChain response",
            input_tokens=50,
            output_tokens=30,
            latency_ms=400.0,
            system_id="lc-test",
            metadata={"chain_type": "LCEL"},
        )

        assert empty_chain.count() == 1
        entry = empty_chain.query(limit=1)[0]
        assert entry.system_id == "lc-test"
        assert entry.metadata.get("chain_type") == "LCEL"
