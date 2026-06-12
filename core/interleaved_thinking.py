"""
core/interleaved_thinking.py
=============================

Adaptive-thinking + tool-use loop for multi-step reasoning over tools with
full audit-trail preservation. Adaptive thinking interleaves reasoning
between tool calls automatically — no beta header, no token budget; depth is
controlled with ``effort``.

WIRING (one-liner):
    from core.interleaved_thinking import interleaved_reason
    result = await interleaved_reason(
        ai, system=SYSTEM_PROMPT, user=USER_QUERY,
        tools=[{"name": "search", "description": "Search docs", "input_schema": {...}}],
        tool_executor=my_async_tool_fn,   # async fn(name, input) -> str
    )
    print(result.final_text)
    print(result.thinking_blocks)  # summarized reasoning trace for Annex IV logging

Protocol:
    1. Send messages with thinking={"type": "adaptive", "display": "summarized"}
    2. Model may respond with thinking + text + tool_use blocks
    3. Extract all content blocks from the response
    4. If stop_reason == "refusal" → raise RefusalError (Fable 5 classifiers)
       If stop_reason == "pause_turn" → re-send to resume (server-side tools)
    5. If tool_use block found:
       a. Execute the tool
       b. Append model's FULL assistant content block list to messages
          (thinking blocks MUST be passed back exactly as received —
          including blocks whose text is empty)
       c. Append tool_result message
       d. Repeat from step 1
    6. If stop_reason == "end_turn" or no tool_use → return result

Key rule: thinking blocks MUST be preserved in the assistant turn and passed
back unchanged on subsequent calls. Modifying or dropping them causes a 400.
"""

from __future__ import annotations

