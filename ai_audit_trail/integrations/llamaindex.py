"""
integrations/llamaindex.py — LlamaIndex callback handler for AI audit logging.

NEW in V2. Hooks into LlamaIndex's CBEventType system to audit:
- Query events (user query + synthesized response)
- Node retrieval events (RAG: which nodes were retrieved)
- LLM call events (raw LLM input/output)
- Embedding events (for vector search auditing)

Requires: pip install llama-index-core

Usage::

    from llama_index.core import VectorStoreIndex, Settings
    from llama_index.core.callbacks import CallbackManager
    from ai_audit_trail.integrations.llamaindex import AuditTrailLlamaIndexCallback
    from ai_audit_trail import AuditChain, RiskTier

    chain = AuditChain("audit.db")
    callback = AuditTrailLlamaIndexCallback(
        audit_chain=chain,
        risk_tier=RiskTier.HIGH,
        system_id="rag-system-v1",
    )
    Settings.callback_manager = CallbackManager([callback])
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional, Union

from ai_audit_trail.chain import AuditChain, DecisionType, RiskTier


class AuditTrailLlamaIndexCallback:
    """
    LlamaIndex BaseCallbackHandler that logs events to an AuditChain.

    Implements the CBEventType interface for llama-index-core.
    Lazy imports LlamaIndex so the core library has zero LlamaIndex dependency.

    Events handled:
    - QUERY:          User query + final response
    - LLM:            Raw LLM call (prompt + completion)
    - RETRIEVE:       Node retrieval (query + node count/sources)
    - EMBEDDING:      Embedding call (text → vector, for audit completeness)
    - SYNTHESIZE:     Response synthesis from nodes
    - FUNCTION_CALL:  Tool/function call in agentic pipeline
    """

    def __init__(
        self,
        audit_chain: AuditChain,
        risk_tier: Union[RiskTier, str] = RiskTier.LIMITED,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        system_id: str = "default",
    ) -> None:
        self.audit_chain = audit_chain
        self.risk_tier = RiskTier(risk_tier) if isinstance(risk_tier, str) else risk_tier
        self.session_id = session_id or str(uuid.uuid4())
        self.metadata = metadata or {}
        self.system_id = system_id

        # In-flight events: event_id -> {t0, payload}
        self._pending: dict[str, dict[str, Any]] = {}

        # Lazy import — verify at construction time
        try:
            from llama_index.core.callbacks import CBEventType
            self.CBEventType = CBEventType
        except ImportError as e:
            raise ImportError(
                "llama-index-core required: pip install llama-index-core"
            ) from e

    def on_event_start(
        self,
        event_type: Any,
        payload: Optional[dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Called at the start of a LlamaIndex event."""
        event_id = event_id or str(uuid.uuid4())
        self._pending[event_id] = {
            "t0": time.perf_counter(),
            "event_type": str(event_type),
            "payload": payload or {},
        }
        return event_id

    def on_event_end(
        self,
        event_type: Any,
        payload: Optional[dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        """Called at the end of a LlamaIndex event."""
        state = self._pending.pop(event_id, None)
        if state is None:
            return

        latency_ms = (time.perf_counter() - state["t0"]) * 1000.0
        event_type_str = str(event_type)
        end_payload = payload or {}

        # Route to specific handler based on event type
        CBEventType = self.CBEventType

        if "QUERY" in event_type_str:
            self._handle_query(state, end_payload, latency_ms)
        elif "LLM" in event_type_str:
            self._handle_llm(state, end_payload, latency_ms)
        elif "RETRIEVE" in event_type_str:
            self._handle_retrieve(state, end_payload, latency_ms)
        elif "SYNTHESIZE" in event_type_str:
            self._handle_synthesize(state, end_payload, latency_ms)
        elif "FUNCTION_CALL" in event_type_str:
            self._handle_function_call(state, end_payload, latency_ms)
        elif "EMBEDDING" in event_type_str:
            self._handle_embedding(state, end_payload, latency_ms)

    def _handle_query(
        self,
        state: dict[str, Any],
        end_payload: dict[str, Any],
        latency_ms: float,
    ) -> None:
        """Audit a top-level user query and response."""
        start_payload = state["payload"]
        # Extract query string
        query_str = ""
        if "query_str" in start_payload:
            query_str = str(start_payload["query_str"])
        elif hasattr(start_payload.get("query", None), "query_str"):
            query_str = start_payload["query"].query_str

        # Extract response
        response_obj = end_payload.get("response", None)
        response_text = ""
        if response_obj is not None:
            if hasattr(response_obj, "response"):
                response_text = str(response_obj.response or "")
            else:
                response_text = str(response_obj)

        self.audit_chain.append(
            session_id=self.session_id,
            model="llama_index:query",
            input_text=query_str[:2000],
            output_text=response_text[:2000],
            input_tokens=len(query_str) // 4,
            output_tokens=len(response_text) // 4,
            latency_ms=latency_ms,
            decision_type=DecisionType.GENERATION,
            risk_tier=self.risk_tier,
            metadata={**self.metadata, "source": "llamaindex_query"},
            system_id=self.system_id,
        )

    def _handle_llm(
        self,
        state: dict[str, Any],
        end_payload: dict[str, Any],
        latency_ms: float,
    ) -> None:
        """Audit a raw LLM call within LlamaIndex."""
        start_payload = state["payload"]
        messages = start_payload.get("messages", [])
        input_text = " ".join(
            str(getattr(m, "content", m)) for m in messages
        )[:2000] if messages else str(start_payload)[:2000]

        response_obj = end_payload.get("response", None)
        output_text = ""
        in_tok = 0
        out_tok = 0
        model_name = "llama_index:llm"

        if response_obj is not None:
            if hasattr(response_obj, "raw"):
                raw = response_obj.raw
                if raw and hasattr(raw, "usage"):
                    in_tok = getattr(raw.usage, "prompt_tokens", 0) or 0
                    out_tok = getattr(raw.usage, "completion_tokens", 0) or 0
                if raw and hasattr(raw, "model"):
                    model_name = raw.model or model_name
            if hasattr(response_obj, "message"):
                output_text = str(getattr(response_obj.message, "content", ""))[:2000]
            elif hasattr(response_obj, "text"):
                output_text = str(response_obj.text or "")[:2000]

        if not in_tok:
            in_tok = len(input_text) // 4
        if not out_tok:
            out_tok = len(output_text) // 4

        self.audit_chain.append(
            session_id=self.session_id,
            model=model_name,
            input_text=input_text,
            output_text=output_text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=latency_ms,
            decision_type=DecisionType.GENERATION,
            risk_tier=self.risk_tier,
            metadata={**self.metadata, "source": "llamaindex_llm"},
            system_id=self.system_id,
        )

    def _handle_retrieve(
        self,
        state: dict[str, Any],
        end_payload: dict[str, Any],
        latency_ms: float,
    ) -> None:
        """Audit a node retrieval event (RAG)."""
        start_payload = state["payload"]
        query_str = str(start_payload.get("query_str", ""))[:1000]
        nodes = end_payload.get("nodes", [])
        node_count = len(nodes) if hasattr(nodes, "__len__") else 0

        sources = []
        if hasattr(nodes, "__iter__"):
            for node_with_score in list(nodes)[:5]:
                node = getattr(node_with_score, "node", node_with_score)
                src = ""
                if hasattr(node, "metadata"):
                    src = node.metadata.get("file_name", "") or node.metadata.get("source", "")
                if src:
                    sources.append(str(src))

        output_text = f"Retrieved {node_count} nodes. Sources: {', '.join(sources[:3]) or 'none'}"

        self.audit_chain.append(
            session_id=self.session_id,
            model="llama_index:retriever",
            input_text=query_str,
            output_text=output_text,
            input_tokens=len(query_str) // 4,
            output_tokens=len(output_text) // 4,
            latency_ms=latency_ms,
            decision_type=DecisionType.RETRIEVAL,
            risk_tier=self.risk_tier,
            metadata={
                **self.metadata,
                "source": "llamaindex_retrieve",
                "node_count": node_count,
                "sources": sources[:5],
            },
            system_id=self.system_id,
        )

    def _handle_synthesize(
        self,
        state: dict[str, Any],
        end_payload: dict[str, Any],
        latency_ms: float,
    ) -> None:
        """Audit response synthesis from retrieved nodes."""
        response_obj = end_payload.get("response", None)
        response_text = str(
            getattr(response_obj, "response", response_obj) or ""
        )[:2000]

        self.audit_chain.append(
            session_id=self.session_id,
            model="llama_index:synthesizer",
            input_text="[node_synthesis]",
            output_text=response_text,
            input_tokens=0,
            output_tokens=len(response_text) // 4,
            latency_ms=latency_ms,
            decision_type=DecisionType.GENERATION,
            risk_tier=self.risk_tier,
            metadata={**self.metadata, "source": "llamaindex_synthesize"},
            system_id=self.system_id,
        )

    def _handle_function_call(
        self,
        state: dict[str, Any],
        end_payload: dict[str, Any],
        latency_ms: float,
    ) -> None:
        """Audit tool/function calls in agentic LlamaIndex pipelines."""
        start_payload = state["payload"]
        fn_name = start_payload.get("function_call", {}).get("name", "unknown_function")
        fn_args = str(start_payload.get("function_call", {}).get("arguments", {}))[:500]
        fn_output = str(end_payload.get("function_call_response", ""))[:500]

        self.audit_chain.append(
            session_id=self.session_id,
            model=f"llama_index:tool:{fn_name}",
            input_text=fn_args,
            output_text=fn_output,
            input_tokens=len(fn_args) // 4,
            output_tokens=len(fn_output) // 4,
            latency_ms=latency_ms,
            decision_type=DecisionType.TOOL_USE,
            risk_tier=self.risk_tier,
            metadata={
                **self.metadata,
                "source": "llamaindex_function_call",
                "function_name": fn_name,
            },
            system_id=self.system_id,
        )

    def _handle_embedding(
        self,
        state: dict[str, Any],
        end_payload: dict[str, Any],
        latency_ms: float,
    ) -> None:
        """Audit embedding calls (minimal — just log count for completeness)."""
        chunks = state["payload"].get("chunks", [])
        chunk_count = len(chunks) if hasattr(chunks, "__len__") else 0
        embeddings = end_payload.get("embeddings", [])
        embedding_count = len(embeddings) if hasattr(embeddings, "__len__") else 0

        self.audit_chain.append(
            session_id=self.session_id,
            model="llama_index:embedding",
            input_text=f"[{chunk_count} text chunks]",
            output_text=f"[{embedding_count} embeddings generated]",
            input_tokens=chunk_count * 50,   # rough estimate
            output_tokens=0,
            latency_ms=latency_ms,
            decision_type=DecisionType.RETRIEVAL,
            risk_tier=RiskTier.MINIMAL,  # Embeddings are generally MINIMAL risk
            metadata={
                **self.metadata,
                "source": "llamaindex_embedding",
                "chunk_count": chunk_count,
                "embedding_count": embedding_count,
            },
            system_id=self.system_id,
        )

    def start_trace(self, trace_id: Optional[str] = None) -> None:
        """Called at start of trace (no-op — handled per event)."""
        pass

    def end_trace(
        self,
        trace_id: Optional[str] = None,
        trace_map: Optional[dict[str, Any]] = None,
    ) -> None:
        """Called at end of trace (no-op)."""
        pass
