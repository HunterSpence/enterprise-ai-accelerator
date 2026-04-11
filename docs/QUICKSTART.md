# Quick Start Guide

## Prerequisites

- Python 3.11 or higher
- Git

An Anthropic API key is **not required** to run any module demo. All demos use synthetic data and run fully offline. The API key is only needed if you want to run the AI-powered analysis against real workload data.

---

## Option 1: Local Setup (Recommended for Evaluation)

### 1. Clone and install core dependencies

```bash
git clone https://github.com/HunterSpence/enterprise-ai-accelerator.git
cd enterprise-ai-accelerator
pip install -r requirements.txt
```

Core dependencies: `anthropic>=0.40.0`, `rich>=13.7.0`. That's it for demos.

### 2. Run a demo

Each module has a self-contained demo that requires no credentials:

```bash
# AI governance + EU AI Act compliance
python -m ai_audit_trail.demo

# FinOps cost intelligence ($340K/month TechCorp scenario)
python -m finops_intelligence.demo

# Migration planning (RetailCo 75-workload scenario)
python -m migration_scout.demo

# Compliance scanner (hiring AI + healthcare AI scenarios)
python -m policy_guard.demo

# AWS infrastructure analysis (AcmeCorp $47K/month waste)
python -m cloud_iq.demo
```

### 3. Run with real data (optional)

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

On Windows:
```cmd
set ANTHROPIC_API_KEY=sk-ant-...
```

MigrationScout can skip Claude API calls for CI/CD runs:
```bash
python -m migration_scout.demo --no-ai
```

---

## Option 2: Docker (Per Module)

Each module ships with its own `Dockerfile` and `docker-compose.yml`.

### AIAuditTrail

```bash
cd ai_audit_trail
docker-compose up
# API server available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### FinOps Intelligence

```bash
cd finops_intelligence
docker-compose up
# Dashboard at http://localhost:8010
```

### PolicyGuard

```bash
cd policy_guard
docker-compose up
# API at http://localhost:8003
```

### CloudIQ

```bash
cd cloud_iq
docker-compose up
# API at http://localhost:8001
```

---

## Option 3: FastAPI Module Servers

Run each module as a standalone FastAPI service:

```bash
# PolicyGuard (port 8003)
cd policy_guard && uvicorn api:app --port 8003 --reload

# CloudIQ (port 8001)
cd cloud_iq && uvicorn api:app --port 8001 --reload

# MigrationScout (port 8002)
cd migration_scout && uvicorn api:app --port 8002 --reload

# AIAuditTrail (port 8000)
cd ai_audit_trail && uvicorn api:app --port 8000 --reload
```

Or start all at once:
```bash
python scripts/run_all.py
```

Interactive API docs are available at `http://localhost:{port}/docs` (Swagger UI) for each running module.

---

## Per-Module Dependencies

The core `requirements.txt` covers demos. For full module functionality:

### FinOps Intelligence (analytical engine)
```bash
pip install -r finops_intelligence/requirements.txt
# Includes: duckdb, pandas, pyarrow (for FOCUS Parquet export)
```

### PolicyGuard (API server + SQL)
```bash
pip install -r policy_guard/requirements.txt
# Includes: fastapi, uvicorn, sqlalchemy
```

### CloudIQ (ML detection)
```bash
pip install -r cloud_iq/requirements.txt
# Includes: scikit-learn, boto3 (optional, for real AWS scans)
```

### AIAuditTrail
```bash
pip install -r ai_audit_trail/pyproject.toml  # or
pip install fastapi uvicorn opentelemetry-sdk
```

---

## AIAuditTrail SDK Integration

Drop the audit decorator onto any AI call:

```python
from ai_audit_trail.decorators import audit_llm_call
from ai_audit_trail.chain import DecisionType, RiskTier

# Decorator pattern — works with any LLM SDK
@audit_llm_call(
    chain_path="./audit.db",
    system_id="my-ai-system",
    decision_type=DecisionType.RECOMMENDATION,
    risk_tier=RiskTier.HIGH,
)
def call_model(prompt: str) -> str:
    # Your existing model call here
    ...
```

The decorator records: model name, input/output tokens, latency, decision type, risk tier, system ID, cost in USD, and the SHA-256 hash linking to the previous entry in the Merkle chain.

