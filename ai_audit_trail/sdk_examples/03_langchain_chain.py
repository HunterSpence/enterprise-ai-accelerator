"""
03_langchain_chain.py — AIAuditTrail + LangChain callback integration.

AuditTrailCallback hooks into LangChain's callback system and logs every
LLM call, chain step, and tool invocation to the audit trail automatically.
Works with any LangChain LLM, chat model, or chain.

Run:
    pip install langchain langchain-anthropic ai-audit-trail
    export ANTHROPIC_API_KEY=sk-ant-...
    python 03_langchain_chain.py
"""

# Step 1: Import the LangChain callback handler from AIAuditTrail.
#         This satisfies EU AI Act Article 12 for LangChain-based pipelines.
from ai_audit_trail.integrations.langchain import AuditTrailCallback

# Step 2: Import the audit chain.
from ai_audit_trail.chain import AuditChain, RiskTier

# Step 3: Create the chain and callback handler.
#         The callback intercepts LangChain's on_llm_end event automatically.
audit_chain = AuditChain("langchain_audit.db")
audit_callback = AuditTrailCallback(
    audit_chain=audit_chain,
    system_id="langchain-pipeline-v1",   # EU AI Act Art.12(d): system identification
    default_risk_tier=RiskTier.LIMITED,
)

# Step 4: Standard LangChain setup — note we ONLY add the callback.
try:
    from langchain_anthropic import ChatAnthropic        # pip install langchain-anthropic
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    # Step 5: Wire AuditTrailCallback into the LLM constructor.
    #         No other code changes needed — all calls are now audited.
    llm = ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        callbacks=[audit_callback],       # ← Single line change for full audit
    )

    # Step 6: Build a standard LCEL chain.
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a compliance expert."),
        ("human", "{question}"),
    ])
    chain = prompt | llm | StrOutputParser()

    # Step 7: Run the chain — every LLM call is automatically audited.
    questions = [
        "What is EU AI Act Article 12?",
        "What does NIST AI RMF MEASURE function cover?",
    ]
    for q in questions:
        # Step 8: The chain runs normally; audit happens in the background.
        answer = chain.invoke({"question": q})
        print(f"Q: {q}")
        print(f"A: {answer[:100]}…\n")

    LANGCHAIN_AVAILABLE = True

except ImportError:
    LANGCHAIN_AVAILABLE = False
    print("[DEMO MODE] langchain-anthropic not installed. Showing mock chain steps.")

# Step 9: Inspect the audit log — see the chain steps that were captured.
print(f"\n--- LangChain Audit Log ({audit_chain.count()} entries) ---")
for entry in audit_chain.query(limit=5):
    print(
        f"  {entry.timestamp[:19]}"
        f"  model={entry.model:25s}"
        f"  decision={entry.decision_type:20s}"
        f"  tokens={entry.input_tokens}+{entry.output_tokens}"
    )

# Step 10: Verify chain integrity and print the Merkle root.
#          One command covers ALL LangChain pipeline steps.
report = audit_chain.verify_chain()
print(f"\nChain integrity: {'✅ VALID' if report.is_valid else '❌ TAMPERED'}")
print(f"Entries logged:  {report.total_entries}")
print(f"Merkle root:     {report.merkle_root[:48]}…")


if __name__ == "__main__":
    import os
    if not os.environ.get("ANTHROPIC_API_KEY") or not LANGCHAIN_AVAILABLE:
        # Demo: inject synthetic chain step entries to show the structure
        from ai_audit_trail.chain import DecisionType
        demo = AuditChain(":memory:")
        demo.append(
            session_id="lc-demo-1",
            model="claude-haiku-4-5-20251001",
            input_text="What is EU AI Act Article 12?",
            output_text="Article 12 requires high-risk AI systems to maintain logs…",
            input_tokens=25,
            output_tokens=60,
            latency_ms=520.0,
            system_id="langchain-pipeline-v1",
            decision_type=DecisionType.GENERATION,
            metadata={"chain_type": "LCEL", "step": "llm_call"},
        )
        print("\nDemo LangChain audit entry:")
        e = demo.query(limit=1)[0]
        print(f"  system_id: {e.system_id}")
        print(f"  metadata:  {e.metadata}")
        print(f"  hash:      {e.entry_hash[:48]}…")
        print("\nRun with ANTHROPIC_API_KEY + langchain-anthropic for live demo.")
