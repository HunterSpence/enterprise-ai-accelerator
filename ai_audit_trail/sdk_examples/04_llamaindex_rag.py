"""
04_llamaindex_rag.py — AIAuditTrail + LlamaIndex RAG pipeline.

AuditTrailLlamaCallback hooks into LlamaIndex's event system and logs
both retrieval events and synthesis (LLM) events. Every RAG query is
fully audited: what was retrieved, what was synthesized, cost, latency.

Run:
    pip install llama-index llama-index-llms-anthropic ai-audit-trail
    export ANTHROPIC_API_KEY=sk-ant-...
    python 04_llamaindex_rag.py
"""

# Step 1: Import the LlamaIndex callback handler from AIAuditTrail.
#         Captures both retrieval and synthesis steps separately.
from ai_audit_trail.integrations.llamaindex import AuditTrailLlamaCallback

# Step 2: Import the audit chain — same chain works across all integrations.
from ai_audit_trail.chain import AuditChain, RiskTier, DecisionType

# Step 3: Create chain and LlamaIndex callback.
#         system_id ties all RAG pipeline calls together for compliance.
audit_chain = AuditChain("llamaindex_audit.db")
audit_callback = AuditTrailLlamaCallback(
    audit_chain=audit_chain,
    system_id="rag-knowledge-base-v1",   # Identifies this RAG system
    default_risk_tier=RiskTier.LIMITED,
)

# Step 4: Standard LlamaIndex setup.
try:
    from llama_index.core import VectorStoreIndex, Document, Settings
    from llama_index.core.callbacks import CallbackManager

    # Step 5: Wire the callback via LlamaIndex's CallbackManager.
    #         This single line audits the entire RAG pipeline.
    Settings.callback_manager = CallbackManager([audit_callback])

    # Step 6: Build a minimal in-memory index from sample documents.
    documents = [
        Document(text="EU AI Act Article 12 requires operators of high-risk AI systems "
                      "to ensure automatic logging of events (logs) throughout the lifetime "
                      "of high-risk AI systems."),
        Document(text="NIST AI RMF MEASURE 2.5: AI system to be deployed is demonstrated "
                      "to be valid and reliable for the defined context of use."),
        Document(text="Merkle trees are binary trees where each leaf node is a hash of a "
                      "data block and each non-leaf node is a hash of its children."),
    ]

    # Step 7: Create index — retrieval operations will be audited automatically.
    index = VectorStoreIndex.from_documents(documents)
    query_engine = index.as_query_engine(similarity_top_k=2)

    # Step 8: Run RAG queries — retrieval + synthesis both logged.
    queries = [
        "What does Article 12 require for high-risk AI systems?",
        "How does NIST MEASURE 2.5 relate to validation?",
    ]
    for q in queries:
        # Step 9: Standard LlamaIndex query — audit happens automatically.
        response = query_engine.query(q)
        print(f"Q: {q}")
        print(f"A: {str(response)[:100]}…\n")

    LLAMAINDEX_AVAILABLE = True

except ImportError:
    LLAMAINDEX_AVAILABLE = False
    print("[DEMO MODE] llama-index not installed. Showing RAG audit structure.")

# Step 10: Inspect retrieval + synthesis audit entries separately.
print(f"\n--- LlamaIndex RAG Audit Log ({audit_chain.count()} entries) ---")
retrieval_entries = audit_chain.query(decision_type=DecisionType.RETRIEVAL.value, limit=5)
generation_entries = audit_chain.query(decision_type=DecisionType.GENERATION.value, limit=5)
print(f"Retrieval entries logged: {len(retrieval_entries)}")
print(f"Synthesis entries logged: {len(generation_entries)}")
for entry in audit_chain.query(limit=4):
    print(
        f"  {entry.decision_type:12s}"
        f"  model={entry.model:25s}"
        f"  tokens={entry.input_tokens}+{entry.output_tokens}"
    )


if __name__ == "__main__":
    import os
    if not os.environ.get("ANTHROPIC_API_KEY") or not LLAMAINDEX_AVAILABLE:
        # Demo: show what RAG audit entries look like
        demo = AuditChain(":memory:")

        # Retrieval step logged
        demo.append(
            session_id="rag-demo-q1",
            model="retrieval",
            input_text="What does Article 12 require?",
            output_text="[Node 1: EU AI Act Article 12 requires operators…] [Node 2: high-risk AI systems must log…]",
            input_tokens=0,
            output_tokens=0,
            latency_ms=12.0,
            system_id="rag-knowledge-base-v1",
            decision_type=DecisionType.RETRIEVAL,
            metadata={"retrieved_nodes": 2, "similarity_top_k": 2},
        )

        # Synthesis step logged
        demo.append(
            session_id="rag-demo-q1",
            model="claude-haiku-4-5-20251001",
            input_text="[Context + Question]",
            output_text="Article 12 requires automatic logging throughout the lifetime of high-risk AI systems.",
            input_tokens=150,
            output_tokens=25,
            latency_ms=680.0,
            system_id="rag-knowledge-base-v1",
            decision_type=DecisionType.GENERATION,
            metadata={"query_type": "synthesis", "context_nodes": 2},
        )

        print("\nDemo RAG pipeline audit entries:")
        for e in demo.query():
            print(f"  step={e.decision_type:12s}  model={e.model:25s}  meta={e.metadata}")
        print("\nRun with ANTHROPIC_API_KEY + llama-index for live demo.")
