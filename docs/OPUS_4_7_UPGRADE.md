# Opus 4.7 Executive Upgrade — April 2026

> **TL;DR for the C-suite.** The Enterprise AI Accelerator now runs on
> Claude Opus 4.7 across every auditable decision path, uses prompt
> caching to cut input-token cost by up to 90% on repeat pipelines,
> exposes native tool-use structured output for deterministic parsing,
> and ships a 1M-context executive chat that answers any CTO question
> against the full enterprise briefing.

---

## Why this release matters

The EU AI Act enters its enforcement window on **August 2, 2026**. On that
date, any high-risk AI system operating in the EU market must produce —
on demand — a full Annex IV technical documentation record for every
decision, including a reasoning trace, the model used, the input
provenance, and the output logged to a tamper-evident store.

Before this release, the platform met Article 12 on the storage side but
relied on regex-based JSON parsing, a single shared coordinator model, and
free-text reasoning that couldn't be persisted as evidence. This release
closes those gaps.

---

## What changed — at a glance

| Layer                    | Before                               | After (Opus 4.7)                                             |
|--------------------------|--------------------------------------|-------------------------------------------------------------|
| Coordinator model        | Claude Opus 4.6                      | **Claude Opus 4.7**                                         |
| Report synthesizer       | Claude Haiku 4.5                     | **Claude Sonnet 4.6** (better executive prose)             |
| Worker model             | Claude Haiku 4.5                     | Claude Haiku 4.5 (retained — cost-efficient)                |
| Structured output        | Regex-parsed JSON, fence-stripping   | **Native tool-use** — schema-validated every call           |
| Prompt caching           | None                                 | **5-min ephemeral** on all system prompts; **1-hour** on executive chat briefings |
| Extended thinking        | Not used                             | **Opt-in on 6R + policy + bias audits** — reasoning trace is persisted to AIAuditTrail as Annex IV evidence |
| Batch API                | Not used                             | **FinOps + MigrationScout bulk** (50% discount, up to 10k requests) |
| Citations API            | Not used                             | **Evidence-grounded compliance Q&A** via new `compliance_citations/` |
| Files API                | Not used                             | Ready via `compliance_citations.EvidenceLibrary`            |
| Context window           | 200k (Sonnet) / 200k (Haiku)         | **1,000,000** (Opus 4.7) — powers unified executive chat    |
| MCP tool count           | 4 (AIAuditTrail only)                | **19 tools** across all six modules + executive chat + citations |
| Per-call telemetry       | Coarse duration + finding count      | **Token-level: input / output / cache-read / cache-creation** — executive cost dashboard ready |

---

## New capabilities executives can demo

### 1. Unified Executive Chat (`executive_chat/`)

Drops the entire briefing — architecture findings, 6R plan, compliance
violations, FinOps anomalies, audit-trail posture, unified risk score —
into Opus 4.7's 1M-token context. First question pays the full ingest
cost; every follow-up inside the 60-minute cache window pays ~10%.

Demo script: _"Which three workloads represent the highest migration risk
given our current compliance posture, and what is the 30-day mitigation
plan?"_ — returns a structured, schema-validated answer with supporting
finding IDs and recommended actions.

### 2. Auditable 6R Classifications (`migration_scout/thinking_audit.py`)

For Replatform/Refactor decisions on high-business-criticality workloads,
run the classification through Opus 4.7 **extended thinking** (up to 32k
reasoning tokens). The reasoning trace is persisted into AIAuditTrail as
Annex IV technical documentation, satisfying EU AI Act Article 15
(accuracy, robustness, and cybersecurity) and Annex IV §4 (description of
the logic and assumptions).

### 3. Evidence-Cited Compliance Answers (`compliance_citations/`)

Load the CIS AWS Benchmark, SOC 2 Trust Services Criteria, HIPAA Security
Rule, PCI-DSS, or EU AI Act Annex IV as `EvidenceLibrary` sources. Every
answer is returned with **character-range citations** into the source
documents — no hallucinated control IDs, no handwaved justifications.

### 4. Batch-Discounted Bulk Scoring

For customers with large migration inventories or high-volume FinOps
reviews, `migration_scout/batch_classifier.py` and
`finops_intelligence/batch_processor.py` submit up to 10,000 requests to
the Anthropic Batches API at **50% of list price** with guaranteed 24h
turnaround. Each result is schema-validated via forced tool-use.

### 5. Platform-Wide Model Governance (`core/`)

