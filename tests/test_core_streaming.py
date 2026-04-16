"""Tests for core/streaming.py — StreamEvent types and SSE formatting."""

import json
from core.streaming import StreamEvent


class TestStreamEvent:
    def test_text_event_construction(self):
        ev = StreamEvent(type="text", data="hello world")
        assert ev.type == "text"
        assert ev.data == "hello world"
        assert ev.block_index == 0

    def test_thinking_event_construction(self):
        ev = StreamEvent(type="thinking", data="I am thinking...", block_index=1)
        assert ev.type == "thinking"
        assert ev.block_index == 1

    def test_tool_use_event_construction(self):
        payload = json.dumps({"name": "search", "input_delta": '{"q"'})
        ev = StreamEvent(type="tool_use", data=payload, block_index=2)
        assert ev.type == "tool_use"
        parsed = json.loads(ev.data)
        assert parsed["name"] == "search"

    def test_stop_event_construction(self):
        ev = StreamEvent(type="stop", data="end_turn")
        assert ev.type == "stop"
        assert ev.data == "end_turn"

    def test_error_event_construction(self):
        ev = StreamEvent(type="error", data="connection reset")
        assert ev.type == "error"

    def test_usage_event_construction(self):
        payload = json.dumps({"input_tokens": 100, "output_tokens": 50})
        ev = StreamEvent(type="usage", data=payload)
        assert ev.type == "usage"
        parsed = json.loads(ev.data)
        assert parsed["input_tokens"] == 100


class TestStreamEventSSE:
    def test_to_sse_format(self):
        ev = StreamEvent(type="text", data="hi", block_index=0)
        sse = ev.to_sse()
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")

    def test_to_sse_is_valid_json(self):
        ev = StreamEvent(type="stop", data="end_turn", block_index=0)
        sse = ev.to_sse()
        payload_str = sse[len("data: "):].strip()
        payload = json.loads(payload_str)
        assert payload["type"] == "stop"
        assert payload["data"] == "end_turn"
        assert payload["block_index"] == 0

    def test_to_sse_block_index_preserved(self):
        ev = StreamEvent(type="thinking", data="...", block_index=3)
        sse = ev.to_sse()
        payload = json.loads(sse[len("data: "):].strip())
        assert payload["block_index"] == 3

    def test_to_sse_tool_use_json_inside_data(self):
        inner = json.dumps({"name": "fn", "input_delta": "{"})
        ev = StreamEvent(type="tool_use", data=inner)
        sse = ev.to_sse()
        outer = json.loads(sse[len("data: "):].strip())
        assert outer["type"] == "tool_use"
        # data field is itself a JSON string
        assert isinstance(outer["data"], str)
