# Examples

Ready-to-run sample data for every Enterprise AI Accelerator module.
No AWS credentials, Terraform state, or API keys needed.

## One-command run

```bash
# POSIX (Linux / macOS / WSL / Git Bash)
bash examples/run_demos.sh

# PowerShell (Windows)
.\examples\run_demos.ps1
```

---

## What each example demos

### `sample_repo/` — App Portfolio Analyzer

A Flask warehouse inventory API with intentionally old dependencies.

```bash
python -m app_portfolio.cli examples/sample_repo --out md --no-ai --no-cve
```

**Expected findings:**
- Language: Python (Flask) + JavaScript (React frontend)
- Old deps flagged: `flask==1.0.2`, `requests==2.20.0`, `sqlalchemy==1.3.0`, `axios==0.19.0`
- Containerization score: ~40/100 — no HEALTHCHECK, runs as root, unpinned base image
- CI maturity: basic (test + build only, no security scan stage)
- Test coverage: shallow (1 test, happy-path only)

**Intentional issues (for demo):**
- `requirements.txt` — deps from 2018-2019, several known CVEs
- `package.json` — React 16.13.0, axios 0.19.0 (CVE-2020-28168)
- `Dockerfile` — no HEALTHCHECK, no USER, `python:3.9` not pinned to digest
- `tests/test_app.py` — single test, no edge-case coverage

---

### `sample_terraform/` — IaC Security Scanner

Terraform module with 7 deliberate policy violations.

```bash
python -m iac_security scan examples/sample_terraform --format md
```

**Expected findings (7 violations):**

| Policy | Severity | Resource |
|--------|----------|----------|
| IAC-001 | HIGH | S3 `public-read` ACL |
| IAC-004 | HIGH | EBS volume not encrypted |
| IAC-007 | HIGH | Security group: SSH from `0.0.0.0/0` |
| IAC-010 | CRITICAL | IAM `Action=*` + `Resource=*` |
| IAC-013 | CRITICAL | RDS `publicly_accessible=true` |
| IAC-014 | MEDIUM | KMS key rotation disabled |
| IAC-015 | HIGH | CloudTrail log validation disabled |

**SBOM generation:**
```bash
python -m iac_security sbom examples/sample_repo --out /tmp/sbom.cdx.json
```

---

### `sample_workloads.json` — CloudIQ Multi-Cloud Inventory

14 workloads across AWS / Azure / GCP / Kubernetes following the `cloud_iq/adapters/base.Workload` schema.

Coverage: 4 EC2 (t3/m5), 2 RDS, 1 Lambda, 2 Azure VMs, 1 Azure SQL, 2 GCP Compute Engine, 2 K8s Deployments. Includes an underutilized m5.4xlarge running at 12% CPU avg (rightsizing candidate).

---

### `sample_cur.csv` — FinOps CUR Analysis

153 rows of synthetic AWS Cost and Usage Report data (Jan 2025).

```bash
python -m finops_intelligence.cli analyze \
    --cur examples/sample_cur.csv \
    --spend 15000 \
    --no-ai
```

**Expected output (excerpt):**
```
[finops] Loading CUR data from: examples/sample_cur.csv
[finops] Loaded 153 cost records
[finops] Date range: 2025-01-01 -> 2025-01-30
[finops] Running RI/SP analysis (lookback=90d)...
[finops] Generating savings report...
```

**Anomaly planted:** 2025-01-18 — m5.4xlarge spend spikes 380% ($28 → $136) due to a simulated runaway batch job. Anomaly detector should flag `ANOM-001`.

---

### `sample_briefing.json` — Executive Chat

Populated `BriefingBundle` across all sections for interactive Q&A with ExecutiveChat.

```python
import json
from executive_chat.chat import BriefingBundle, ExecutiveChat
from core import AIClient

bundle_data = json.load(open("examples/sample_briefing.json"))
bundle = BriefingBundle(**bundle_data)
chat = ExecutiveChat(AIClient())
# await chat.ask(bundle, "Which workloads should we migrate first?")
```

Covers: architecture findings, migration plan, compliance violations, FinOps anomalies, audit posture, risk score (68/100 grade C), 3 recent incidents.

---

### `sample_bias_dataset.json` — Policy Guard Bias Audit

Synthetic hiring model statistics with clear demographic parity violations.

```python
import json
from policy_guard.thinking_audit import PolicyThinkingAudit

data = json.load(open("examples/sample_bias_dataset.json"))
# auditor = PolicyThinkingAudit()
# await auditor.audit_bias_decision(data)
```

**Violations planted:**
- Gender: female recommendation rate 25.1% vs 41.2% male (disparate impact ratio 0.61 — below 4/5 rule)
- Ethnicity: Black candidates at 24.1% vs 38.9% white (ratio 0.62)
- Suspect features: `name_embedding` and `zip_code_cluster` likely encode protected attributes

---

## Note on intentional imperfections

Every sample file is deliberately flawed so the analyzers have something interesting to report.
The violations are documented in the individual READMEs and inline comments.
**Do not use any of these as templates for production infrastructure.**