---

## FinOps FOCUS Export

```python
from finops_intelligence.focus_exporter import FOCUSExporter

exporter = FOCUSExporter(provider="aws", account_id="123456789012")

# Export billing data in FOCUS 1.3 format
focus_rows = exporter.from_spend_data(spend_data.service_breakdown)
exporter.export_jsonl("./billing_focus.jsonl", focus_rows)
exporter.export_csv("./billing_focus.csv", focus_rows)
exporter.export_parquet("./billing_focus.parquet", focus_rows)  # FOCUS 1.4-ready

# AI/LLM costs in FOCUS format
ai_rows = exporter.export_ai_model_costs([
    {"model": "claude-sonnet-4-6", "input_tokens": 1_000_000,
     "output_tokens": 200_000, "total_cost": 4.20},
])
```

---

## Risk Aggregator

Combine outputs from any modules into a single risk score:

```python
from risk_aggregator import WorkloadRiskAggregator, RiskInput

risk = WorkloadRiskAggregator()
score = risk.compute(RiskInput(
    # From PolicyGuard
    policy_score=72.0,
    policy_critical_findings=3,
    policy_high_findings=8,
    # From FinOps Intelligence
    finops_waste_pct=38.5,
    # From MigrationScout
    migration_risk_score=65,
    # From AIAuditTrail
    audit_trail_present=True,
    ai_systems_count=3,
))

print(f"Risk: {score.overall_score}/100 ({score.risk_tier})")
print(f"Top driver: {score.top_risk_driver}")
print(score.executive_narrative)
```

All `RiskInput` fields are optional. The aggregator weights only the dimensions you provide.

---

## GitHub SARIF Integration (PolicyGuard)

PolicyGuard exports findings in SARIF 2.1.0 format for direct upload to GitHub's Security tab:

```bash
# Generate SARIF report
python -m policy_guard.demo --output sarif > findings.sarif

# Upload via GitHub CLI
gh api repos/{owner}/{repo}/code-scanning/sarifs \
  --method POST \
  --field commit_sha=$(git rev-parse HEAD) \
  --field ref=refs/heads/main \
  --field sarif=@findings.sarif
```

Or add to your GitHub Actions workflow:
```yaml
- name: Upload PolicyGuard findings
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: findings.sarif
```

---

## Environment Variables

| Variable | Module | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | All | Required for AI-powered analysis (not needed for demos) |
| `AWS_ACCESS_KEY_ID` | CloudIQ | Read-only AWS access for real scans |
| `AWS_SECRET_ACCESS_KEY` | CloudIQ | Read-only AWS access for real scans |
| `AWS_DEFAULT_REGION` | CloudIQ | Target AWS region (default: us-east-1) |
| `AUDIT_DB_PATH` | AIAuditTrail | Path to SQLite audit database (default: ./audit.db) |
| `JIRA_API_TOKEN` | PolicyGuard, CloudIQ | Jira ticket creation from findings |
| `SLACK_WEBHOOK_URL` | All | Alert delivery channel |

Copy `.env.example` to `.env` and fill in the values you need.

---

## Verifying the Installation

Run this to confirm everything is importable:

```bash
python -c "
from ai_audit_trail.chain import AuditChain, DecisionType, RiskTier
from ai_audit_trail.eu_ai_act import days_until_enforcement
from risk_aggregator import WorkloadRiskAggregator, RiskInput
days = days_until_enforcement('high_risk_systems')
print(f'EU AI Act Article 12 enforcement: {days} days')
print('Installation OK')
"
```

Expected output:
```
EU AI Act Article 12 enforcement: 113 days
Installation OK
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'rich'`**
Run `pip install rich` or `pip install -r requirements.txt` from the repo root.

**`ModuleNotFoundError: No module named 'duckdb'`**
FinOps Intelligence requires its own dependencies: `pip install -r finops_intelligence/requirements.txt`

**Windows: SQLite WAL file lock on cleanup**
Expected on Windows. The demos use `ignore_cleanup_errors=True` on temp directories. No data is lost.

**`anthropic.AuthenticationError`**
Your `ANTHROPIC_API_KEY` is missing or invalid. Demos don't require it — only real data analysis does.

**Port already in use**
Change the port: `uvicorn api:app --port 8010` (or any available port).
