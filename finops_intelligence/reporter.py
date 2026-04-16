"""
reporter.py — FinOps Intelligence V2 CFO Report Generator

Generates a self-contained HTML report with:
  - Chart.js 4.x charts bundled via CDN (cost trend, services breakdown,
    forecast fan P10/P50/P90, optimization waterfall)
  - SCQA Pyramid Principle executive narrative (Claude Sonnet)
  - Responsive dark-mode layout + print-ready CSS
  - Zero external images or fonts — renders in any browser offline
    (requires CDN access for Chart.js only)

Usage:
    reporter = Reporter(config)
    html = await reporter.generate(report_data)
    Path("report.html").write_text(html)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ReportConfig:
    company_name: str = "TechCorp Enterprise"
    monthly_spend: float = 340_000.0
    monthly_budget: float = 380_000.0
    savings_monthly: float = 89_400.0
    currency: str = "USD"
    # Claude model for SCQA narrative (falls back to canned text if key missing)
    narrative_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str | None = None
    # Chart.js CDN version
    chartjs_version: str = "4.4.2"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MonthlySpend:
    month: str          # "Jan", "Feb", …
    amount: float       # $K
    budget: float       # $K
    ec2: float
    rds: float
    s3: float
    other: float


@dataclass
class ForecastPoint:
    month: str
    p10: float
    p50: float
    p90: float
    budget: float


@dataclass
class OptimizationItem:
    rank: int
    name: str
    category: str       # Usage | Rate | Governance
    monthly_savings: float
    confidence: str     # HIGH | MEDIUM | LOW
    risk: str           # None | Low | Medium | Critical
    effort: str         # "15 min" | "1 day" | …


@dataclass
class ReportData:
    config: ReportConfig
    monthly_spend: list[MonthlySpend]
    forecast: list[ForecastPoint]
    optimizations: list[OptimizationItem]
    anomaly_summary: str = ""
    unit_economics_summary: str = ""
    maturity_stage: str = "Walk"
    maturity_score: int = 52
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Default demo data
# ---------------------------------------------------------------------------

def _default_report_data(config: ReportConfig) -> ReportData:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    spend_vals = [238, 245, 252, 260, 271, 283, 296, 311, 326, 340, 355, 372]
    ec2_vals   = [98,  100, 103, 107, 111, 117, 121, 128, 134, 139, 145, 152]
    rds_vals   = [33,  34,  35,  36,  37,  40,  41,  44,  46,  48,  50,  52]
    s3_vals    = [19,  20,  20,  21,  22,  23,  24,  25,  26,  27,  28,  30]
    budget_val = 280

    monthly = [
        MonthlySpend(
            month=m, amount=s, budget=budget_val,
            ec2=e, rds=r, s3=s3v,
            other=round(s - e - r - s3v, 1),
        )
        for m, s, e, r, s3v in zip(months, spend_vals, ec2_vals, rds_vals, s3_vals)
    ]

    forecast = [
        ForecastPoint("Sep", 310, 326, 342, 380),
        ForecastPoint("Oct", 316, 340, 364, 380),
        ForecastPoint("Nov", 322, 355, 388, 380),
        ForecastPoint("Dec", 329, 372, 415, 380),
    ]

    optimizations = [
        OptimizationItem(1,  "EC2 Autoscaling cap",            "Usage",      18400, "HIGH",   "Critical", "15 min"),
        OptimizationItem(2,  "Savings Plans (3yr partial)",     "Rate",       17200, "HIGH",   "Low",      "1 day"),
        OptimizationItem(3,  "RDS Reserved Instances",          "Rate",       12100, "HIGH",   "Low",      "1 day"),
        OptimizationItem(4,  "SageMaker idle notebooks",        "Usage",       9400, "HIGH",   "None",     "30 min"),
        OptimizationItem(5,  "S3 Intelligent-Tiering",          "Rate",        7800, "MEDIUM", "Low",      "2 days"),
        OptimizationItem(6,  "CloudFront cache optimization",   "Usage",       6200, "MEDIUM", "None",     "30 min"),
        OptimizationItem(7,  "EC2 right-sizing (18 instances)", "Usage",       5900, "MEDIUM", "Medium",   "1 week"),
        OptimizationItem(8,  "ElastiCache RI conversion",       "Rate",        4400, "MEDIUM", "Low",      "1 day"),
        OptimizationItem(9,  "Lambda over-provisioned memory",  "Usage",       3800, "LOW",    "None",     "1 day"),
        OptimizationItem(10, "EBS gp2 to gp3 migration",        "Rate",        2700, "LOW",    "None",     "2 days"),
        OptimizationItem(11, "Untagged resource cleanup",        "Governance",  1400, "LOW",    "None",     "1 week"),
    ]

    return ReportData(
        config=config,
        monthly_spend=monthly,
        forecast=forecast,
        optimizations=optimizations,
        anomaly_summary="CRITICAL: EC2 +340% in 4h — autoscaling misconfiguration in us-east-1. Anomaly score 9.7/10.",
        unit_economics_summary="Cost/user: $1.20 → $4.80 (+300%). Infra as % of revenue: 3.2% → 11.8%.",
        maturity_stage="Walk",
        maturity_score=52,
    )


# ---------------------------------------------------------------------------
# SCQA narrative generator
# ---------------------------------------------------------------------------

async def _generate_scqa_narrative(data: ReportData) -> str:
    """Generate Claude Sonnet SCQA narrative, or return canned text if no API key."""
    cfg = data.config
    key = cfg.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    savings_annual = cfg.savings_monthly * 12

    if not _ANTHROPIC_AVAILABLE or not key:
        return (
            f"<p><strong>Situation:</strong> {cfg.company_name} cloud spend reached "
            f"${cfg.monthly_spend:,.0f}/month — {(cfg.monthly_spend/cfg.monthly_budget - 1)*100:.0f}% "
            f"over the ${cfg.monthly_budget:,.0f} budget. {data.anomaly_summary}</p>"
            f"<p><strong>Complication:</strong> At current trajectory, annual spend will exceed "
            f"${cfg.monthly_spend * 12 / 1e6:.1f}M. {data.unit_economics_summary} "
            f"Budget breach is projected before Q4 board review.</p>"
            f"<p><strong>Question:</strong> Can we reduce cloud spend materially without slowing "
            f"engineering velocity or incurring significant migration risk?</p>"
            f"<p><strong>Answer:</strong> Yes. FinOps Intelligence V2 identified "
            f"<strong>${cfg.savings_monthly:,.0f}/month (${savings_annual:,.0f}/year)</strong> "
            f"across {len(data.optimizations)} initiatives. Four require zero engineering effort. "
            f"Quick wins save over $30,000 this week.</p>"
        )

    client = anthropic.Anthropic(api_key=key)
    opt_summary = "\n".join(
        f"  {o.rank}. {o.name}: ${o.monthly_savings:,}/mo [{o.confidence}]"
        for o in data.optimizations[:5]
    )
    prompt = (
        f"Write a 4-paragraph CFO executive brief in the Pyramid Principle SCQA format "
        f"(Situation, Complication, Question, Answer) for the following cloud FinOps findings. "
        f"Be direct and quantitative. No bullet points — flowing prose paragraphs only. "
        f"Label each paragraph in bold: Situation, Complication, Question, Answer.\n\n"
        f"Company: {cfg.company_name}\n"
        f"Monthly cloud spend: ${cfg.monthly_spend:,.0f} (budget: ${cfg.monthly_budget:,.0f})\n"
        f"Anomaly: {data.anomaly_summary}\n"
        f"Unit economics: {data.unit_economics_summary}\n"
        f"Maturity: {data.maturity_stage} stage ({data.maturity_score}/100)\n"
        f"Top 5 optimizations:\n{opt_summary}\n"
        f"Total savings identified: ${cfg.savings_monthly:,.0f}/month "
        f"(${savings_annual:,.0f}/year)\n"
    )

    response = client.messages.create(
        model=cfg.narrative_model,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text  # type: ignore[index]
    # Wrap in paragraph tags for HTML embedding
    paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
    return "\n".join(f"<p>{p}</p>" for p in paragraphs)


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def _build_css() -> str:
    return """
