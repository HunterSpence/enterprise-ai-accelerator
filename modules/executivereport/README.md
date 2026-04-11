# ExecutiveReport — Board Deck Generator

Paste raw metrics JSON (cloud spend, utilization %, incidents, migration progress, security scores). Claude transforms them into C-suite language with narrative, insights, risk flags, and board recommendations.

## What It Does

- **Executive summary** — 3-4 sentences, no jargon, business-context first
- **Key metrics dashboard** — formatted for non-technical stakeholders  
- **Risk register** — HIGH/MEDIUM/LOW with business impact framing
- **Board recommendations** — specific, time-bound, with owner and investment
- **Financial narrative** — spend trajectory, budget variance, savings opportunity

## Run It

```bash
cd modules/executivereport
uvicorn app:app --reload --port 8004
# Open http://localhost:8004
```

## Example Input

```json
{
  "period": "Q1 2025",
  "cloud_spend": {"total_monthly": 284000, "vs_budget": "+18%"},
  "utilization": {"compute_avg": 34, "waste_estimate_monthly": 67000},
  "migration_progress": {"workloads_total": 127, "percent_complete": 34},
  "incidents": {"p1_count": 3, "availability_pct": 99.71},
  "security": {"compliance_score": 71, "critical_findings_open": 7}
}
```

## Example Output

```json
{
  "title": "Q1 2025 Cloud Transformation — Board Update",
  "executive_summary": "Cloud spend reached $284K/month, 18% over budget, driven by compute expansion supporting the ERP migration. Availability targets were met at 99.71%, though three P1 incidents in Q1 require architectural review. The migration program is 6 weeks behind schedule with 34% of workloads complete.",
  "risks": [
    {"level": "HIGH", "risk": "Cloud spend trajectory", "impact": "On track to exceed annual budget by $400K if growth continues unchecked"},
    {"level": "HIGH", "risk": "Security compliance gap", "impact": "7 critical findings open; SOC2 audit at risk if not resolved before Q3"}
  ],
  "recommended_actions": [
    "Approve $180K reserved instance purchase — payback in 7 months, saves $310K annually",
    "Assign dedicated security engineer to resolve 7 critical findings before May 15 audit"
  ]
}
```
