"""
02_openai_quickstart.py — AIAuditTrail + OpenAI SDK in 10 lines.

Same pattern as the Anthropic quickstart. AuditedOpenAI wraps the
OpenAI client transparently — every chat.completions.create() call is
logged to the tamper-evident hash chain.

Run:
    pip install openai ai-audit-trail
    export OPENAI_API_KEY=sk-...
    python 02_openai_quickstart.py
"""

# Step 1: Import AuditedOpenAI — drop-in replacement for openai.OpenAI.
from ai_audit_trail.integrations.openai_sdk import AuditedOpenAI

# Step 2: Import AuditChain and risk classification.
from ai_audit_trail.chain import AuditChain, RiskTier, DecisionType

# Step 3: Open a separate chain for OpenAI calls (or reuse an existing one).
chain = AuditChain("openai_audit.db")

# Step 4: Create the audited OpenAI client.
#         All parameters match openai.OpenAI() — api_key, base_url, etc.
client = AuditedOpenAI(
    audit_chain=chain,
    system_id="gpt-assistant-v1",
    default_risk_tier=RiskTier.LIMITED,
)

# Step 5: Make calls with the standard OpenAI API — unchanged.
prompts = [
    "Explain GDPR Article 25 in one sentence.",
    "What is differential privacy?",
    "How does RLHF training work?",
]

for i, prompt in enumerate(prompts):
    # Step 6: Standard openai.chat.completions.create() signature.
    response = client.chat.completions.create(
        model="gpt-4o-mini",      # Any OpenAI model works
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )

    # Step 7: Real OpenAI response returned unchanged.
    answer = response.choices[0].message.content or ""
    print(f"\n[{i+1}] Q: {prompt}")
    print(f"     A: {answer[:80]}…")

# Step 8: Audit log captured the same fields as the Anthropic integration.
print(f"\n--- OpenAI Audit Log ({chain.count()} entries) ---")
for entry in chain.query(limit=3):
    print(
        f"  model: {entry.model:20s}"
        f"  tokens: {entry.input_tokens:5d}+{entry.output_tokens:5d}"
        f"  cost: ${entry.cost_usd:.5f}"
        f"  decision: {entry.decision_type}"
    )

# Step 9: Both Anthropic and OpenAI chains can be verified the same way.
report = chain.verify_chain()
print(f"\nChain integrity: {'✅ VALID' if report.is_valid else '❌ TAMPERED'}")
print(f"Total entries:  {report.total_entries}")

# Step 10: Multi-cloud AI audit — same compliance posture across all providers.
print("\nMulti-provider audit achieved. EU AI Act Article 12 covered for all calls.")


if __name__ == "__main__":
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        print("\n[DEMO MODE] OPENAI_API_KEY not set — showing audit structure.")
        from ai_audit_trail.chain import AuditChain as _AC
        demo_chain = _AC(":memory:")
        demo_chain.append(
            session_id="demo-openai",
            model="gpt-4o-mini",
            input_text="Explain GDPR in one sentence.",
            output_text="GDPR is a European data protection regulation…",
            input_tokens=8,
            output_tokens=22,
            latency_ms=410.0,
            system_id="gpt-assistant-v1",
            cost_usd=0.000018,
            decision_type=DecisionType.GENERATION,
        )
        entry = demo_chain.query(limit=1)[0]
        print(f"\nDemo entry: model={entry.model}, tokens={entry.input_tokens}+{entry.output_tokens}")
        print(f"entry_hash: {entry.entry_hash[:48]}…")
        print("\nRun with OPENAI_API_KEY set for live calls.")
