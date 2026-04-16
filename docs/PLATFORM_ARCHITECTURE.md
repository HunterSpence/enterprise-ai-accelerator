# Platform Architecture — Enterprise AI Accelerator

This document describes the full platform architecture as of v0.2.0 (April 2026). For the EU AI Act-specific compliance story, see [OPUS_4_7_UPGRADE.md](OPUS_4_7_UPGRADE.md).

---

## System Overview

Enterprise AI Accelerator is a unified cloud governance platform. It has five layers:

1. **Entry points** — CLI, Python SDK, MCP server (Claude Code / Desktop), webhook receivers
2. **Core optimization layer** — model routing, result caching, batch coalescing, OTEL, Prometheus
3. **Capability modules** — the seven functional domains
4. **Cross-cutting services** — risk aggregation, executive chat, audit trail
5. **Integration + observability** — outbound adapters, traces, dashboards

---

## Full Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                               Entry Points                                        │
│                                                                                   │
│   python -m app_portfolio.cli .        (CLI)                                     │
│   python -m iac_security <path>        (CLI)                                     │
│   python mcp_server.py                 (MCP — 19 tools, Claude Code/Desktop)     │
│   from core.ai_client import AIClient  (Python SDK)                              │
│   POST /findings webhook               (inbound from CI/CD)                      │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────────┐
│                         core/ — Anthropic Optimization Layer                      │
│                                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  ┌───────────────────┐ │
│  │ AIClient     │  │ ModelRouter  │  │ ResultCache      │  │ BatchCoalescer    │ │
│  │ (single      │  │ (complexity- │  │ (SQLite TTL —    │  │ (auto-queue →     │ │
│  │  Anthropic   │  │  based Opus/ │  │  identical reqs  │  │  Batch API,       │ │
│  │  wrapper)    │  │  Sonnet/     │  │  cost nothing)   │  │  50% discount)    │ │
│  └──────┬───────┘  │  Haiku)      │  └─────────────────┘  └───────────────────┘ │
│         │          └──────────────┘                                               │
│  ┌──────▼───────┐  ┌──────────────┐  ┌─────────────────┐  ┌───────────────────┐ │
│  │ _hooks.py    │  │ StreamHandler│  │ FilesAPIClient   │  │ InterleavedThink  │ │
│  │ (OTEL spans  │  │ (SSE)        │  │ (doc upload +    │  │ ingLoop           │ │
│  │  on every    │  │              │  │  reuse)          │  │ (thinking+tools)  │ │
│  │  API call)   │  └──────────────┘  └─────────────────┘  └───────────────────┘ │
│         │                                                                         │
│  ┌──────▼─────────────────────────────────────────────────────────────────────┐  │
│  │ telemetry.py · prometheus_exporter.py · logging.py · cost_estimator.py     │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
┌─────────▼──────────┐  ┌──────────▼───────────┐  ┌────────▼─────────────────────┐
│  cloud_iq/         │  │  app_portfolio/      │  │  iac_security/               │
│  adapters/         │  │                      │  │                              │
│  AWSAdapter        │  │  LanguageDetector    │  │  TerraformParser             │
│  AzureAdapter      │  │  DependencyScanner   │  │  PulumiParser                │
│  GCPAdapter        │  │  CVEScanner (OSV)    │  │  PolicyEngine (20 policies)  │
│  KubernetesAdapter │  │  ContainerScore      │  │  SBOMGenerator (CycloneDX)   │
│  UnifiedDiscovery  │  │  CIMaturityScore     │  │  OSVScanner                  │
│  .auto()           │  │  TestCoverageScanner │  │  DriftDetector               │
│                    │  │  SixRScorer (Opus47) │  │  SARIFExporter               │
└────────────────────┘  └──────────────────────┘  └──────────────────────────────┘

┌─────────────────────┐  ┌─────────────────────┐  ┌───────────────────────────────┐
│  finops_intelligence│  │  migration_scout/   │  │  policy_guard/                │
│                     │  │                     │  │                               │
│  CURIngestor        │  │  WorkloadAssessor   │  │  ComplianceScanner            │
│  RISPOptimizer      │  │  DependencyMapper   │  │  BiasDetector                 │
│  RightSizer         │  │  WavePlanner        │  │  SARIFExporter                │
│  CarbonTracker      │  │  TCOCalculator      │  │  IncidentResponse             │
│  SavingsReporter    │  │  BatchClassifier    │  │  ThinkingAudit                │
│  AnomalyDetector    │  │  ThinkingAudit      │  │                               │
│  FocusExporter      │  │                     │  │                               │
└─────────────────────┘  └─────────────────────┘  └───────────────────────────────┘
          │                        │                        │
          └────────────────────────▼────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────────┐
