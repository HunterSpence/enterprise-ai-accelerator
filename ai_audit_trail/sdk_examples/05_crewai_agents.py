"""
05_crewai_agents.py — AIAuditTrail + CrewAI multi-agent audit trail.

AIAuditTrailCrewCallback hooks into CrewAI's event bus and logs every
agent action, tool call, and handoff in the multi-agent pipeline.
Each agent step becomes a separate AUTONOMOUS_ACTION audit entry.

Run:
    pip install crewai ai-audit-trail
    export ANTHROPIC_API_KEY=sk-ant-...
    python 05_crewai_agents.py
"""

# Step 1: Import CrewAI callback from AIAuditTrail.
#         Captures agent task start/end, tool calls, and handoffs.
from ai_audit_trail.integrations.crewai import AIAuditTrailCrewCallback

# Step 2: Import chain — audit covers ALL agents in a crew with one chain.
from ai_audit_trail.chain import AuditChain, RiskTier, DecisionType

# Step 3: Create chain and callback.
#         Every agent action from every crew member will be logged here.
audit_chain = AuditChain("crewai_audit.db")
audit_callback = AIAuditTrailCrewCallback(
    audit_chain=audit_chain,
    system_id="compliance-crew-v1",   # Identifies the multi-agent system
    default_risk_tier=RiskTier.HIGH,  # Agents making decisions → HIGH risk
)

# Step 4: Standard CrewAI agent + task setup.
try:
    from crewai import Agent, Task, Crew, Process

    # Step 5: Define agents — standard CrewAI, no audit code in agents.
    researcher = Agent(
        role="AI Compliance Researcher",
        goal="Research EU AI Act requirements for high-risk AI systems",
        backstory="Expert in EU AI Act Regulation 2024/1689",
        verbose=True,
    )

    analyst = Agent(
        role="Risk Analyst",
        goal="Analyze compliance gaps and prioritize remediation",
        backstory="Specialist in AI governance and NIST AI RMF",
        verbose=True,
    )

    # Step 6: Define tasks — standard CrewAI tasks.
    research_task = Task(
        description="Research the Article 12 logging requirements",
        expected_output="A concise summary of Article 12 obligations",
        agent=researcher,
    )

    analysis_task = Task(
        description="Identify the top 3 compliance gaps for a loan approval AI",
        expected_output="Ranked list of compliance gaps with remediation steps",
        agent=analyst,
    )

    # Step 7: Create crew with audit callback in process_kwargs.
    #         This single addition audits all agent actions automatically.
    crew = Crew(
        agents=[researcher, analyst],
        tasks=[research_task, analysis_task],
        process=Process.sequential,
        callbacks=[audit_callback],      # ← One line to audit the entire crew
        verbose=False,
    )

    # Step 8: Kick off the crew — agent handoffs are logged as they happen.
    print("Starting compliance research crew…")
    result = crew.kickoff()
    print(f"\nCrew result: {str(result)[:200]}…")

    CREWAI_AVAILABLE = True

except ImportError:
    CREWAI_AVAILABLE = False
    print("[DEMO MODE] crewai not installed. Showing multi-agent audit structure.")

# Step 9: Review agent handoff audit trail.
print(f"\n--- CrewAI Multi-Agent Audit Log ({audit_chain.count()} entries) ---")
agent_actions = audit_chain.query(
    decision_type=DecisionType.AUTONOMOUS_ACTION.value, limit=10
)
tool_calls = audit_chain.query(
    decision_type=DecisionType.TOOL_USE.value, limit=10
)
print(f"Agent actions logged: {len(agent_actions)}")
print(f"Tool calls logged:    {len(tool_calls)}")
for entry in audit_chain.query(limit=5):
    agent_name = entry.metadata.get("agent_role", "unknown")
    print(
        f"  agent={agent_name:20s}"
        f"  type={entry.decision_type:20s}"
        f"  model={entry.model:20s}"
    )

# Step 10: Multi-agent compliance is critical — one verify covers all agents.
report = audit_chain.verify_chain()
print(f"\nFull crew audit integrity: {'✅ VALID' if report.is_valid else '❌ TAMPERED'}")
print(f"Total agent steps logged: {report.total_entries}")


if __name__ == "__main__":
    import os
    if not os.environ.get("ANTHROPIC_API_KEY") or not CREWAI_AVAILABLE:
        # Demo: simulate a multi-agent run with synthetic entries
        demo = AuditChain(":memory:")

        # Agent 1: researcher task
        demo.append(
            session_id="crew-demo-run-1",
            model="claude-sonnet-4-6",
            input_text="Research Article 12 logging requirements",
            output_text="Article 12 requires: timestamps, input/output logs, model ID…",
            input_tokens=45,
            output_tokens=180,
            latency_ms=1240.0,
            system_id="compliance-crew-v1",
            decision_type=DecisionType.AUTONOMOUS_ACTION,
            risk_tier=RiskTier.HIGH,
            metadata={"agent_role": "AI Compliance Researcher", "task": "research_task"},
        )

        # Agent 2: analyst task (handoff)
        demo.append(
            session_id="crew-demo-run-1",
            model="claude-sonnet-4-6",
            input_text="Analyze compliance gaps: [researcher output]",
            output_text="Top 3 gaps: 1) Retention policy missing…",
            input_tokens=220,
            output_tokens=310,
            latency_ms=1890.0,
            system_id="compliance-crew-v1",
            decision_type=DecisionType.AUTONOMOUS_ACTION,
            risk_tier=RiskTier.HIGH,
            metadata={"agent_role": "Risk Analyst", "task": "analysis_task", "handoff_from": "researcher"},
        )

        print("\nDemo multi-agent audit trail:")
        for e in demo.query():
            print(
                f"  agent={e.metadata.get('agent_role', '?'):25s}"
                f"  task={e.metadata.get('task', '?'):15s}"
                f"  tokens={e.input_tokens}+{e.output_tokens}"
            )
        r = demo.verify_chain()
        print(f"\nChain integrity: {'✅ VALID' if r.is_valid else '❌ TAMPERED'}")
        print(f"Merkle root: {r.merkle_root[:48]}…")
        print("\nRun with ANTHROPIC_API_KEY + crewai for live demo.")
