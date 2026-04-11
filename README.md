# Enterprise AI Accelerator

**Production-ready AI modules for cloud migration, governance, and executive reporting — built on Claude**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Anthropic Claude](https://img.shields.io/badge/Claude-Opus_4.6-cc785c?style=flat-square)](https://anthropic.com)
[![License MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

A Claude-native platform demonstrating hands-on AI deployment across 5 enterprise use cases: architecture analysis, migration planning, IaC governance, executive reporting, and multi-agent orchestration. Each module is a working FastAPI service backed by real Claude API calls.

---

## Modules

| Module | Description | Key Feature |
|--------|-------------|-------------|
| [**CloudIQ**](modules/cloudiq/) | AI Architecture Analyzer | Security/cost/complexity scoring from AWS config, Terraform, or plain text |
| [**MigrationScout**](modules/migrationscout/) | Workload Migration Planner | Wave planning, 6R classification, dependency resolution from CSV/JSON inventory |
| [**PolicyGuard**](modules/policyguard/) | IaC Governance & Policy Checker | CRITICAL/HIGH/MEDIUM violations with exact Terraform remediation snippets |
| [**ExecutiveReport**](modules/executivereport/) | Board Deck Generator | Transforms raw metrics JSON into C-suite narrative with risks and recommendations |
| [**AgentOps**](modules/agentops/) | Multi-Agent Orchestration Monitor | Claude as orchestrator decomposing tasks across specialized sub-agents via tool use |

---

## Quick Start

```bash
git clone https://github.com/HunterSpence/enterprise-ai-accelerator
cd enterprise-ai-accelerator
pip install -r requirements.txt
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY

# Run any module
cd modules/cloudiq && uvicorn app:app --reload --port 8001
# Open http://localhost:8001
```

Each module runs independently. No shared state, no database, no auth setup required — just an Anthropic API key.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Enterprise AI Accelerator                    │
├───────────────┬────────────────┬─────────────┬─────────────────┤
│   CloudIQ     │ MigrationScout │ PolicyGuard │ ExecutiveReport │
│   :8001       │   :8002        │   :8003     │   :8004         │
├───────────────┴────────────────┴─────────────┴─────────────────┤
│                    AgentOps :8005                               │
│   Orchestrator Claude → tool calls → specialized sub-agents    │
└─────────────────────────────────────────────────────────────────┘
          │               │               │               │
          └───────────────┴───────────────┴───────────────┘
                                  │
                    Anthropic Claude API (claude-opus-4-6)
                    anthropic Python SDK · messages.create()
```

Each module follows the same pattern:

```
User Input (paste box)
      ↓
FastAPI app.py
      ↓
analyzer.py / planner.py / checker.py / generator.py / orchestrator.py
      ↓
client.messages.create(model="claude-opus-4-6", system=<expert prompt>, ...)
      ↓
Structured JSON response → parsed → HTML rendered
```

AgentOps adds tool use: Claude calls `security_agent`, `cost_agent`, `migration_agent`, and `reporting_agent` tools — each backed by its own Claude API call with a domain-expert system prompt.

---

## Module Details

### CloudIQ — AI Architecture Analyzer

**Input:** Paste AWS config JSON, Terraform HCL, or describe your architecture in plain text.

**Output:** Security score (0-100), cost waste estimate ($/month), migration complexity (1-10), CRITICAL/HIGH/MEDIUM findings, top 3 recommendations.

```bash
cd modules/cloudiq && uvicorn app:app --reload --port 8001
```

**Claude prompt strategy:** System prompt establishes Claude as a "senior AWS Solutions Architect with 15 years at Big 4 firms." Enforces JSON-only response with exact schema. Input truncated at 8K chars.

---

### MigrationScout — Workload Migration Planner

**Input:** CSV or JSON workload inventory (`name, type, description, dependencies, size_gb`).

**Output:** 3-wave migration roadmap, 6R classification per workload (Rehost/Replatform/Refactor/Rearchitect/Retire/Retain), effort estimates in weeks, risk register with mitigations.

```bash
cd modules/migrationscout && uvicorn app:app --reload --port 8002
```

---

### PolicyGuard — IaC Governance & Policy Checker

**Input:** Terraform HCL or CloudFormation YAML/JSON (paste or upload).

**Output:** Compliance score (0-100), violations with CRITICAL/HIGH/MEDIUM/LOW severity, exact resource names, Terraform fix code snippets per violation, estimated remediation time.

**Checks:** S3 public access, unencrypted storage, open security groups (SSH/RDP/DB ports), hardcoded secrets, missing MFA, no IMDSv2, required tag compliance.

```bash
cd modules/policyguard && uvicorn app:app --reload --port 8003
```

---

### ExecutiveReport — Board Deck Generator

**Input:** Raw metrics JSON (cloud spend, utilization %, incident counts, migration progress, security scores).

**Output:** Board-ready executive summary, key metrics formatted for non-technical stakeholders, risk register with business impact framing, specific board recommendations with investment and timeline.

```bash
cd modules/executivereport && uvicorn app:app --reload --port 8004
```

---

### AgentOps — Multi-Agent Orchestration Monitor

**Input:** A goal (text) and optional context (JSON or text).

**Output:** Full execution trace showing Claude decomposing the task, routing to 4 specialized agents via `tool_use`, and synthesizing their outputs into a final answer.

```bash
cd modules/agentops && uvicorn app:app --reload --port 8005
```

This is the most technically sophisticated module. It demonstrates:
- Claude's **tool use** capability for agent dispatching
- The **orchestrator → sub-agent → synthesis** pattern
- How to build **multi-agent systems** where each agent has a distinct domain
- Transparency into the agentic loop via the execution trace UI

```python
# Core pattern — orchestrator.py
response = client.messages.create(
    model="claude-opus-4-6",
    tools=[security_agent_tool, cost_agent_tool, migration_agent_tool, reporting_agent_tool],
    messages=[{"role": "user", "content": task}]
)
# When stop_reason == "tool_use", dispatch sub-agent and feed result back
```

---

## Why This Exists

Consulting firms charge $500K–$5M for cloud migration assessments that involve weeks of manual workshops, architecture reviews, and report writing. The analytical work — security scanning, workload classification, compliance checking, executive reporting — is increasingly automatable with AI.

This platform demonstrates what hands-on AI deployment looks like versus slide-deck consulting. It's built with the Anthropic Python SDK, uses Claude's tool use for agentic patterns, and is structured as production-ready FastAPI services — not Jupyter notebooks.

Relevant context:
- **PwC** is a confirmed Anthropic reseller
- **Cognizant** deployed Claude to 350K associates
- **BCG X** and **McKinsey QuantumBlack** are building AI-native delivery models

The question for consulting firms isn't whether to use AI — it's who on their team actually understands how to deploy it.

---

## Contact

**Hunter Spence** · AI Deployment Specialist  
hunter@vantaweb.dev  
[github.com/HunterSpence](https://github.com/HunterSpence)
