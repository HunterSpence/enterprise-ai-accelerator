# MigrationScout

AI-powered cloud migration assessment. Automates the $50K–$200K consulting engagement that Accenture and Deloitte do manually. One engineer replaces a 5-person team in 6 weeks.

## What It Does

| Manual Process | MigrationScout |
|---|---|
| 6–12 week consulting engagement | < 5 minutes end-to-end |
| $150K–$500K billing | ~$8 in API calls |
| Excel spreadsheets + PowerPoints | Structured data + exportable artifacts |
| Manual dependency workshops | Automated graph analysis |
| Gut-feel risk estimates | Monte Carlo simulation (1,000 iterations) |
| Templated Terraform snippets | Workload-specific runbooks |

## Demo

```bash
# Install dependencies
pip install anthropic networkx numpy rich

# Run demo (rule-based mode, no API key needed)
python -m migration_scout.demo

# Run with AI enrichment (Claude Haiku + Sonnet)
ANTHROPIC_API_KEY=sk-ant-... python -m migration_scout.demo --ai

# Export runbooks and dependency graph
python -m migration_scout.demo --ai --export-runbooks --export-dot
```

The demo runs a full assessment of **RetailCo** — a fictional 47-workload mixed on-prem/legacy-cloud estate:

- Current run cost: ~$287,000/month
- Projected cloud cost: ~$112,000/month  
- 3-year net savings: ~$2.1M
- Oracle license elimination alone: $270K/year

## Modules

### `assessor.py` — 6R Classification

Classifies each workload using the AWS 6R framework. Rule-based pre-classification runs in milliseconds. Claude Haiku enriches complex workloads with rationale, quick wins, and risks.

```python
from migration_scout import WorkloadAssessor, WorkloadInventory

assessor = WorkloadAssessor(use_ai=True)
workload = WorkloadInventory(
    id="web-01", name="E-Commerce Frontend", workload_type="web_app",
    language="Java", framework="Spring MVC", os="RHEL 7",
    cpu_cores=16, ram_gb=64, storage_gb=500,
    monthly_on_prem_cost=12000, age_years=14, dependency_count=12,
    business_criticality="critical",
)
assessment = assessor.assess_workload(workload)
print(assessment.strategy)          # MigrationStrategy.REPLATFORM
print(assessment.cloud_readiness_score)   # 68
print(assessment.ai_rationale)      # "This workload is a strong Replatform..."
```

**Outputs per workload:**
- `strategy`: One of the 6Rs
- `cloud_readiness_score`: 0–100
- `complexity`: Low / Medium / High
- `risk_score`: 0–100
- `target_service`: Specific AWS service (e.g., "ECS Fargate", "RDS Aurora MySQL")
- `estimated_migration_weeks` and `estimated_migration_cost_usd`
- `annual_savings_usd` and `three_year_savings`
- `ai_rationale`, `quick_wins`, `risks`

### `dependency_mapper.py` — Graph Analysis

Builds a directed NetworkX graph from workload dependencies. Finds clusters that must migrate together, circular dependencies (flags for Refactor), and computes topological migration order.

```python
from migration_scout import DependencyMapper, WorkloadNode, DependencyEdge

mapper = DependencyMapper()
mapper.add_nodes([WorkloadNode(id="api", ...), WorkloadNode(id="db", ...)])
mapper.add_edge(DependencyEdge(source_id="api", target_id="db", strength="tight"))

graph = mapper.analyze()
mapper.print_ascii_graph(graph)   # Terminal visualization
mapper.export_dot(graph, "deps.dot")  # Graphviz export
```

**Outputs:**
- `topological_order`: Valid migration sequence
- `clusters`: Tightly coupled groups (must migrate together)
- `circular_dependencies`: Cycles flagged for Refactor
- `critical_path`: Longest dependency chain
- DOT format for Graphviz visualization

### `wave_planner.py` — Wave Planning + Monte Carlo

Groups workloads into migration waves respecting dependency order. Runs 1,000 Monte Carlo simulations using triangular distributions calibrated to risk level, producing P50/P80/P95 timeline estimates.

