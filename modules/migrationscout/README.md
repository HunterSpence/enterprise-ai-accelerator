# MigrationScout — Workload Migration Planner

Upload a CSV or JSON workload inventory. Claude produces a prioritized migration roadmap with wave planning, dependency resolution, and risk scoring.

## What It Does

- **6R classification** per workload (Rehost/Replatform/Refactor/Rearchitect/Retire/Retain)
- **Wave planning** — groups workloads into 3 waves by complexity and dependency
- **Effort estimation** — total weeks, per-wave breakdown
- **Risk register** — per-workload risks with mitigation strategies
- **Dependency resolution** — respects your dependency declarations

## Run It

```bash
cd modules/migrationscout
uvicorn app:app --reload --port 8002
# Open http://localhost:8002
```

## Input Format

**CSV (recommended):**
```csv
name,type,description,dependencies,size_gb
ERP-SAP,enterprise_app,SAP ERP for financials,Oracle-DB,500
Oracle-DB,database,Oracle 19c primary,,2000
WebApp,web,Customer React app,API-Gateway,50
```

**JSON:**
```json
[
  {"name": "ERP-SAP", "type": "enterprise_app", "dependencies": "Oracle-DB", "size_gb": 500},
  {"name": "Oracle-DB", "type": "database", "dependencies": "", "size_gb": 2000}
]
```

## Example Output

```json
{
  "total_workloads": 15,
  "total_effort_weeks": 47,
  "estimated_months": 12,
  "wave_1": ["Email-Service", "DevTools-Jenkins", "Monitoring-Nagios", "WebApp-Frontend"],
  "wave_2": ["API-Gateway", "Auth-Service", "CRM-Salesforce", "File-Share"],
  "wave_3": ["ERP-SAP", "Oracle-DB", "Legacy-Billing", "DataWarehouse"],
  "strategy_breakdown": {"Rehost": 4, "Replatform": 6, "Refactor": 3, "Retire": 2}
}
```