Every module now imports its model identifiers from `core.models`. Model
upgrades are a two-line change in one file — no more scattered string
literals. `core.AIClient` is the single Anthropic wrapper with consistent
caching, tool-use, and extended-thinking handling.

---

## Token economics — the cost story for CFOs

For a typical pipeline run (4 agents × ~2k-token system prompts):

| Scenario                                   | Input tokens charged | Relative cost |
|--------------------------------------------|----------------------|---------------|
| Pre-upgrade (no caching, 10 runs/hour)     | ~80,000              | 1.00×         |
| Opus 4.7 + 5-min cache (10 runs/hour)      | ~12,000              | ~0.15×        |
| Opus 4.7 + 1-hour cache (executive chat)   | ~4,000               | ~0.05×        |
| Opus 4.7 batch for 1,000-workload 6R scan  | Full input, 50% rate | ~0.50×        |

Cache reads are charged at 10% of input rate. Cache creation is charged at
125%. The break-even point for the 5-minute cache is the second call —
and every pipeline runs at least four agents within the window.

---

## Compliance story for auditors

Every Opus 4.7 extended-thinking audit (6R strategy, policy decision,
bias assessment) returns both:

1. The **structured verdict** (validated against a JSON schema via
   native tool use — deterministic, parseable, auditable).
2. The **reasoning trace** (up to 32k tokens of interleaved thinking).

Both are persisted into AIAuditTrail via the existing SHA-256 hash chain.
The reasoning trace becomes part of the Annex IV evidence package.
SARIF export remains 2.1.0-compliant.

EU AI Act Article references the upgrade now satisfies:

- **Article 9** — Risk management: unified risk score + per-module traces.
- **Article 10** — Data governance: Citations API grounds every compliance
  claim in the cited regulatory source.
- **Article 12** — Record-keeping: tamper-evident Merkle chain, unchanged.
- **Article 13** — Transparency: reasoning trace on every high-stakes call.
- **Article 15** — Accuracy / robustness: extended thinking budget on audit
  paths documents the model's decision process.
- **Article 62** — Incident reporting: unchanged (still backed by
  `ai_audit_trail.incident_manager`).

---

## Migration notes for existing deployments

Upgrade path:

```bash
pip install 'anthropic>=0.69.0'
# pull the new release
git pull origin main

# restart the MCP server — it will auto-discover the expanded tool catalog
python mcp_server.py

# the orchestrator auto-uses core.AIClient — no code changes required in
# existing pipelines. Token usage appears on `PipelineResult.token_usage`.
```

Breaking changes: **none.** All legacy constructors accept either an
`AsyncAnthropic` client (old behavior) or an `AIClient` (new). The
`_parse_json_response` helper is kept as a deprecated fallback.

---

## What this replaces in the market

| Tool                                   | List price        | Equivalent capability           |
|---------------------------------------|-------------------|---------------------------------|
| Accenture MyNav                        | $500K engagement  | CloudIQ + MigrationScout        |
| IBM OpenPages AI Governance            | $500K/year        | AIAuditTrail + PolicyGuard      |
| Credo AI                               | $180K/year        | Bias + compliance audits        |
| Vendor executive AI copilots           | $100K+/year       | ExecutiveChat (1M-context)      |

All capabilities above run on a single open-source codebase on a single
Claude Opus 4.7 subscription — one contract, one audit trail, one risk
score.

---

## April 2026 Platform Expansion (v0.2.0)

Commit: `39f1e6d`. Seven parallel capability tracks added. 68 new files,
16,931 LoC, 15 new OSS dependencies. Zero paid SaaS services introduced.

### Before / After Platform Posture

| Dimension | v0.1.0 (cdb8bdb) | v0.2.0 (39f1e6d) |
|---|---|---|
| Cloud discovery | Synthetic/mock data only | Real boto3/azure-mgmt/google-cloud/kubernetes adapters |
| App intelligence | Not present | 11 languages, 9 dep manifests, OSV CVE, 6R per repo |
| IaC security | Not present | 20 policies (CIS/PCI/SOC2/HIPAA), SBOM, CVE, drift, SARIF |
| FinOps depth | FOCUS 1.3 export + anomaly detection | + CUR ingestion, RI/SP optimizer, right-sizer, carbon, savings report |
| Observability | Coarse duration counters | Full OTEL gen_ai.*, 8 Prometheus metrics, 2 Grafana dashboards, Jaeger |
| Cost optimization | Prompt caching only | + ModelRouter (~95% savings), ResultCache, BatchCoalescer, CostEstimator |
| Integrations | None | Slack, Jira, ServiceNow, GitHub, Teams, PagerDuty, SMTP (all free-tier) |

