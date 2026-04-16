# FinOps Intelligence

**CloudZero costs $60K+/year. This runs locally for free.**

Open-source cloud cost optimization powered by ML anomaly detection, time-series forecasting, and Claude AI. Pulls AWS Cost & Usage Reports, finds waste, forecasts spend, and answers cost questions in plain English.

## Feature Comparison

| Feature | AWS Cost Explorer (free) | CloudZero ($60K+/yr) | IBM Cloudability ($150K+/yr) | **FinOps Intelligence (free)** |
|---------|--------------------------|----------------------|------------------------------|-------------------------------|
| Multi-cloud ingestion | AWS only | AWS, Azure, GCP | AWS, Azure, GCP, OCI | AWS (Azure/GCP roadmap) |
| ML anomaly detection | Basic threshold alerts | Yes (proprietary) | Yes (proprietary) | **Isolation Forest + Z-Score** |
| Natural language queries | Amazon Q (preview, read-only) | AI Hub | Limited | **Claude-powered, stateful** |
| Plain-English explanations | No | No | No | **Yes — root cause per anomaly** |
| CFO narrative reports | No | Dashboard only | Dashboard only | **AI-written HTML report** |
| Spend forecasting | Basic regression | Yes | Yes | **Prophet/SARIMA, P10/P90 bands** |
| RI/SP optimization | Yes | Yes | Yes | **Yes, with commitment gap analysis** |
| Waste detection | No | Yes | Yes | **Yes — EBS, EIPs, snapshots** |
| Rightsizing | Via Compute Optimizer | Yes | Yes | **Yes, with Graviton comparison** |
| Tag coverage analysis | No | Yes | Yes | **Yes + auto-tag suggestions** |
| Data stays in your account | Yes | **No** (vendor SaaS) | **No** (vendor SaaS) | **Yes** |
| Open-source / auditable | No | No | No | **Yes** |
| Setup time | Instant | 3–6 weeks | 4–8 weeks | **15 minutes** |
| Price | Free | $50K–$200K/year | $50K–$200K/year | **$0** |

## Quickstart

```bash
pip install finops-intelligence

# Demo mode (no AWS credentials needed)
python -m finops_intelligence.demo

# Connect to real AWS
finops connect aws --profile production
finops ask "Why did my bill spike last Tuesday?"
finops report cfo --month 2026-04 --output report.html
```

## Architecture

```
Data Sources            Processing Layer          Interface Layer
─────────────           ────────────────          ───────────────
AWS Cost Explorer  ─┐   pandas DataFrames    ─┐   Rich TUI (terminal)
AWS CUR (S3/Parquet)┘   scikit-learn (ML)    │   HTML reports (inline CSS)
                        Prophet/SARIMA       ─┘   Claude API (NL queries)
                        (forecasting)
```

## Modules

| Module | Description |
|--------|-------------|
| `cost_tracker.py` | AWS Cost Explorer + CUR ingestion, tag coverage analysis |
| `anomaly_detector.py` | Isolation Forest + Z-score anomaly detection, Claude explanations |
| `forecaster.py` | Prophet/SARIMA forecasting, burn rate, commitment gap |
| `optimizer.py` | Rightsizing, RI/SP recommendations, waste detection |
| `nl_interface.py` | Stateful Claude-powered cost Q&A |
| `dashboard.py` | Rich terminal dashboard |
| `reporter.py` | CFO HTML report generator |
| `demo.py` | Full demo with realistic mock data |

## AWS Setup

Minimum IAM permissions:
```json
{
  "Effect": "Allow",
  "Action": [
    "ce:GetCostAndUsage",
    "ce:GetRightsizingRecommendation",
    "ce:GetSavingsPlansPurchaseRecommendation",
    "ce:GetSavingsPlansUtilization",
    "compute-optimizer:GetEC2InstanceRecommendations",
    "s3:GetObject",
    "ec2:DescribeVolumes",
    "ec2:DescribeAddresses",
    "ec2:DescribeSnapshots"
  ]
}
```

For CUR: enable Cost & Usage Reports in Billing Console, Parquet format, S3 destination.

## The CFO Demo

```
$ python -m finops_intelligence.demo

[Step 1] Ingesting 90 days of cost data...
  Account: TechStartupCo Production (847523192400)
  Total spend (90d): $387,420
  Projected month-end: $128,200

[Step 2] Anomaly Detection (Isolation Forest + Z-Score)
  CRITICAL  2026-04-03  AWS Data Transfer   +$14,800 (+6,919%)
  HIGH      2026-04-03  Amazon EC2          +$892    (+42.1%)

  Anomaly explanation:
  "Data Transfer costs spiked $14,800 on April 3rd due to a Lambda function
   entering a retry loop, generating excessive NAT Gateway traffic. Normal daily
   NAT costs for this account are ~$210. Add a Dead Letter Queue and set
   SQS maxReceiveCount=3 to prevent recurrence."

[Step 4] Optimization Engine
  Total identified savings: $31,200/month ($374,400/year)
  #1  Purchase Compute Savings Plan           $12,800/mo  LOW effort
  #2  Rightsize 8 EC2 instances               $4,800/mo   MEDIUM effort
  #3  Downsize idle RDS instance              $3,800/mo   LOW effort
  ...

[Step 5] Natural Language Q&A
  Q: "Why did our AWS bill spike this month?"
  A: "Your AWS data transfer costs spiked $14,800 (+6,919%) on April 3rd.
      Root cause: a Lambda function in the event-processor function entered
      a retry loop, generating continuous NAT Gateway traffic..."
```