│                        agent_ops/ — Multi-Agent Orchestrator                      │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │  CoordinatorAgent (Opus 4.7)                                                │ │
│  │  Decomposes task → routes to workers → evaluates results → asks follow-ups  │ │
│  └─────────────────────────────┬───────────────────────────────────────────────┘ │
│            ┌────────────────────┼────────────────────┐                           │
│  ┌─────────▼──────┐  ┌─────────▼──────┐  ┌──────────▼───────┐                  │
│  │ WorkerAgent    │  │ WorkerAgent    │  │ WorkerAgent      │  (Haiku 4.5)       │
│  │ (module task)  │  │ (module task)  │  │ (module task)    │                    │
│  └────────────────┘  └────────────────┘  └──────────────────┘                   │
│            └────────────────────┬────────────────────┘                           │
│  ┌─────────────────────────────▼─────────────────────────────────────────────┐  │
│  │  ReporterAgent (Sonnet 4.6) — synthesizes worker outputs into exec prose   │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
┌─────────▼──────────┐  ┌──────────▼───────────┐  ┌────────▼─────────────────────┐
│  ai_audit_trail/   │  │  executive_chat/     │  │  compliance_citations/       │
│  MerkleChain       │  │  ExecutiveChat       │  │  EvidenceLibrary             │
│  EUAIActLogger     │  │  (1M-token context)  │  │  CitationsEngine             │
│  NISTRMFScorer     │  │  BriefingLoader      │  │  (character-range citations) │
│  IncidentManager   │  │  (1-hour cache)      │  │  (CIS/HIPAA/SOC2/EU AI Act)  │
│  SARIFExporter     │  │                      │  │                              │
└────────────────────┘  └──────────────────────┘  └──────────────────────────────┘
          │                        │                        │
          └────────────────────────▼────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  risk_aggregator.py          │
                    │  Weighted 0–100 score        │
                    │  Security      35%           │
                    │  FinOps        25%           │
                    │  Migration     20%           │
                    │  AI Governance 20%           │
                    └──────────────┬──────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
┌─────────▼──────────┐  ┌──────────▼───────────┐  ┌────────▼─────────────────────┐
│  integrations/     │  │  observability/      │  │  GitHub Security tab         │
│  FindingRouter     │  │  OTEL Collector      │  │  (SARIF 2.1.0 upload)        │
│  WebhookDispatcher │  │  Prometheus          │  │                              │
│  Slack · Jira      │  │  Grafana dashboards  │  │  GitHub PR check-runs        │
│  ServiceNow        │  │  Jaeger              │  │  (inline annotations)        │
│  GitHub · Teams    │  │  structlog JSON      │  │                              │
│  PagerDuty · SMTP  │  │                      │  │                              │
└────────────────────┘  └──────────────────────┘  └──────────────────────────────┘
```

---

## Data Flow

### Standard pipeline run

1. Entry point (CLI or MCP tool call) triggers a module
2. Module calls `core.AIClient` — `ModelRouter` selects model tier; `ResultCache` checks for cache hit
3. On cache miss: API call is made; OTEL span created; Prometheus metrics incremented; cost estimated
4. Module produces structured findings
5. `FindingRouter` in `integrations/` routes findings to configured adapters (Slack, Jira, etc.)
6. `ai_audit_trail` logs the decision with SHA-256 Merkle chain
7. SARIF exporter writes findings; GitHub Actions uploads to Security tab

### Executive briefing flow

1. All module outputs assembled into a `BriefingDocument`
2. `BriefingLoader` serializes to ~200k tokens of structured text
3. `ExecutiveChat.load(briefing)` uploads to Opus 4.7 with 1-hour prompt cache
4. First `ask()` call: full input cost (~$3–5); subsequent calls within 60 min: ~10% of that
5. Each answer includes structured finding references for auditability

### Batch scoring flow

1. Large inventory (e.g. 1,000 workloads) arrives at `BatchClassifier` or `BatchCoalescer`
2. Requests coalesce into Anthropic Batch API submissions (up to 10k per batch)
3. Results polled with exponential backoff; delivered to caller within 24 hours
4. Each result schema-validated via native tool use

---

## Model Tier Assignment

| Tier | Model | Use cases |
|---|---|---|
| High | claude-opus-4-7-20250514 | Coordination, extended thinking, executive chat, high-stakes compliance audits, interleaved thinking loops |
| Medium | claude-sonnet-4-6-20241022 | Report synthesis, moderate-complexity analysis, IaC policy explanations |
| Low | claude-haiku-4-5-20241022 | High-volume worker tasks, simple classification, data extraction, CVE triage |

`ModelRouter.select(task, token_estimate)` returns a model string. Override by passing `model=` directly to `AIClient.complete()`.

---

## Deployment Topology

The platform is designed for single-node deployment (Docker Compose or bare Python). There is no multi-node or distributed architecture documented yet.

```
Host machine
├── python mcp_server.py          (port 8080 — MCP endpoint)
├── python -m finops_intelligence (port 8001 — optional FastAPI)
├── python -m policy_guard        (port 8003 — optional FastAPI)
└── docker compose -f observability/docker-compose.obs.yaml up
    ├── prometheus:9090
    ├── grafana:3000
    ├── jaeger:16686
    └── otel-collector:4317/4318
```

Module FastAPI servers are optional. All modules also run as CLI tools or Python library imports.

---

## Key Design Decisions

**Single LLM provider.** All AI calls go through Anthropic. This simplifies the audit trail (one vendor, one model naming convention, one pricing table) and enables prompt caching across all modules via a shared `AIClient`.

**SQLite for the audit chain.** SHA-256 Merkle chain on SQLite is sufficient for MVP and single-node deployments. For production-scale multi-writer deployments, this should be replaced with a write-ahead log on a durable store (Postgres with WAL, or S3 + DynamoDB for the index).

**SARIF as the compliance export format.** SARIF 2.1.0 is supported natively by GitHub, GitLab, Azure DevOps, and most SIEM tools. Using SARIF means compliance findings integrate with existing developer workflows without custom tooling.

**Adapters over a message bus.** The `integrations/` module uses direct webhook calls rather than a message bus (Kafka, SQS). This keeps the deployment simple and avoids paid infrastructure. The circuit-breaker + retry on `WebhookDispatcher` handles transient failures. A message bus would be appropriate if finding volume exceeded ~100/second.
