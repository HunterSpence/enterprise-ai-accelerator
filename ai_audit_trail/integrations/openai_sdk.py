"""
integrations/openai_sdk.py — Drop-in audited wrapper for the OpenAI SDK.

V2 upgrades:
- o1/o3/o4 model support: reasoning_tokens captured from usage
- Function calling / tool use capture
- Cost calculation per call (GPT-4o, o1, o3, GPT-4 pricing)
- cache_read_tokens support (OpenAI prompt caching)
- system_id field for multi-system tracking

Replace::

    from openai import OpenAI
    client = OpenAI()

With::

    from ai_audit_trail.integrations.openai_sdk import AuditedOpenAI
    client = AuditedOpenAI(audit_chain=chain)

All client.chat.completions.create() calls are automatically logged.
The response is returned unchanged.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Iterator, Optional, Union

from ai_audit_trail.chain import AuditChain, DecisionType, RiskTier
from ai_audit_trail.decorators import _extract_tokens

# Module-level import so tests can patch ai_audit_trail.integrations.openai_sdk.OpenAI
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# OpenAI pricing table (USD per 1M tokens, April 2026 estimates)
# ---------------------------------------------------------------------------

_OPENAI_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 5.00, "output": 15.00, "cache_read": 2.50},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cache_read": 0.075},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00, "cache_read": 5.00},
    "gpt-4": {"input": 30.00, "output": 60.00, "cache_read": 15.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50, "cache_read": 0.25},
    "o1": {"input": 15.00, "output": 60.00, "cache_read": 7.50},
    "o1-mini": {"input": 3.00, "output": 12.00, "cache_read": 1.50},
    "o3": {"input": 10.00, "output": 40.00, "cache_read": 5.00},
    "o3-mini": {"input": 1.10, "output": 4.40, "cache_read": 0.55},
    "o4-mini": {"input": 1.10, "output": 4.40, "cache_read": 0.275},
}


def _calculate_openai_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Calculate OpenAI API call cost in USD."""
    model_lower = model.lower()
    pricing = None
    for key, rates in _OPENAI_PRICING.items():
        if key in model_lower:
            pricing = rates
            break

    if pricing is None:
        pricing = {"input": 5.00, "output": 15.00, "cache_read": 2.50}

    return round(
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
        + (reasoning_tokens / 1_000_000) * pricing["output"]  # reasoning at output rate
        + (cache_read_tokens / 1_000_000) * pricing.get("cache_read", 0.0),
        8,
    )


def _extract_openai_tool_calls(response: Any) -> list[dict[str, Any]]:
    """Extract function/tool calls from an OpenAI chat completion."""
    tool_calls: list[dict[str, Any]] = []
    if not response.choices:
        return tool_calls
    msg = response.choices[0].message
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        for tc in msg.tool_calls:
            tool_calls.append({
                "tool_id": getattr(tc, "id", ""),
                "tool_name": getattr(tc.function, "name", "") if hasattr(tc, "function") else "",
                "type": getattr(tc, "type", "function"),
            })
    return tool_calls


