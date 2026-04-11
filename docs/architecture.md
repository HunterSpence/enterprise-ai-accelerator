# Architecture — Enterprise AI Accelerator

## Overview

Five FastAPI modules, each a standalone Claude-powered service. Each can run independently on its own port. Shared only: the Anthropic Python SDK and the `ANTHROPIC_API_KEY` environment variable.

## Module Architecture

```
enterprise-ai-accelerator/
│
├── modules/
│   ├── cloudiq/          :8001  AWS config → security + cost + complexity analysis
│   ├── migrationscout/   :8002  Workload CSV/JSON → wave-based migration roadmap
│   ├── policyguard/      :8003  Terraform/CF → policy violations + remediation
│   ├── executivereport/  :8004  Raw metrics → board-ready narrative
│   └── agentops/         :8005  Goal + context → multi-agent orchestration trace
│
├── cloudiq/              Legacy library module (pre-FastAPI)
├── migration_scout/      Legacy library module
├── policy_guard/         Legacy library module
└── executive_report/     Legacy library module
```

## Request Flow (Modules 1-4)

```
Browser/Client
      │
      │ POST /analyze (or /plan, /check, /generate)
      ▼
  FastAPI app.py
      │
      │ calls analyzer.py / planner.py / checker.py / generator.py
      ▼
  anthropic.Anthropic().messages.create(
      model="claude-opus-4-6",
      system=<domain-expert system prompt>,
      messages=[{"role": "user", "content": <formatted input>}]
  )
      │
      ▼
  Claude API (Anthropic)
      │
      ▼
  JSON response → parsed → AnalysisResult / MigrationPlan / PolicyResult / ExecutiveReport
      │
      ▼
  Jinja2 / inline HTML template → rendered HTML response
```

## AgentOps Architecture (Module 5 — Agentic)

```
Browser/Client
      │
      │ POST /run {task, context}
      ▼
  FastAPI app.py → AgentOrchestrator.orchestrate()
      │
      │ messages.create(tools=[security_agent, cost_agent, migration_agent, reporting_agent])
      ▼
  Orchestrator Claude (claude-opus-4-6)
      │ stop_reason = "tool_use"
      ├──► security_agent tool call
      │         └── messages.create(system=SECURITY_PROMPT, ...)
      │                  └── Security Claude → result
      │
      ├──► cost_agent tool call
      │         └── messages.create(system=COST_PROMPT, ...)
      │                  └── FinOps Claude → result
      │
      ├──► migration_agent tool call → Migration Claude
      └──► reporting_agent tool call → Reporting Claude
      │
      │ tool_results fed back to Orchestrator
      ▼
  Orchestrator Claude final synthesis (stop_reason = "end_turn")
      │
      ▼
  OrchestrationResult {agent_calls, final_synthesis, execution_trace}
      │
      ▼
  HTML execution trace rendered to browser
```

## Claude API Usage Per Module

| Module | Model | max_tokens | Key Technique |
|--------|-------|-----------|---------------|
| CloudIQ | claude-opus-4-6 | 2048 | JSON-mode via system prompt |
| MigrationScout | claude-opus-4-6 | 2048 | Structured output parsing |
| PolicyGuard | claude-opus-4-6 | 2048 | Domain-expert system prompt |
| ExecutiveReport | claude-opus-4-6 | 2048 | Audience-aware generation |
| AgentOps | claude-opus-4-6 | 2048 | Tool use + agentic loop |

## Security

- API key loaded from environment (`ANTHROPIC_API_KEY`) — never hardcoded
- Input truncated at 8,000 characters before sending to Claude
- No user data stored — stateless per-request processing
- FastAPI input validation via `Form(...)` type annotations

## Running All Modules

```bash
# Terminal 1-5 (or use a process manager)
cd modules/cloudiq      && uvicorn app:app --port 8001 &
cd modules/migrationscout && uvicorn app:app --port 8002 &
cd modules/policyguard  && uvicorn app:app --port 8003 &
cd modules/executivereport && uvicorn app:app --port 8004 &
cd modules/agentops     && uvicorn app:app --port 8005 &
```

Or with a single script:

```bash
python scripts/run_all.py  # starts all 5 on ports 8001-8005
```
