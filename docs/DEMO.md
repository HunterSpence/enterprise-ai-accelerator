# Demo Scripts — Enterprise AI Accelerator

Three demo formats: 5-minute exec demo for CTOs/VPs, 15-minute technical demo for engineering leads, 3-minute whiteboard pitch for interviews.

---

## Prerequisites

```bash
git clone https://github.com/HunterSpence/enterprise-ai-accelerator.git
cd enterprise-ai-accelerator
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

All demos below work on synthetic data. No cloud credentials required unless stated.

---

## 5-Minute Exec Demo

**Audience:** CTO, VP Engineering, Head of Cloud.
**Goal:** Show a unified governance platform that replaces five point solutions in five minutes.
**Talking points:** EU AI Act deadline, AWS Migration Hub closure, cost savings story.

### Step 1 — App Portfolio Scan (90 seconds)

```bash
python -m app_portfolio.cli .
```

**What to show:** Language breakdown, CVE count, containerization score, 6R recommendation with confidence.

**What to say:** "This scanned the entire repo in under 10 seconds. CAST Highlight charges $150K–$600K a year and takes weeks to set up. We get the same output instantly. The 6R recommendation — Replatform, confidence 0.84 — comes from Opus 4.7 reading the actual dependency tree, not a static decision tree."

### Step 2 — IaC Security Scan (60 seconds)

```bash
python -m iac_security . --format json | python -c "
import json,sys
d=json.load(sys.stdin)
print(f'Findings: {d[\"summary\"][\"total\"]} ({d[\"summary\"][\"critical\"]} critical)')
"
```

**What to show:** Critical finding count. If there are findings, show one with its remediation text.

**What to say:** "20 built-in policies covering CIS AWS, PCI-DSS, SOC 2, HIPAA. Snyk IaC costs $200K a year. SARIF output uploads directly to the GitHub Security tab — no custom tooling needed."

### Step 3 — FinOps Intelligence (60 seconds)

```bash
python -m finops_intelligence.demo
```

**What to show:** Step 2 anomaly detection output + Step 4 savings total.

**What to say:** "$89,400 a month in identified savings on a $340K spend. Apptio Cloudability costs $200K–$1M a year. This runs locally, data never leaves your account, and it tells you the root cause in plain English."

### Step 4 — EU AI Act Audit Trail (60 seconds)

```bash
python -m ai_audit_trail.demo
```

**What to show:** Merkle chain verification output + the tamper-detection step.

**What to say:** "Every AI decision logged with a SHA-256 Merkle chain. Any modification is detected in O(log n). SARIF 2.1.0 export goes straight to GitHub. EU AI Act enforcement hits August 2, 2026 — 113 days. IBM OpenPages costs $500K a year for this. This is MIT licensed."

### Step 5 — Executive Chat (30 seconds)

```python
# Run interactively in a Python REPL
from executive_chat import ExecutiveChat
chat = ExecutiveChat()
# (load a briefing or use the demo briefing)
response = chat.ask("Which three workloads have the highest migration risk given our current compliance posture?")
print(response.answer)
```

**What to say:** "The entire enterprise briefing — architecture, migration plan, compliance posture, FinOps data — fits in one 1M-token context. First question costs a few cents. Every follow-up in the next hour costs about 10% of that."

---

## 15-Minute Technical Demo

**Audience:** Staff engineers, platform/infra leads, AI/ML architects.
**Goal:** Show the architecture, cost optimization layer, and integration surface.

### Section 1 — Architecture walkthrough (3 min)

Walk through `README.md` ASCII diagram. Explain the three-tier model structure:
- Opus 4.7 for coordination, extended thinking, executive chat
- Sonnet 4.6 for report synthesis
- Haiku 4.5 for high-volume worker tasks

Point to `core/model_router.py` — show that complexity scoring is automatic.

### Section 2 — Cost optimization live (3 min)

```python
from core.cost_estimator import CostEstimator
from core.model_router import ModelRouter

router = ModelRouter()
estimator = CostEstimator()

