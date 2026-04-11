# Architecture — Enterprise AI Accelerator

## Overview

Five independent modules plus a cross-module Risk Aggregator. Each module is a self-contained Python package with its own FastAPI server, Dockerfile, and CLI demo. Modules share nothing at runtime — they communicate through structured output schemas, not shared memory or message buses.

The Risk Aggregator is the one layer that reads output from multiple modules. Every other dependency is one-way: CloudIQ and FinOps Intelligence can feed data into MigrationScout's TCO calculator; no module calls back into another at runtime.

---

## Module Map

```
enterprise-ai-accelerator/
├── ai_audit_trail/          Port 8000 — SQLite + Merkle chain + FastAPI
├── finops_intelligence/     Port 8010 — DuckDB + pandas + FastAPI
├── migration_scout/         Port 8002 — NetworkX + Claude + FastAPI
├── policy_guard/            Port 8003 — SQLAlchemy + SARIF + FastAPI
├── cloud_iq/                Port 8001 — boto3 (optional) + ML + FastAPI
├── risk_aggregator.py       Standalone script — no server, pure Python
└── docs/
```

---

## Data Flow

### Full Pipeline (all modules)

```
Input Sources
  ├── AWS credentials (optional, CloudIQ)
  ├── Workload inventory JSON/CSV (MigrationScout)
  ├── IaC files: Terraform / CloudFormation (PolicyGuard)
  ├── Cloud billing export (FinOps Intelligence)
  └── Live AI decision stream (AIAuditTrail decorator)
         │
         ▼
┌────────────────────────────────────────────────────────┐
│                    Module Layer                         │
│                                                        │
│  CloudIQ          FinOps Intelligence                  │
│  ─────────────    ─────────────────────────            │
│  InfraSnapshot    CostReport (FOCUS 1.3)               │
│  SecurityScore    AnomalyAlerts                        │
│  WasteItems       CommitmentRecommendations            │
│        │                  │                            │
│        └──────────────────┤                            │
│                           ▼                            │
│               MigrationScout                           │
│               ─────────────────────                    │
│               WorkloadAssessments (6R)                 │
│               DependencyGraph (SCC)                    │
│               WavePlan (Monte Carlo)                   │
│               TCOCalculation                           │
│                           │                            │
│  PolicyGuard              │                            │
│  ─────────────────        │                            │
│  ComplianceReport ────────┤                            │
│  SARIFExport              │                            │
│  BiasReport               │                            │
│  IncidentLog              │                            │
│                           │                            │
│  AIAuditTrail             │                            │
│  ─────────────────        │                            │
│  AuditChain (SQLite) ─────┘                            │
│  MerkleRoot                                            │
│  Article12ComplianceReport                             │
│  IncidentReports                                       │
└──────────────────┬─────────────────────────────────────┘
                   │
                   ▼
         Risk Aggregator
         ─────────────────────────────────────────
         RiskInput (any combination of the above)
         │
         Dimension scoring:
         │  security_compliance  ×0.35  ← PolicyGuard score (inverted)
         │  financial_waste      ×0.25  ← FinOps waste percentage
         │  migration_complexity ×0.20  ← MigrationScout risk score
         │  ai_governance        ×0.20  ← AIAuditTrail completeness
         │
         Critical finding multiplier: ×1.25
         High finding multiplier:     ×1.10
         │
         RiskScore {
           overall_score: 0–100
           risk_tier: LOW / MEDIUM / HIGH / CRITICAL
           top_risk_driver: string
           dimension_scores: dict
           executive_narrative: string (3 sentences, board-level)
         }
                   │
                   ▼
         Output Channels
         ├── Jira: ticket creation from findings
         ├── Slack: alert delivery
         └── GitHub: SARIF upload → Security tab
```

---

## Module Internals

### AIAuditTrail

**Storage:** SQLite with WAL mode. Thread-safe via exclusive lock on tip lookup + insert.

**Hash chain:** Each `LogEntry` contains a SHA-256 hash of the previous entry's hash, forming a cryptographic chain. `chain.py` uses stdlib only — no cryptography package dependency.

**Merkle tree:** Root hash checkpointed every 1,000 entries. Single-entry proof verification is O(log n) via Merkle proof path. Full chain verification iterates all entries sequentially.

**Key files:**
- `chain.py` — `AuditChain`, `LogEntry`, `VerificationReport`. The hash chain implementation. Stdlib only.
- `eu_ai_act.py` — Article 12 Annex IV compliance check, Article 62 incident reporting, enforcement timeline countdown, bias detection from audit log patterns.
- `nist_rmf.py` — GOVERN / MAP / MEASURE / MANAGE scoring against the NIST AI Risk Management Framework. Returns maturity level (Initial / Developing / Defined / Managed / Optimizing).
- `incident_manager.py` — `IncidentManager`, `IncidentSeverity` (P0–P3). Article 62 deadline tracking. P0-DISCRIMINATION triggers automatic Article 62 report generation.
- `decorators.py` — `@audit_llm_call` decorator. Drop-in for Anthropic, OpenAI, LangChain, LlamaIndex, raw HTTP.
- `reporter.py` — HTML compliance report generator.

