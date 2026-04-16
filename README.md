# Enterprise AI Accelerator

**Open-source AI governance, FinOps, and cloud migration intelligence. The capabilities consulting firms charge $500K for, automated and MIT licensed.**

[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](#)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![EU AI Act](https://img.shields.io/badge/EU%20AI%20Act-Article%2012%20compliant-orange.svg)](#ai-audit-trail)
[![FOCUS 1.3](https://img.shields.io/badge/FOCUS-1.3%20compliant-purple.svg)](#finops-intelligence)
[![Claude Opus 4.7](https://img.shields.io/badge/Claude-Opus%204.7-black.svg)](docs/OPUS_4_7_UPGRADE.md)
[![Prompt Caching](https://img.shields.io/badge/prompt%20caching-5m%20%2B%201h-8A2BE2.svg)](docs/OPUS_4_7_UPGRADE.md)
[![Extended Thinking](https://img.shields.io/badge/extended%20thinking-Annex%20IV%20audit%20trail-orange.svg)](docs/OPUS_4_7_UPGRADE.md)
[![1M Context](https://img.shields.io/badge/context-1M%20tokens-informational.svg)](docs/OPUS_4_7_UPGRADE.md)
[![Batch API](https://img.shields.io/badge/batch%20API-50%25%20discount-green.svg)](docs/OPUS_4_7_UPGRADE.md)

> **April 2026 — Opus 4.7 Executive Upgrade.** Platform now runs on Claude
> Opus 4.7 across every auditable path, with prompt caching, native
> tool-use structured output, extended-thinking reasoning traces as Annex
> IV evidence, a 1M-context executive chat, and Batch API bulk scoring.
> See [docs/OPUS_4_7_UPGRADE.md](docs/OPUS_4_7_UPGRADE.md) for the full
> executive brief.

---

## The Problem

Enterprise AI governance is fragmented. No single tool covers compliance, cost, migration risk, and security together — so firms pay Accenture, Deloitte, or PwC $150K–$500K and wait 6–12 weeks for a report that should take hours.

Meanwhile, the EU AI Act high-risk system obligations hit on **August 2, 2026** (113 days). AWS Migration Hub closed to new customers in November 2025. FOCUS 1.3 billing normalization is now required by major enterprise FinOps frameworks. The tools to meet these deadlines either don't exist as open source or are siloed point solutions with no cross-module risk view.

This platform closes all four gaps.

---

## Six Modules, One Risk Score

| Module | What It Does | Key Differentiator | Run |
|---|---|---|---|
| **AIAuditTrail** | Tamper-evident AI decision logging with EU AI Act Article 12/62 compliance + NIST AI RMF | Only OSS tool combining OTEL + SARIF 2.1.0 + Article 12. IBM OpenPages costs $500K/yr. | `python -m ai_audit_trail.demo` |
| **FinOps Intelligence** | Multi-cloud cost tracking, anomaly detection, commitment optimization | Only OSS tool combining FOCUS 1.3 billing normalization + AI/LLM model cost tracking | `python -m finops_intelligence.demo` |
| **MigrationScout** | AI-native 6R workload classification, dependency mapping, Monte Carlo wave planning | Only OSS tool with AI-native 6R + Monte Carlo wave planning. AWS Migration Hub closed Nov 2025. | `python -m migration_scout.demo` |
| **PolicyGuard** | Compliance scanning across EU AI Act, HIPAA, SOC 2, PCI-DSS, CIS AWS, NIST SP 800-53 | Multi-framework cross-mapping: one implementation covers 3 regulatory frameworks | `python -m policy_guard.demo` |
| **CloudIQ** | AWS infrastructure analysis — security score, cost waste identification, right-sizing | $47K/month waste identified in a single AcmeCorp demo without AWS credentials | `python -m cloud_iq.demo` |
| **Risk Aggregator** | Unified 0–100 risk score correlating signals from all five modules | No competitor correlates security findings + FinOps waste + migration complexity + AI governance in one score | `python risk_aggregator.py` |
| **ExecutiveChat** *(new)* | 1M-context CTO chat grounded in the full enterprise briefing — architecture, migration, compliance, FinOps, audit posture | Opus 4.7 1M context + 1-hour prompt cache — follow-up questions cost ~10% of the first | `from executive_chat import ExecutiveChat` |
| **ComplianceCitations** *(new)* | Evidence-grounded regulatory Q&A with character-range citations (CIS, SOC 2, HIPAA, PCI-DSS, EU AI Act Annex IV) | Anthropic Citations API — every claim links to source document span, no hallucinated control IDs | `from compliance_citations import EvidenceLibrary` |

---

## Opus 4.7 Capabilities in This Release

| Capability | Where it lives | Why it matters |
|---|---|---|
| **Prompt caching (5-min + 1-hour)** | `core/ai_client.py` | ~90% input-token cost reduction on repeat pipelines and executive chat follow-ups |
| **Native tool-use structured output** | Every agent + MCP dispatcher | Replaces fragile JSON-regex parsing — every model response is schema-validated |
| **Extended thinking (up to 32k reasoning tokens)** | `migration_scout/thinking_audit.py`, `policy_guard/thinking_audit.py` | Reasoning trace is persistable as EU AI Act Annex IV technical documentation |
| **1M-token context** | `executive_chat/` | Entire enterprise briefing loads into one system prompt — no chunking, no retrieval loop |
| **Citations API** | `compliance_citations/` | Grounds compliance claims in cited regulatory text — auditor-ready evidence trail |
| **Message Batches API (50% discount)** | `migration_scout/batch_classifier.py`, `finops_intelligence/batch_processor.py` | Bulk 6R classification + bulk FinOps explanation at half list price |
| **Unified MCP surface (19 tools)** | `mcp_server.py` | Every module is drivable from Claude Code / Claude Desktop without writing integration code |

See [docs/OPUS_4_7_UPGRADE.md](docs/OPUS_4_7_UPGRADE.md) for the full executive brief, token economics, and compliance mapping.

---

## How We Compare

| Feature | enterprise-ai-accelerator | AgentLedger | AIR Blackbox | ai-trace-auditor | Aulite | Langfuse | Credo AI |
|---------|--------------------------|-------------|--------------|------------------|--------|----------|----------|
| EU AI Act Art.12 | Yes (full) | Yes | Yes (6 articles) | Yes (Art.11-13,25) | Yes | No | Yes |
| SARIF 2.1.0 export | Yes | No | No | No | No | No | No |
| OpenTelemetry | Yes (native) | No | Yes (proxy) | Yes (consumer) | No | Yes (v3) | No |
| Tamper-proof chain | SHA-256 Merkle | SHA-256 SQLite | HMAC-SHA256 | No | No | No | Unknown |
| Python SDK | Yes | Yes | Yes | CLI only | No (TypeScript) | Yes | SaaS |
| Streamlit UI | Yes | No | No | No | No | Yes (web) | Yes (SaaS) |
| Test suite | 418 tests | Unknown | Unknown | Unknown | Unknown | Yes | N/A |
| License | MIT | MIT | Apache 2.0 | Unknown | Unknown | MIT (core) | Proprietary |
| Cost | Free | Free | Free | Free | Free | Free (self-host) | $50K+/yr |
| GitHub stars | New | ~5 | 12 | ~10 | 26 | 24,677 | N/A |

The SARIF 2.1.0 + OpenTelemetry + Article 12 combination is unique in the open-source ecosystem. No other tool produces GitHub Security tab-compatible compliance findings while also generating OTEL traces for enterprise observability stacks. Commercial alternatives like Credo AI and Holistic AI cover compliance but cost $50K–$500K/year and are closed-source.

---

## Architecture

The Risk Aggregator is the connective layer. Each module produces structured output; the aggregator weights them into a single executive-level score with a three-sentence narrative.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Entry Points                                 │
│     CLI  ·  FastAPI (per module, ports 8001–8005)  ·  Python SDK    │
└────┬──────────────┬──────────────┬──────────────┬───────────────────┘
     │              │              │              │
┌────▼────┐  ┌──────▼──────┐  ┌───▼───────┐  ┌──▼──────────────────┐
│ CloudIQ │  │  FinOps     │  │Migration  │  │   PolicyGuard        │
│         │  │Intelligence │  │  Scout    │  │  (+ BiasDetector)    │
│AWS scan │  │FOCUS 1.3    │  │6R + Monte │  │EU AI Act · HIPAA     │
│cost IDs │  │AI cost track│  │Carlo waves│  │SOC2 · PCI-DSS · NIST │
└────┬────┘  └──────┬──────┘  └───┬───────┘  └──┬──────────────────┘
     │              │              │              │
     └──────────────┴──────────────┴──────────────┘
                              │
                 ┌────────────▼────────────┐
                 │     AIAuditTrail        │
                 │  SHA-256 Merkle chain   │
                 │  SARIF 2.1.0 export     │
                 │  Article 12/62 logging  │
                 │  NIST AI RMF mapping    │
                 └────────────┬────────────┘
                              │
                 ┌────────────▼────────────┐
                 │    Risk Aggregator      │
                 │  Weighted 0–100 score   │
                 │  Security   35%         │
                 │  FinOps     25%         │
                 │  Migration  20%         │
                 │  AI Gov.    20%         │
                 └────────────┬────────────┘
                              │
              ┌───────────────┼───────────────┐
              │                               │
     ┌────────▼────────┐            ┌─────────▼─────────┐
     │  GitHub Actions  │            │    Jira / Slack    │
     │  SARIF upload    │            │    Alert delivery  │
     │  (Security tab)  │            │    Ticket creation │
     └──────────────────┘            └───────────────────┘
```

**Data flow:** Each module runs independently or as a pipeline. CloudIQ and FinOps Intelligence feed MigrationScout's TCO calculator. PolicyGuard's SARIF output uploads directly to GitHub's Security tab. AIAuditTrail wraps any module's output in a tamper-evident log entry. The Risk Aggregator accepts output from any combination of modules — all fields optional.

---

## Quick Start

**Three commands to run any module demo (no cloud credentials required):**

```bash
git clone https://github.com/HunterSpence/enterprise-ai-accelerator.git
cd enterprise-ai-accelerator
pip install -r requirements.txt
```

Then run any module:

```bash
# AI governance + EU AI Act compliance (3 enterprise scenarios)
python -m ai_audit_trail.demo

# $340K/month cloud spend optimization ($89.4K/month identified)
python -m finops_intelligence.demo

# 75-workload migration plan, Oracle $420K/yr license elimination
python -m migration_scout.demo

# EU AI Act compliance scanner (Fortune 500 hiring AI + healthcare AI)
python -m policy_guard.demo

# AWS infrastructure analysis ($47,200/month waste identified)
python -m cloud_iq.demo
```

**All demos run on synthetic data. No AWS credentials, no Anthropic API key required to see output.**

For the FastAPI module servers:

```bash
# Individual module API (example: PolicyGuard on port 8003)
cd policy_guard && uvicorn api:app --port 8003

# All modules (ports 8001–8005)
python scripts/run_all.py
```

Docker support: each module has its own `Dockerfile` and `docker-compose.yml`.

---

## Module Details

### AIAuditTrail

Tamper-evident audit logging for AI decisions. Built for the EU AI Act Article 12 (Annex IV) logging obligations that become legally enforceable August 2, 2026.

**What it actually does:**
- SHA-256 Merkle hash chain: every log entry hashes the previous entry. Any database modification invalidates all subsequent hashes and is detected in O(log n) time via Merkle proofs.
- Article 12 Annex IV compliance: mandatory fields (decision type, risk tier, model, input/output tokens, latency, system ID, cost in USD) structured per the regulation text.
- Article 62 incident reporting: P0/P1/P2 severity ladder with automatic 72-hour regulatory deadline tracking. Auto-generates the Article 62 report document.
- NIST AI RMF dual-framework mapping: GOVERN / MAP / MEASURE / MANAGE scored 0–5.0 with maturity level classification.
- Bias detection: identifies disparate impact patterns in loan/hiring/scoring decision logs (name-correlated decline rate analysis).
- SARIF 2.1.0 export: compliance findings upload directly to GitHub Security tab via existing CI/CD pipeline.
- 5 SDK integrations: decorator-based drop-in for OpenAI, Anthropic, LangChain, LlamaIndex, and raw HTTP calls.

**The demo runs three scenarios:** enterprise deploy of 3 AI systems simultaneously (50+ audit entries, Merkle checkpoint), a loan model bias incident (P0-DISCRIMINATION raised, Article 62 report generated, 72-hour deadline shown), and a 90-day regulator audit request (2,500 entries, tamper injected and caught).

**Cost comparison:** $0 vs IBM OpenPages ($500K/yr) vs Credo AI ($180K/yr).

```bash
python -m ai_audit_trail.demo
```

---

### FinOps Intelligence

Multi-cloud cost intelligence with FOCUS 1.3 billing normalization and AI/LLM token cost tracking.

**What it actually does:**
- Ingests 847,000 billing rows for TechCorp Enterprise ($340K/month spend) and identifies $89,400/month in optimization opportunities ($1.07M/year).
- FOCUS 1.3 exporter: converts spend data to the FinOps Foundation Open Cost and Usage Specification format — all 33 required columns plus FOCUS 1.2/1.3 optional columns. Parquet export for FOCUS 1.4-ready columnar output.
- AI/LLM cost rows: per-model token spend (input + output) in FOCUS format — unique in OSS tooling.
- Ensemble anomaly detection: statistical + ML-based cost spike identification.
- Commitment optimizer: Reserved Instance and Savings Plan purchase recommendations.
- Natural language query interface: ask cost questions in plain English against the DuckDB-backed analytics engine.
- Unit economics engine: cost-per-user, cost-per-transaction, cost-per-API-call breakdowns.
- CFO-ready report generation.

**Competitor gap:** OpenCost (6.4K GitHub stars) is Kubernetes-only with no FOCUS support. LiteLLM tracks AI model costs but has no billing normalization. No OSS tool combines both.

```bash
python -m finops_intelligence.demo
```

---

### MigrationScout

AI-native cloud migration planning. 75-workload RetailCo demo: 6 migration waves, Oracle $420K/yr license elimination, $1.2M 3-year net savings, 14-month payback.

**What it actually does:**
- 6R classification per workload (Rehost, Replatform, Repurchase, Refactor, Retire, Retain) with AI reasoning for each decision.
- Dependency mapper: identifies circular dependency loops (SCC — Strongly Connected Components resolution) and proposes containerize-first workarounds.
- Monte Carlo wave planner: probabilistic effort estimation with confidence intervals, not deterministic point estimates.
- TCO calculator: 3-year total cost of ownership including license elimination, managed service migration, and RI coverage.
- Runbook generator: produces migration runbooks per wave.
- AWS MAP alignment: Assess / Mobilize / Migrate phase mapping.

**Market context:** AWS Migration Hub closed to new customers November 7, 2025. AWS Transform (its replacement) handles only .NET and mainframe code modernization — no general-purpose 6R classification or wave planning. Azure Copilot Migration Agent is Azure-only. MigrationScout is the only open-source tool filling this gap.

```bash
python -m migration_scout.demo
# --no-ai flag skips Claude API calls for CI runs
# --waves 3 runs first 3 waves only
```

---

### PolicyGuard

Multi-framework compliance scanner for AI systems and cloud infrastructure. Annex III category classification, bias detection, and incident response.

**What it actually does:**
- EU AI Act compliance scanning: Annex III category assignment (employment, credit, healthcare, law enforcement), risk tier classification, documentation completeness scoring.
- Cross-framework efficiency: one control implementation maps to EU AI Act + HIPAA + SOC 2 simultaneously.
- Bias detector: statistical disparate impact analysis across demographic proxies.
- Incident response engine: P0/P1/P2/P3 severity ladder with SLA tracking.
- SARIF exporter: findings exported in SARIF 2.1.0 format for GitHub Security tab integration.
- Remediation generator: produces remediation plans with effort estimates and compliance score projections.
- Dashboard renderer: live Rich UI showing compliance posture across all scanned systems.

**The demo runs two scenarios:** Fortune 500 with an AI hiring system (17% baseline compliance → 89% after remediation, Annex III Category 4 Employment) and a healthcare AI diagnostic (HIPAA PHI + EU AI Act HIGH RISK + SOC 2 AICC cross-framework).

```bash
python -m policy_guard.demo
# --scenario=a or --scenario=b for individual scenarios
# --bias runs the bias detection scenario
```

---

### CloudIQ

AWS infrastructure analysis: security posture, cost waste identification, right-sizing, and compliance pre-checks.

**What it actually does:**
- Scans EC2, EBS, RDS, S3, ECS, EKS, Lambda, ElastiCache, VPC, and Elastic IP resources.
- Identifies $47,200/month in waste for AcmeCorp demo (right-sizing, orphaned volumes, idle capacity, Shadow IT).
- Natural language query interface (NL query engine) for ad hoc analysis.
- Terraform generator: produces right-sized replacement configs.
- ML-based anomaly detection for cost spikes and configuration drift.
- K8s analyzer for container workload optimization.
- Multi-provider support: AWS, Azure, GCP provider modules.

```bash
python -m cloud_iq.demo
```

---

### Risk Aggregator

The connective layer. Combines signals from all five modules into a single 0–100 workload risk score with dimensional breakdown and executive narrative.

**Dimension weights (tuned to CTO/CISO priorities):**
- Security compliance: 35% (regulatory and reputational exposure)
- Financial waste: 25% (direct P&L impact)
- Migration complexity: 20% (project delivery risk)
- AI governance: 20% (increasing regulatory urgency)

Critical findings apply a 1.25x severity multiplier. The aggregator accepts output from any combination of modules — all inputs are optional. Output includes: overall score, risk tier, top three risk drivers, and a three-sentence executive narrative for board-level consumption.

```python
from risk_aggregator import WorkloadRiskAggregator, RiskInput

risk = WorkloadRiskAggregator()
score = risk.compute(RiskInput(
    policy_score=72.0,
    policy_critical_findings=3,
    finops_waste_pct=38.5,
    migration_risk_score=65,
    audit_trail_present=True,
    ai_systems_count=3,
))

print(f"Overall Risk: {score.overall_score}/100 ({score.risk_tier})")
print(score.executive_narrative)
```

---

## Why This Matters Now

**EU AI Act — August 2, 2026:** High-risk AI system obligations (Articles 8–25) become enforceable in 113 days. Logging, documentation, human oversight, and incident reporting requirements apply to any AI system in employment, credit scoring, healthcare, education, or law enforcement categories. Article 62 requires serious incident reporting to national supervisory authorities within 72 hours. Non-compliance: up to 3% of global annual turnover.

**AWS Migration Hub closure — November 7, 2025:** The standard OSS migration planning tool is gone. AWS Transform covers only .NET and mainframe. The market gap for general-purpose migration intelligence is open.

**FOCUS 1.3 adoption:** The FinOps Foundation's Open Cost and Usage Specification is now the basis for multi-cloud billing normalization across enterprise FinOps platforms. Organizations without FOCUS-compliant tooling face manual data transformation across every cloud billing export.

---

## Competitive Landscape

| | Enterprise AI Accelerator | Accenture MyNav / Deloitte Navigate | IBM OpenPages | OpenCost | LiteLLM |
|---|---|---|---|---|---|
| **License** | MIT (open source) | Closed, $150K–$500K engagement | $500K/yr SaaS | Apache 2.0 | MIT |
| **EU AI Act Article 12** | Full (Merkle chain + SARIF) | Manual / bespoke | Partial | None | None |
| **FOCUS 1.3 billing** | Yes (all 33 columns + AI rows) | No | No | No | No |
| **AI/LLM cost tracking** | Yes (FOCUS format) | No | No | No | Yes (no normalization) |
| **6R migration planning** | Yes (AI-native + Monte Carlo) | Yes (manual workshops) | No | No | No |
| **Multi-framework compliance** | EU AI Act + HIPAA + SOC 2 + PCI-DSS + NIST | Varies by engagement | SOC 2 / GRC focus | No | No |
| **Cross-module risk score** | Yes (Risk Aggregator) | No | No | No | No |
| **Time to first output** | Minutes (demo, no credentials) | 6–12 weeks | Weeks of setup | Hours (K8s only) | Minutes |
| **Cloud provider** | AWS + Azure + GCP | All | All | K8s (cloud-agnostic) | All |

---

## For Consulting Firms

If you're an AI practice lead at Accenture, Deloitte, Cognizant, PwC, Infosys, or Slalom, this platform addresses the gap between what clients need and what your current tooling delivers:

**Pre-engagement scoping:** Feed a client's architecture description into CloudIQ before the kickoff call. Walk in with preliminary findings instead of blank slides.

**Migration assessment acceleration:** MigrationScout classifies a 75-workload inventory in minutes with dependency-resolved wave plans. The activity that normally consumes 3 weeks of workshops runs as a pipeline.

**EU AI Act readiness:** PolicyGuard + AIAuditTrail give clients a compliance posture and audit-ready logging before your formal assessment begins. The Article 62 incident response module is production-ready today.

**Cost justification:** FinOps Intelligence quantifies the financial case in FOCUS 1.3 format — the billing standard your clients' procurement and FinOps teams already understand.

**The platform handles the 80% that is pattern-matching.** Human expertise still owns stakeholder management, change leadership, and edge-case judgment. This is acceleration infrastructure, not a replacement.

White-label and enterprise licensing inquiries: hunter@vantaweb.io

---

## Requirements

```
Python 3.11+
anthropic>=0.40.0
rich>=13.7.0
```

Per-module dependencies (heavier ML/data libraries) are listed in each module's `requirements.txt`. The core demos run on the two packages above.

For FinOps Intelligence: `duckdb`, `pandas` (analytical engine). For PolicyGuard: `fastapi`, `uvicorn` (API server). Full dependency list: see `docs/QUICKSTART.md`.

---

## Repository Structure

```
enterprise-ai-accelerator/
├── ai_audit_trail/          EU AI Act logging + NIST AI RMF + incident management
│   ├── chain.py             SHA-256 Merkle hash chain (stdlib only)
│   ├── eu_ai_act.py         Article 12/62 compliance engine
│   ├── nist_rmf.py          GOVERN/MAP/MEASURE/MANAGE scoring
│   ├── incident_manager.py  P0-P3 severity + Article 62 deadline tracking
│   ├── decorators.py        Drop-in SDK integrations (5 frameworks)
│   └── demo.py              3-scenario enterprise demo
├── finops_intelligence/     FOCUS 1.3 FinOps + AI cost tracking
│   ├── focus_exporter.py    FOCUS 1.3 schema (all 33 columns + AI rows)
│   ├── analytics_engine.py  DuckDB-backed cost analytics
│   ├── anomaly_detector_v2.py  Ensemble anomaly detection
│   ├── commitment_optimizer.py RI/SP recommendations
│   └── demo.py              TechCorp $340K/month scenario
├── migration_scout/         6R classification + wave planning
│   ├── assessor.py          AI-native 6R workload classifier
│   ├── dependency_mapper.py SCC circular dependency resolution
│   ├── wave_planner.py      Monte Carlo migration wave planner
│   ├── tco_calculator.py    3-year TCO with license elimination
│   └── demo.py              RetailCo 75-workload scenario
├── policy_guard/            Multi-framework compliance scanner
│   ├── scanner.py           EU AI Act + HIPAA + SOC2 + PCI-DSS scanner
│   ├── bias_detector.py     Statistical disparate impact analysis
│   ├── sarif_exporter.py    SARIF 2.1.0 → GitHub Security tab
│   ├── incident_response.py P0-P3 severity + SLA tracking
│   └── demo.py              Hiring AI + Healthcare AI scenarios
├── cloud_iq/                AWS infrastructure analysis
│   ├── scanner.py           Multi-resource AWS scanner
│   ├── cost_analyzer.py     Waste identification + right-sizing
│   ├── ml_detector.py       Anomaly detection
│   └── demo.py              AcmeCorp $47K/month waste scenario
├── risk_aggregator.py       Cross-module unified risk score
└── docs/
    ├── QUICKSTART.md        Step-by-step setup (Docker + local)
    └── ARCHITECTURE.md      Module interactions + data flow
```

---

## Author

**Hunter Spence**
4 years at Accenture, Infrastructure Transformation (CL-9). Delivered cloud migration engagements across enterprise clients. AWS Certified Cloud Practitioner.

[LinkedIn](https://linkedin.com/in/hunterspence) · [Email](mailto:hunter@vantaweb.io) · [VantaWeb](https://vantaweb.io)

---

## License

MIT. Use it, extend it, white-label it. See [LICENSE](LICENSE).

*Built because the gap between what Big 4 firms charge and what the technology can do autonomously is no longer defensible.*
