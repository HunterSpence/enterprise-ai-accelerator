# Enterprise AI Accelerator

**AI-native unified cloud governance platform — multi-cloud discovery, 6R migration planning, IaC security, FinOps intelligence, 11-framework compliance, tamper-evident AI audit, and executive AI chat. Built entirely on Claude Fable 5. Zero paid SaaS dependencies.**

[![CI](https://img.shields.io/badge/CI-tests%20%2B%20evals-brightgreen.svg)](.github/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Claude Fable 5](https://img.shields.io/badge/Claude-Fable%205-black.svg)](docs/FABLE_5_UPGRADE.md)
[![EU AI Act](https://img.shields.io/badge/EU%20AI%20Act-Annex%20IV%20evidence-orange.svg)](docs/EU_AI_ACT_EVIDENCE_PACK.md)
[![Compliance](https://img.shields.io/badge/frameworks-11-red.svg)](#capabilities-by-theme)
[![Evals](https://img.shields.io/badge/evals-offline%20CI%20gate-8A2BE2.svg)](evals/README.md)
[![Guardrails](https://img.shields.io/badge/guardrails-OWASP%20LLM%202025-darkred.svg)](#tested-and-guarded-not-just-claimed)
[![MCP](https://img.shields.io/badge/MCP-streamable%20HTTP%20%2B%20audited%20tools-0078d4.svg)](#mcp-surface)
[![FOCUS 1.3](https://img.shields.io/badge/FOCUS-1.3%20conformant-purple.svg)](#finops-intelligence)
[![Carbon Aware](https://img.shields.io/badge/carbon%20tracking-open%20coefficients-3d9970.svg)](finops_intelligence/README.md)

> **June 2026 — v0.4.0: Fable 5 refresh + governance hardening.** The platform now runs on
> Claude Fable 5 across every coordinator and high-stakes reasoning path, ships an offline
> eval harness with a CI gate, a guardrail layer mapped to OWASP LLM Top 10 (2025), an MCP
> server with Streamable HTTP transport whose every tool call is logged to the platform's own
> tamper-evident Merkle chain, compliance coverage current to June 2026 law (11 frameworks,
> including Colorado SB 26-189 and Texas TRAIGA), and CycloneDX ML-BOM generation for
> EU AI Act Annex IV evidence. See [CHANGELOG.md](CHANGELOG.md).

---

## The problem this exists to solve

Enterprise AI programs are failing at industrial scale — and the firms paid to fix that are part of the failure:

- **95% of enterprise GenAI pilots produce zero measurable P&L impact** (MIT NANDA, July 2025). The root cause isn't model quality — it's that pilots never become integrated, governed, operational systems.
- **AI project abandonment jumped from 17% to 42% in a single year** (S&P Global, 2025).
- **Gartner predicts over 40% of agentic AI projects will be canceled by end of 2027**, and documents widespread "agent washing" — of thousands of vendors claiming agentic capability, only ~130 are genuine.
- **Deloitte refunded part of an AU$440K government engagement** after its "independent assurance review" was found to contain fabricated court cases and citations — generated with undisclosed GPT-4o. The firms selling "Trustworthy AI" frameworks could not audit their own AI output.

The pattern: enterprises pay $3.2M–$12M for 12–18 month transformation engagements and receive recommendations, not running systems — with no verifiable trail for the AI-generated parts.

This platform is the opposite bet: **a working, self-hosted, MIT-licensed governance system you can deploy today, where every AI decision is reasoning-traced, citation-grounded, and tamper-evidently logged.**

---

## What this is

Enterprise AI Accelerator is an AI-native unified cloud governance platform built exclusively on Claude Fable 5 and open-source dependencies. It replaces the fragmented point solutions — migration tools, IaC scanners, FinOps dashboards, compliance auditors — that enterprise teams currently assemble from five to ten separate vendors, and does so at a fraction of the cost with a single audit trail. The platform covers the full cloud governance lifecycle: discover your multi-cloud estate, classify workloads for migration, scan infrastructure code for security and compliance violations, optimize cloud spend down to carbon emissions, and surface every decision in a tamper-evident audit chain designed for EU AI Act Annex IV evidence. Everything runs on a single Anthropic subscription with no paid SaaS intermediaries.

---

## Why this doesn't hallucinate (verifiably)

Every consulting firm now claims AI quality controls. This platform makes the controls **inspectable artifacts**:

| Failure mode | Structural control | Artifact you can hand an auditor |
|---|---|---|
| Fabricated citations (the Deloitte Australia failure) | **Anthropic Citations API** — compliance claims are grounded in character-range citations to the actual regulation text; the model cannot emit a control ID that isn't in the source | Citation-annotated compliance evidence (`compliance_citations/`) |
| Untraceable AI decisions | **Extended-thinking traces persisted** for every high-stakes call (6R classification, compliance audit) | Reasoning trace files, structured as Annex IV technical documentation |
| After-the-fact log tampering | **SHA-256 Merkle chain** over every audit event — any modification detected in O(log n) | `audit-trail://chain-verify` + anchored Merkle roots (file/webhook anchor backends) |
| Silent quality drift | **Offline eval harness with a CI gate** — golden datasets for 6R classification, IaC policy detection, and prompt-injection resistance; PRs fail below threshold | `python -m evals.run --offline` report |
| Prompt injection / excessive agency | **Guardrail layer** (input/output/execution rails + per-run budget caps), mapped to OWASP LLM Top 10 2025 | `core/guardrails.py` + red-team eval suite |
| Unaccountable tool use | **The MCP server logs every tool invocation into the same Merkle chain** — the platform's own AI surface is under the audit regime it sells | MCP tool-call audit entries |

No Big-6 platform publicly ships any of these as inspectable, self-hostable artifacts.

---

## What This Replaces

> **Bottom line.** A Big 6 cloud-transformation engagement delivers recommendations in 12–18 months for **$3.2M–$12M**. This platform ships the equivalent technical surface area today for **$25K–$80K / year** — one Anthropic subscription, zero paid SaaS, a single tamper-evident audit trail. Pricing details: [PRICING.md](PRICING.md).

### Big 6 consulting platforms

| Firm / Platform | Engagement | What they ship | What this platform ships instead |
|---|---:|---|---|
| **Accenture** — MyNav / AI Refinery | $500K–$5M | NVIDIA-locked closed platform; bespoke pricing only; no self-service | Open MIT source; runs in your cloud account; public pricing |
| **Deloitte** — CloudCompass / Zora AI | $400K–$3M + $200K/yr | Agent libraries atop undisclosed third-party models; post-Australia-refund trust deficit | Citations-grounded evidence; tamper-evident Merkle audit chain; disclosed model stack |
| **PwC** — agent OS | $300K–$2M | "25,000 agents deployed" — a count metric, not a quality metric | Eval-gated quality: published golden datasets + CI thresholds |
| **EY** — Nexus for Cloud | $400K–$2M | Thin glue over AWS Migration Hub / Azure Migrate; slide deliverables | Unified 6R + compliance + FinOps on one audit trail; SARIF 2.1.0 |
| **KPMG** — Powered Enterprise Cloud | $500K–$4M | SAP-centric; light on cloud-native / K8s / serverless | Multi-cloud adapters (AWS / Azure / GCP / K8s); IaC drift detection |
| **IBM** — watsonx / Consulting Advantage | $200K–$2M | Five overlapping products; Gartner: "unlikely to gain traction outside IBM ecosystem" | One coherent platform, model-portable, no ecosystem lock |
| **BCG X** | — | No cloud governance platform offering at all | The category exists; they don't compete in it |

**Where the Big 6 still win.** Brand trust with boards, regulatory sign-off at Fortune 500 scale, and the organizational change-management muscle a 200-person program office provides. This platform is the technical substrate — not a replacement for that program office. It's also what makes their recommendations *executable* without a second engagement.

### Commercial point tools

| Tool | Category | List price | Replaced by |
|---|---|---:|---|
| CAST Highlight / vFunction | App portfolio + refactoring | $150K–$600K/yr | `app_portfolio/` |
| Snyk IaC / Prisma Cloud | IaC security | $200K–$1M/yr | `iac_security/` |
| IBM OpenPages AI Governance | AI risk + compliance | $500K–$2M/yr | `ai_audit_trail/` + `policy_guard/` + `compliance_citations/` |
| Credo AI | Bias + AI compliance | $180K/yr | `policy_guard/` |
| ServiceNow IRM + AIOps | GRC + ops | $300K–$2M/yr | `integrations/` + `executive_chat/` |
| Apptio Cloudability / CloudZero | FinOps | $100K–$1M/yr | `finops_intelligence/` |
| Flexera One / Turbonomic | Cloud cost + optimization | $100K–$2M/yr | `cloud_iq/adapters/` + `finops_intelligence/right_sizer.py` |
| Datadog / New Relic | Observability | $50K–$500K/yr | `observability/` (OSS OTEL + Prometheus + Grafana) |

### 3-year TCO — 10,000-workload enterprise

| Approach | Year 1 | Year 3 cumulative |
|---|---:|---:|
| Big 6 engagement + licensed tools | $3.2M–$12M | $6M–$25M |
| Best-of-breed commercial tools, assembled in-house | $1.5M–$4M | $4.5M–$12M |
| **This platform** (Anthropic API + self-hosted) | **$25K–$80K** | **$75K–$240K** |

---

## About vendor lock-in (the question every buyer asks)

- **License:** MIT. Fork it, white-label it, leave any time. There is no proprietary tier withholding core capability.
- **Your cloud, your data:** all computation runs in your own account; the Anthropic API is the only external call. See [docs/SOVEREIGN_DEPLOYMENT.md](docs/SOVEREIGN_DEPLOYMENT.md) for sovereign and regulated-environment deployment, including routing options through cloud-provider model endpoints.
- **Model abstraction:** every model call goes through `core/AIClient` + `ModelRouter`; model IDs live in one file (`core/models.py`) with environment overrides. Migrating tiers is a config change, not a rewrite — this release's Opus 4.7 → Fable 5 migration exercised exactly that path.
- **Open interfaces everywhere:** MCP for tools, SARIF 2.1.0 for findings, CycloneDX for SBOM/ML-BOM, FOCUS for billing data, OpenTelemetry for traces. Nothing is exportable only through us.

---

## Quick Start — time to value

```bash
git clone https://github.com/HunterSpence/enterprise-ai-accelerator.git
cd enterprise-ai-accelerator
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# ~4 minutes to first findings — scan a local repo (no cloud credentials needed)
python -m app_portfolio.cli .

# ~15 minutes to a governance report — IaC security scan with SARIF output
python -m iac_security .

# ~1 hour to an EU AI Act evidence pack — audit trail + ML-BOM + SARIF
python -m ai_audit_trail.demo
python -m iac_security mlbom
```

All module demos run offline against synthetic fixtures — **demo mode never calls the live API and never bills you.** Set `ANTHROPIC_API_KEY` only to enable the AI-powered paths.

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Entry Points                                        │
│   CLI  ·  MCP Server (19 tools, stdio + streamable-HTTP)  ·  Python SDK  ·      │
│   Webhook Dispatcher                                                             │
└──────┬──────────────────┬────────────────────┬──────────────────────────────────┘
       │                  │                    │
       ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         core/ — Anthropic Optimization Layer                     │
│  AIClient · ModelRouter · Guardrails (input/output/execution rails + budget)    │
│  ResultCache · BatchCoalescer · Streaming · FilesAPI · CostEstimator            │
└──────┬──────────────────┬────────────────────┬──────────────────────────────────┘
       │                  │                    │
┌──────▼──────┐  ┌────────▼────────┐  ┌────────▼───────┐  ┌───────────────────────┐
│  cloud_iq/  │  │  app_portfolio/ │  │  iac_security/ │  │  finops_intelligence/ │
│  adapters/  │  │  (11 languages) │  │  (20 policies) │  │  CUR + RI/SP + right- │
│  AWS·Azure  │  │  OSV CVE scan   │  │  SBOM + ML-BOM │  │  sizing + carbon      │
│  GCP·K8s    │  │  6R via Fable 5 │  │  drift·SARIF   │  │  DuckDB analytics     │
└──────┬──────┘  └────────┬────────┘  └────────┬───────┘  └──────────┬────────────┘
       │                  │                    │                      │
       └──────────────────┴────────────────────┴──────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────────────┐
│        agent_ops/ — Multi-Agent Orchestrator (retries · budgets ·              │
│        checkpoints · human-in-the-loop approval hooks)                          │
│        Fable 5 Coordinator · Sonnet 4.6 Reporter · Haiku 4.5 Workers           │
└───────────────────────────────────┬────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
┌─────────▼──────────┐   ┌──────────▼──────────┐   ┌─────────▼──────────────────┐
│  migration_scout/  │   │   policy_guard/     │   │   ai_audit_trail/           │
│  6R + Monte Carlo  │   │  11 frameworks incl │   │   SHA-256 Merkle chain      │
│  dependency maps   │   │  EU AI Act · NIST   │   │   + anchor backends         │
│  wave planning     │   │  CO SB 26-189·TRAIGA│   │   SARIF 2.1.0 + Art. 12     │
└────────────────────┘   └─────────────────────┘   └────────────────────────────┘
          │                         │                         │
          └─────────────────────────▼─────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────────────┐
│   executive_chat/ + compliance_citations/ + risk_aggregator.py + evals/         │
│   1M-context CTO Q&A · Citations evidence · 0–100 risk score · CI eval gate    │
└───────────────────────────────────┬────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────────────┐
│              integrations/ + observability/                                     │
│   Slack · Jira · ServiceNow · GitHub · Teams · PagerDuty · SMTP                │
│   OTEL gen_ai.* traces · Prometheus metrics · Grafana dashboards               │
└────────────────────────────────────────────────────────────────────────────────┘
```

**Model tier:** Fable 5 (`claude-fable-5`) handles coordination and high-stakes reasoning (6R, audit-grade adaptive thinking, executive chat) — overridable to Opus 4.8. Sonnet 4.6 handles report synthesis and long-context work (1M window at 30% of flagship input price). Haiku 4.5 handles high-volume worker tasks. The model router selects the tier — and the recommended effort level — automatically by task complexity. Fable 5 safety-classifier declines fail over to Opus 4.8 server-side in the same round trip, so a refusal never takes the pipeline down.

---

## Tested and guarded — not just claimed

Two things this release adds that you will not find in a consulting-firm platform demo:

**An eval harness with teeth.** `evals/` ships golden datasets (6R workload classification, IaC policy detection, a prompt-injection red-team corpus) and an offline runner with per-suite thresholds wired into CI — a PR that degrades detection quality fails. Run it yourself:

```bash
python -m evals.run --offline
```

**A guardrail layer mapped to OWASP LLM Top 10 (2025).** Input rails (prompt-injection detection across instruction-override, encoding, and tool-arg-smuggling patterns), output rails (secret/PII redaction), execution rails (tool allowlists), and hard per-run token/cost budgets. The red-team eval suite exercises the rails in CI.

The platform also **dogfoods its own audit regime**: every MCP tool call made against it is hashed and appended to the same Merkle chain it offers customers (`audit-trail://chain-verify`).

---

## Module Reference

| Module | Purpose | Key Classes | Value Prop |
|---|---|---|---|
| **core/** | Anthropic optimization + safety layer | `AIClient`, `ModelRouter`, `GuardrailEngine`, `BudgetGuard`, `ResultCache`, `BatchCoalescer`, `CostEstimator` | Complexity routing + caching + batching cut model spend by roughly an order of magnitude vs all-flagship; rails enforce OWASP LLM 2025 controls |
| **cloud_iq/** + **adapters/** | Multi-cloud discovery & analysis | `CloudScanner`, `CostAnalyzer`, `AWSAdapter`, `AzureAdapter`, `GCPAdapter`, `KubernetesAdapter` | Real boto3 / azure-mgmt / google-cloud / kubernetes discovery with graceful degradation; offline demo mode |
| **app_portfolio/** | Repository intelligence | `LanguageDetector`, `DependencyScanner`, `CVEScanner`, `SixRScorer` | 11 languages, 9 dep manifests, OSV.dev CVE scan, Fable 5 extended-thinking 6R per repo |
| **migration_scout/** | 6R workload classification | `WorkloadAssessor`, `DependencyMapper`, `WavePlanner`, `BatchClassifier`, `ThinkingAudit` | AI-native 6R + Monte Carlo wave planning (AWS Migration Hub closed Nov 2025 — this gap is open) |
| **policy_guard/** | Multi-framework compliance | `ComplianceScanner`, `BiasDetector`, `SARIFExporter`, `IncidentResponse` | **11 frameworks**: EU AI Act, NIST AI RMF 2.0, ISO/IEC 42001, HIPAA, SOC 2, CIS AWS, DORA, FedRAMP Rev 5, PCI DSS 4.0, **Colorado SB 26-189**, **Texas TRAIGA** — with cross-framework traceability |
| **iac_security/** | IaC security + SBOM + ML-BOM | `TerraformParser`, `PulumiParser`, `PolicyEngine`, `SBOMGenerator`, `OSVScanner`, `DriftDetector` | 20 policies, CycloneDX SBOM **and ML-BOM**, OSV CVE, SARIF to GitHub Security tab |
| **finops_intelligence/** | Cloud cost intelligence | `CURIngestor`, `RISPOptimizer`, `RightSizer`, `CarbonTracker`, `SavingsReporter` | AWS CUR via DuckDB, FOCUS 1.3 conformant (FOCUS 1.4 AI-token columns on roadmap), carbon tracking with open coefficients |
| **ai_audit_trail/** | EU AI Act audit logging | `MerkleChain`, `AnchorBackend`, `EUAIActLogger`, `NISTRMFScorer`, `IncidentManager` | SHA-256 Merkle chain + file/webhook root anchoring + SARIF 2.1.0 + Article 12 / Annex IV + 72-hour Article 62 incident tracking |
| **executive_chat/** | 1M-context CTO Q&A | `ExecutiveChat`, `BriefingLoader` | Full enterprise briefing in one prompt; follow-ups at a fraction of first-call cost via 1-hour cache |
| **compliance_citations/** | Evidence-grounded compliance | `EvidenceLibrary`, `CitationsEngine` | Anthropic Citations API — character-range citations, no hallucinated control IDs |
| **agent_ops/** | Multi-agent orchestration | `Orchestrator`, `CoordinatorAgent`, `WorkerAgent` | Fable 5 coordinator with retries, checkpoint/resume, per-run budgets, and human-in-the-loop approval hooks |
| **evals/** | Quality gate | golden datasets + offline scorers + CI gate | The platform's accuracy claims are reproducible: `python -m evals.run --offline` |
| **integrations/** | Notification + ticketing | `FindingRouter`, `WebhookDispatcher`, adapters | Slack / Jira / ServiceNow / GitHub / Teams / PagerDuty / SMTP with retry + circuit-breaker |
| **observability/** | Full OTEL stack | `TelemetryClient`, `PrometheusExporter`, Grafana dashboards | gen_ai.* conventions, Prometheus metrics, Grafana platform + cost dashboards, Jaeger traces |
| **risk_aggregator.py** | Cross-module risk score | `WorkloadRiskAggregator` | Unified 0–100 score from any combination of module outputs |
| **mcp_server.py** | MCP surface | 19 tools + resources + prompts | Every module drivable from Claude Code / Claude Desktop; stdio + streamable-HTTP (+ legacy SSE); bearer-token auth; Merkle-audited tool calls |

---

## Capabilities by Theme

| Theme | What the platform covers |
|---|---|
| **Discovery** | boto3/azure-mgmt/google-cloud/kubernetes discovery; 11 programming languages; 9 dependency manifest formats; OSV.dev CVE feed |
| **Migration Planning** | AI-native 6R classification; Monte Carlo wave planning with confidence intervals; dependency SCC resolution; 3-year TCO; AWS MAP alignment |
| **Compliance** | **11 frameworks** with cross-framework traceability: EU AI Act (Articles 9/10/12/13/15/62), NIST AI RMF 2.0 (73 subcategories + GenAI profile), ISO/IEC 42001:2023 (47 controls), HIPAA, SOC 2, CIS AWS, DORA, FedRAMP Rev 5 (248 controls), PCI DSS 4.0, Colorado SB 26-189 (effective Jan 1 2027), Texas TRAIGA (effective Jan 1 2026) |
| **AI Quality** | Offline eval harness (golden 6R + IaC + injection-red-team datasets) with CI thresholds; guardrail rails mapped to OWASP LLM Top 10 2025; per-run budget enforcement |
| **FinOps** | AWS CUR ingestion via DuckDB; FOCUS 1.3 conformance; RI/SP optimization; right-sizing with CloudWatch; carbon emissions; CFO-ready savings report |
| **Observability** | OpenTelemetry gen_ai.* conventions; Prometheus metrics; structlog JSON; Grafana dashboards; Jaeger traces |
| **Audit** | SHA-256 Merkle chain with anchor backends; reasoning traces as Annex IV evidence; SARIF 2.1.0; 72-hour Article 62 incident tracking; MCP tool-call audit |
| **AI Governance** | Extended-thinking trace persistence; Citations-grounded evidence; bias detection; NIST AI RMF scoring; CycloneDX ML-BOM; EU AI Act Annex III classification |

---

## Cost Optimization

The `core/` optimization layer applies four levers automatically:

| Lever | Mechanism | Saving |
|---|---|---|
| **Complexity routing** | `ModelRouter` scores each task; simple tasks go to Haiku 4.5 instead of Fable 5 ($10/MTok input) | ~10× on worker-tier input |
| **Result cache** | SQLite-backed `ResultCache` returns identical results without a second API call | 100% on cache hits |
| **Batch coalescing** | `BatchCoalescer` auto-submits accumulated requests to the Anthropic Batch API | 50% discount on batched calls |
| **Prompt caching** | 5-min ephemeral on all system prompts; 1-hour on executive chat | large reduction on repeat pipelines |

Stacked, the levers cut bulk-pipeline costs by roughly **90–95% vs an all-flagship baseline**.

**Honest benchmark note (v0.4.0):** Fable 5's tokenizer counts up to ~35% more tokens for identical text than the Opus 4.7-era tokenizer, while list prices dropped ($10/$50 vs $15/$75 per MTok). Pre-June-2026 per-pipeline dollar figures published in earlier versions of this README are therefore not directly comparable and are being re-benchmarked; the relative savings ratios above hold. Cost figures here are representative estimates at Anthropic list prices (June 2026), and depend on workload characteristics.

---

## EU AI Act Readiness

**Where the timeline actually stands (June 2026):** GPAI obligations have been in force since August 2, 2025. High-risk (Annex III) enforcement — originally August 2, 2026 — was deferred to **December 2, 2027** by the Digital Omnibus agreement (provisionally agreed May 2026; Annex I embedded systems: August 2, 2028). The deadline moved; the evidence burden did not — penalties still reach 3% of global annual turnover, and Annex IV technical documentation takes most organizations 12–18 months to assemble. Procurement teams are asking for it now.

| Article | Obligation | Platform capability |
|---|---|---|
| **Article 9** | Risk management system | Unified 0–100 risk score + per-module traces via `risk_aggregator.py` |
| **Article 10** | Data governance | Citations API grounds every compliance claim in cited regulatory source text |
| **Article 12** | Record-keeping | SHA-256 Merkle chain in `ai_audit_trail/` — tampering detected in O(log n); roots anchorable to external backends |
| **Article 13** | Transparency | Reasoning trace on every extended-thinking call, persisted as Annex IV evidence |
| **Article 15** | Accuracy / robustness | Extended-thinking traces + the offline eval suite document model decision quality |
| **Article 62** | Incident reporting | P0–P3 severity ladder + 72-hour deadline tracking |
| **Annex IV** | Technical documentation | SARIF 2.1.0 + reasoning traces + **CycloneDX ML-BOM** form a complete evidence package |

Step-by-step: [docs/EU_AI_ACT_EVIDENCE_PACK.md](docs/EU_AI_ACT_EVIDENCE_PACK.md) — which command produces each Annex IV artifact.

The reasoning-trace + Citations + SARIF + ML-BOM combination is not available in any other open-source tool.

---

## How We Compare

| Feature | Enterprise AI Accelerator | AgentLedger | AIR Blackbox | ai-trace-auditor | Langfuse | Credo AI |
|---|---|---|---|---|---|---|
| EU AI Act Art.12 | Yes (full) | Yes | Yes (6 articles) | Yes (Art.11-13,25) | No | Yes |
| SARIF 2.1.0 export | Yes | No | No | No | No | No |
| OpenTelemetry | Yes (native gen_ai.*) | No | Yes (proxy) | Yes (consumer) | Yes (v3) | No |
| Tamper-proof chain | SHA-256 Merkle + anchors | SHA-256 SQLite | HMAC-SHA256 | No | No | Unknown |
| Offline eval CI gate | Yes | No | No | No | Evals (live) | No |
| Guardrail layer (OWASP LLM 2025) | Yes | No | No | No | No | No |
| ML-BOM (CycloneDX) | Yes | No | No | No | No | No |
| Multi-cloud discovery | AWS+Azure+GCP+K8s | No | No | No | No | No |
| IaC security (20 policies) | Yes | No | No | No | No | No |
| Carbon tracking | Yes (open coefficients) | No | No | No | No | No |
| License | MIT | MIT | Apache 2.0 | Unknown | MIT (core) | Proprietary |
| Cost | Free | Free | Free | Free | Free (self-host) | $50K+/yr |

---

## Pricing

The platform is MIT-licensed and free, forever, in full. Paid offerings are support and services around it:

| Tier | Price | What it is |
|---|---:|---|
| **OSS Core** | Free | The entire platform. No feature gates. |
| **Enterprise Support** | $25K–$80K/yr | SLA support, compliance evidence packs, upgrade assistance (Starter / Standard / Enterprise) |
| **Fixed-Scope Services** | $15K–$50K | Cloud Governance Sprint (2 wk), Migration Planning Package, Compliance Audit Acceleration |
| **FinOps outcome option** | 10% of realized savings | Measured at month 6 against the platform's own savings report |

Details and tier contents: [PRICING.md](PRICING.md).

---

## Roadmap

Honest status — see [ROADMAP.md](ROADMAP.md) for the full list with rationale.

| Item | Status |
|---|---|
| Multi-tenant RBAC | Not built — single-org today |
| Web app UI | Streamlit compliance dashboard ships today; full app UI not built |
| SOC 2 Type II (of this platform) | Not started — observation period is the next step |
| Hyperscaler marketplace listings | Not listed yet |
| Claude Agent SDK migration | Planned — orchestrator hardening (retries/budgets/checkpoints/HITL) landed natively in v0.4.0 |
| A2A protocol interop | Planned |
| GraphRAG knowledge module | Planned |
| Multi-region / HA deployment | Not documented — single-node only |

---

## Demo Commands

```bash
# App portfolio scan (simplest entry point)
python -m app_portfolio.cli .

# AI governance + EU AI Act (3 enterprise scenarios, no credentials)
python -m ai_audit_trail.demo

# Cloud spend optimization demo
python -m finops_intelligence.demo

# 75-workload migration plan demo
python -m migration_scout.demo

# 11-framework compliance scanner demo
python -m policy_guard.demo

# AWS infrastructure analysis demo
python -m cloud_iq.demo

# ML-BOM for the platform's own model stack
python -m iac_security mlbom

# Offline eval suite (the CI quality gate)
python -m evals.run --offline

# Full observability stack (Prometheus + Grafana + Jaeger)
cd observability && docker compose -f docker-compose.obs.yaml up -d
```

All demos run offline by default — demo mode performs no billable API calls. See [docs/DEMO.md](docs/DEMO.md) for the 5-minute exec demo and 15-minute technical walkthrough.

---

## MCP Surface

Every module is drivable from Claude Code / Claude Desktop / any MCP client: 19 tools, plus resources and prompts.

### Transports

```bash
# stdio (default — Claude Code, Claude Desktop local)
python mcp_server.py

# Streamable HTTP (recommended network transport, MCP spec 2025-03-26+)
python mcp_server.py --transport streamable-http --host 0.0.0.0 --port 8765

# SSE (legacy — superseded by streamable-http)
python mcp_server.py --transport sse --host 0.0.0.0 --port 8765
```

- **Auth:** set `EAA_MCP_AUTH_TOKEN` to require `Authorization: Bearer` on network transports.
- **Audited by design:** every tool invocation is hashed and appended to the platform's Merkle chain (`EAA_MCP_AUDIT`, default on).
- Client config example: [mcp-config-example.json](mcp-config-example.json).

---

## Why This Matters Now

**EU AI Act:** GPAI obligations are already in force (August 2025); high-risk Annex III obligations land December 2, 2027 after the Digital Omnibus deferral — and Annex IV evidence packs take 12–18 months to assemble, which makes 2026 the build year. US state law is moving faster: Texas TRAIGA took effect January 1, 2026; Colorado's SB 26-189 takes effect January 1, 2027.

**The consulting trust gap is open:** post-Deloitte-Australia, "show me your reasoning" is the first question in AI procurement. Tamper-evident evidence is the answer this platform was built around.

**AWS Migration Hub closed November 7, 2025:** the standard OSS migration planning path is gone; the general-purpose migration intelligence gap remains open.

**FOCUS 1.4 (June 2026)** standardizes AI token economics in FinOps data — this platform's FOCUS 1.3 conformance and token-level cost telemetry are the on-ramp.

---

## Requirements

```
Python 3.11–3.13
anthropic>=0.69.0
mcp>=1.27.0
```

Full dependency list: `requirements.txt`. All dependencies are OSS (Apache 2.0 / MIT). Zero paid SaaS services.

> Note: Python 3.14 is not yet supported (a transitive dependency lacks 3.14 wheels).

---

## Project Governance

This is a solo-maintained project built to enterprise-reviewable standards: [GOVERNANCE.md](GOVERNANCE.md) covers the maintainer model, release cadence, and bus-factor mitigations (MIT license = fork-safe; documented architecture; offline test + eval suites; zero proprietary dependencies). Security policy: [SECURITY.md](SECURITY.md). Vulnerability reports are answered within 72 hours.

---

## Author

**Hunter Spence**
4 years at Accenture, Infrastructure Transformation (CL-9). Delivered cloud migration engagements across enterprise clients. AWS Certified Cloud Practitioner. Built this because the gap between what Big-6 firms charge and what the technology can do autonomously is no longer defensible.

[LinkedIn](https://linkedin.com/in/hunterspence) · [Email](mailto:hunter@vantaweb.io) · [VantaWeb](https://vantaweb.io)

---

## Contributing

Pull requests welcome. See `CONTRIBUTING.md` for the contribution guide and code style. CI runs the offline test suite and the eval gate on every PR.

---

## License

MIT. Use it, extend it, white-label it. See [LICENSE](LICENSE).
