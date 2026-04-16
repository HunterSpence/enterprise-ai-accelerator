"""Tests for core/batch_coalescer.py — submit, flush on size, graceful shutdown."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.batch_coalescer import BatchCoalescer, BatchableRequest, BatchFuture, _extract_batch_result
from core.models import MODEL_HAIKU_4_5


def _make_mock_ai(batch_id="batch-123"):
    """Build a minimal AIClient mock that BatchCoalescer can call."""
    ai = MagicMock()
    batch_obj = MagicMock()
    batch_obj.id = batch_id
    ai.raw.messages.batches.create = AsyncMock(return_value=batch_obj)
    ai.raw.messages.batches.retrieve = AsyncMock(return_value=MagicMock(processing_status="ended"))
    ai.raw.messages.batches.results = AsyncMock(return_value=_aiter([]))
    return ai


async def _aiter(items):
    for item in items:
        yield item


class TestBatchCoalescerSubmit:
    async def test_submit_returns_batch_future(self):
        ai = _make_mock_ai()
        coalescer = BatchCoalescer(ai=ai, flush_interval_s=999)
        req = BatchableRequest(model=MODEL_HAIKU_4_5, system="sys", user="usr")
        future = await coalescer.submit(req)
        assert isinstance(future, BatchFuture)

    async def test_submit_assigns_custom_id_if_empty(self):
        ai = _make_mock_ai()
        coalescer = BatchCoalescer(ai=ai, flush_interval_s=999)
        req = BatchableRequest(model=MODEL_HAIKU_4_5, system="sys", user="usr", custom_id="")
        await coalescer.submit(req)
        assert req.custom_id != ""

    async def test_submit_respects_provided_custom_id(self):
        ai = _make_mock_ai()
        coalescer = BatchCoalescer(ai=ai, flush_interval_s=999)
        req = BatchableRequest(model=MODEL_HAIKU_4_5, system="sys", user="usr", custom_id="my-id")
        await coalescer.submit(req)
        assert req.custom_id == "my-id"

    async def test_closed_coalescer_raises(self):
        ai = _make_mock_ai()
        coalescer = BatchCoalescer(ai=ai)
        coalescer._closed = True
        with pytest.raises(RuntimeError, match="closed"):
            await coalescer.submit(BatchableRequest(model=MODEL_HAIKU_4_5, system="s", user="u"))

    async def test_stats_queued_count(self):
        ai = _make_mock_ai()
        coalescer = BatchCoalescer(ai=ai, flush_interval_s=999)
        await coalescer.submit(BatchableRequest(model=MODEL_HAIKU_4_5, system="s", user="u1"))
        await coalescer.submit(BatchableRequest(model=MODEL_HAIKU_4_5, system="s", user="u2"))
        stats = coalescer.stats()
        assert stats["queued"] == 2


class TestBatchCoalescerFlush:
    async def test_flush_on_max_size_triggers_batch_create(self):
        ai = _make_mock_ai()
        coalescer = BatchCoalescer(ai=ai, max_batch_size=2, flush_interval_s=999)
        req1 = BatchableRequest(model=MODEL_HAIKU_4_5, system="s", user="u1")
        req2 = BatchableRequest(model=MODEL_HAIKU_4_5, system="s", user="u2")
        await coalescer.submit(req1)
        await coalescer.submit(req2)
        # give event loop a tick so the ensure_future flush runs
        await asyncio.sleep(0.05)
        ai.raw.messages.batches.create.assert_called()

    async def test_build_batch_params_includes_custom_id(self):
        req = BatchableRequest(
            model=MODEL_HAIKU_4_5, system="sys", user="usr", custom_id="abc"
        )
        params = BatchCoalescer._build_batch_params(req)
        assert params["custom_id"] == "abc"

    async def test_build_batch_params_with_schema(self):
        req = BatchableRequest(
            model=MODEL_HAIKU_4_5, system="s", user="u",
            schema={"type": "object", "properties": {"x": {"type": "string"}}},
            tool_name="extract",
        )
        params = BatchCoalescer._build_batch_params(req)
        assert "tools" in params["params"]
        assert params["params"]["tool_choice"]["name"] == "extract"

    async def test_build_batch_params_without_schema(self):
        req = BatchableRequest(model=MODEL_HAIKU_4_5, system="s", user="u")
        params = BatchCoalescer._build_batch_params(req)
        assert "tools" not in params["params"]


class TestExtractBatchResult:
    def test_extracts_tool_use(self):
        block = MagicMock()
        block.type = "tool_use"
        block.input = {"label": "test"}
        msg = MagicMock()
        msg.content = [block]
        result = _extract_batch_result(msg)
        assert result["type"] == "tool_use"
        assert result["data"]["label"] == "test"

    def test_extracts_text(self):
        block = MagicMock()
        block.type = "text"
        block.text = "hello"
        msg = MagicMock()
        msg.content = [block]
        result = _extract_batch_result(msg)
        assert result["type"] == "text"
        assert result["text"] == "hello"

    def test_empty_content_returns_empty_type(self):
        msg = MagicMock()
        msg.content = []
        result = _extract_batch_result(msg)
        assert result["type"] == "empty"
