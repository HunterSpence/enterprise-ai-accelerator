"""
01_anthropic_quickstart.py — AIAuditTrail + Anthropic SDK in 10 lines.

Every call to client.messages.create() is automatically logged to a
tamper-evident Merkle-tree hash chain. Zero changes to business logic.

Run:
    pip install anthropic ai-audit-trail
    export ANTHROPIC_API_KEY=sk-ant-...
    python 01_anthropic_quickstart.py
"""

# Step 1: Import the audited wrapper instead of the plain Anthropic client.
#         AuditedAnthropic is a drop-in replacement — same API surface.
from ai_audit_trail.integrations.anthropic_sdk import AuditedAnthropic

# Step 2: Import AuditChain — the append-only SQLite ledger.
from ai_audit_trail.chain import AuditChain, RiskTier

# Step 3: Create the audit chain. SQLite WAL-mode, zero external deps.
chain = AuditChain("anthropic_audit.db")

# Step 4: Create the audited client, passing the chain.
#         system_id tags every log entry with this AI system's identity —
#         required for EU AI Act Article 12(1)(d) compliance.
client = AuditedAnthropic(
    audit_chain=chain,
    system_id="my-assistant-v1",
    default_risk_tier=RiskTier.LIMITED,
)

# Step 5: Make calls exactly as you normally would — nothing changes here.
for i, prompt in enumerate([
    "What is the EU AI Act?",
    "Summarize Article 12 logging requirements.",
    "What is a Merkle tree?",
]):
    # Step 6: client.messages.create() is 100% standard Anthropic SDK.
    #         The wrapper captures tokens, cost, latency, and hashes the
    #         input/output before passing through the original response.
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # Use any Claude model
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    # Step 7: The response is the real Anthropic response — no wrapping.
    answer = response.content[0].text if response.content else ""
    print(f"\n[{i+1}] Q: {prompt}")
    print(f"     A: {answer[:80]}…")

# Step 8: Inspect the audit log — see what was captured automatically.
print(f"\n--- Audit Log ({chain.count()} entries) ---")
for entry in chain.query(limit=3):
    print(
        f"  entry_id: {entry.entry_id[:12]}…"
        f"  model: {entry.model}"
        f"  tokens: {entry.input_tokens}+{entry.output_tokens}"
        f"  cost: ${entry.cost_usd:.5f}"
        f"  risk: {entry.risk_tier}"
    )

# Step 9: Verify the chain has not been tampered with.
report = chain.verify_chain()
print(f"\nChain integrity: {'✅ VALID' if report.is_valid else '❌ TAMPERED'}")
print(f"Merkle root: {report.merkle_root[:32]}…")

# Step 10: That's it. Full EU AI Act Article 12 logging in 3 changed lines.
print("\nDone. Every call is now in a tamper-evident audit trail.")


if __name__ == "__main__":
    # Demo mode: runs with mock client if ANTHROPIC_API_KEY is not set.
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n[DEMO MODE] ANTHROPIC_API_KEY not set — showing audit log structure.")
        demo_chain = AuditChain(":memory:")
        demo_chain.append(
            session_id="demo-session",
            model="claude-haiku-4-5-20251001",
            input_text="What is the EU AI Act?",
            output_text="The EU AI Act is a comprehensive regulation…",
            input_tokens=12,
            output_tokens=45,
            latency_ms=320.0,
            system_id="my-assistant-v1",
            cost_usd=0.000042,
        )
        entry = demo_chain.query(limit=1)[0]
        print(f"\nDemo entry logged:")
        print(f"  entry_id:   {entry.entry_id}")
        print(f"  model:      {entry.model}")
        print(f"  input_hash: {entry.input_hash[:32]}…")
        print(f"  prev_hash:  {entry.prev_hash[:32]}…")
        print(f"  entry_hash: {entry.entry_hash[:32]}…")
        print(f"\nRun with ANTHROPIC_API_KEY set for live calls.")