## Technical Requirements

- Python 3.12+
- `pandas`, `numpy`, `scikit-learn` — core data + ML
- `rich` — terminal UI
- `anthropic` — NL interface and report narratives (optional — falls back to rule-based)
- `statsmodels` — SARIMA forecasting (optional — falls back to linear)
- `prophet` — time-series forecasting (optional — falls back to SARIMA/linear)
- `boto3` — AWS APIs (optional — mock mode available)
- `pyarrow` — CUR Parquet parsing (optional)

## Why This Exists

The FinOps tooling market has a $50K–$200K/year paywall. The open-source alternatives (OpenCost, cloud-custodian, Infracost) each cover one slice of the problem. No unified open-source tool combines multi-cloud ingestion, ML anomaly detection, AI-powered explanations, and CFO-ready reporting.

FinOps Intelligence is that tool.

---

## v0.2.0 Additions — Advanced FinOps Track

The following components were added in the April 2026 platform expansion:

### `CURIngestor` (`cur_ingestor.py`)

AWS Cost and Usage Report ingestion via DuckDB. Reads Parquet CUR files from S3 (or a local path) and registers them as a DuckDB table for SQL analytics.

```python
from finops_intelligence.cur_ingestor import CURIngestor

ingestor = CURIngestor(s3_bucket="my-cur-bucket", s3_prefix="cur/")
df = ingestor.load_month("2026-04")
# Returns a DuckDB relation — query with SQL or .to_pandas()
```

Supports: Parquet CUR v2, legacy CSV CUR, FOCUS 1.3 export format.

### `RISPOptimizer` (`ri_sp_optimizer.py`)

Reserved Instance and Savings Plan optimizer. Analyzes on-demand spend patterns and recommends RI/SP purchases with an 80% coverage cap to avoid over-commitment.

```python
from finops_intelligence.ri_sp_optimizer import RISPOptimizer

optimizer = RISPOptimizer()
recommendations = optimizer.optimize(usage_df=df)

for rec in recommendations:
    print(rec.type, rec.term, rec.monthly_savings, rec.breakeven_months)
```

The 80% cap is intentional: committing beyond 80% of baseline usage creates waste when workloads scale down. Configurable via `coverage_cap` parameter.

### `RightSizer` (`right_sizer.py`)

CloudWatch metrics + curated AWS instance catalog right-sizer. Fetches CPU/memory utilization for EC2 instances and compares against a catalog of 200+ AWS instance types to find the optimal size.

```python
from finops_intelligence.right_sizer import RightSizer

sizer = RightSizer()
opportunities = sizer.analyze(instance_ids=["i-abc123", "i-def456"])

for opp in opportunities:
    print(opp.instance_id, opp.current_type, opp.recommended_type,
          f"${opp.monthly_savings:.0f}/mo")
```

Includes Graviton comparison — suggests ARM-based instances where the workload is compatible.

### `CarbonTracker` (`carbon_tracker.py`)

Carbon emissions tracker using open-source regional grid carbon intensity coefficients (based on Electricity Maps / Our World in Data data, periodically updated).

```python
from finops_intelligence.carbon_tracker import CarbonTracker

tracker = CarbonTracker()
emissions = tracker.estimate(
    usage_df=df,   # CUR-format dataframe with region and instance hours
)

print(f"Total estimated emissions: {emissions.total_kg_co2e:.0f} kg CO2e/month")
print(f"Top emitting region: {emissions.top_region}")
```

Coefficients cover all AWS, Azure, and GCP regions where published data exists. Regions without published data use a conservative global average.

### `SavingsReporter` (`savings_reporter.py`)

Aggregates RI/SP optimizer, right-sizer, anomaly findings, and carbon data into a CFO-ready executive savings report. Output: structured `SavingsReport` object + optional HTML export.

```python
from finops_intelligence.savings_reporter import SavingsReporter

reporter = SavingsReporter()
report = reporter.generate(
    ri_sp_recommendations=recommendations,
    rightsizing_opportunities=opportunities,
    anomalies=anomalies,
    carbon_emissions=emissions,
)

print(f"Total annualized savings opportunity: ${report.total_annual_savings:,.0f}")
reporter.export_html(report, "savings_report.html")
```

---

Part of [enterprise-ai-accelerator](https://github.com/HunterSpence/enterprise-ai-accelerator) — production-grade AI modules for cloud infrastructure.