:root{
  --bg:#0d1117;--surface:#161b22;--border:#30363d;
  --text:#e6edf3;--dim:#8b949e;
  --green:#3fb950;--red:#f85149;--blue:#58a6ff;
  --yellow:#d29922;--accent:#a371f7;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  padding:2rem;line-height:1.5}
h1{font-size:1.8rem;font-weight:700}
h2{font-size:1rem;font-weight:600;color:var(--blue);margin-bottom:1rem}
.header{border-bottom:1px solid var(--border);padding-bottom:1.5rem;margin-bottom:2rem}
.header p{color:var(--dim);margin-top:.4rem}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:1rem;margin-bottom:2rem}
.kpi{background:var(--surface);border:1px solid var(--border);
  border-radius:8px;padding:1.2rem}
.kpi .label{font-size:.75rem;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
.kpi .value{font-size:1.7rem;font-weight:700;margin-top:.3rem}
.kpi .delta{font-size:.82rem;margin-top:.2rem}
.c-green{color:var(--green)}.c-red{color:var(--red)}
.c-blue{color:var(--blue)}.c-yellow{color:var(--yellow)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-bottom:2rem}
.card{background:var(--surface);border:1px solid var(--border);
  border-radius:8px;padding:1.5rem}
.scqa{background:var(--surface);border:1px solid var(--border);
  border-radius:8px;padding:1.5rem;margin-bottom:2rem}
.scqa h2{color:var(--accent)}
.scqa p{margin-bottom:.8rem;color:#cdd9e5}
.scqa strong{color:var(--text)}
table.opt{width:100%;border-collapse:collapse;font-size:.85rem}
table.opt th{text-align:left;padding:.5rem .75rem;
  border-bottom:1px solid var(--border);color:var(--dim);font-weight:500}
table.opt td{padding:.5rem .75rem;border-bottom:1px solid #21262d}
.badge{display:inline-block;padding:.15rem .5rem;border-radius:12px;
  font-size:.72rem;font-weight:600}
.b-red{background:rgba(248,81,73,.2);color:var(--red)}
.b-yellow{background:rgba(210,153,34,.2);color:var(--yellow)}
.b-green{background:rgba(63,185,80,.2);color:var(--green)}
footer{color:var(--dim);font-size:.78rem;text-align:center;margin-top:2rem;
  padding-top:1.5rem;border-top:1px solid var(--border)}
@media print{
  body{background:#fff;color:#000}
  .kpi,.card,.scqa{background:#f6f8fa;border-color:#d0d7de}
  canvas{max-width:100%}
}
"""


def _build_kpis(data: ReportData) -> str:
    cfg = data.config
    savings_annual = cfg.savings_monthly * 12
    over_pct = (cfg.monthly_spend / cfg.monthly_budget - 1) * 100
    kpis = [
        ("Monthly Cloud Spend", f"${cfg.monthly_spend:,.0f}",
         f"+{over_pct:.0f}% over ${cfg.monthly_budget/1000:.0f}K budget", "c-red"),
        ("Annual Run Rate", f"${cfg.monthly_spend * 12 / 1e6:.2f}M",
         "+20% YoY trajectory", "c-yellow"),
        ("Savings Identified", f"${cfg.savings_monthly:,.0f}/mo",
         f"= ${savings_annual:,.0f}/year", "c-green"),
        ("Optimization Opps", str(len(data.optimizations)),
         "4 zero-effort quick wins", "c-blue"),
        ("Maturity Stage", data.maturity_stage,
         f"{data.maturity_score}/100 — peer median 65", "c-yellow"),
        ("Critical Anomalies", "1",
         "EC2 +340% in 4h", "c-red"),
    ]
    rows = []
    for label, value, delta, color in kpis:
        rows.append(
            f'<div class="kpi">'
            f'<div class="label">{label}</div>'
            f'<div class="value {color}">{value}</div>'
            f'<div class="delta {color}">{delta}</div>'
            f'</div>'
        )
    return '<div class="kpis">' + "\n".join(rows) + "</div>"


def _build_opt_table(data: ReportData) -> str:
    badge_cls = {"HIGH": "b-red", "MEDIUM": "b-yellow", "LOW": "b-green"}
    rows = []
    for o in data.optimizations:
        bc = badge_cls.get(o.confidence, "b-green")
        rows.append(
            f"<tr>"
            f"<td>{o.rank}</td>"
            f"<td>{o.name}</td>"
            f"<td>{o.category}</td>"
            f'<td class="c-green">${o.monthly_savings:,}</td>'
            f'<td><span class="badge {bc}">{o.confidence}</span></td>'
            f"<td>{o.risk}</td>"
            f"<td>{o.effort}</td>"
            f"</tr>"
        )
    return (
        '<div class="card" style="margin-bottom:2rem">'
        "<h2>Optimization Opportunities — Priority Order</h2>"
        '<table class="opt">'
        "<thead><tr><th>#</th><th>Opportunity</th><th>Category</th>"
        "<th>Monthly Savings</th><th>Confidence</th><th>Risk</th><th>Effort</th></tr></thead>"
        "<tbody>" + "\n".join(rows) + "</tbody>"
        "</table></div>"
    )


def _build_chart_js(data: ReportData, chartjs_version: str) -> str:
    months   = [m.month   for m in data.monthly_spend]
    spend    = [m.amount  for m in data.monthly_spend]
    budget   = [m.budget  for m in data.monthly_spend]
    ec2      = [m.ec2     for m in data.monthly_spend]
    rds      = [m.rds     for m in data.monthly_spend]
    s3       = [m.s3      for m in data.monthly_spend]
    other    = [m.other   for m in data.monthly_spend]
    f_months = [f.month   for f in data.forecast]
    f_p10    = [f.p10     for f in data.forecast]
    f_p50    = [f.p50     for f in data.forecast]
    f_p90    = [f.p90     for f in data.forecast]
    f_budget = [f.budget  for f in data.forecast]
    opt_labels = [o.name  for o in data.optimizations]
    opt_vals   = [o.monthly_savings for o in data.optimizations]

    cdn = (
        f'<script src="https://cdn.jsdelivr.net/npm/chart.js@{chartjs_version}'
        '/dist/chart.umd.min.js"></script>'
    )

    script = f"""
<script>
Chart.defaults.color = '#8b949e';
Chart.defaults.borderColor = '#30363d';

// 1. Cost trend
new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(months)},
    datasets: [
      {{label:'Actual ($K)',data:{json.dumps(spend)},
        borderColor:'#58a6ff',backgroundColor:'rgba(88,166,255,0.1)',fill:true,tension:0.3}},
      {{label:'Budget ($K)',data:{json.dumps(budget)},
        borderColor:'#f85149',borderDash:[6,3],fill:false}}
    ]
  }},
  options:{{plugins:{{legend:{{labels:{{color:'#8b949e'}}}}}},
    scales:{{y:{{beginAtZero:false}}}}}}
}});