**API (port 8000):** `POST /log`, `GET /query`, `POST /verify`, `GET /compliance/article12`, `POST /incidents`

---

### FinOps Intelligence

**Storage:** DuckDB (in-memory or file-backed). Ingests up to 847,000 billing rows. Pandas for transformation; PyArrow for Parquet export.

**FOCUS implementation:** `focus_exporter.py` implements all 33 required FOCUS 1.0 columns plus FOCUS 1.2/1.3 optional columns. `export_ai_model_costs()` maps per-model token spend (input + output) into FOCUS `ServiceCategory=AI` rows. This combination does not exist in any other OSS tool.

**Anomaly detection:** `anomaly_detector_v2.py` uses an ensemble: statistical (z-score / IQR), isolation forest, and time-series decomposition. `EnsembleAnomalyDetector` aggregates votes across methods.

**Key files:**
- `focus_exporter.py` — FOCUS 1.3 schema + Parquet export.
- `analytics_engine.py` — DuckDB-backed `AnalyticsEngine`.
- `nl_interface.py` — NL-to-SQL query interface.
- `anomaly_detector_v2.py` — Ensemble anomaly detection.
- `commitment_optimizer.py` — RI / Savings Plan recommendation engine.
- `forecaster.py` — Time-series cost forecasting.
- `unit_economics.py` — Cost-per-unit breakdown.
- `maturity_assessment.py` — FinOps maturity scoring.
- `reporter.py` — CFO-ready report generator.

**API (port 8010):** `POST /analyze`, `POST /export/focus`, `GET /anomalies`, `POST /optimize/commitments`

---

### MigrationScout

**6R classification:** `assessor.py` scores each workload across complexity dimensions (containerization readiness, vendor lock-in, active development status, dependency count, age, team size, criticality) and maps to a 6R recommendation with Claude-generated reasoning.

**Dependency resolution:** `dependency_mapper.py` builds a directed graph and uses Tarjan's SCC algorithm to detect circular dependency loops. Proposes containerize-first workarounds for unresolvable cycles.

**Wave planning:** `wave_planner.py` uses Monte Carlo simulation. Output includes P50 / P80 / P95 effort estimates per wave, not deterministic point estimates.

**TCO:** `tco_calculator.py` computes 3-year total cost including: current infrastructure, migration labor, managed service costs, license elimination (Oracle, SQL Server, Windows Server), and RI/SP coverage.

**Key files:**
- `assessor.py` — `WorkloadAssessor`, `WorkloadInventory`. 6R with AI reasoning.
- `dependency_mapper.py` — `DependencyMapper`. SCC cycle detection.
- `wave_planner.py` — `WavePlanner`, `MigrationApproach`. Monte Carlo simulation.
- `tco_calculator.py` — 3-year savings with license elimination.
- `runbook_generator.py` — Per-wave migration runbooks.
- `report_generator.py` — HTML migration plan report.

**API (port 8002):** `POST /assess`, `POST /plan`, `GET /dependencies`, `POST /tco`

---

### PolicyGuard

**Scanning:** `scanner.py` evaluates AI system configurations against compliance frameworks. `ComplianceScanner` accepts a `ScanConfig` with system attributes and returns a `ComplianceReport` with per-framework scores.

**Frameworks:** EU AI Act (Annex III category + Articles 9/13), HIPAA, SOC 2, PCI-DSS v4.0, CIS AWS Foundations v2.0, NIST SP 800-53.

**Cross-framework efficiency:** `frameworks/eu_ai_act.py` maps EU AI Act controls to equivalent HIPAA and SOC 2 controls. One implementation satisfies multiple frameworks simultaneously.

**SARIF export:** `sarif_exporter.py` produces SARIF 2.1.0 from `ComplianceReport` findings. Each violation maps to a SARIF `Result` with `ruleId`, `level`, `message`, and `locations`.

**Incident response:** `incident_response.py` implements P0 (4-hour SLA), P1 (24-hour), P2 (72-hour), P3 (7-day). Integrates with AIAuditTrail's incident manager.

**Key files:**
- `scanner.py` — `ComplianceScanner`, `ScanConfig`, `ComplianceReport`.
- `sarif_exporter.py` — SARIF 2.1.0 export.
- `bias_detector.py` — Statistical disparate impact analysis.
- `incident_response.py` — P0–P3 SLA tracking.
- `remediation_generator.py` — Remediation plans with effort estimates.
- `dashboard.py` — Live Rich UI compliance posture.
- `frameworks/eu_ai_act.py` — Annex III classifier + enforcement countdown.
- `sql/` — Database schema for persistent compliance state.

**API (port 8003):** `POST /scan`, `GET /report/{scan_id}`, `POST /export/sarif`, `POST /incidents`

---

### CloudIQ

**Scanner:** `scanner.py` models AWS resource types as typed dataclasses: `EC2Instance`, `EBSVolume`, `RDSInstance`, `S3Bucket`, `ECSCluster`, `EKSCluster`, `LambdaFunction`, `ElastiCacheCluster`, `VPC`, `ElasticIP`. `InfrastructureSnapshot` aggregates all resources.

