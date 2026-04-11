# Enterprise AI Accelerator

**What Accenture charges $50M for. Open source. Runs in 5 minutes.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![Claude Powered](https://img.shields.io/badge/powered%20by-Claude%20(Anthropic)-orange.svg)](https://anthropic.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Multi-Agent](https://img.shields.io/badge/architecture-multi--agent-purple.svg)](#agentops)
[![Patent Pending](https://img.shields.io/badge/AI%20agent%20framework-patent--pending-red.svg)](#)

---

## The Problem

Cloud migrations at enterprise scale have a cost problem — and it's not the cloud bill.

- **Consulting fees run $15M–$100M** for a standard cloud migration (Accenture, Deloitte, EY). 12–18 months. 50–200 consultants. Opaque pricing.
- **35–40% of cloud infrastructure spend is wasted** on oversized instances, orphaned resources, and mis-architected workloads (AWS Well-Architected benchmark data).
- **Compliance gaps discovered late cost $2M–$20M** in remediation, fines, or delayed launches — HIPAA, SOC2, PCI-DSS violations caught after the fact.

The existing answer is: hire a Big 4 firm. They send consultants with spreadsheets and PowerPoints. You get a roadmap in month nine.

This project is the other answer.

---

## What This Does

Six AI-powered modules that replace the core deliverables of a $50M cloud migration engagement. Each runs in minutes, not months.

| Module | What It Does | Business Value |
|---|---|---|
| **CloudIQ** | AWS architecture analyzer: security score, cost waste, migration readiness | Replaces a 6-week Well-Architected Review |
| **MigrationScout** | 6R workload classifier with phased migration roadmap | Replaces a $2M–$5M migration planning engagement |
| **PolicyGuard** | IaC compliance checker (SOC2, HIPAA, PCI-DSS, CIS-AWS, NIST) | Catches violations before they become $10M+ fines |
| **CostAnalyzer** | Financial impact calculator: ROI, 3-year savings, quick wins | Quantifies the business case for board approval |
| **ExecutiveReport** | Board-ready HTML report generator | Replaces the $150K/month slide deck engagement |
| **AgentOps** | Multi-agent orchestration monitor — parallel Claude agents working in real time | The infrastructure layer that makes all of this fast |

**Integrations:** Slack (alert delivery) + Jira (ticket creation from findings)

---

## Live Demo

```bash
$ python accelerator.py analyze --account prod-aws-123

[CloudIQ]      Scanning 847 resources across us-east-1, us-west-2...
[PolicyGuard]  Checking 23 Terraform modules against SOC2, HIPAA, PCI-DSS...
[CostAnalyzer] Analyzing spend patterns across 6 months of Cost Explorer data...

SECURITY SCORE:     64/100  (3 CRITICAL, 11 HIGH findings)
COST WASTE:         $47,200/month identified (38% of current spend)
COMPLIANCE STATUS:  FAIL — 4 HIPAA violations, 2 PCI-DSS gaps
MIGRATION READY:    12 of 34 workloads (Rehost/Replatform candidates highlighted)

3-YEAR SAVINGS:     $1.7M  (after migration and right-sizing)
QUICK WINS:         $14,400/month recoverable in < 30 days

[ExecutiveReport]   Board-ready PDF generated → report_prod-aws-123_20260411.html
[AgentOps]          6 parallel agents completed in 4m 12s
```

Full report includes: executive summary, module-by-module findings, remediation roadmap, ROI waterfall chart.

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/hunterspence/enterprise-ai-accelerator.git
cd enterprise-ai-accelerator
pip install -r requirements.txt

# 2. Set your keys
cp .env.example .env
# Add ANTHROPIC_API_KEY and AWS credentials

# 3. Run
python accelerator.py analyze --account your-aws-account-id
```

AWS credentials need read-only access: `ReadOnlyAccess` IAM policy is sufficient. No write permissions required.

---

## Module Deep-Dives

### CloudIQ — AWS Architecture Analyzer

Performs a programmatic Well-Architected Review across five pillars: Security, Reliability, Performance, Cost Optimization, and Operational Excellence.

**What it scans:**
- IAM: overprivileged roles, root key usage, MFA enforcement
- Networking: public S3 buckets, unrestricted security groups (0.0.0.0/0)
- Compute: right-sizing opportunities, reserved instance coverage gaps
- Storage: unattached EBS volumes, S3 lifecycle gaps, cross-region transfer waste
- Encryption: unencrypted RDS snapshots, EBS volumes, S3 buckets at rest

**Output:** Scored findings by severity, mapped to AWS Well-Architected Framework pillars. Exportable as JSON for integration into existing tooling.

**Replaces:** A 4–6 week manual Well-Architected Review engagement, typically $150K–$300K at Big 4 rates.

---

### MigrationScout — 6R Migration Planner

Classifies workloads against the six migration strategies (Rehost, Replatform, Repurchase, Refactor, Retire, Retain) and generates a phased roadmap with dependency mapping.

**What it analyzes:**
- Application dependencies (from AWS Application Discovery Service or manual input)
- Database engine compatibility with managed services (RDS, Aurora)
- Containerization readiness signals
- Licensing cost implications (Windows Server, SQL Server)
- Business criticality vs. migration complexity scoring

**Output:** A ranked workload list with recommended strategy per application, phased migration waves (typically 3–4 waves over 12 months), and effort estimates by wave.

**Replaces:** The migration planning phase of a cloud migration engagement — typically 3–4 months and $2M–$5M in consulting fees.

---

### PolicyGuard — IaC Compliance Checker

Scans Terraform, CloudFormation, and CDK infrastructure-as-code against five regulatory frameworks before deployment.

**Frameworks supported:**
- SOC 2 Type II (Security, Availability, Confidentiality)
- HIPAA (Administrative, Physical, Technical Safeguards)
- PCI-DSS v4.0 (Network security, access control, encryption)
- CIS AWS Foundations Benchmark v2.0
- NIST SP 800-53 (Federal baseline)

**What it catches:**
- Publicly accessible RDS instances
- S3 buckets without encryption or versioning
- CloudTrail disabled or incomplete logging
- Security groups with unrestricted inbound access
- Missing deletion protection on production databases
- Non-compliant KMS key rotation policies

**Output:** Violation report with severity, affected resource, regulatory citation, and Terraform remediation snippet.

**The cost case:** A single HIPAA violation discovered post-deployment averages $1.5M in remediation and penalties. PolicyGuard catches it in the PR.

---

### CostAnalyzer — Financial Impact Calculator

Translates technical findings into CFO-readable financial projections. This is what gets budget approved.

**What it calculates:**
- Monthly waste identified (right-sizing, orphaned resources, idle capacity)
- Quick wins: savings achievable within 30 days with zero architectural changes
- 3-year TCO comparison: current state vs. optimized vs. migrated
- ROI timeline: months to break even on migration investment
- Reserved Instance / Savings Plan purchase recommendations

**Output:** ROI waterfall chart, 3-year savings projection table, executive summary paragraph (board-paste-ready).

---

### ExecutiveReport — Board-Ready Report Generator

Assembles all module outputs into a single HTML report designed for C-suite consumption. No engineering jargon. No raw JSON.

**Report sections:**
- Executive Summary (1 page, written in business language)
- Financial Impact Overview (the numbers that matter)
- Security Risk Register (prioritized, with business impact, not just CVE IDs)
- Migration Roadmap (Gantt-style timeline)
- Compliance Status Dashboard
- Recommended Next Steps (30/60/90-day plan)

**Output:** Self-contained HTML file. No external dependencies. Send as email attachment or host internally.

---

### AgentOps — Multi-Agent Orchestration Monitor

The infrastructure layer. When you run a full analysis, AgentOps coordinates six Claude agents running in parallel — one per module — and monitors their execution in real time.

**What it does:**
- Spawns parallel Claude agents with module-specific tool access
- Tracks agent state, token usage, and execution time per agent
- Surfaces inter-agent dependencies (MigrationScout uses CloudIQ output)
- Aggregates results into the unified report pipeline
- Logs all agent reasoning traces for auditability

**Why this matters:** A sequential execution takes 20–30 minutes. Parallel multi-agent execution completes in under 5 minutes on a standard AWS account with 500–1,000 resources. At 5,000+ resources, the difference is hours vs. minutes.

This is a production Claude deployment pattern — not a demo. The same multi-agent orchestration architecture underlies the patent-pending AI agent framework this project is built on.

---

## Comparison

| | Accenture Cloud Migration Factory | Manual In-House | Enterprise AI Accelerator |
|---|---|---|---|
| **Cost** | $15M–$100M | $2M–$10M (staff + time) | Open source |
| **Timeline** | 12–18 months | 18–24 months | First report in 5 minutes |
| **Team size** | 50–200 consultants | 5–20 engineers | 1 engineer + Claude |
| **Compliance checks** | Manual review, point-in-time | Depends on team knowledge | Automated, every commit |
| **Executive reporting** | Bespoke deck, $150K/month | Ad hoc | Automated HTML, every run |
| **Transparency** | Opaque deliverables | Internal only | Open source, auditable |
| **Lock-in** | Heavy (managed services contracts) | Low | None |
| **Dependency mapping** | Manual workshops (months) | Manual | Automated (MigrationScout) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CLI / API Entry Point                   │
│              accelerator.py analyze --account X            │
└────────────────────────┬────────────────────────────────────┘
                         │
                    ┌────▼─────┐
                    │ AgentOps │  Multi-agent orchestrator
                    │ Monitor  │  Spawns + monitors parallel agents
                    └────┬─────┘
          ┌──────────────┼──────────────┐
          │              │              │
    ┌─────▼──────┐ ┌─────▼──────┐ ┌───▼────────┐
    │  CloudIQ   │ │PolicyGuard │ │CostAnalyzer│
    │  (AWS API) │ │  (IaC scan)│ │(Cost Expl.)│
    └─────┬──────┘ └─────┬──────┘ └───┬────────┘
          │              │              │
    ┌─────▼──────────────▼──────────────▼────────┐
    │              MigrationScout                 │
    │  Consumes CloudIQ + Cost findings           │
    │  Outputs: 6R classification + roadmap       │
    └─────────────────────┬───────────────────────┘
                          │
                ┌─────────▼──────────┐
                │  ExecutiveReport   │
                │  Assembles all     │
                │  module outputs    │
                │  → board-ready HTML│
                └─────────┬──────────┘
                          │
           ┌──────────────┼──────────────┐
           │                             │
    ┌──────▼──────┐             ┌────────▼──────┐
    │    Slack    │             │     Jira      │
    │  (Alerts)   │             │  (Tickets)    │
    └─────────────┘             └───────────────┘
```

Each module uses Claude with tool access scoped to its domain. CloudIQ has AWS read-only tools. PolicyGuard has filesystem access for IaC scanning. CostAnalyzer has Cost Explorer API access. No module can exceed its granted tool scope — this is enforced at the AgentOps orchestration layer.

---

## Patent-Pending Framework

The multi-agent orchestration pattern in AgentOps — specifically the approach to scoped tool access, inter-agent dependency resolution, and parallel execution with result aggregation — is part of a patent-pending AI agent framework.

The open-source implementation here demonstrates the core concepts. Enterprise licensing inquiries: see contact below.

---

## Who This Is For

**Cloud/infrastructure engineers** building the business case for a migration and need a defensible cost and risk analysis fast.

**CTOs and VPs of Engineering** who need to present migration ROI to the board without commissioning a $500K consulting study first.

**Chief AI Officers and digital transformation leads** at consulting firms evaluating what AI-native tooling looks like versus the consultant-and-spreadsheet status quo.

**Enterprises mid-migration** who want continuous compliance validation and cost monitoring, not a point-in-time assessment.

---

## Requirements

- Python 3.11+
- Anthropic API key (Claude Sonnet or Opus recommended for full analysis)
- AWS credentials (ReadOnlyAccess IAM policy minimum)
- For PolicyGuard: Terraform/CloudFormation files accessible locally or via S3
- For Jira integration: Jira API token + project key

Tested on: Linux (Ubuntu 22.04), macOS 14, Windows 11. Docker support coming.

---

## Roadmap

- [ ] Azure and GCP support (CloudIQ + MigrationScout)
- [ ] Terraform remediation auto-generation (PolicyGuard)
- [ ] Continuous monitoring mode (scheduled scans, drift detection)
- [ ] Docker deployment for enterprise self-hosting
- [ ] SSO / RBAC for multi-team use
- [ ] API server mode for CI/CD pipeline integration

---

## Author

**Hunter Spence**  
Ex-Accenture, Infrastructure Transformation (CL-9) — 4 years delivering cloud migration engagements across enterprise clients.

AWS Certified Cloud Practitioner. Builder of production Claude deployments.

[LinkedIn](https://linkedin.com/in/hunterspence) · [Email](mailto:hunter@vantaweb.io) · [VantaWeb](https://vantaweb.io)

---

*Built because the gap between what Big 4 firms charge and what the technology can do autonomously is no longer defensible.*