class AuditedCompletions:
    """Proxy for client.chat.completions that intercepts .create() calls."""

    def __init__(
        self,
        completions: Any,
        chain: AuditChain,
        session_id: str,
        decision_type: DecisionType,
        risk_tier: RiskTier,
        metadata: dict[str, Any],
        system_id: str,
        background_logging: bool,
    ) -> None:
        self._completions = completions
        self._chain = chain
        self._session_id = session_id
        self._decision_type = decision_type
        self._risk_tier = risk_tier
        self._metadata = metadata
        self._system_id = system_id
        self._background_logging = background_logging

    def create(self, **kwargs: Any) -> Any:
        messages = kwargs.get("messages", [])
        input_parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [
                    b.get("text", "") if isinstance(b, dict) else str(b)
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                content = " ".join(text_parts)
            input_parts.append(f"{role}: {content}")
        input_text = "\n".join(input_parts)

        model_name: str = kwargs.get("model", "openai/unknown")
        is_stream: bool = kwargs.get("stream", False)
        t0 = time.perf_counter()

        if is_stream:
            stream = self._completions.create(**kwargs)
            return _AuditedOpenAIStream(
                stream=stream,
                chain=self._chain,
                input_text=input_text,
                model_name=model_name,
                session_id=self._session_id,
                decision_type=self._decision_type,
                risk_tier=self._risk_tier,
                metadata=self._metadata,
                system_id=self._system_id,
                background_logging=self._background_logging,
                t0=t0,
            )

        response = self._completions.create(**kwargs)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        output_text = ""
        if response.choices:
            msg = response.choices[0].message
            output_text = msg.content or ""

        # Extract tokens directly from OpenAI usage (avoids Anthropic path in _extract_tokens)
        in_tok: int = 0
        out_tok: int = 0
        try:
            usage = response.usage
            if hasattr(usage, "prompt_tokens") and isinstance(usage.prompt_tokens, int):
                in_tok = usage.prompt_tokens
                out_tok = int(usage.completion_tokens or 0)
            elif hasattr(usage, "input_tokens") and isinstance(usage.input_tokens, int):
                in_tok = usage.input_tokens
                out_tok = int(getattr(usage, "output_tokens", 0) or 0)
            else:
                in_tok = len(input_text) // 4
                out_tok = len(output_text) // 4
        except Exception:
            in_tok = len(input_text) // 4
            out_tok = len(output_text) // 4

        # V2: reasoning tokens (o1/o3/o4 models)
        reasoning_tokens = 0
        try:
            if hasattr(response, "usage") and hasattr(response.usage, "completion_tokens_details"):
                details = response.usage.completion_tokens_details
                if details is not None and not callable(details) and hasattr(details, "reasoning_tokens"):
                    val = details.reasoning_tokens
                    if isinstance(val, int):
                        reasoning_tokens = val
        except Exception:
            pass

        # V2: cache_read_tokens (OpenAI prompt caching)
        cache_read_tokens = 0
        try:
            if hasattr(response, "usage") and hasattr(response.usage, "prompt_tokens_details"):
                details = response.usage.prompt_tokens_details
                if details is not None and not callable(details) and hasattr(details, "cached_tokens"):
                    val = details.cached_tokens
                    if isinstance(val, int):
                        cache_read_tokens = val
        except Exception:
            pass

        cost = _calculate_openai_cost(model_name, in_tok, out_tok, reasoning_tokens, cache_read_tokens)

        # V2: tool calls
        tool_calls = _extract_openai_tool_calls(response)
        meta = dict(self._metadata)
        if tool_calls:
            meta["tool_calls"] = tool_calls
        if reasoning_tokens:
            meta["reasoning_tokens"] = reasoning_tokens

        def _write() -> None:
            self._chain.append(
                session_id=self._session_id,
                model=model_name,
                input_text=input_text,
                output_text=output_text,
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_ms=latency_ms,
                decision_type=self._decision_type,
                risk_tier=self._risk_tier,
                metadata=meta,
                system_id=self._system_id,
                cache_read_tokens=cache_read_tokens,
                cost_usd=cost,
            )

        if self._background_logging:
            threading.Thread(target=_write, daemon=True).start()
        else:
            _write()

        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._completions, name)


