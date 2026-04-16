# Case Study: Ironside Insurance

## AI-Accelerated Cloud Transformation at a Fortune 500 Insurance Carrier
### From 18-Month Engagement to 6-Week Delivery

> This is a fictional but realistic case study illustrating platform capabilities
> against a representative F500 engagement. Ironside Insurance is not a real company.
> All metrics are based on platform output patterns; financial figures are synthetic.

---

## Background

Ironside Insurance is a $8B-revenue P&C insurance carrier headquartered in
Hartford, Connecticut. The company operates across 14,000 cloud workloads spanning
AWS (primary), Azure (M&A legacy), and a Kubernetes-managed private cloud at two
co-location facilities. Their Terraform estate spans 200 modules across 47
repositories, and the application portfolio runs 400 microservices, most of them
inherited from three acquisitions between 2019 and 2023.

Ironside had engaged Accenture's MyNav practice 18 months earlier to produce a
cloud transformation roadmap. The engagement delivered a 380-page PowerPoint deck
and a migration backlog for $2.4M. By late 2025, the deck was largely ignored —
the inventory was stale, the 6R recommendations hadn't accounted for a major
acquisition, and the compliance team had flagged the Accenture deliverable as
insufficient for EU AI Act Annex IV purposes because Ironside was rolling out an
AI-assisted underwriting tool across the EU.

The EU AI Act's high-risk system enforcement deadline — August 2, 2026 — was
fourteen months away. Ironside's Head of Cloud, Marcus Tan, put it plainly in the
kickoff call: "We need a living system, not a slide deck. And we need the AI
governance story ready before the regulators ask for it."

---

## Week 1 — Platform Deployment and Initial Discovery