### Track 1 — Multi-Cloud Discovery (`cloud_iq/adapters/`)

Real SDK-backed discovery replaces mock data. `UnifiedDiscovery.auto()`
probes for credentials across AWS (boto3), Azure (azure-mgmt), GCP
(google-cloud), and Kubernetes (kubernetes client), then combines all
reachable inventories. Graceful degradation — missing credentials skip
that adapter without error.

Before: `cloud_iq.demo` ran on entirely synthetic data.
After: production deployments can point at real cloud accounts and get a
live multi-cloud asset inventory in seconds.

### Track 2 — App Portfolio Intelligence (`app_portfolio/`)

New module. Scans any code repository and returns: language composition
(11 languages), dependency inventory (9 manifest formats), CVE findings
(OSV.dev, no API key), containerization score, CI maturity score, test
coverage, and an Opus 4.7 extended-thinking 6R recommendation per repo.
CLI: `python -m app_portfolio.cli <path>`. Replaces CAST Highlight
($150K–$600K/yr commercial equivalent) for portfolio-level migration
scoping.

### Track 3 — Integration Hub (`integrations/`)

New module. Routes platform findings to Slack, Jira Cloud, ServiceNow,
GitHub Issues, GitHub App PR check-runs (inline annotations), Teams,
SMTP, and PagerDuty. All adapters use free-tier or webhook endpoints —
no paid middleware. `WebhookDispatcher` applies exponential-backoff retry
+ circuit-breaker + per-adapter rate limiting. Dry-run mode on all
adapters.

### Track 4 — IaC Security (`iac_security/`)

New module. Parses Terraform (python-hcl2) and Pulumi IaC, checks 20
built-in policies (CIS AWS / PCI-DSS / SOC 2 / HIPAA), generates
CycloneDX SBOM, scans declared dependencies via OSV.dev, detects drift
between IaC state and live cloud state, and exports SARIF 2.1.0 for the
GitHub Security tab. Replaces Snyk IaC / Prisma Cloud ($200K+/yr).

### Track 5 — Full Observability (`observability/` + `core/` additions)

`core/telemetry.py` implements the OpenTelemetry gen_ai.* semantic
conventions. `core/prometheus_exporter.py` exports 8 Prometheus metrics.
`core/logging.py` provides structlog JSON logging. `core/_hooks.py` wires
OTEL spans into `AIClient`. `observability/docker-compose.obs.yaml` brings
up Prometheus + Grafana + Jaeger + OTEL Collector with one command; two
Grafana dashboards (eaa_platform, eaa_cost) are auto-provisioned.

Before: per-call metrics were coarse duration + finding count.
After: full distributed traces, token-level attribution, cost counters per
model, and cache hit rate in Grafana.

### Track 6 — Advanced FinOps (`finops_intelligence/` additions)

Four new components extend the existing FinOps module: `CURIngestor` (AWS
CUR via DuckDB, Parquet), `RISPOptimizer` (RI/SP with 80% coverage cap),
`RightSizer` (CloudWatch + 200+ instance types + Graviton), `CarbonTracker`
(open-source regional grid coefficients), and `SavingsReporter` (CFO
executive summary). Before, FinOps covered FOCUS 1.3 export and anomaly
detection. After, the full AWS cost optimization lifecycle is covered in
a single module.

### Track 7 — Anthropic-Native Cost Optimization Layer (`core/` additions)

Seven new components in `core/` reduce platform operating cost by
approximately 95% vs. an always-Opus-4.7 baseline:

- `ModelRouter` — complexity-based model selection (Opus/Sonnet/Haiku)
- `ResultCache` — SQLite TTL cache; identical requests never hit the API twice
- `BatchCoalescer` — auto-coalescing Batch API submission (50% discount)
- `StreamHandler` — SSE streaming
- `FilesAPIClient` — Files API wrapper for document reuse
- `InterleavedThinkingLoop` — agentic thinking + tool-use loop
- `CostEstimator` — per-call USD cost with model-specific pricing

Combined effect: a 1,000-workload 6R scan costs ~$7–10 vs. ~$150 at
all-Opus list price.

### Known Limitations (as of v0.2.0)

- No multi-tenant RBAC — single org/user only
- No React/web UI — observability via Grafana; no app-layer dashboard
- Platform itself has not undergone SOC 2 Type II audit
- No hyperscaler marketplace listing
- Carbon coefficients are estimates; not suitable for regulatory carbon reporting

See [README.md#roadmap](../README.md#roadmap) for the full gap list.
