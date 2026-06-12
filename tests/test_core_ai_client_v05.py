"""Tests for the v0.5.0 AIClient API surface.

Covers the June-2026 request shapes: adaptive thinking + effort, structured
outputs via output_config.format, refusal handling, server-side fallbacks,
task budgets, and the deprecated budget_tokens translation layer.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.ai_client import (
    AIClient,
    RefusalError,
    _served_by_fallback,
    _strict_schema,
)
from core.models import (
    BETA_SERVER_SIDE_FALLBACK,
    BETA_TASK_BUDGETS,
    EFFORT_HIGH,
    EFFORT_MEDIUM,
    EFFORT_XHIGH,
    MODEL_FABLE_5,
    MODEL_FALLBACK,
    MODEL_HAIKU_4_5,
    MODEL_SONNET_4_6,
    describe_model,
    effort_for_budget,
    is_fable,
    validate_effort,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _thinking_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "thinking"
    block.thinking = text
    return block


def _response(
    *,
    content=None,
    stop_reason: str = "end_turn",
    model: str = MODEL_FABLE_5,
    stop_details=None,
    iterations=None,
):
    resp = MagicMock()
    resp.content = content or [_text_block(json.dumps({"ok": True}))]
    resp.stop_reason = stop_reason
    resp.stop_details = stop_details
    resp.model = model
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 0
    usage.iterations = iterations
    resp.usage = usage
    return resp


def _make_client(response=None, *, enable_fallbacks: bool = True) -> tuple[AIClient, MagicMock]:
    raw = MagicMock()
    resp = response or _response()
    raw.messages.create = AsyncMock(return_value=resp)
    raw.beta.messages.create = AsyncMock(return_value=resp)
    ai = AIClient(client=raw, enable_fallbacks=enable_fallbacks)
    return ai, raw


_SCHEMA = {
    "type": "object",
    "required": ["ok"],
    "properties": {"ok": {"type": "boolean"}},
}


# ---------------------------------------------------------------------------
# models.py helpers
# ---------------------------------------------------------------------------

class TestModelHelpers:
    def test_effort_for_budget_mapping(self):
        assert effort_for_budget(4_000) == EFFORT_MEDIUM
        assert effort_for_budget(16_000) == EFFORT_HIGH
        assert effort_for_budget(32_000) == EFFORT_XHIGH
        assert effort_for_budget(0) == EFFORT_HIGH  # default

    def test_validate_effort_rejects_unknown(self):
        with pytest.raises(ValueError):
            validate_effort("ultra")

    def test_is_fable(self):
        assert is_fable("claude-fable-5")
        assert is_fable("claude-mythos-5")
        assert not is_fable("claude-opus-4-8")

    def test_describe_model_fable_capabilities(self):
        meta = describe_model(MODEL_FABLE_5)
        assert meta["supports_adaptive_thinking"] is True
        assert meta["supports_effort"] is True
        assert meta["always_on_thinking"] is True
        assert meta["can_refuse"] is True
        assert meta["supports_structured_outputs"] is True

    def test_describe_model_haiku_no_effort(self):
        meta = describe_model(MODEL_HAIKU_4_5)
        assert meta["supports_effort"] is False
        assert meta["supports_adaptive_thinking"] is False

    def test_sonnet_context_window_is_1m(self):
        assert describe_model(MODEL_SONNET_4_6)["context_window"] == 1_000_000


# ---------------------------------------------------------------------------
# _strict_schema
# ---------------------------------------------------------------------------

class TestStrictSchema:
    def test_injects_additional_properties_recursively(self):
        schema = {
            "type": "object",
            "properties": {
                "nested": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                },
                "items": {
                    "type": "array",
                    "items": {"type": "object", "properties": {}},
                },
            },
        }
        out = _strict_schema(schema)
        assert out["additionalProperties"] is False
        assert out["properties"]["nested"]["additionalProperties"] is False
        assert out["properties"]["items"]["items"]["additionalProperties"] is False

    def test_does_not_mutate_input(self):
        schema = {"type": "object", "properties": {}}
        _strict_schema(schema)
        assert "additionalProperties" not in schema

    def test_preserves_explicit_false(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {}}
        out = _strict_schema(schema)
        assert out["additionalProperties"] is False


# ---------------------------------------------------------------------------
# structured() — structured outputs + fallback routing
# ---------------------------------------------------------------------------

class TestStructured:
    async def test_uses_output_config_json_schema(self):
        ai, raw = _make_client(enable_fallbacks=False)
        await ai.structured(system="s", user="u", schema=_SCHEMA, model=MODEL_SONNET_4_6)
        kwargs = raw.messages.create.call_args.kwargs
        fmt = kwargs["output_config"]["format"]
        assert fmt["type"] == "json_schema"
        assert fmt["schema"]["additionalProperties"] is False
        assert "tools" not in kwargs
        assert "tool_choice" not in kwargs

    async def test_fable_routes_through_beta_with_fallbacks(self):
        ai, raw = _make_client(enable_fallbacks=True)
        await ai.structured(system="s", user="u", schema=_SCHEMA, model=MODEL_FABLE_5)
        raw.messages.create.assert_not_called()
        kwargs = raw.beta.messages.create.call_args.kwargs
        assert BETA_SERVER_SIDE_FALLBACK in kwargs["betas"]
        assert kwargs["fallbacks"] == [{"model": MODEL_FALLBACK}]

    async def test_non_fable_skips_fallbacks(self):
        ai, raw = _make_client(enable_fallbacks=True)
        await ai.structured(system="s", user="u", schema=_SCHEMA, model=MODEL_SONNET_4_6)
        raw.beta.messages.create.assert_not_called()
        raw.messages.create.assert_called_once()

    async def test_parses_json_skipping_thinking_block(self):
        payload = {"strategy": "rehost", "confidence": 0.9}
        resp = _response(
            content=[_thinking_block("reasoning..."), _text_block(json.dumps(payload))]
        )
        ai, _ = _make_client(resp, enable_fallbacks=False)
        out = await ai.structured(system="s", user="u", schema=_SCHEMA, model=MODEL_SONNET_4_6)
        assert out.data == payload

    async def test_refusal_raises_typed_error(self):
        details = MagicMock()
        details.category = "cyber"
        details.explanation = "declined"
        resp = _response(content=[], stop_reason="refusal", stop_details=details)
        ai, _ = _make_client(resp, enable_fallbacks=False)
        with pytest.raises(RefusalError) as exc_info:
            await ai.structured(system="s", user="u", schema=_SCHEMA, model=MODEL_FABLE_5)
        assert exc_info.value.category == "cyber"

    async def test_task_budget_adds_beta_and_output_config(self):
        ai, raw = _make_client(enable_fallbacks=False)
        await ai.structured(
            system="s", user="u", schema=_SCHEMA,
            model=MODEL_FABLE_5, task_budget_tokens=100_000,
        )
        kwargs = raw.beta.messages.create.call_args.kwargs
        assert BETA_TASK_BUDGETS in kwargs["betas"]
        assert kwargs["output_config"]["task_budget"] == {"type": "tokens", "total": 100_000}

    async def test_task_budget_clamped_to_minimum(self):
        ai, raw = _make_client(enable_fallbacks=False)
        await ai.structured(
            system="s", user="u", schema=_SCHEMA,
            model=MODEL_FABLE_5, task_budget_tokens=5_000,
        )
        kwargs = raw.beta.messages.create.call_args.kwargs
        assert kwargs["output_config"]["task_budget"]["total"] == 20_000


# ---------------------------------------------------------------------------
# thinking() — adaptive thinking, no budget_tokens on the wire
# ---------------------------------------------------------------------------

class TestThinking:
    async def test_fable_gets_adaptive_summarized(self):
        ai, raw = _make_client(enable_fallbacks=False)
        await ai.thinking(system="s", user="u", model=MODEL_FABLE_5)
        kwargs = raw.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert kwargs["output_config"]["effort"] == EFFORT_HIGH
        assert "budget_tokens" not in str(kwargs.get("thinking", {}))

    async def test_sonnet_gets_plain_adaptive(self):
        ai, raw = _make_client(enable_fallbacks=False)
        await ai.thinking(system="s", user="u", model=MODEL_SONNET_4_6)
        kwargs = raw.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "adaptive"}

    async def test_haiku_gets_no_thinking_param(self):
        ai, raw = _make_client(enable_fallbacks=False)
        await ai.thinking(system="s", user="u", model=MODEL_HAIKU_4_5)
        kwargs = raw.messages.create.call_args.kwargs
        assert "thinking" not in kwargs
        assert "output_config" not in kwargs  # effort errors on Haiku

    async def test_budget_tokens_deprecated_translates_to_effort(self):
        ai, raw = _make_client(enable_fallbacks=False)
        with pytest.warns(DeprecationWarning):
            await ai.thinking(
                system="s", user="u", model=MODEL_FABLE_5, budget_tokens=32_000
            )
        kwargs = raw.messages.create.call_args.kwargs
        assert kwargs["output_config"]["effort"] == EFFORT_XHIGH
        assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}

    async def test_extracts_thinking_trace(self):
        resp = _response(
            content=[_thinking_block("step 1... step 2..."), _text_block("answer")]
        )
        ai, _ = _make_client(resp, enable_fallbacks=False)
        out = await ai.thinking(system="s", user="u", model=MODEL_FABLE_5)
        assert out.thinking_trace == "step 1... step 2..."
        assert out.text == "answer"


# ---------------------------------------------------------------------------
# structured_with_thinking()
# ---------------------------------------------------------------------------

class TestStructuredWithThinking:
    async def test_combines_format_and_thinking(self):
        payload = {"ok": True}
        resp = _response(
            content=[_thinking_block("trace"), _text_block(json.dumps(payload))]
        )
        ai, raw = _make_client(resp, enable_fallbacks=False)
        structured, trace = await ai.structured_with_thinking(
            system="s", user="u", schema=_SCHEMA, model=MODEL_FABLE_5, effort=EFFORT_XHIGH
        )
        kwargs = raw.beta.messages.create.call_args.kwargs if raw.beta.messages.create.called \
            else raw.messages.create.call_args.kwargs
        assert kwargs["output_config"]["format"]["type"] == "json_schema"
        assert kwargs["output_config"]["effort"] == EFFORT_XHIGH
        assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert structured.data == payload
        assert trace == "trace"


# ---------------------------------------------------------------------------
# Fallback detection
# ---------------------------------------------------------------------------

class TestServedByFallback:
    def test_detects_fallback_message_iteration(self):
        entry = MagicMock()
        entry.type = "fallback_message"
        resp = _response(iterations=[entry])
        assert _served_by_fallback(resp) is True

    def test_no_iterations_means_primary(self):
        resp = _response(iterations=None)
        assert _served_by_fallback(resp) is False

    def test_plain_message_iterations_means_primary(self):
        entry = MagicMock()
        entry.type = "message"
        resp = _response(iterations=[entry])
        assert _served_by_fallback(resp) is False