The platform deployed in a single `docker-compose up` across a dedicated EC2
`r6a.4xlarge` (128 GB RAM, suitable for DuckDB's in-memory CUR analytics). AWS,
Azure, and Kubernetes adapters were configured with read-only IAM roles and a
service principal; no write permissions were provisioned.

The `cloud_iq` discovery adapter ran its first full sweep in 4 hours. It returned
**14,247 workloads** — 247 more than the Accenture deck had catalogued. The
discrepancy traced to three sources: 89 Azure workloads created after the Accenture
engagement closed, 112 Kubernetes pods that the previous inventory tool hadn't
enumerated from the private cloud clusters, and 46 workloads in a shadow AWS
account a development team had opened during the acquisition integration period.

Marcus's reaction, on reviewing the initial discovery report: "We've been making
decisions based on an inventory that was missing 1.7% of our estate. That's 247
workloads we had no visibility on."

The FinOps team simultaneously ingested 90 days of Cost and Usage Report data into
DuckDB via `finops_intelligence/cur_ingestor.py`. The initial analytics run
confirmed $11.2M in trailing-90-day cloud spend across the catalogued estate.

---

## Week 2 — Application Portfolio Scan

The `app_portfolio` scanner ran across all 400 microservice repositories, executing
language detection, CI maturity scoring, containerization assessment, CVE scanning,
and test coverage analysis in parallel. The scan completed overnight.

The findings landed hard. Ironside's Chief Compliance Officer, Dr. Elena Vasquez,
had assumed the acquisition integrations had normalized the portfolio. They had not.

- **312 repositories** had at least one critical CVE in their dependency tree,
  identified via batched OSV.dev queries across 9,847 unique package pins
- **89 repositories** had no Dockerfile — still running on bare VMs or
  Elastic Beanstalk legacy environments
- **167 repositories** had no CI pipeline whatsoever
- **42 repositories** showed zero commit activity in the past six months with
  fewer than 500 lines of active code — strong Retire candidates
- **23 repositories** had test coverage below 5%

The 6R scoring via Opus 4.7 extended thinking produced the following distribution
across the 400 services:

| Strategy | Count | Rationale |
|----------|-------|-----------|
| Retire | 42 | Dormant 6+ months, low LoC, no business owner found |
| Rehost | 89 | Already containerized, stable, no code change needed |
| Replatform | 156 | Need managed DB, autoscaling, minor config changes |
| Refactor | 88 | Active codebases with architectural tech debt, cloud-native target |
| Repurchase | 25 | Commodity functions with well-priced SaaS alternatives |
| Retain | 0 | No services recommended for on-prem retention |

For the 88 Refactor candidates — the highest-risk and highest-investment category —
the platform ran `ThinkingAudit`, generating extended-thinking reasoning traces for
each. These traces, averaging 8,000 tokens per service, were persisted to the
AIAuditTrail Merkle chain as Annex IV technical documentation.

Dr. Vasquez reviewed three of the Refactor reasoning traces during the week 2
readout. "This is what we needed from the beginning. Not a recommendation — an
explanation. I can show this to an auditor."

---

## Week 3 — IaC Security Scan

The `iac_security` scanner processed all 200 Terraform modules. The Terraform
parser walked each HCL file, extracted resource blocks, and evaluated them against
20 built-in compliance policies.

The results were worse than anyone expected.

**47 policy violations** were found, including **12 critical**:

- 4 S3 buckets with public access enabled (ACL `public-read` or `public-read-write`)
- 3 RDS instances with encryption disabled
- 2 security groups with `0.0.0.0/0` ingress on port 22 (open SSH)
- 2 security groups with `0.0.0.0/0` ingress on port 3306 (open MySQL)
- 1 EC2 launch template with IMDSv1 enabled (instance metadata v1 is deprecated
  and susceptible to SSRF attacks)

The 35 non-critical violations included untagged resources, missing VPC flow logs,
and IAM roles with overly broad inline policies.

The drift detector ran simultaneously, comparing the Terraform declarations against
the live AWS state discovered in Week 1. It found 23 resources declared in
Terraform that had no corresponding live workload (likely decommissioned without
IaC cleanup) and 31 live resources with no Terraform declaration — unmanaged
infrastructure created manually.

A CycloneDX SBOM was generated across all repositories and a SARIF 2.1.0 report
was produced, suitable for import into GitHub Advanced Security. Marcus's team
pushed the SARIF directly into their GitHub Enterprise instance, making all 47
violations visible as code-scanning alerts in the relevant repositories.

The Head of Security, James Okafor, sent a Slack message to Marcus during the week
3 readout: "We've been running on-demand scans with Checkov for two years and none
of these came up? I need to understand why."

The answer: Checkov had been configured to scan only new Terraform modules, not the
legacy estate inherited from the 2021 acquisition.

---

## Week 4 — FinOps Intelligence

The `finops_intelligence` module ran its full analysis suite against the 90-day CUR
data. DuckDB's in-memory analytics processed 90 days of line-item data in under 8
minutes on the r6a instance.

The RI/SP optimizer analyzed EC2, RDS, and ElastiCache usage patterns. It found
that Ironside was running $12.3M/year in on-demand spend on steady-state workloads
— workloads with less than 15% variance in utilization over the 90-day window.
These were ideal Reserved Instance candidates.

The savings breakdown:

| Category | Annual Savings |
|----------|---------------|
| Reserved Instances + Savings Plans (EC2, RDS, ElastiCache) | $4.2M |
| Right-sizing (22 over-provisioned instance families) | $1.8M |
| Region migration (4 workloads in eu-west-1 vs. eu-central-1 for carbon) | $380K |
| Retirement of 42 dormant services (compute + storage elimination) | ~$42K/month → $504K/yr |

**Total identified savings: $6.38M/year** — vs. the $2.1M identified in the
Accenture engagement. The delta was primarily explained by: (a) the additional 247
workloads the Accenture inventory had missed, (b) the 42 retirement candidates
Accenture had classified as Retain, and (c) the 90-day CUR analysis window vs.
the 30-day snapshot Accenture had used.

The carbon tracker flagged 4 workloads generating disproportionate carbon intensity
due to their eu-west-1 placement; eu-central-1 runs on a higher renewable energy
mix. The region migration recommendation was small in dollar terms but high in ESG
reporting value — Ironside has public sustainability commitments.

---

## Week 5 — Executive Chat Activation

The `ExecutiveChat` session was activated with the full Ironside briefing bundle:
all cloud_iq discovery data, the app_portfolio 6R recommendations, the iac_security
violation list, the FinOps anomaly set, and the audit trail governance posture.
The bundle loaded into Opus 4.7's 1M-token context in a single system prompt block,
cached with a 1-hour window.

Over the course of the week, the Ironside CTO, Sandra Wei, asked **37 questions**.
Selected examples:

> **Q: Which of the 88 Refactor candidates should we tackle first, given budget
> constraints?**
>
> A: [Platform response] Prioritized by NPV of cloud-native savings vs. refactor
> cost, 12 services stand out: three in the underwriting domain (EU AI Act exposure
> compounds urgency), four in claims processing (highest RDS cost in the portfolio),
> and five in the data platform (currently running on unencrypted RDS — critical
> compliance risk). Detailed prioritization in the attached structured output.

> **Q: How does our current IaC compliance posture affect our EU AI Act Annex IV
> readiness?**
>
> A: [Platform response, with Citations-grounded evidence] Three of the 12 critical
> IaC violations directly affect systems in scope for Annex IV: the two open-SSH
> security groups border the underwriting AI cluster, and the unencrypted RDS
> instances store training data for the underwriting model. Annex IV Article 9(1)
> requires that technical robustness measures be documented — these violations are
> a gap. The platform's SARIF report and Merkle-chained audit log constitute the
> documentation baseline once the violations are remediated.

Sandra's comment at the week 5 readout: "I've been asking my team these questions
for three months. This is the first time I've gotten answers backed by evidence
rather than someone's opinion."

The 37-question session cost approximately $340 in Anthropic spend, including the
initial briefing ingestion. Follow-up questions averaged under $3 each due to the
1-hour cache.

---

## Week 6 — EU AI Act Annex IV Package

The compliance team ran the Annex IV audit package generation across the platform's
output. The `eu_ai_act.py` module assembled:

- Article 12 mandatory fields for the underwriting AI system
- Reasoning traces for all 88 Refactor-classified services (stored in the Merkle
  chain)
- Chain verification result: 0 tampered entries across 2,847 logged decisions
- SARIF 2.1.0 export covering all IaC and portfolio findings
- Article 62 serious incident reporting tracker (no reportable incidents in the
  audit window)

The internal audit committee reviewed the package over two days. The Merkle chain
verification was demonstrated live — an auditor modified a test entry in a copy of
the database, and `verify()` returned the exact position of the modification in
under 200 milliseconds.

The package passed the internal audit on the first submission.

Dr. Vasquez, after the week 6 review: "We were looking at hiring two additional FTEs
to build this audit documentation manually. That's $400K in annual salary and twelve
months of work. We got a better result in six weeks."

---

## Results Summary

| Metric | Accenture Engagement | Enterprise AI Accelerator |
|--------|---------------------|--------------------------|
| Time to completion | 18 months | 6 weeks |
| Cost | $2.4M consulting fee | $18K Anthropic spend + $6K infra |
| Workloads discovered | 14,000 | 14,247 (+247) |
| IaC violations found | Not scoped | 47 (12 critical) |
| FinOps savings identified | $2.1M/yr | $6.38M/yr |
| EU AI Act Annex IV ready | No | Yes — passed internal audit |
| Audit trail tamper-evidence | No | SHA-256 Merkle chain, verified |
| Time to first executive insight | 6 weeks | Day 5 |

---

## Appendix: Sample Output Snippets

### A. 6R Recommendation (Structured Output)

```json
{
  "service": "ironside-underwriting-v2",
  "strategy": "refactor",
  "confidence": 0.87,
  "rationale": "Active codebase (1,247 commits in 12 months), 94 open PRs, complex
    business logic in Python. Currently on-prem PostgreSQL with no connection pooling.
    High cloud-native savings potential via Aurora Serverless + Lambda event
    processing. 3 critical CVEs in sqlalchemy 1.4.x — refactor enables upgrade path.",
  "blockers": [
    "Requires database schema migration (estimated 3-sprint effort)",
    "Implicit dependency on on-prem LDAP — needs replacement with Cognito or Okta"
  ],
  "evidence_weight": {
    "commit_activity_12m": 0.35,
    "cve_severity": 0.25,
    "containerization_score": 0.20,
    "test_coverage": 0.12,
    "ci_maturity": 0.08
  },
  "annex_iv_trace_id": "a3f7c2d8-4b91-4e2a-9f3a-1d8e7b5c4a2f"
}
```

### B. SARIF Sample (Critical Violation)

```json
{
  "ruleId": "EAA-IAC-S3-PUBLIC-001",
  "level": "error",
  "message": {
    "text": "S3 bucket 'ironside-claims-archive-2021' has public ACL 'public-read'.
      All objects in this bucket are publicly accessible. PCI-DSS 3.2.1 Req 1.3
      prohibits unrestricted public access to cardholder data environments."
  },
  "locations": [{
    "physicalLocation": {
      "artifactLocation": {"uri": "modules/storage/s3-claims.tf"},
      "region": {"startLine": 47, "endLine": 52}
    }
  }],
  "properties": {
    "severity": "CRITICAL",
    "compliance_frameworks": ["PCI-DSS", "SOC2", "EU-AI-Act-Annex-IV"],
    "remediation": "Set bucket ACL to 'private' and enable S3 Block Public Access."
  }
}
```

### C. Executive Chat Q&A Excerpt

**Question:** What is the estimated cost of not acting on the RI/SP recommendations
in Q2?

**Answer:**
> Based on the 90-day CUR analysis, Ironside is currently spending $12.3M/year on
> on-demand compute for steady-state workloads. The identified RI/SP opportunity
> covers $4.2M/year at approximately 36-60% discount rates depending on commitment
> term. Each quarter of delay costs Ironside approximately $1.05M in avoidable
> on-demand spend. At current burn rates, Q2 inaction represents a $1.05M
> opportunity cost against the $18K platform deployment investment.
>
> Confidence: HIGH. The baseline utilization window is 90 days of actuals; the
> only uncertainty is workload growth rate, which the forecaster estimates at +12%
> YoY for the underwriting cluster.

### D. Cost Breakdown (Anthropic Spend, 6 Weeks)

| Activity | Model | Tokens (approx.) | Cost |
|----------|-------|------------------|------|
| Cloud discovery + enrichment | Haiku 4.5 | 180M input | $144 |
| Portfolio 6R batch scoring | Haiku 4.5 + Batch API | 120M input | $48 |
| Refactor thinking audits (88 services) | Opus 4.7 | 14M input, 5M output | $585 |
| IaC policy evaluation | Haiku 4.5 | 40M input | $32 |
| CVE + SBOM analysis | Haiku 4.5 | 22M input | $18 |
| Executive chat (37 questions + briefing) | Opus 4.7 | 8M input (cached) | $340 |
| Report synthesis | Sonnet 4.6 | 12M input | $36 |
| Compliance citations + Annex IV | Opus 4.7 | 3M input | $195 |
| **Total** | | | **~$1,398** |

> Note: The $18K figure in the results summary is total platform cost including
> EC2 compute, storage, and a 6-week Anthropic commitment with overhead buffer.
> Direct Anthropic API spend for this engagement was approximately $1,400.
