# CloudIQ — AI Architecture Analyzer

Paste any AWS config JSON, Terraform HCL, or architecture description. Claude analyzes it as a senior solutions architect.

## What It Does

- **Security scoring** (0-100) with CRITICAL/HIGH/MEDIUM findings per resource
- **Cost analysis** — identifies waste, quantifies monthly spend (e.g. "$12,400/mo on idle instances")
- **Migration complexity score** (1-10) with specific blockers called out
- **Top 3 recommendations** prioritized by impact

## Run It

```bash
cd modules/cloudiq
uvicorn app:app --reload --port 8001
# Open http://localhost:8001
```

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI routes, Jinja2 template rendering |
| `analyzer.py` | Claude API integration, prompt engineering, JSON parsing |
| `templates/index.html` | Web UI with dark-mode results display |

## Example Input

```json
{
  "resources": {
    "s3_buckets": [{"name": "company-data", "acl": "public-read"}],
    "ec2_instances": [{"type": "t2.micro", "count": 8}],
    "rds": {"instance_class": "db.t2.medium", "multi_az": false, "encrypted": false}
  }
}
```

## Example Output

```json
{
  "security_score": 42,
  "cost_score": 31,
  "migration_complexity": 6,
  "critical_findings": ["S3 bucket 'company-data' has public-read ACL — PII exposure risk"],
  "cost_waste_monthly": 8400,
  "top_recommendations": [
    "Remove S3 public ACL and enable Block Public Access",
    "Enable RDS encryption at rest and multi-AZ",
    "Right-size EC2 fleet — 8x t2.micro → 2x t3.small saves $380/mo"
  ]
}
```