import json
import logging
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.models import (
    DEFAULT_MAX_TOKENS,
    EFFORT_HIGH,
    MODEL_COORDINATOR,
    effort_for_budget,
    is_fable,
    supports_adaptive_thinking,
    supports_effort,
    validate_effort,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class InterleavedResult:
    """Result of an interleaved thinking + tool use conversation.

    Attributes
    ----------
    final_text:
        The model's final visible response text.
    tool_calls:
        List of all tool invocations made during the reasoning loop.
        Each entry: {"name": str, "input": dict, "result": str, "iteration": int}
    thinking_blocks:
        All thinking trace strings across all iterations, in order.
        Suitable for persistence as Annex IV audit evidence.
    total_tokens:
        Sum of input + output tokens across all API calls in the loop.
    iterations:
        Number of reasoning → tool → reasoning cycles completed.
    """

    final_text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    thinking_blocks: list[str] = field(default_factory=list)
    total_tokens: int = 0
    iterations: int = 0


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

async def interleaved_reason(
    ai: Any,
    *,
    system: str,
    user: str,
    tools: list[dict[str, Any]],
    tool_executor: Callable[[str, dict[str, Any]], Any] | None = None,
    max_iterations: int = 10,
    effort: str = EFFORT_HIGH,
    thinking_budget: int = 0,  # deprecated → effort
    model: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    cache_system: bool = True,
) -> InterleavedResult:
    """Run an adaptive-thinking + tool-use loop.

    Adaptive thinking automatically interleaves reasoning between tool calls
    (no beta header, no token budget); ``effort`` controls the depth.

    Parameters
    ----------
    ai:
        ``AIClient`` instance from core.ai_client.
    system:
        System prompt. Will be wrapped in ephemeral cache block if
        ``cache_system=True``.
    user:
        Initial user message.
    tools:
        List of Anthropic tool schema dicts (name, description, input_schema).
    tool_executor:
        Async callable ``(tool_name: str, tool_input: dict) -> str | Any``.
        The return value is serialised to JSON and fed back as the tool result.
        If None, a no-op stub is used (returns empty string) — useful for
        testing the thinking loop structure without real tool backends.
    max_iterations:
        Hard cap on reasoning → tool → reasoning cycles (default 10).
    effort:
        Effort level for output_config ("low"/"medium"/"high"/"xhigh"/"max").
        Default "high" — agentic loops respond well to "xhigh" when accuracy
        matters more than cost.
    thinking_budget:
        DEPRECATED. Rejected by Fable 5 / Opus 4.7+; a positive value is
        translated to the nearest effort level.
    model:
        Model ID. Defaults to MODEL_COORDINATOR (Fable 5).
    max_tokens:
        Max output tokens per API call (adaptive thinking spends from this
        cap too, so keep it generous).
    cache_system:
        Wrap system in ephemeral cache block (default True).

    Returns
    -------
    InterleavedResult
        Accumulated final text, tool calls, thinking traces, and token totals.
    """
    model = model or MODEL_COORDINATOR
    executor = tool_executor or _noop_tool_executor

    if thinking_budget > 0:
        warnings.warn(
            "thinking_budget is deprecated (rejected on Fable 5 / Opus 4.7+); "
            "pass effort='low|medium|high|xhigh|max' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        effort = effort_for_budget(thinking_budget)
    effort = validate_effort(effort)

    # Build system blocks
    if cache_system:
        system_blocks: Any = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system_blocks = system

    create_kwargs: dict[str, Any] = {}
    if supports_adaptive_thinking(model):
        if is_fable(model) or "opus-4-7" in model or "opus-4-8" in model:
            create_kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
        else:
            create_kwargs["thinking"] = {"type": "adaptive"}
    if supports_effort(model):
        create_kwargs["output_config"] = {"effort": effort}

    # Conversation state
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    result = InterleavedResult(final_text="")
    total_input_tokens = 0
    total_output_tokens = 0

    for iteration in range(max_iterations):
        logger.debug("interleaved_reason: iteration %d", iteration)

        response = await ai.raw.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=messages,
            tools=tools,
            **create_kwargs,
        )

        # Accumulate token usage
        usage = getattr(response, "usage", None)
        if usage:
            total_input_tokens += getattr(usage, "input_tokens", 0)
            total_output_tokens += getattr(usage, "output_tokens", 0)

        # Collect ALL content blocks from this response — MUST include thinking
        response_content_blocks: list[Any] = list(getattr(response, "content", []) or [])

        # Extract thinking traces, visible text, and tool_use blocks
        thinking_texts: list[str] = []
        visible_texts: list[str] = []
        tool_use_blocks: list[Any] = []

        for block in response_content_blocks:
            btype = _block_type(block)
            if btype == "thinking":
                thinking_texts.append(_block_text(block, attr="thinking"))
            elif btype == "text":
                visible_texts.append(_block_text(block, attr="text"))
            elif btype == "tool_use":
                tool_use_blocks.append(block)

        # Accumulate thinking traces
        result.thinking_blocks.extend(thinking_texts)

        # Check stop condition
        stop_reason = getattr(response, "stop_reason", None) or ""

        if stop_reason == "refusal":
            # Safety classifiers declined (HTTP 200, not an exception) —
            # surface as a typed error; partial output should be discarded.
            from core.ai_client import RefusalError

            details = getattr(response, "stop_details", None)
            raise RefusalError(
                category=getattr(details, "category", None) if details else None,
                explanation=getattr(details, "explanation", None) if details else None,
                model=model,
            )

        if stop_reason == "pause_turn":
            # Server-side tool loop paused — re-send to resume. Do NOT add a
            # "continue" user message; the API detects the trailing state.
            assistant_content = _serialize_blocks(response_content_blocks)
            messages.append({"role": "assistant", "content": assistant_content})
            continue

        if not tool_use_blocks or stop_reason == "end_turn":
            # Final response — gather text and exit loop
            result.final_text = "\n".join(visible_texts).strip()
            result.iterations = iteration + 1
            break

        # --- Tool use branch ---
        # Append the full assistant turn (thinking + text + tool_use) to messages.
        # Anthropic's interleaved-thinking protocol REQUIRES thinking blocks here.
        assistant_content = _serialize_blocks(response_content_blocks)
        messages.append({"role": "assistant", "content": assistant_content})

        # Execute each tool and collect results
        tool_results: list[dict[str, Any]] = []
        for tb in tool_use_blocks:
            tool_name = _get_attr(tb, "name")
            tool_id = _get_attr(tb, "id")
            tool_input = _get_attr(tb, "input") or {}
            if isinstance(tool_input, str):
                try:
                    tool_input = json.loads(tool_input)
                except json.JSONDecodeError:
                    tool_input = {"raw": tool_input}

            logger.debug("interleaved_reason: executing tool %s", tool_name)
            try:
                raw_result = await executor(tool_name, tool_input)
                tool_result_str = (
                    raw_result if isinstance(raw_result, str)
                    else json.dumps(raw_result, default=str)
                )
            except Exception as exc:
                logger.error("interleaved_reason: tool %s failed: %s", tool_name, exc)
                tool_result_str = f"Error: {exc}"

            result.tool_calls.append(
                {
                    "name": tool_name,
                    "input": dict(tool_input),
                    "result": tool_result_str,
                    "iteration": iteration,
                }
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": tool_result_str,
                }
            )

        # Append tool results as a user message
        messages.append({"role": "user", "content": tool_results})

    else:
        # Hit max_iterations — return whatever text we have
        logger.warning(
            "interleaved_reason: hit max_iterations=%d without end_turn", max_iterations
        )
        result.iterations = max_iterations

    result.total_tokens = total_input_tokens + total_output_tokens
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _block_type(block: Any) -> str:
    if isinstance(block, dict):
        return block.get("type", "")
    return getattr(block, "type", "")


def _block_text(block: Any, *, attr: str) -> str:
    if isinstance(block, dict):
        return block.get(attr, "") or ""
    return getattr(block, attr, "") or ""


def _get_attr(obj: Any, attr: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(attr)
    return getattr(obj, attr, None)


def _serialize_blocks(blocks: list[Any]) -> list[dict[str, Any]]:
    """Convert SDK block objects to plain dicts for message history."""
    out: list[dict[str, Any]] = []
    for block in blocks:
        if isinstance(block, dict):
            out.append(block)
            continue
        btype = getattr(block, "type", "")
        if btype == "thinking":
            out.append(
                {
                    "type": "thinking",
                    "thinking": getattr(block, "thinking", ""),
                    # Preserve the signature field required by Anthropic
                    **({"signature": block.signature} if hasattr(block, "signature") else {}),
                }
            )
        elif btype == "text":
            out.append({"type": "text", "text": getattr(block, "text", "")})
        elif btype == "tool_use":
            out.append(
                {
                    "type": "tool_use",
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}),
                }
            )
        else:
            # Unknown block — pass through as dict representation
            try:
                out.append(block.model_dump())
            except AttributeError:
                out.append({"type": btype})
    return out


async def _noop_tool_executor(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Stub tool executor — returns empty string. Replace in production."""
    logger.debug("noop_tool_executor: %s(%s)", tool_name, tool_input)
    return ""
