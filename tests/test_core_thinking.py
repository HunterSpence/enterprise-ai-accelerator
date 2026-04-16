"""Tests for core/interleaved_thinking.py — InterleavedResult, tool_executor loop."""

from core.interleaved_thinking import InterleavedResult


class TestInterleavedResult:
    def test_default_construction(self):
        result = InterleavedResult(final_text="done")
        assert result.final_text == "done"
        assert result.tool_calls == []
        assert result.thinking_blocks == []
        assert result.total_tokens == 0
        assert result.iterations == 0

    def test_with_tool_calls(self):
        result = InterleavedResult(
            final_text="result",
            tool_calls=[{"name": "search", "input": {"q": "x"}, "result": "found", "iteration": 1}],
            iterations=1,
        )
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "search"

    def test_with_thinking_blocks(self):
        result = InterleavedResult(
            final_text="answer",
            thinking_blocks=["Step 1: analyze...", "Step 2: conclude..."],
        )
        assert len(result.thinking_blocks) == 2

    def test_total_tokens_field(self):
        result = InterleavedResult(final_text="x", total_tokens=1500)
        assert result.total_tokens == 1500

    def test_empty_thinking_blocks_list(self):
        result = InterleavedResult(final_text="ok")
        result.thinking_blocks.append("new thought")
        assert len(result.thinking_blocks) == 1

    def test_multiple_iterations(self):
        result = InterleavedResult(
            final_text="final",
            iterations=3,
            tool_calls=[
                {"name": "fn", "input": {}, "result": "r1", "iteration": 1},
                {"name": "fn", "input": {}, "result": "r2", "iteration": 2},
                {"name": "fn", "input": {}, "result": "r3", "iteration": 3},
            ],
        )
        assert result.iterations == 3
        assert len(result.tool_calls) == 3
