"""
integrations/langchain.py — LangChain callback handler for AI audit logging.

V2 upgrades:
- All chain events: on_chain_start, on_chain_end, on_chain_error
- Agent events: on_agent_action, on_agent_finish (full agentic pipeline auditing)
- Retriever events: on_retriever_start, on_retriever_end (RAG auditing)
- Tool events: on_tool_start, on_tool_end, on_tool_error (with tool name capture)
- system_id and cost_usd tracking per event

Usage::

    from langchain_anthropic import ChatAnthropic
    from ai_audit_trail.integrations.langchain import AuditTrailCallback
    from ai_audit_trail import AuditChain, DecisionType, RiskTier

    chain = AuditChain("audit.db")
    callback = AuditTrailCallback(
        audit_chain=chain,
        risk_tier=RiskTier.HIGH,
        system_id="rag-pipeline-v2",
    )
    llm = ChatAnthropic(model="claude-sonnet-4-6", callbacks=[callback])
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional, Union

from ai_audit_trail.chain import AuditChain, DecisionType, RiskTier


class AuditTrailCallback:
    """
    LangChain BaseCallbackHandler subclass.

    V2 hooks:
    - LLM:       on_llm_start, on_llm_end, on_llm_error
    - Chain:     on_chain_start, on_chain_end, on_chain_error
    - Agent:     on_agent_action, on_agent_finish
    - Retriever: on_retriever_start, on_retriever_end
    - Tool:      on_tool_start, on_tool_end, on_tool_error
    """

    def __init__(
        self,
        audit_chain: AuditChain,
        decision_type: Union[DecisionType, str] = DecisionType.GENERATION,
        risk_tier: Union[RiskTier, str] = RiskTier.LIMITED,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        system_id: str = "default",
    ) -> None:
        try:
            from langchain_core.callbacks import BaseCallbackHandler
            self._base_class = BaseCallbackHandler
        except ImportError:
            try:
                from langchain.callbacks.base import BaseCallbackHandler  # type: ignore
                self._base_class = BaseCallbackHandler
            except ImportError as e:
                raise ImportError("pip install langchain-core") from e

        self.audit_chain = audit_chain
        self.decision_type = (
            DecisionType(decision_type) if isinstance(decision_type, str) else decision_type
        )
        self.risk_tier = (
            RiskTier(risk_tier) if isinstance(risk_tier, str) else risk_tier
        )
        self.session_id = session_id or str(uuid.uuid4())
        self.metadata = metadata or {}
        self.system_id = system_id

        # In-flight state keyed by run_id
        self._llm_pending: dict[str, dict[str, Any]] = {}
        self._chain_pending: dict[str, dict[str, Any]] = {}
        self._tool_pending: dict[str, dict[str, Any]] = {}
        self._retriever_pending: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # LLM hooks
    # ------------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id) if run_id else str(uuid.uuid4())
        model = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or serialized.get("name", "langchain/unknown")
        )
        self._llm_pending[run_key] = {
            "t0": time.perf_counter(),
            "input_text": "\n".join(prompts),
            "model": model,
        }

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id) if run_id else ""
        state = self._llm_pending.pop(run_key, None)
        if state is None:
            return

        latency_ms = (time.perf_counter() - state["t0"]) * 1000.0
        output_text = ""
        in_tok = 0
        out_tok = 0

        if hasattr(response, "generations"):
            parts = []
            for gen_list in response.generations:
                for gen in gen_list:
                    if hasattr(gen, "text"):
                        parts.append(gen.text)
                    elif hasattr(gen, "message") and hasattr(gen.message, "content"):
                        content = gen.message.content
                        if isinstance(content, str):
                            parts.append(content)
                        elif isinstance(content, list):
                            parts.extend(
                                b.get("text", "") if isinstance(b, dict) else ""
                                for b in content
                                if isinstance(b, dict) and b.get("type") == "text"
                            )
            output_text = "\n".join(parts)

        if hasattr(response, "llm_output") and response.llm_output:
            usage = response.llm_output.get("usage", {}) or response.llm_output.get("token_usage", {})
            in_tok = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
            out_tok = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)

        if not in_tok:
            in_tok = len(state["input_text"]) // 4
        if not out_tok:
            out_tok = len(output_text) // 4

        self.audit_chain.append(
            session_id=self.session_id,
            model=state["model"],
            input_text=state["input_text"],
            output_text=output_text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=latency_ms,
            decision_type=self.decision_type,
            risk_tier=self.risk_tier,
            metadata={**self.metadata, "source": "langchain_llm"},
            system_id=self.system_id,
        )

    def on_llm_error(
        self,
        error: Exception,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id) if run_id else ""
        state = self._llm_pending.pop(run_key, None)
        if state is None:
            return
        latency_ms = (time.perf_counter() - state["t0"]) * 1000.0
        self.audit_chain.append(
            session_id=self.session_id,
            model=state["model"],
            input_text=state["input_text"],
            output_text=f"ERROR: {type(error).__name__}: {error}",
            input_tokens=len(state["input_text"]) // 4,
            output_tokens=0,
            latency_ms=latency_ms,
            decision_type=self.decision_type,
            risk_tier=self.risk_tier,
            metadata={**self.metadata, "error": True, "source": "langchain_llm"},
            system_id=self.system_id,
        )

    # ------------------------------------------------------------------
    # Chain hooks
    # ------------------------------------------------------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id) if run_id else str(uuid.uuid4())
        self._chain_pending[run_key] = {
            "t0": time.perf_counter(),
            "chain_name": serialized.get("name", "unknown_chain"),
            "input_text": str(inputs)[:2000],  # Truncate large inputs
        }

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id) if run_id else ""
        state = self._chain_pending.pop(run_key, None)
        if state is None:
            return

        latency_ms = (time.perf_counter() - state["t0"]) * 1000.0
        output_text = str(outputs)[:2000]

        self.audit_chain.append(
            session_id=self.session_id,
            model=f"chain:{state['chain_name']}",
            input_text=state["input_text"],
            output_text=output_text,
            input_tokens=len(state["input_text"]) // 4,
            output_tokens=len(output_text) // 4,
            latency_ms=latency_ms,
            decision_type=DecisionType.GENERATION,
            risk_tier=self.risk_tier,
            metadata={**self.metadata, "source": "langchain_chain", "chain_name": state["chain_name"]},
            system_id=self.system_id,
        )

    def on_chain_error(
        self,
        error: Exception,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id) if run_id else ""
        state = self._chain_pending.pop(run_key, None)
        if state is None:
            return
        latency_ms = (time.perf_counter() - state["t0"]) * 1000.0
        self.audit_chain.append(
            session_id=self.session_id,
            model=f"chain:{state['chain_name']}",
            input_text=state["input_text"],
            output_text=f"ERROR: {type(error).__name__}: {error}",
            input_tokens=len(state["input_text"]) // 4,
            output_tokens=0,
            latency_ms=latency_ms,
            decision_type=DecisionType.GENERATION,
            risk_tier=self.risk_tier,
            metadata={**self.metadata, "error": True, "source": "langchain_chain"},
            system_id=self.system_id,
        )

    # ------------------------------------------------------------------
    # Agent hooks (V2 new)
    # ------------------------------------------------------------------

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Log agent action (tool selection) as AUTONOMOUS_ACTION."""
        tool = getattr(action, "tool", "unknown_tool")
        tool_input = getattr(action, "tool_input", "")
        log_str = getattr(action, "log", "")

        self.audit_chain.append(
            session_id=self.session_id,
            model="agent",
            input_text=str(tool_input)[:1000],
            output_text=log_str[:1000],
            input_tokens=len(str(tool_input)) // 4,
            output_tokens=len(log_str) // 4,
            latency_ms=0.0,
            decision_type=DecisionType.AUTONOMOUS_ACTION,
            risk_tier=self.risk_tier,
            metadata={
                **self.metadata,
                "source": "langchain_agent_action",
                "tool": tool,
            },
            system_id=self.system_id,
        )

    def on_agent_finish(
        self,
        finish: Any,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Log agent final output."""
        return_values = getattr(finish, "return_values", {})
        log_str = getattr(finish, "log", "")
        output_text = str(return_values.get("output", log_str))[:2000]

        self.audit_chain.append(
            session_id=self.session_id,
            model="agent",
            input_text="[agent_finish]",
            output_text=output_text,
            input_tokens=0,
            output_tokens=len(output_text) // 4,
            latency_ms=0.0,
            decision_type=DecisionType.GENERATION,
            risk_tier=self.risk_tier,
            metadata={**self.metadata, "source": "langchain_agent_finish"},
            system_id=self.system_id,
        )

    # ------------------------------------------------------------------
    # Retriever hooks — RAG auditing (V2 new)
    # ------------------------------------------------------------------

    def on_retriever_start(
        self,
        serialized: dict[str, Any],
        query: str,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Log RAG retriever query start."""
        run_key = str(run_id) if run_id else str(uuid.uuid4())
        self._retriever_pending[run_key] = {
            "t0": time.perf_counter(),
            "query": query,
            "retriever_name": serialized.get("name", "retriever"),
        }

    def on_retriever_end(
        self,
        documents: Any,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Log RAG retriever results (node count + source metadata)."""
        run_key = str(run_id) if run_id else ""
        state = self._retriever_pending.pop(run_key, None)
        if state is None:
            return

        latency_ms = (time.perf_counter() - state["t0"]) * 1000.0
        doc_count = len(documents) if hasattr(documents, "__len__") else 0
        sources = []
        if hasattr(documents, "__iter__"):
            for doc in list(documents)[:5]:
                src = getattr(doc, "metadata", {}).get("source", "")
                if src:
                    sources.append(str(src))

        output_text = f"Retrieved {doc_count} documents. Sources: {', '.join(sources[:3]) or 'none'}"

        self.audit_chain.append(
            session_id=self.session_id,
            model=f"retriever:{state['retriever_name']}",
            input_text=state["query"][:1000],
            output_text=output_text,
            input_tokens=len(state["query"]) // 4,
            output_tokens=len(output_text) // 4,
            latency_ms=latency_ms,
            decision_type=DecisionType.RETRIEVAL,
            risk_tier=self.risk_tier,
            metadata={
                **self.metadata,
                "source": "langchain_retriever",
                "doc_count": doc_count,
                "sources": sources[:5],
            },
            system_id=self.system_id,
        )

    # ------------------------------------------------------------------
    # Tool hooks (V2 enhanced)
    # ------------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id) if run_id else str(uuid.uuid4())
        self._tool_pending[run_key] = {
            "t0": time.perf_counter(),
            "tool_name": serialized.get("name", "unknown_tool"),
            "input_str": input_str[:500],
        }

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id) if run_id else ""
        state = self._tool_pending.pop(run_key, None)
        if state is None:
            return

        latency_ms = (time.perf_counter() - state["t0"]) * 1000.0
        self.audit_chain.append(
            session_id=self.session_id,
            model=f"tool:{state['tool_name']}",
            input_text=state["input_str"],
            output_text=str(output)[:1000],
            input_tokens=len(state["input_str"]) // 4,
            output_tokens=len(str(output)) // 4,
            latency_ms=latency_ms,
            decision_type=DecisionType.TOOL_USE,
            risk_tier=self.risk_tier,
            metadata={
                **self.metadata,
                "source": "langchain_tool",
                "tool_name": state["tool_name"],
            },
            system_id=self.system_id,
        )

    def on_tool_error(
        self,
        error: Exception,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id) if run_id else ""
        state = self._tool_pending.pop(run_key, None)
        if state is None:
            return
        latency_ms = (time.perf_counter() - state["t0"]) * 1000.0
        self.audit_chain.append(
            session_id=self.session_id,
            model=f"tool:{state['tool_name']}",
            input_text=state["input_str"],
            output_text=f"ERROR: {type(error).__name__}: {error}",
            input_tokens=len(state["input_str"]) // 4,
            output_tokens=0,
            latency_ms=latency_ms,
            decision_type=DecisionType.TOOL_USE,
            risk_tier=self.risk_tier,
            metadata={
                **self.metadata,
                "error": True,
                "source": "langchain_tool",
                "tool_name": state["tool_name"],
            },
            system_id=self.system_id,
        )

    def on_text(self, *args: Any, **kwargs: Any) -> None:
        pass
