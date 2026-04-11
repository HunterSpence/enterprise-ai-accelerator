"""
decorators.py — Zero-friction LLM call auditing via Python decorators.

Usage::

    from ai_audit_trail import AuditChain, DecisionType, RiskTier
    from ai_audit_trail.decorators import audit_llm_call

    chain = AuditChain("audit.db")

    @audit_llm_call(
        chain=chain,
        decision_type=DecisionType.CLASSIFICATION,
        risk_tier=RiskTier.HIGH,
        session_id="user-session-abc",
    )
    def classify_loan_application(prompt: str) -> str:
        # your LLM call here
        return my_llm_client.complete(prompt)

Design notes:
- Input and output are hashed, never stored, unless store_plaintext=True.
- Works with any synchronous or async function that accepts a prompt and
  returns a string (or an object with a .content / .text attribute).
- Token counts are extracted from the response if available, otherwise
  estimated from text length.
- Latency is measured wall-clock time around the wrapped call.
"""

from __future__ import annotations

import functools
import inspect
import time
import uuid
from typing import Any, Callable, Optional, TypeVar, Union

from ai_audit_trail.chain import AuditChain, DecisionType, RiskTier

F = TypeVar("F", bound=Callable[..., Any])


def _extract_text(obj: Any) -> str:
    """
    Best-effort extraction of string content from various LLM response shapes.
    Handles: plain str, Anthropic Message, OpenAI ChatCompletion, dicts.
    """
    if isinstance(obj, str):
        return obj
    # Anthropic SDK: message.content is a list of ContentBlock
    if hasattr(obj, "content"):
        content = obj.content
        if isinstance(content, list):
            parts = []
            for block in content:
                if hasattr(block, "text"):
                    parts.append(block.text)
                elif isinstance(block, dict) and "text" in block:
                    parts.append(block["text"])
            return "\n".join(parts)
        if isinstance(content, str):
            return content
    # OpenAI ChatCompletion: choices[0].message.content
    if hasattr(obj, "choices"):
        choices = obj.choices
        if choices and hasattr(choices[0], "message"):
            return choices[0].message.content or ""
    # Dict fallback
    if isinstance(obj, dict):
        for key in ("content", "text", "output", "response"):
            if key in obj:
                val = obj[key]
                return val if isinstance(val, str) else str(val)
    return str(obj)


def _extract_tokens(
    response: Any,
    input_text: str,
    output_text: str,
) -> tuple[int, int]:
    """
    Extract token counts from response usage metadata, or estimate if absent.
    Estimation: ~4 chars per token (rough but consistent heuristic).
    """
    # Anthropic usage
    if hasattr(response, "usage"):
        usage = response.usage
        if hasattr(usage, "input_tokens") and hasattr(usage, "output_tokens"):
            in_val, out_val = usage.input_tokens, usage.output_tokens
            if isinstance(in_val, int) and isinstance(out_val, int):
                return in_val, out_val
    # OpenAI usage
    if hasattr(response, "usage") and hasattr(response.usage, "prompt_tokens"):
        p_val, c_val = response.usage.prompt_tokens, response.usage.completion_tokens
        if isinstance(p_val, int) and isinstance(c_val, int):
            return p_val, c_val
    # Dict usage
    if isinstance(response, dict) and "usage" in response:
        u = response["usage"]
        return u.get("input_tokens", 0) or u.get("prompt_tokens", 0), \
               u.get("output_tokens", 0) or u.get("completion_tokens", 0)
    # Estimate
    return len(input_text) // 4, len(output_text) // 4


def _extract_input_text(args: tuple, kwargs: dict) -> str:
    """
    Extract the prompt/input text from function arguments.
    Handles: first positional arg, 'prompt', 'message', 'messages', 'input' kwargs.
    """
    # Named kwargs first
    for key in ("prompt", "message", "input", "text", "query"):
        if key in kwargs:
            val = kwargs[key]
            return val if isinstance(val, str) else str(val)
    # messages=[{"role": "user", "content": "..."}] pattern
    if "messages" in kwargs:
        msgs = kwargs["messages"]
        if isinstance(msgs, list):
            parts = [
                m.get("content", "") if isinstance(m, dict) else str(m)
                for m in msgs
            ]
            return "\n".join(str(p) for p in parts)
    # First positional arg
    if args:
        val = args[0]
        return val if isinstance(val, str) else str(val)
    return "<no input captured>"


# ---------------------------------------------------------------------------
# Main decorator
# ---------------------------------------------------------------------------