**Cost analysis:** `cost_analyzer.py` produces `WasteItem` records (right-sizing, orphaned resources, idle capacity) and `ShadowITItem` records. `RightsizingRecommendation` includes current and target instance sizes with monthly savings.

**Key files:**
- `scanner.py` — Resource type models + `InfrastructureSnapshot`.
- `cost_analyzer.py` — Waste identification + right-sizing.
- `ml_detector.py` — Anomaly detection on resource configuration.
- `terraform_generator_v2.py` — Right-sized Terraform output.
- `nl_query.py` — NL-to-structured-query interface.
- `providers/` — AWS, Azure, GCP provider modules.

**API (port 8001):** `POST /analyze`, `GET /report/{analysis_id}`, `POST /terraform`, `GET /waste`

---

## Integration Points

### GitHub Actions — SARIF Upload

```yaml
# .github/workflows/ai-compliance.yml
- name: Run PolicyGuard compliance scan
  run: python -m policy_guard.demo --output sarif > findings.sarif

- name: Upload to GitHub Security tab
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: findings.sarif
```

### Anthropic SDK — AIAuditTrail Decorator

```python
import anthropic
from ai_audit_trail.decorators import audit_llm_call
from ai_audit_trail.chain import DecisionType, RiskTier

client = anthropic.Anthropic()

@audit_llm_call(
    chain_path="./production_audit.db",
    system_id="loan-review-v3",
    decision_type=DecisionType.RECOMMENDATION,
    risk_tier=RiskTier.HIGH,
)
def analyze_loan(applicant_data: dict) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": str(applicant_data)}],
    )
    return response.content[0].text
```

### Jira

PolicyGuard and CloudIQ write findings to Jira when `JIRA_API_TOKEN` and `JIRA_PROJECT_KEY` are set. CRITICAL findings map to Bug (P1), HIGH to Bug (P2), MEDIUM to Task.

### Slack

All modules support Slack alert delivery via `SLACK_WEBHOOK_URL`. Alerts fire on: CRITICAL compliance findings, P0/P1 incidents, anomaly triggers, and EU AI Act deadline warnings (30-day, 14-day, 7-day).

---

## Security Model

- `ANTHROPIC_API_KEY` loaded from environment only — never hardcoded or logged.
- AWS credentials loaded from environment or IAM role — never stored in the audit chain.
- AIAuditTrail SQLite database is a compliance artifact: restrict write access; the Merkle chain detects any direct-write attempt.
- Input truncated at 8,000 characters before any Claude API call.
- All modules are stateless per request except AIAuditTrail, which is intentionally append-only stateful.
- No PII is stored by default — log entries record decision type, risk tier, and token counts. Raw applicant data appears only if explicitly passed to `input_text`.

---

## Running the Full Stack

```bash
# Terminal 1: AIAuditTrail
cd ai_audit_trail && uvicorn api:app --port 8000

# Terminal 2: CloudIQ
cd cloud_iq && uvicorn api:app --port 8001

# Terminal 3: MigrationScout
cd migration_scout && uvicorn api:app --port 8002

# Terminal 4: PolicyGuard
cd policy_guard && uvicorn api:app --port 8003

# Terminal 5: FinOps Intelligence
cd finops_intelligence && uvicorn api:app --port 8010

# Or all at once:
python scripts/run_all.py
```

Interactive API docs at `http://localhost:{port}/docs` for each module.

---

## Claude API Usage Per Module

| Module | Model | Technique |
|--------|-------|-----------|
| CloudIQ | claude-sonnet-4-6 | JSON-mode via system prompt |
| MigrationScout | claude-sonnet-4-6 | Structured output + 6R reasoning |
| PolicyGuard | claude-sonnet-4-6 | Domain-expert system prompt |
| AIAuditTrail | claude-haiku-4-5 (bias), sonnet (HIGH risk) | Risk-tier-based routing |
| Risk Aggregator | None | Deterministic scoring, no LLM call |

MigrationScout can skip Claude API calls entirely with `--no-ai` for CI runs. All other demos use synthetic data and do not call the Anthropic API.

---

## Design Decisions

**Why SQLite for AIAuditTrail?**
Stdlib only, zero deployment dependencies, WAL mode provides concurrent read access. The Merkle chain provides tamper evidence that a heavier database cannot improve. For high-volume production (>10K decisions/day), the module documents PostgreSQL WAL advisory lock support as an alternative backend.

**Why DuckDB for FinOps Intelligence?**
847,000 billing rows fit in memory for analytics workloads. DuckDB's columnar engine handles the GROUP BY and window function queries FinOps analysis requires without a server process.

**Why are modules independent rather than a monolith?**
Consulting firms and enterprises typically need one or two modules, not all five. A client implementing EU AI Act compliance does not need the migration planner. Independent modules allow independent deployment and incremental adoption.

**Why is Risk Aggregator a standalone script?**
It has no server — its purpose is to accept structured output from other modules and produce a weighted score. A FastAPI wrapper adds deployment complexity without adding capability. It runs from CI/CD pipelines, notebooks, or management scripts.