# Show routing decision for different task types
tasks = [
    ("classify_workload", 800),     # goes to Haiku
    ("synthesize_report", 3000),    # goes to Sonnet
    ("executive_briefing", 50000),  # goes to Opus
]

for task, tokens in tasks:
    model = router.select(task=task, token_estimate=tokens)
    cost = estimator.estimate(model=model, input_tokens=tokens, output_tokens=tokens//4)
    print(f"{task}: {model.split('-')[1]} — ${cost:.4f}")
```

**What to say:** "At 1,000 workloads, routing saves ~$140. The result cache means identical scans cost nothing on re-run. The batch coalescer submits overnight jobs at 50% discount automatically."

### Section 3 — IaC security deep-dive (3 min)

```bash
# Show policy catalog
python -c "from iac_security.policies import POLICIES; [print(p.id, p.severity, p.name) for p in POLICIES]"

# Run with SARIF output
python -m iac_security . --sarif /tmp/findings.sarif
cat /tmp/findings.sarif | python -m json.tool | head -60
```

Point to SARIF `rules` array and `results[].locations` — explain GitHub Security tab upload.

### Section 4 — Multi-cloud discovery (2 min)

```python
from cloud_iq.adapters.unified import UnifiedDiscovery

# With credentials configured:
d = UnifiedDiscovery.auto()
print(f"Active adapters: {[a.__class__.__name__ for a in d.active_adapters]}")
assets = d.discover()
print(f"Assets: {len(assets)} across {len(set(a.provider for a in assets))} providers")

# Without credentials: graceful degradation
# Output: "Active adapters: [] — 0 assets (no credentials configured)"
```

### Section 5 — Observability stack (2 min)

```bash
cd observability && docker compose -f docker-compose.obs.yaml up -d
```

Open `http://localhost:3000` — show both Grafana dashboards. Point to token spend panel and cache hit rate.

### Section 6 — MCP server (2 min)

```bash
python mcp_server.py
```

Show `mcp-config-example.json`. Explain: 19 tools, every module drivable from Claude Code / Desktop. Demo one tool call via Claude Desktop if available.

---

## 3-Minute Whiteboard Pitch

**Audience:** Interviewer at a cloud/DevOps/AI-eng role.
**Goal:** Show architectural thinking + commercial awareness.

### The pitch (speak to these points — adapt to your style)

"Enterprise cloud governance is fragmented. A typical enterprise buys Snyk for IaC security, Apptio for FinOps, CAST for app portfolio, IBM OpenPages for AI governance, and a consulting firm for migration planning. That's $1–2M a year, five vendor relationships, and five separate audit trails.

I built a unified platform on Claude Opus 4.7 that covers all five areas. The architecture has three layers: a core optimization layer that handles model routing, result caching, and batch API coalescing — that gets you ~95% cost savings vs. always using the most capable model. Above that is the module layer — multi-cloud discovery, app portfolio scanning, IaC security, FinOps, and EU AI Act compliance. At the top is the integration and observability layer — OTEL traces with gen_ai.* conventions, Prometheus metrics, Grafana dashboards, and webhook-based routing to Slack, Jira, ServiceNow, GitHub.

The technical decisions I'm proud of: using complexity-based model routing so you never pay Opus prices for a task Haiku handles fine; using the Anthropic Batch API for 50% discounts on bulk scoring jobs; wiring the extended-thinking reasoning trace into the audit trail as EU AI Act Annex IV evidence; and building SARIF 2.1.0 output so security findings go directly to the GitHub Security tab without custom tooling.

It's MIT licensed, 68 new files, ~17k LoC in the last release. Zero paid SaaS dependencies."

**Expected follow-ups:**
- "How do you handle multi-tenancy?" — Honest: not built yet. Single org today. RBAC is on the roadmap.
- "What would you do differently?" — Separate the read/write concerns in the audit trail (Merkle chain + SQLite in one file is fine for MVP, not for production scale). Also add async streaming for the IaC scanner.
- "How does the model router decide?" — Complexity scoring: estimated token count, tool call count, whether extended thinking is requested, and module context. Thresholds are configurable. Could be improved with a learned model.