// 2. Services stacked bar
new Chart(document.getElementById('serviceChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(months)},
    datasets: [
      {{label:'EC2',  data:{json.dumps(ec2)},  backgroundColor:'#58a6ff'}},
      {{label:'RDS',  data:{json.dumps(rds)},  backgroundColor:'#3fb950'}},
      {{label:'S3',   data:{json.dumps(s3)},   backgroundColor:'#d29922'}},
      {{label:'Other',data:{json.dumps(other)},backgroundColor:'#a371f7'}}
    ]
  }},
  options:{{plugins:{{legend:{{labels:{{color:'#8b949e'}}}}}},
    scales:{{x:{{stacked:true}},y:{{stacked:true}}}}}}
}});

// 3. Forecast fan
new Chart(document.getElementById('forecastChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(f_months)},
    datasets: [
      {{label:'P50',data:{json.dumps(f_p50)},borderColor:'#58a6ff',fill:false,tension:0.3}},
      {{label:'P90 (high)',data:{json.dumps(f_p90)},borderColor:'#f85149',borderDash:[4,2],fill:false}},
      {{label:'P10 (low)', data:{json.dumps(f_p10)},borderColor:'#3fb950',borderDash:[4,2],fill:false}},
      {{label:'Budget',    data:{json.dumps(f_budget)},borderColor:'#d29922',borderDash:[8,4],fill:false}}
    ]
  }},
  options:{{plugins:{{legend:{{labels:{{color:'#8b949e'}}}}}}}}
}});