```python
from migration_scout import WavePlanner

planner = WavePlanner(max_waves=5, monte_carlo_iterations=1000)
plan = planner.plan(dep_graph, assessments)

print(f"P50: {plan.monte_carlo.p50_weeks:.1f} weeks")
print(f"P80: {plan.monte_carlo.p80_weeks:.1f} weeks")
print(f"P95: {plan.monte_carlo.p95_weeks:.1f} weeks")

planner.print_wave_plan(plan, dep_graph)  # Rich terminal output with ASCII histogram
```

**Monte Carlo model:**
- Duration: Triangular distribution (min, mode, max) calibrated to risk level
- Cost: Log-normal distribution (right-skewed — overruns are more common)
- Random overhead events: 35% probability of scope-creep weeks

### `tco_calculator.py` — Financial Modeling

Computes full TCO comparison: on-premises (hardware + power + datacenter + staff + licenses + maintenance) vs cloud (compute + storage + database + network + support). Outputs 3-year NPV, break-even analysis, and 7-scenario sensitivity matrix.

```python
from migration_scout import TCOCalculator

calc = TCOCalculator()
tco = calc.analyze_portfolio(assessments)

print(f"Annual savings: ${tco.annual_savings:,.0f}")
print(f"3-year NPV: ${tco.npv_3yr:,.0f}")
print(f"Break-even: {tco.payback_period_str}")

calc.print_tco_report(tco)
```

**Sensitivity scenarios:**
1. Base case
2. Cloud costs +20%
3. Cloud costs +40%
4. Cloud costs −20% (optimization)
5. Staff savings reduced 50%
6. Worst case (cloud +30%, staff −50%)
7. Best case

### `runbook_generator.py` — AI Runbooks

Generates wave-specific migration runbooks using Claude Sonnet. Falls back to template-based generation if no API key is present. Exports as Markdown.

```python
from migration_scout import RunbookGenerator

gen = RunbookGenerator(use_ai=True)
wave_runbooks = gen.generate_all_wave_runbooks(
    plan, assessments, output_dir="./runbooks/"
)
```

Each runbook includes:
- Pre-migration checklist (10–12 items)
- Migration execution steps with real AWS CLI commands
- Validation tests
- Rollback procedure
- Post-migration checklist

## Architecture

```
WorkloadInventory (input)
        │
        ▼
  WorkloadAssessor ──── Claude Haiku ──► WorkloadAssessment (6R + scores)
        │
        ▼
  DependencyMapper ──── NetworkX ──────► DependencyGraph (clusters + order)
        │
        ▼
  WavePlanner ──────── Monte Carlo ────► WavePlan (waves + P50/P80/P95)
        │
        ├───────────── TCOCalculator ──► TCOAnalysis (NPV + sensitivity)
        │
        └───────────── RunbookGenerator ─ Claude Sonnet ──► WaveRunbook (Markdown)
```

## Requirements

```
python >= 3.12
anthropic >= 0.40.0
networkx >= 3.0
numpy >= 1.26
rich >= 13.0
```

## Model Usage

| Task | Model | Rationale |
|---|---|---|
| 6R classification enrichment | `claude-haiku-4-5-20251001` | Fast, cheap, good structured output |
| Migration runbook generation | `claude-sonnet-4-6` | Complex multi-step content requires reasoning |

Estimated cost per full assessment (47 workloads, all AI features enabled): **~$0.15–$0.40**

Consulting firm equivalent: **$150,000–$500,000**

## Why This Matters for Cloud/DevOps Roles

This module demonstrates:

1. **AWS architecture knowledge** — Knows the right target service for every workload type (EC2, ECS Fargate, RDS Aurora, Lambda, AWS Batch, OpenSearch, ElastiCache, AWS Glue, etc.)
2. **Graph algorithms** — NetworkX topological sort, SCC detection, critical path analysis
3. **Financial modeling** — NPV, IRR, sensitivity analysis, Monte Carlo simulation
4. **AI integration** — Claude API with appropriate model routing (Haiku for speed, Sonnet for quality)
5. **Production code quality** — Full type hints, dataclasses, error handling, rich terminal UI
6. **Consulting domain expertise** — Replicates $150K–$500K deliverables in code

---

*Part of the [enterprise-ai-accelerator](https://github.com/hunterspence/enterprise-ai-accelerator) portfolio.*