class _AuditedOpenAIStream:
    """Wrapper around OpenAI streaming response that logs on completion."""

    def __init__(
        self,
        stream: Any,
        chain: AuditChain,
        input_text: str,
        model_name: str,
        session_id: str,
        decision_type: DecisionType,
        risk_tier: RiskTier,
        metadata: dict[str, Any],
        system_id: str,
        background_logging: bool,
        t0: float,
    ) -> None:
        self._stream = stream
        self._chain = chain
        self._input_text = input_text
        self._model_name = model_name
        self._session_id = session_id
        self._decision_type = decision_type
        self._risk_tier = risk_tier
        self._metadata = metadata
        self._system_id = system_id
        self._background_logging = background_logging
        self._t0 = t0
        self._chunks: list[str] = []
        self._tool_call_names: list[str] = []
        self._flushed = False

    def __iter__(self) -> Iterator[Any]:
        for chunk in self._stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    self._chunks.append(delta.content)
                # Tool call streaming
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        fn = getattr(tc, "function", None)
                        if fn and hasattr(fn, "name") and fn.name:
                            self._tool_call_names.append(fn.name)
            yield chunk
        self._flush()

    def _flush(self) -> None:
        if self._flushed:
            return
        self._flushed = True
        latency_ms = (time.perf_counter() - self._t0) * 1000.0
        output_text = "".join(self._chunks)
        in_tok = len(self._input_text) // 4
        out_tok = len(output_text) // 4
        cost = _calculate_openai_cost(self._model_name, in_tok, out_tok)

        meta = dict(self._metadata)
        if self._tool_call_names:
            meta["tool_calls"] = [{"tool_name": n} for n in self._tool_call_names]

        def _write() -> None:
            self._chain.append(
                session_id=self._session_id,
                model=self._model_name,
                input_text=self._input_text,
                output_text=output_text,
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_ms=latency_ms,
                decision_type=self._decision_type,
                risk_tier=self._risk_tier,
                metadata=meta,
                system_id=self._system_id,
                cost_usd=cost,
            )

        if self._background_logging:
            threading.Thread(target=_write, daemon=True).start()
        else:
            _write()

    def __enter__(self) -> "_AuditedOpenAIStream":
        return self

    def __exit__(self, *args: Any) -> Any:
        result = self._stream.__exit__(*args) if hasattr(self._stream, "__exit__") else None
        self._flush()
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


class AuditedChat:
    """Proxy for client.chat that wraps .completions."""

    def __init__(self, chat: Any, **kw: Any) -> None:
        self._chat = chat
        self._completions = AuditedCompletions(chat.completions, **kw)

    @property
    def completions(self) -> AuditedCompletions:
        return self._completions

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chat, name)


class AuditedOpenAI:
    """
    Drop-in replacement for openai.OpenAI.

    V2: o1/o3/o4 reasoning token support, tool use capture,
    cost calculation, background logging.

    Usage::

        from ai_audit_trail.integrations.openai_sdk import AuditedOpenAI
        from ai_audit_trail import AuditChain, DecisionType, RiskTier

        chain = AuditChain("audit.db")
        client = AuditedOpenAI(
            audit_chain=chain,
            risk_tier=RiskTier.HIGH,
            system_id="fraud-detection-v3",
        )
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
        )
    """

    def __init__(
        self,
        audit_chain: AuditChain,
        decision_type: Union[DecisionType, str] = DecisionType.GENERATION,
        risk_tier: Union[RiskTier, str] = RiskTier.LIMITED,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        system_id: str = "default",
        background_logging: bool = False,
        **openai_kwargs: Any,
    ) -> None:
        if OpenAI is None:
            raise ImportError("pip install openai")

        self._client = OpenAI(**openai_kwargs)
        self._chain = audit_chain
        self._decision_type = (
            DecisionType(decision_type) if isinstance(decision_type, str) else decision_type
        )
        self._risk_tier = (
            RiskTier(risk_tier) if isinstance(risk_tier, str) else risk_tier
        )
        self._session_id = session_id or str(uuid.uuid4())
        self._metadata = metadata or {}
        self._system_id = system_id
        self._background_logging = background_logging

    @property
    def audit_chain(self) -> AuditChain:
        """Public accessor so tests can assert client.audit_chain is chain."""
        return self._chain

    @audit_chain.setter
    def audit_chain(self, value: AuditChain) -> None:
        self._chain = value

    @property
    def chat(self) -> AuditedChat:
        return AuditedChat(
            self._client.chat,
            chain=self._chain,
            session_id=self._session_id,
            decision_type=self._decision_type,
            risk_tier=self._risk_tier,
            metadata=self._metadata,
            system_id=self._system_id,
            background_logging=self._background_logging,
        )

    def new_session(self, session_id: Optional[str] = None) -> "AuditedOpenAI":
        wrapper = AuditedOpenAI.__new__(AuditedOpenAI)
        wrapper._client = self._client
        wrapper._chain = self._chain
        wrapper._decision_type = self._decision_type
        wrapper._risk_tier = self._risk_tier
        wrapper._session_id = session_id or str(uuid.uuid4())
        wrapper._metadata = self._metadata.copy()
        wrapper._system_id = self._system_id
        wrapper._background_logging = self._background_logging
        return wrapper

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)