def audit_llm_call(
    chain: AuditChain,
    decision_type: Union[DecisionType, str] = DecisionType.GENERATION,
    risk_tier: Union[RiskTier, str] = RiskTier.LIMITED,
    session_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    store_plaintext: bool = False,
    model_override: Optional[str] = None,
    system_id: str = "default",
) -> Callable[[F], F]:
    """
    Decorator factory that wraps any LLM-calling function with audit logging.

    Parameters
    ----------
    chain:
        The AuditChain instance to log into.
    decision_type:
        Category of AI decision (RECOMMENDATION, CLASSIFICATION, etc.).
    risk_tier:
        EU AI Act risk tier for this decision class.
    session_id:
        Optional fixed session ID. If None, a UUID is generated per call.
        To group calls in a conversation, pass the same session_id.
    metadata:
        Static metadata dict merged with any call-time metadata.
    store_plaintext:
        If True, store the actual prompt and response text alongside hashes.
        Use only in development environments.
    model_override:
        Override the model name logged. Useful when the model isn't available
        from the response object.
    system_id:
        Identifier for the AI system making this call. Used for per-system
        dashboards, cost tracking, and EU AI Act Article 12 system logging.
    """
    if isinstance(decision_type, str):
        decision_type = DecisionType(decision_type)
    if isinstance(risk_tier, str):
        risk_tier = RiskTier(risk_tier)

    # Override chain's store_plaintext if explicitly set here
    effective_store_plaintext = store_plaintext or chain.store_plaintext

    def decorator(func: F) -> F:
        is_async = inspect.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                sid = session_id or str(uuid.uuid4())
                input_text = _extract_input_text(args, kwargs)
                t0 = time.perf_counter()
                response = await func(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000.0

                output_text = _extract_text(response)
                in_tok, out_tok = _extract_tokens(response, input_text, output_text)
                model = model_override or _extract_model(response, func)

                # Override chain plaintext setting for this call
                orig = chain.store_plaintext
                chain.store_plaintext = effective_store_plaintext
                chain.append(
                    session_id=sid,
                    model=model,
                    input_text=input_text,
                    output_text=output_text,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    latency_ms=latency_ms,
                    decision_type=decision_type,
                    risk_tier=risk_tier,
                    metadata={**(metadata or {}), "function": func.__name__},
                    system_id=system_id,
                )
                chain.store_plaintext = orig
                return response

            return async_wrapper  # type: ignore[return-value]

        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                sid = session_id or str(uuid.uuid4())
                input_text = _extract_input_text(args, kwargs)
                t0 = time.perf_counter()
                response = func(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000.0

                output_text = _extract_text(response)
                in_tok, out_tok = _extract_tokens(response, input_text, output_text)
                model = model_override or _extract_model(response, func)

                orig = chain.store_plaintext
                chain.store_plaintext = effective_store_plaintext
                chain.append(
                    session_id=sid,
                    model=model,
                    input_text=input_text,
                    output_text=output_text,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    latency_ms=latency_ms,
                    decision_type=decision_type,
                    risk_tier=risk_tier,
                    metadata={**(metadata or {}), "function": func.__name__},
                    system_id=system_id,
                )
                chain.store_plaintext = orig
                return response

            return sync_wrapper  # type: ignore[return-value]

    return decorator


def _extract_model(response: Any, func: Callable) -> str:
    """Attempt to find model name in response metadata."""
    if hasattr(response, "model"):
        return response.model
    if isinstance(response, dict) and "model" in response:
        return response["model"]
    return func.__module__ + "." + func.__qualname__


# ---------------------------------------------------------------------------
# Context manager variant (for non-decorator usage)
# ---------------------------------------------------------------------------


class AuditContext:
    """
    Context manager for auditing code that calls an LLM inline.

    Usage::

        with AuditContext(
            chain=chain,
            input_text=prompt,
            decision_type=DecisionType.RECOMMENDATION,
            risk_tier=RiskTier.HIGH,
            session_id=session_id,
        ) as ctx:
            response = client.messages.create(...)
            ctx.set_output(response)
    """

    def __init__(
        self,
        chain: AuditChain,
        input_text: str,
        decision_type: Union[DecisionType, str] = DecisionType.GENERATION,
        risk_tier: Union[RiskTier, str] = RiskTier.LIMITED,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        model: str = "unknown",
        system_id: str = "default",
    ) -> None:
        self.chain = chain
        self.input_text = input_text
        self.decision_type = decision_type
        self.risk_tier = risk_tier
        self.session_id = session_id or str(uuid.uuid4())
        self.metadata = metadata or {}
        self.model = model
        self.system_id = system_id
        self._t0: float = 0.0
        self._response: Any = None

    def set_output(self, response: Any) -> None:
        self._response = response

    def __enter__(self) -> "AuditContext":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            return  # Don't log failed calls
        latency_ms = (time.perf_counter() - self._t0) * 1000.0
        output_text = _extract_text(self._response) if self._response else ""
        in_tok, out_tok = _extract_tokens(
            self._response, self.input_text, output_text
        )
        self.chain.append(
            session_id=self.session_id,
            model=self.model,
            input_text=self.input_text,
            output_text=output_text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=latency_ms,
            decision_type=self.decision_type,
            risk_tier=self.risk_tier,
            metadata=self.metadata,
            system_id=self.system_id,
        )
