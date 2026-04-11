# AgentOps — Multi-Agent Orchestration Monitor

The most advanced module. Define a goal — Claude acts as an orchestrator, decomposing the task and dispatching specialized sub-agents via tool calls. Each agent runs its own Claude API call with a domain-specific system prompt.

## Architecture

```
User Goal
    ↓
Orchestrator (Claude + tool_use)
    ├── security_agent tool → Security Claude call
    ├── cost_agent tool → FinOps Claude call  
    ├── migration_agent tool → Migration Claude call
    └── reporting_agent tool → Executive Claude call
    ↓
Final Synthesis
```

This demonstrates **agentic AI** — not just an LLM answering questions, but Claude dynamically deciding which specialized agents to invoke, in what order, and synthesizing their outputs.

## Run It

```bash
cd modules/agentops
uvicorn app:app --reload --port 8005
# Open http://localhost:8005
```

## Specialized Sub-Agents

| Agent | Domain | System Prompt Focus |
|-------|--------|---------------------|
| `security_agent` | Cloud security | Vulnerabilities, compliance, remediation priorities |
| `cost_agent` | FinOps | Spend analysis, waste, savings opportunities |
| `migration_agent` | Cloud migration | 6R classification, wave planning, dependencies |
| `reporting_agent` | Executive communication | Board narratives, business impact framing |

## How It Works (Code)

```python
# orchestrator.py — simplified
tools = [
    {"name": "security_agent", "description": "...", "input_schema": {...}},
    {"name": "cost_agent", "description": "...", "input_schema": {...}},
    # ...
]

# Orchestrator loop
response = client.messages.create(
    model="claude-opus-4-6",
    tools=tools,
    messages=[{"role": "user", "content": task}]
)

# When Claude calls a tool, we run a sub-agent
for block in response.content:
    if block.type == "tool_use":
        agent_result = run_sub_agent(block.name, block.input)
        # Feed result back to orchestrator
```

## What You'll See in the UI

1. **Orchestrator Reasoning** — Claude's decomposition of the task
2. **Agent Execution Trace** — Each tool call with inputs and outputs
3. **Final Synthesis** — Orchestrator's integrated response after all agents complete

## Key Feature for Interviews

This module shows you understand the difference between:
- **Single LLM call**: "Ask Claude a question"
- **Agentic AI**: "Claude decomposes a task, routes to specialists, synthesizes results"

That distinction is what separates AI-native consulting from slide-deck consulting.
