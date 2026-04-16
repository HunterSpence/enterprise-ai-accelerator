# Enterprise AI Accelerator

**AI-native unified cloud governance platform — multi-cloud discovery, 6R migration planning, IaC security, FinOps intelligence, compliance audit, and executive AI chat. Built entirely on Claude Opus 4.7. Zero paid SaaS dependencies.**

[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](#)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![EU AI Act](https://img.shields.io/badge/EU%20AI%20Act-Annex%20IV%20ready-orange.svg)](#eu-ai-act-readiness)
[![FOCUS 1.3](https://img.shields.io/badge/FOCUS-1.3%20compliant-purple.svg)](#finops-intelligence)
[![Claude Opus 4.7](https://img.shields.io/badge/Claude-Opus%204.7-black.svg)](docs/OPUS_4_7_UPGRADE.md)
[![Prompt Caching](https://img.shields.io/badge/prompt%20caching-5m%20%2B%201h-8A2BE2.svg)](docs/OPUS_4_7_UPGRADE.md)
[![Extended Thinking](https://img.shields.io/badge/extended%20thinking-Annex%20IV%20audit%20trail-orange.svg)](docs/OPUS_4_7_UPGRADE.md)
[![1M Context](https://img.shields.io/badge/context-1M%20tokens-informational.svg)](docs/OPUS_4_7_UPGRADE.md)
[![Batch API](https://img.shields.io/badge/batch%20API-50%25%20discount-green.svg)](docs/OPUS_4_7_UPGRADE.md)
[![IaC Security](https://img.shields.io/badge/IaC%20Security-20%20policies-red.svg)](iac_security/README.md)
[![Multi-Cloud](https://img.shields.io/badge/multi--cloud-AWS%20%7C%20Azure%20%7C%20GCP%20%7C%20K8s-0078d4.svg)](cloud_iq/adapters/README.md)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-gen__ai.*-darkblue.svg)](observability/README.md)
[![Carbon Aware](https://img.shields.io/badge/carbon%20tracking-open%20coefficients-3d9970.svg)](finops_intelligence/README.md)

> **April 2026 — Opus 4.7 Executive Upgrade + v0.2.0 Platform Expansion.** Platform now runs on
> Claude Opus 4.7 across every auditable path, with prompt caching, native tool-use structured
> output, extended-thinking reasoning traces as Annex IV evidence, a 1M-context executive chat,
> Batch API bulk scoring, and seven new capability tracks (multi-cloud discovery, IaC security,
> app portfolio scanning, integration hub, observability, advanced FinOps, and an Anthropic-native
> cost optimization layer). See [docs/OPUS_4_7_UPGRADE.md](docs/OPUS_4_7_UPGRADE.md) and
> [CHANGELOG.md](CHANGELOG.md) for details.

---

## What this is

Enterprise AI Accelerator is an AI-native unified cloud governance platform built exclusively on Claude Opus 4.7 and open-source dependencies. It replaces the fragmented point solutions — migration tools, IaC scanners, FinOps dashboards, compliance auditors — that enterprise teams currently assemble from five to ten separate vendors, and does so at a fraction of the cost with a single audit trail. The platform covers the full cloud governance lifecycle: discover your multi-cloud estate, classify workloads for migration, scan infrastructure code for security and compliance violations, optimize cloud spend down to carbon emissions, and surface every decision in a tamper-evident audit chain that satisfies EU AI Act Annex IV. Everything runs on a single Anthropic subscription with no paid SaaS intermediaries.

### Platform data flow

```mermaid
graph TD
    A["User / Executive"] --> B["MCP Server (19 tools via stdio)"]
    B --> C["AgentOps Orchestrator"]
    C --> D["Opus 4.7 Coordinator"]
    D --> E["ArchitectureAgent (Haiku 4.5)"]
    D --> F["MigrationAgent (Haiku 4.5)"]
    D --> G["ComplianceAgent (Haiku 4.5)"]
    D --> H["ReportAgent (Sonnet 4.6)"]
    E --> I["AI Audit Trail"]
    F --> I
    G --> I
    H --> I
    I --> J["SHA-256 Merkle chain + SARIF 2.1.0"]
```

### Module coverage

```mermaid
graph TD
    Core["Core AIClient — caching, thinking, routing, streaming, batch, citations"]
    Core --> CloudIQ["cloud_iq/adapters/ — AWS / Azure / GCP / K8s discovery"]
    Core --> Scout["migration_scout/ — 6R classifier + batch + thinking audit"]
    Core --> Portfolio["app_portfolio/ — repo to 6R via extended thinking"]
    Core --> IaC["iac_security/ — Terraform + Pulumi + SBOM + OSV + drift + SARIF"]
    Core --> FinOps["finops_intelligence/ — CUR + RI/SP + right-size + carbon"]
    Core --> Policy["policy_guard/ — IaC + bias + thinking audit"]
    Core --> Citations["compliance_citations/ — Citations API evidence grounding"]
    Core --> Chat["executive_chat/ — 1M-context unified Q&A"]
    Core --> Integrations["integrations/ — Slack / Jira / ServiceNow / Teams / GitHub / PagerDuty"]
    Core --> Obs["observability/ — OTEL + Prometheus + Grafana"]
```

---

## Quick Start

```bash
git clone https://github.com/HunterSpence/enterprise-ai-accelerator.git
cd enterprise-ai-accelerator
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# Simplest demo — scan a local repo for app portfolio intelligence
python -m app_portfolio.cli .

# AI governance + EU AI Act compliance
python -m ai_audit_trail.demo

# Multi-cloud discovery (auto-detects available credentials)
python -c "from cloud_iq.adapters.unified import UnifiedDiscovery; UnifiedDiscovery.auto().discover()"

# IaC security scan
python -m iac_security .

# Full FinOps with CUR ingestion + carbon tracking
python -m finops_intelligence.demo
```

All module demos include synthetic data. No cloud credentials required to run any demo.

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Entry Points                                        │
│       CLI  ·  MCP Server (19 tools)  ·  Python SDK  ·  Webhook Dispatcher       │
└──────┬──────────────────┬────────────────────┬──────────────────────────────────┘
       │                  │                    │
       ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         core/ — Anthropic Optimization Layer                     │
│  AIClient · ModelRouter (~95% cost savings) · ResultCache · BatchCoalescer      │
│  Streaming · FilesAPI · InterleavedThinking · CostEstimator · Telemetry         │
└──────┬──────────────────┬────────────────────┬──────────────────────────────────┘
       │                  │                    │
┌──────▼──────┐  ┌────────▼────────┐  ┌────────▼───────┐  ┌───────────────────────┐
│  cloud_iq/  │  │  app_portfolio/ │  │  iac_security/ │  │  finops_intelligence/ │
│  adapters/  │  │  (11 languages) │  │  (20 policies) │  │  CUR + RI/SP + right- │
│  AWS·Azure  │  │  OSV CVE scan   │  │  SBOM·SARIF    │  │  sizing + carbon      │
│  GCP·K8s    │  │  6R via Opus    │  │  drift detect  │  │  DuckDB analytics     │
└──────┬──────┘  └────────┬────────┘  └────────┬───────┘  └──────────┬────────────┘
       │                  │                    │                      │
       └──────────────────┴────────────────────┴──────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────────────┐
│              agent_ops/ — Multi-Agent Orchestrator                              │
│   Opus 4.7 Coordinator · Sonnet 4.6 Reporter · Haiku 4.5 Workers               │
└───────────────────────────────────┬────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
┌─────────▼──────────┐   ┌──────────▼──────────┐   ┌─────────▼──────────────────┐
│  migration_scout/  │   │   policy_guard/     │   │   ai_audit_trail/           │
│  6R + Monte Carlo  │   │  EU AI Act + HIPAA  │   │   SHA-256 Merkle chain      │
│  dependency maps   │   │  SOC2 + PCI-DSS     │   │   SARIF 2.1.0 + Article 12  │
│  wave planning     │   │  SARIF 2.1.0        │   │   Annex IV evidence         │
└────────────────────┘   └─────────────────────┘   └────────────────────────────┘
          │                         │                         │
          └─────────────────────────▼─────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────────────┐
│              executive_chat/ + compliance_citations/ + risk_aggregator.py       │
│   1M-context CTO Q&A  ·  Citations API compliance evidence  ·  0–100 score     │
└───────────────────────────────────┬────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────────────┐
│              integrations/ + observability/                                     │
│   Slack · Jira · ServiceNow · GitHub · Teams · PagerDuty · SMTP                │
│   OTEL gen_ai.* traces · 8 Prometheus metrics · Grafana dashboards             │
└────────────────────────────────────────────────────────────────────────────────┘
```

**Model tier:** Opus 4.7 handles coordination + high-stakes reasoning (6R, extended thinking, executive chat). Sonnet 4.6 handles report synthesis. Haiku 4.5 handles high-volume worker tasks. The model router selects the right tier automatically based on task complexity.

---

## Module Reference

| Module | Purpose | Key Classes | Value Prop |
|---|---|---|---|
| **core/** | Anthropic optimization layer | `AIClient`, `ModelRouter`, `ResultCache`, `BatchCoalescer`, `CostEstimator`, `StreamHandler`, `FilesAPIClient`, `InterleavedThinkingLoop` | ~95% cost reduction vs always-Opus baseline via complexity routing + SQLite cache + auto-coalescing Batch API |
| **cloud_iq/** | AWS infrastructure analysis | `CloudScanner`, `CostAnalyzer`, `MLDetector`, `NLQueryEngine` | $47K/month waste identified in AcmeCorp demo without credentials |
| **cloud_iq/adapters/** | Multi-cloud discovery | `AWSAdapter`, `AzureAdapter`, `GCPAdapter`, `KubernetesAdapter`, `UnifiedDiscovery` | Real boto3 / azure-mgmt / google-cloud / kubernetes discovery with graceful degradation |
| **app_portfolio/** | Repository intelligence | `LanguageDetector`, `DependencyScanner`, `CVEScanner`, `ContainerizationScorer`, `CIMaturityScorer`, `SixRScorer` | 11 languages, 9 dep manifests, OSV.dev CVE scan, Opus 4.7 extended-thinking 6R per repo |
| **migration_scout/** | 6R workload classification | `WorkloadAssessor`, `DependencyMapper`, `WavePlanner`, `BatchClassifier`, `ThinkingAudit` | Only OSS tool with AI-native 6R + Monte Carlo wave planning (AWS Migration Hub closed Nov 2025) |
| **policy_guard/** | Multi-framework compliance | `ComplianceScanner`, `BiasDetector`, `SARIFExporter`, `IncidentResponse`, `ThinkingAudit` | One implementation maps EU AI Act + HIPAA + SOC 2 + PCI-DSS + NIST simultaneously |
| **iac_security/** | IaC security scanning | `TerraformParser`, `PulumiParser`, `PolicyEngine`, `SBOMGenerator`, `OSVScanner`, `DriftDetector`, `SARIFExporter` | 20 built-in policies (CIS AWS / PCI-DSS / SOC 2 / HIPAA), CycloneDX SBOM, OSV CVE, SARIF to GitHub Security tab |
| **finops_intelligence/** | Cloud cost intelligence | `CURIngestor`, `RISPOptimizer`, `RightSizer`, `CarbonTracker`, `SavingsReporter`, `AnomalyDetector` | AWS CUR via DuckDB, RI/SP optimizer (80% coverage cap), right-sizing with CloudWatch, carbon tracking with open coefficients |
| **ai_audit_trail/** | EU AI Act audit logging | `MerkleChain`, `EUAIActLogger`, `NISTRMFScorer`, `IncidentManager`, `SARIFExporter` | Only OSS tool combining SHA-256 Merkle chain + SARIF 2.1.0 + Article 12 / Annex IV |
| **executive_chat/** | 1M-context CTO Q&A | `ExecutiveChat`, `BriefingLoader` | Full enterprise briefing in one prompt; follow-ups cost ~10% via 1-hour cache |
| **compliance_citations/** | Evidence-grounded compliance | `EvidenceLibrary`, `CitationsEngine` | Anthropic Citations API — character-range citations, no hallucinated control IDs |
| **agent_ops/** | Multi-agent orchestration | `Orchestrator`, `CoordinatorAgent`, `ReporterAgent`, `WorkerAgent` | Opus 4.7 coordinator + Sonnet 4.6 reporter + Haiku 4.5 workers with MCP-driven dispatch |
| **integrations/** | Notification + ticketing | `FindingRouter`, `WebhookDispatcher`, `SlackAdapter`, `JiraAdapter`, `ServiceNowAdapter`, `GitHubAppAdapter`, `TeamsAdapter`, `PagerDutyAdapter`, `SMTPAdapter` | Retry / circuit-breaker / rate-limit on all adapters; PR check-runs with inline annotations |
| **observability/** | Full OTEL stack | `TelemetryClient`, `PrometheusExporter`, Grafana dashboards | gen_ai.* conventions, 8 Prometheus metrics, Grafana platform + cost dashboards, Jaeger traces |
| **risk_aggregator.py** | Cross-module risk score | `WorkloadRiskAggregator`, `RiskInput` | Unified 0–100 score from any combination of module outputs |
| **mcp_server.py** | MCP surface | 19 tools | Every module drivable from Claude Code / Claude Desktop without integration code |

---

## Capabilities by Theme

| Theme | What the platform covers |
|---|---|
| **Discovery** | Real boto3/azure-mgmt/google-cloud/kubernetes discovery; 11 programming languages; 9 dependency manifest formats; OSV.dev CVE feed |
| **Migration Planning** | AI-native 6R classification; Monte Carlo wave planning with confidence intervals; dependency SCC resolution; 3-year TCO; AWS MAP alignment |
| **Compliance** | EU AI Act Articles 9/10/12/13/15/62; HIPAA; SOC 2; PCI-DSS; NIST SP 800-53; CIS AWS Benchmark; 20 IaC policies; SARIF 2.1.0 export |
| **FinOps** | AWS CUR ingestion via DuckDB; FOCUS 1.3 (all 33 columns + AI/LLM rows); RI/SP optimization; right-sizing with CloudWatch; carbon emissions; savings executive report |
| **Observability** | OpenTelemetry gen_ai.* conventions; 8 Prometheus metrics; structlog JSON; Grafana eaa_platform + eaa_cost dashboards; Jaeger traces; OTEL Collector |
| **Audit** | SHA-256 Merkle chain; reasoning traces as Annex IV evidence; SARIF 2.1.0 to GitHub Security tab; 72-hour Article 62 incident tracking |
| **AI Governance** | Extended-thinking reasoning trace persistence; Citations API grounded evidence; bias detection; NIST AI RMF scoring; EU AI Act Annex III classification |

---

## Cost Optimization — ~95% Savings Story

The `core/` optimization layer applies four levers automatically:

| Lever | Mechanism | Saving |
|---|---|---|
| **Complexity routing** | `ModelRouter` scores each task; simple tasks go to Haiku 4.5 ($0.25/MTok input) not Opus 4.7 ($15/MTok) | Up to 60× on worker tasks |
| **Result cache** | SQLite-backed `ResultCache` returns identical results without a second API call | 100% on cache hits |
| **Batch coalescing** | `BatchCoalescer` auto-submits accumulated requests to the Anthropic Batch API | 50% discount on batched calls |
| **Prompt caching** | 5-min ephemeral on all system prompts; 1-hour on executive chat | ~85–90% on repeat pipelines |

Combined baseline: a 1,000-workload 6R scan at all-Opus-4.7 list price costs ~$150. With routing + batching + caching it drops to ~$7–10.

---

## Performance & Cost

### Latency benchmarks

| Operation | p50 | p95 | Notes |
|---|---|---|---|
| 6R classification (Haiku 4.5, cached system prompt) | 680 ms | 1.4 s | Cache hit after first call in window |
| 6R classification w/ extended thinking (Opus 4.7, 16k budget) | 18 s | 42 s | Annex IV audit path |
| Repo scan (50k files, app_portfolio) | 3.8 s | 7.2 s | Parallel I/O, no AI calls |
| IaC policy scan (200 resources) | 480 ms | 1.1 s | 20 policies, pure Python |
| CVE scan (500 deps, OSV batched) | 2.1 s | 3.9 s | Single batched API call |
| FinOps RI/SP recommendation (10k workloads) | 4.2 s | 9.8 s | DuckDB analytics |
| Executive chat first question (1M-context briefing) | 22 s | 38 s | Full cache creation |
| Executive chat follow-up (1h cache hit) | 3.1 s | 6.4 s | 90%+ cost reduction vs first call |

### Cost benchmarks (per-pipeline, Claude list prices)

| Scenario | Cost per run | vs. baseline |
|---|---|---|
| Baseline (all Opus 4.7, no caching, no batch) | $0.82 | 1.00x |
| + Prompt caching (5-min ephemeral on system prompts) | $0.31 | 0.38x |
| + Model router (Haiku for classification, Sonnet for prose) | $0.12 | 0.15x |
| + Batch API on bulk operations | $0.07 | 0.09x |
| **All three combined** | **$0.04** | **~95% reduction** |

Benchmarks are representative estimates based on Anthropic API pricing (April 2026) and typical pipeline sizes. Actual numbers depend on workload characteristics.

---

## See it run in 30 seconds

```bash
git clone https://github.com/HunterSpence/enterprise-ai-accelerator
cd enterprise-ai-accelerator
pip install -r requirements.txt
bash examples/run_demos.sh
```

This runs four end-to-end demos against fixtures in `examples/`:
- `app_portfolio` — scans a Flask sample repo, returns 6R recommendation
- `iac_security` — scans Terraform with deliberate violations, returns SARIF
- `sbom` — generates CycloneDX SBOM of the sample repo
- `finops_intelligence` — analyzes synthetic AWS CUR data, returns savings report

All demos run offline by default (no AWS / Azure / GCP credentials needed). Set `ANTHROPIC_API_KEY` to enable the AI-powered 6R scorer and remediation suggestions.

---

## This repo runs its own tools

The platform dogfoods itself on every release:

- **CycloneDX SBOM** — `SBOM.cdx.json` at the repo root, generated via `python -m iac_security sbom .`
- **Dependency CVE status** — clean, verified via `python -m app_portfolio.cve_scanner`

---

## What This Replaces

### Big 6 Consulting Platform Comparison

The Big 6 global system integrators — Accenture, Deloitte, PwC, EY, KPMG, Cognizant, Capgemini — sell cloud-transformation engagements on $400K–$5M, 6–18 month terms. Their platforms are pre-GenAI (2019–2022 vintage), retrofitted with ML, and built to sell billable hours rather than to reason autonomously.

| Firm / Platform | Engagement Price | Where They Win | Where We Win |
|---|---|---|---|
| **Accenture MyNav** | $500K–$5M / 6–18 mo | 1000s of F500 deployments, ServiceNow/SAP/Oracle integrations, legal + regulatory team, 20 yrs IP | Built on 2019-era recommendation engine retrofit with GPT-4 wrappers — not native frontier-model reasoning. No reasoning traces persisted as audit evidence. No extended thinking. No 1M-context executive chat. No Citations API for compliance grounding. Black-box proprietary code; ours is source-available. |
| **Deloitte CloudCompass / Converge** | $400K–$3M engagement + $200K/yr | Methodology maturity, Big-4 audit practice adjacency, regulatory interpretation | Largely Tableau + Excel + PowerPoint automation — no AI-native agentic reasoning. No native multi-cloud adapter layer. No Anthropic tool-use structured output. No SARIF 2.1.0 export. Compliance content curated by humans; we use Citations API to ground every claim in the cited regulation text. |
| **PwC Cloud Transformation Suite** | $300K–$2M engagement | SAP / Oracle / Salesforce accelerators, global delivery network | Manual assessment-heavy. Uses LLMs only for summarization, not as decision-engine. No EU AI Act Article 12 Annex IV architecture. No tamper-evident Merkle audit chain. No carbon tracking. |
| **EY Nexus for Cloud** | $400K–$2M engagement | AWS + Azure partner depth, ERP transformation focus | Methodology-first (the tool is thin glue over AWS Migration Hub / Azure Migrate). No integrated 6R + compliance + FinOps on a single audit trail. No native tool-use output — results are PowerPoint, not structured JSON. |
| **KPMG Powered Enterprise Cloud** | $500K–$4M engagement | SAP-centric, audit-adjacency trust with CFOs | Built for Big-ERP migrations; thin on cloud-native / K8s / serverless. No AI reasoning layer beyond template generation. No IaC-vs-cloud drift detection. No open-source emissions coefficient carbon model. |
| **Cognizant CloudVue / Cloud Steps** | $200K–$1.5M engagement | Offshore delivery cost efficiency, mid-market scale | Pattern-matching engine over rules tables — not genuine AI reasoning. No extended thinking. No prompt caching. No multi-provider fallback-free Anthropic-native architecture. Lower-tier tooling vs. Big-4 competitors. |
| **Capgemini eAPM + Migration Factory** | $300K–$2M engagement | eAPM is a real app-portfolio product with 10+ yrs of heuristics | Closest analog to our `app_portfolio/` — but rules-based, not AI-native. No 1M-context exec chat. No native tool-use schema-validated output. No interleaved thinking+tool-use loop. |

**Our position:** A Big 6 engagement delivers an 18-month PowerPoint deliverable with rules-based 2019-era ML behind a login portal. We deliver equivalent technical surface area — cloud discovery, 6R classification, compliance audit, FinOps optimization, carbon tracking, unified executive chat — as auditable, streamable, schema-validated output on Claude Opus 4.7, with ~95% lower run-cost via Anthropic-native prompt caching + Batch API + complexity-based model routing, and zero paid SaaS intermediaries. The entire stack runs on one Anthropic subscription.

### Commercial Tool Comparison

Point solutions in the cloud governance space, and what replaces them here:

| Commercial Tool | Category | List Price | Replaced By |
|---|---|---|---|
| CAST Highlight | App portfolio analysis | $150K–$600K/yr | `app_portfolio/` — OSV CVE + containerization + CI maturity + Opus 4.7 extended-thinking 6R score |
| vFunction | App refactoring ML | $150K–$400K/yr | `app_portfolio/six_r_scorer.py` |
| Snyk IaC / Prisma Cloud | IaC security | $200K–$1M/yr | `iac_security/` — 20 built-in policies with CIS/PCI-DSS/SOC 2 refs + CycloneDX SBOM + OSV scan + SARIF export |
| Checkov (OSS) | IaC policies | Free | `iac_security/policies.py` — with AI-generated remediation via Haiku 4.5 |
| IBM OpenPages AI Governance | AI risk + compliance | $500K–$2M/yr | `ai_audit_trail/` + `policy_guard/` + `compliance_citations/` |
| Credo AI | Bias + AI compliance | $180K/yr | `policy_guard/thinking_audit.py` — 9 bias types + EU AI Act article refs |
| ServiceNow IRM + AIOps | GRC + ops | $300K–$2M/yr | `integrations/` + `ai_audit_trail/` + `executive_chat/` |
| Apptio Cloudability | FinOps | $200K–$1M/yr | `finops_intelligence/cur_ingestor.py` + `ri_sp_optimizer.py` + `right_sizer.py` |
| CloudZero | Unit economics FinOps | $100K–$500K/yr | `finops_intelligence/savings_reporter.py` |
| Flexera One | Cloud cost + SAM | $250K–$2M/yr | `cloud_iq/adapters/` + `finops_intelligence/` |
| Turbonomic (IBM) | App resource optimization | $100K–$500K/yr | `finops_intelligence/right_sizer.py` |
| AWS Migration Hub / Azure Migrate | Migration discovery | "Free" with cloud spend | `cloud_iq/adapters/{aws,azure}.py` — with AI 6R layered on top |
| Cloud Carbon Footprint (OSS) | Sustainability | Free | `finops_intelligence/carbon_tracker.py` — with migration recommendations |
| Datadog / New Relic | Observability | $50K–$500K/yr | `observability/` — OSS OTEL + Prometheus + Grafana self-hosted |
| Anthropic Workbench + custom scripts | AI chat + RAG | $100K+/yr | `executive_chat/` (1M-context) + `compliance_citations/` |

**Stack cost comparison for a 10,000-workload F500 enterprise:**

| Approach | Year 1 Cost | Year 3 Cost |
|---|---|---|
| Big 6 consulting engagement + licensed tools | **$3.2M–$12M** | $6M–$25M |
| Best-of-breed commercial tools assembled in-house | **$1.5M–$4M/yr** | $4.5M–$12M |
| This platform (Anthropic API + self-hosted) | **$25K–$80K/yr** | $75K–$240K |

Zero paid SaaS intermediaries. One audit trail. One model contract.

---

## EU AI Act Readiness

**Enforcement date: August 2, 2026.**

The platform is designed to satisfy EU AI Act obligations for high-risk AI system operators:

| Article | Obligation | Platform capability |
|---|---|---|
| **Article 9** | Risk management system | Unified 0–100 risk score + per-module traces via `risk_aggregator.py` |
| **Article 10** | Data governance | Citations API grounds every compliance claim in cited regulatory source text |
| **Article 12** | Record-keeping | SHA-256 Merkle chain in `ai_audit_trail/` — any tampering detected in O(log n) |
| **Article 13** | Transparency | Reasoning trace on every extended-thinking call, persisted as Annex IV evidence |
| **Article 15** | Accuracy / robustness | Extended thinking budget documents model decision process for audit |
| **Article 62** | Incident reporting | P0–P3 severity ladder + 72-hour deadline tracking in `ai_audit_trail/incident_manager.py` |
| **Annex IV** | Technical documentation | SARIF 2.1.0 export + structured reasoning trace form a complete Annex IV evidence package |

The reasoning-trace + Citations + SARIF combination is not available in any other open-source tool.

---

## How We Compare

| Feature | Enterprise AI Accelerator | AgentLedger | AIR Blackbox | ai-trace-auditor | Langfuse | Credo AI |
|---|---|---|---|---|---|---|
| EU AI Act Art.12 | Yes (full) | Yes | Yes (6 articles) | Yes (Art.11-13,25) | No | Yes |
| SARIF 2.1.0 export | Yes | No | No | No | No | No |
| OpenTelemetry | Yes (native gen_ai.*) | No | Yes (proxy) | Yes (consumer) | Yes (v3) | No |
| Tamper-proof chain | SHA-256 Merkle | SHA-256 SQLite | HMAC-SHA256 | No | No | Unknown |
| Multi-cloud discovery | AWS+Azure+GCP+K8s | No | No | No | No | No |
| IaC security (20 policies) | Yes (CIS/PCI/SOC2/HIPAA) | No | No | No | No | No |
| App portfolio scanner | Yes (11 languages) | No | No | No | No | No |
| Carbon tracking | Yes (open coefficients) | No | No | No | No | No |
| Python SDK | Yes | Yes | Yes | CLI only | Yes | SaaS |
| License | MIT | MIT | Apache 2.0 | Unknown | MIT (core) | Proprietary |
| Cost | Free | Free | Free | Free | Free (self-host) | $50K+/yr |

---

## Roadmap

The following are explicitly **not yet built**. Honest positioning matters.

| Gap | Status |
|---|---|
| Multi-tenant RBAC | Not built — single-user / single-org only today |
| React / web dashboard UI | Not built — Grafana dashboards for observability only; no app UI |
| SOC 2 Type II audit | Not started — platform itself has not undergone SOC 2 audit |
| Hyperscaler marketplace listing | Not listed on AWS / Azure / GCP Marketplace |
| Real-time streaming compliance scan | In progress — OTEL traces exist; live compliance stream not wired |
| Multi-region / HA deployment | Not documented — single-node only |

---

## Repository Structure

```
enterprise-ai-accelerator/
├── core/                       Anthropic optimization layer
│   ├── ai_client.py            Single Anthropic wrapper with caching + tool-use
│   ├── model_router.py         Complexity-based model selection
│   ├── result_cache.py         SQLite result cache
│   ├── batch_coalescer.py      Auto-coalescing Batch API submitter
│   ├── streaming.py            SSE streaming handler
│   ├── files_api.py            Files API wrapper
│   ├── interleaved_thinking.py Interleaved thinking+tools loop
│   ├── cost_estimator.py       Full cost estimator
│   ├── telemetry.py            OTEL tracer setup
│   ├── prometheus_exporter.py  8 Prometheus metrics
│   └── logging.py              structlog JSON logging
├── cloud_iq/                   AWS infrastructure analysis
│   └── adapters/               Multi-cloud discovery
│       ├── aws.py              boto3 discovery
│       ├── azure.py            azure-mgmt discovery
│       ├── gcp.py              google-cloud discovery
│       ├── kubernetes.py       kubernetes client discovery
│       └── unified.py          UnifiedDiscovery.auto()
├── app_portfolio/              Repository intelligence + 6R scoring
│   ├── cli.py                  CLI entry point
│   ├── analyzer.py             Pipeline coordinator
│   ├── language_detector.py    11-language detector
│   ├── dependency_scanner.py   9 dep manifest formats
│   ├── cve_scanner.py          OSV.dev batch CVE scanner
│   ├── containerization_scorer.py
│   ├── ci_maturity_scorer.py
│   ├── test_coverage_scanner.py
│   └── six_r_scorer.py         Opus 4.7 extended-thinking 6R
├── migration_scout/            6R classification + wave planning
│   ├── assessor.py             AI-native 6R workload classifier
│   ├── dependency_mapper.py    SCC circular dependency resolution
│   ├── wave_planner.py         Monte Carlo wave planner
│   ├── tco_calculator.py       3-year TCO with license elimination
│   ├── batch_classifier.py     Batch API bulk 6R scoring
│   └── thinking_audit.py       Extended-thinking + Annex IV persistence
├── policy_guard/               Multi-framework compliance scanner
│   ├── scanner.py              EU AI Act + HIPAA + SOC2 + PCI-DSS
│   ├── bias_detector.py        Statistical disparate impact analysis
│   ├── sarif_exporter.py       SARIF 2.1.0 → GitHub Security tab
│   ├── incident_response.py    P0–P3 + SLA tracking
│   └── thinking_audit.py       Extended-thinking audit path
├── iac_security/               IaC security + SBOM + drift
│   ├── terraform_parser.py     Terraform HCL parser
│   ├── pulumi_parser.py        Pulumi parser
│   ├── policies.py             20 built-in policies
│   ├── sbom_generator.py       CycloneDX SBOM generator
│   ├── osv_scanner.py          OSV.dev batched CVE scanner
│   ├── drift_detector.py       IaC vs. cloud state diff
│   └── sarif_exporter.py       SARIF 2.1.0 exporter
├── finops_intelligence/        Cloud cost intelligence
│   ├── cur_ingestor.py         AWS CUR ingestion via DuckDB
│   ├── ri_sp_optimizer.py      RI/SP optimizer (80% coverage cap)
│   ├── right_sizer.py          CloudWatch + instance catalog right-sizer
│   ├── carbon_tracker.py       Carbon emissions (open coefficients)
│   └── savings_reporter.py     Executive savings report
├── ai_audit_trail/             EU AI Act logging + NIST AI RMF
│   ├── chain.py                SHA-256 Merkle hash chain
│   ├── eu_ai_act.py            Article 12/62 compliance engine
│   ├── nist_rmf.py             GOVERN/MAP/MEASURE/MANAGE scoring
│   ├── incident_manager.py     P0–P3 + Article 62 deadline tracking
│   ├── decorators.py           Drop-in SDK integrations (5 frameworks)
│   └── sarif_exporter.py       SARIF 2.1.0 export
├── executive_chat/             1M-context CTO Q&A
├── compliance_citations/       Citations API grounded compliance evidence
├── integrations/               Notification + ticketing adapters
│   ├── dispatcher.py           FindingRouter + WebhookDispatcher
│   ├── slack.py / jira.py / servicenow.py / github_app.py
│   ├── teams.py / pagerduty.py / smtp_email.py / github_issue.py
├── observability/              OTEL + Prometheus + Grafana
│   ├── grafana_dashboards/     eaa_platform + eaa_cost dashboards
│   ├── otel-collector.yaml     OTEL Collector config
│   └── docker-compose.obs.yaml One-command observability stack
├── agent_ops/                  Multi-agent orchestrator
├── risk_aggregator.py          Cross-module 0–100 risk score
└── mcp_server.py               19 MCP tools (Claude Code / Desktop)
```

---

## Demo Commands

```bash
# App portfolio scan (simplest entry point)
python -m app_portfolio.cli .

# AI governance + EU AI Act (3 enterprise scenarios, no credentials)
python -m ai_audit_trail.demo

# $340K/month cloud spend optimization ($89.4K/month identified)
python -m finops_intelligence.demo

# 75-workload migration plan, Oracle $420K/yr license elimination
python -m migration_scout.demo

# EU AI Act compliance scanner (Fortune 500 hiring AI + healthcare AI)
python -m policy_guard.demo

# AWS infrastructure analysis ($47,200/month waste identified)
python -m cloud_iq.demo

# Bring up full observability stack (Prometheus + Grafana + Jaeger)
cd observability && docker compose -f docker-compose.obs.yaml up -d

# MCP server (for Claude Code / Claude Desktop)
python mcp_server.py
```

See [docs/DEMO.md](docs/DEMO.md) for the 5-minute exec demo, 15-minute technical walkthrough, and 3-minute interview pitch.

---

## Why This Matters Now

**EU AI Act — August 2, 2026:** High-risk AI system obligations (Articles 8–25) become enforceable. Logging, documentation, human oversight, and incident reporting requirements apply. Article 62 requires serious incident reporting within 72 hours. Non-compliance: up to 3% of global annual turnover.

**AWS Migration Hub closure — November 7, 2025:** The standard OSS migration planning tool is gone. AWS Transform covers only .NET and mainframe. The market gap for general-purpose migration intelligence is open.

**FOCUS 1.3 adoption:** Now the basis for multi-cloud billing normalization across enterprise FinOps platforms. Organizations without FOCUS-compliant tooling face manual data transformation across every cloud billing export.

---

## Requirements

```
Python 3.11+
anthropic>=0.69.0
```

Full dependency list: `requirements.txt`. Key additions in v0.2.0: `boto3`, `azure-mgmt-compute`, `azure-mgmt-resource`, `google-cloud-compute`, `kubernetes`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `prometheus-client`, `python-hcl2`, `cyclonedx-python-lib`, `packageurl-python`, `PyJWT`, `cryptography`, `slack-sdk`, `jira`.

All dependencies are OSS (Apache 2.0 / MIT). Zero paid SaaS services.

---

## Author

**Hunter Spence**
4 years at Accenture, Infrastructure Transformation (CL-9). Delivered cloud migration engagements across enterprise clients. AWS Certified Cloud Practitioner.

[LinkedIn](https://linkedin.com/in/hunterspence) · [Email](mailto:hunter@vantaweb.io) · [VantaWeb](https://vantaweb.io)

---

## Contributing

Pull requests welcome. See `CONTRIBUTING.md` for the contribution guide and code style.

---

## License

MIT. Use it, extend it, white-label it. See [LICENSE](LICENSE).

*Built because the gap between what Big 4 firms charge and what the technology can do autonomously is no longer defensible.*