// 4. Optimization waterfall (horizontal bar)
new Chart(document.getElementById('waterfallChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(opt_labels)},
    datasets: [{{
      label:'Monthly Savings ($)',
      data:{json.dumps(opt_vals)},
      backgroundColor:'#3fb950'
    }}]
  }},
  options:{{
    indexAxis:'y',
    plugins:{{legend:{{display:false}}}},
    scales:{{x:{{beginAtZero:true}}}}
  }}
}});
</script>"""

    return cdn + script


# ---------------------------------------------------------------------------
# Reporter class
# ---------------------------------------------------------------------------

class Reporter:
    def __init__(self, config: ReportConfig | None = None) -> None:
        self.config = config or ReportConfig()

    async def generate(self, data: ReportData | None = None) -> str:
        """Generate and return self-contained HTML report string."""
        if data is None:
            data = _default_report_data(self.config)

        scqa_html = await _generate_scqa_narrative(data)
        cfg = data.config
        savings_annual = cfg.savings_monthly * 12

        css = _build_css()
        kpis_html = _build_kpis(data)
        opt_table = _build_opt_table(data)
        charts_js = _build_chart_js(data, cfg.chartjs_version)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FinOps Intelligence V2 \u2014 CFO Report \u2014 {cfg.company_name}</title>
<style>{css}</style>
</head>
<body>

<div class="header">
  <h1>FinOps Intelligence V2 \u2014 CFO Report</h1>
  <p>{cfg.company_name} &nbsp;|&nbsp;
     Generated {data.generated_at.strftime("%Y-%m-%d %H:%M UTC")} &nbsp;|&nbsp;
     Powered by FinOps Intelligence V2</p>
</div>

{kpis_html}

<div class="scqa">
  <h2>Executive Brief (SCQA \u2014 Pyramid Principle)</h2>
  {scqa_html}
</div>

<div class="grid">
  <div class="card">
    <h2>12-Month Spend vs Budget</h2>
    <canvas id="trendChart" height="220"></canvas>
  </div>
  <div class="card">
    <h2>Top Services \u2014 Spend Breakdown</h2>
    <canvas id="serviceChart" height="220"></canvas>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>90-Day Forecast (P10 / P50 / P90)</h2>
    <canvas id="forecastChart" height="220"></canvas>
  </div>
  <div class="card">
    <h2>Optimization Waterfall (${cfg.savings_monthly:,.0f}/mo)</h2>
    <canvas id="waterfallChart" height="220"></canvas>
  </div>
</div>

{opt_table}

<footer>
  Generated by FinOps Intelligence V2 &nbsp;|&nbsp;
  DuckDB \u00b7 Prophet \u00b7 Ensemble ML \u00b7 FastAPI &nbsp;|&nbsp;
  Competes with CloudZero ($60\u201390K/yr) and IBM Cloudability (2\u20133% of spend)
  &nbsp;|&nbsp; Open-source stack
</footer>

{charts_js}
</body>
</html>"""
        return html

    async def write(self, path: str | Path, data: ReportData | None = None) -> Path:
        """Generate report and write to file. Returns resolved path."""
        html = await self.generate(data)
        p = Path(path)
        p.write_text(html, encoding="utf-8")
        return p.resolve()


# ---------------------------------------------------------------------------
# Convenience — matches V1 API surface
# ---------------------------------------------------------------------------

async def generate_cfo_report(
    output_path: str | Path = "finops_cfo_report.html",
    config: ReportConfig | None = None,
    data: ReportData | None = None,
) -> Path:
    """One-call wrapper: generate + write CFO HTML report."""
    reporter = Reporter(config)
    return await reporter.write(output_path, data)
