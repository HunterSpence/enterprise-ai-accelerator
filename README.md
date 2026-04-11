# Enterprise AI Accelerator

**Claude-powered enterprise cloud migration & AI governance platform**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Anthropic Claude](https://img.shields.io/badge/Powered_by-Claude_Opus-cc785c?style=flat-square)](https://anthropic.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

What consulting firms charge $500K–$5M to deliver manually, this platform automates with Claude. Open source. Working demos. Built by someone who spent 4 years doing this at Accenture.

---

## Modules

| Module | What It Does | What It Replaces |
|--------|-------------|------------------|
| [**CloudIQ**](#cloudiq) | AI-powered cloud architecture analysis | Accenture/Deloitte manual architecture review ($200K+) |
| [**MigrationScout**](#migrationscout) | Workload migration planner with 6R scoring | Cloud Migration Factory ($500K+ engagement) |
| [**PolicyGuard**](#policyguard) | IaC compliance & security checker | KPMG/PwC governance assessment ($150K+) |
| [**ExecutiveReport**](#executivereport) | Board-ready AI-generated migration proposals | 40 hours of MD time per engagement |

---

## Quick Start

```bash
git clone https://github.com/HunterSpence/enterprise-ai-accelerator
cd enterprise-ai-accelerator
pip install -r requirements.txt
cp .env.example .env  # Add your ANTHROPIC_API_KEY

# Run a demo analysis
python demo/run_demo.py
```

---

## CloudIQ

Drop in any AWS config, Terraform state, or architecture description. Get a full security posture analysis, cost optimization recommendations, and migration readiness score — in seconds.

```python
from cloudiq import CloudIQAnalyzer

analyzer = CloudIQAnalyzer()
result = analyzer.analyze(config_json)

print(result.security_score)       # 0-100
print(result.cost_waste_monthly)   # $12,400/mo wasted on oversized instances
print(result.critical_findings)    # ["Public S3 bucket with PII", ...]
print(result.recommendations)      # Prioritized action items
```

**Demo:** `python cloudiq/demo.py` — analyzes a sample enterprise AWS config in ~15 seconds

---

## MigrationScout

Feed it a workload inventory (CSV or JSON). Get a complete migration plan: 6R classification per workload, complexity scores, phased roadmap, effort estimates, and risk flags.

```python
from migration_scout import MigrationPlanner

planner = MigrationPlanner()
plan = planner.plan(workload_inventory_csv)

print(plan.summary)                # "47 workloads: 12 Rehost, 18 Replatform..."
print(plan.total_effort_weeks)     # 34
print(plan.phase_1_workloads)      # High-value, low-risk first
print(plan.risk_register)          # Per-workload risk breakdown
```

**Demo:** `python migration_scout/demo.py` — plans a 50-workload migration in ~30 seconds

---

## PolicyGuard

Point it at Terraform, CloudFormation, or raw IaC. Get a compliance score against SOC2, HIPAA, or PCI-DSS, plus specific remediation steps for every finding.

```python
from policy_guard import PolicyChecker

checker = PolicyChecker(frameworks=["SOC2", "HIPAA"])
result = checker.check(terraform_directory)

print(result.compliance_score)     # 72/100
print(result.critical_violations)  # ["Unencrypted RDS at rest", ...]
print(result.remediation_steps)    # Exact Terraform fixes for each issue
```

**Demo:** `python policy_guard/demo.py` — checks a misconfigured Terraform setup

---

## ExecutiveReport

Feed it any analysis output. Get a board-ready PDF/HTML report with executive summary, financial impact, risk matrix, and recommended next steps — formatted for non-technical stakeholders.

```python
from executive_report import ReportGenerator

generator = ReportGenerator()
report = generator.generate(
    cloudiq_result=analysis,
    migration_plan=plan,
    company_name="Acme Corp",
    audience="board"
)

report.save_html("board_report.html")
report.save_pdf("board_report.pdf")
```

**Demo:** `python executive_report/demo.py` — generates a full board report from sample data

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Enterprise AI Accelerator             │
├──────────────┬──────────────┬─────────────┬────────────┤
│   CloudIQ    │ MigrationScout│ PolicyGuard │ ExecReport │
│              │              │             │            │
│ AWS Config → │ Inventory → │ IaC Files → │ Any Output │
│ Claude API  │ Claude API   │ Claude API  │ Claude API │
│ Security +  │ 6R Plan +    │ Compliance  │ Board Deck │
│ Cost Report │ Roadmap      │ Remediation │ Generation │
└──────────────┴──────────────┴─────────────┴────────────┘
         │              │              │            │
         └──────────────┴──────────────┴────────────┘
                              │
              Claude Opus / Sonnet (configurable)
```

---

## Why This Exists

I spent 4 years at Accenture watching teams of 8 consultants spend 3 months producing cloud migration assessments that could be 80% automated. The remaining 20% — the judgment calls, the stakeholder translation, the risk framing — is where human expertise actually matters.

This platform handles the 80%. You focus on the 20%.

I also filed patents on AI agent oversight systems and built production AI deployments (voice agents, multi-agent orchestration, RAG pipelines). This project demonstrates what's possible when AI is used to _accelerate_ consulting work rather than just advise about it.

---

## Comparison to Consulting Tools

| Feature | This Platform | Accenture Cloud Migration Factory | Deloitte Cloud Migration Factory |
|---------|--------------|-----------------------------------|----------------------------------|
| Architecture analysis | ✅ AI-automated | Manual (2-4 week engagement) | Manual (2-4 week engagement) |
| 6R workload classification | ✅ Automated | Manual workshops | Manual workshops |
| Compliance checking | ✅ Automated | Manual review | Manual review |
| Executive reporting | ✅ Auto-generated | PM creates manually | PM creates manually |
| Cost | Free / API costs | $500K–$5M | $500K–$5M |
| Time to first insight | Minutes | Weeks | Weeks |
| Customizable | ✅ Open source | ❌ Proprietary | ❌ Proprietary |

---

## Contact

- **Hunter Spence** — hunter@vantaweb.dev
- **LinkedIn** — [linkedin.com/in/hunterspence](https://linkedin.com/in/hunterspence)
- **Portfolio** — [github.com/HunterSpence/aws-cloud-portfolio](https://github.com/HunterSpence/aws-cloud-portfolio)
- **Patents** — AI Agent Oversight Systems (provisional, filed 2026-02-27)
