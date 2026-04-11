"""
ExecutiveReport — Board Deck Generator
FastAPI app: paste raw metrics JSON → get C-suite ready narrative with insights and recommendations
Run: uvicorn app:app --reload --port 8004
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from generator import ReportGenerator

load_dotenv()

app = FastAPI(title="ExecutiveReport — Board Deck Generator", version="1.0.0")

_generator = None

EXAMPLE_METRICS = """{
  "period": "Q1 2025",
  "company": "Acme Corp",
  "cloud_spend": {
    "total_monthly": 284000,
    "vs_budget": "+18%",
    "vs_prior_quarter": "+31%",
    "breakdown": {
      "compute": 142000,
      "storage": 51000,
      "data_transfer": 38000,
      "managed_services": 53000
    }
  },
  "utilization": {
    "compute_avg": 34,
    "storage_used_pct": 61,
    "reserved_instance_coverage": 42,
    "waste_estimate_monthly": 67000
  },
  "migration_progress": {
    "workloads_total": 127,
    "workloads_migrated": 43,
    "workloads_in_progress": 12,
    "percent_complete": 34,
    "behind_schedule_weeks": 6
  },
  "incidents": {
    "p1_count": 3,
    "p2_count": 11,
    "mean_time_to_resolve_hours": 4.2,
    "availability_pct": 99.71
  },
  "security": {
    "critical_findings_open": 7,
    "high_findings_open": 23,
    "compliance_score": 71,
    "frameworks": ["SOC2", "PCI-DSS"]
  },
  "cost_optimization_opportunities": 890000
}"""


def get_generator() -> ReportGenerator:
    global _generator
    if _generator is None:
        _generator = ReportGenerator()
    return _generator


def render_page(metrics_input: str = "", report=None, error: str = "") -> str:
    error_block = f'<div class="error">&#9888; {error}</div>' if error else ""

    results_block = ""
    if report:
        # Render the report sections
        key_findings_html = ""
        for f in report.key_findings:
            key_findings_html += f'<li style="padding:8px 0;border-bottom:1px solid #21262d;color:#c9d1d9;font-size:14px">&#128312; {f}</li>'

        risk_html = ""
        for r in report.risks:
            level = r.get("level", "MEDIUM")
            color = "#f85149" if level == "HIGH" else "#d29922" if level == "MEDIUM" else "#3fb950"
            risk_html += f"""
            <div style="display:flex;align-items:flex-start;gap:12px;padding:12px;border:1px solid #30363d;border-left:3px solid {color};border-radius:4px;margin-bottom:8px;background:#0d1117">
              <span style="color:{color};font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;border:1px solid {color};flex-shrink:0">{level}</span>
              <div>
                <div style="font-size:13px;font-weight:600;color:#e6edf3">{r.get("risk","")}</div>
                <div style="font-size:12px;color:#8b949e;margin-top:2px">{r.get("impact","")}</div>
              </div>
            </div>"""

        actions_html = ""
        for i, action in enumerate(report.recommended_actions, 1):
            actions_html += f'<div style="padding:10px 12px;background:#0d1a10;border:1px solid #238636;border-radius:4px;margin-bottom:8px;font-size:13px;color:#c9d1d9"><strong style="color:#3fb950">{i}.</strong> {action}</div>'

        metrics_html = ""
        for k, v in report.key_metrics.items():
            metrics_html += f"""
            <div style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:16px;text-align:center">
              <div style="font-size:11px;color:#8b949e;text-transform:uppercase;margin-bottom:6px">{k}</div>
              <div style="font-size:22px;font-weight:700;color:#58a6ff">{v}</div>
            </div>"""

        results_block = f"""
        <div style="display:grid;gap:20px">
          <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:24px">
            <div style="font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">EXECUTIVE SUMMARY</div>
            <h2 style="font-size:20px;font-weight:700;color:#e6edf3;margin-bottom:12px">{report.title}</h2>
            <p style="font-size:15px;color:#c9d1d9;line-height:1.7">{report.executive_summary}</p>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px">
            {metrics_html}
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
            <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px">
              <h3 style="font-size:14px;font-weight:600;margin-bottom:14px">&#128202; Key Findings</h3>
              <ul style="list-style:none">{key_findings_html}</ul>
            </div>
            <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px">
              <h3 style="font-size:14px;font-weight:600;margin-bottom:14px">&#9888; Risk Register</h3>
              {risk_html}
            </div>
          </div>
          <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px">
            <h3 style="font-size:14px;font-weight:600;margin-bottom:14px">&#9989; Board Recommendations</h3>
            {actions_html}
          </div>
        </div>"""

    safe_input = metrics_input.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_example = EXAMPLE_METRICS.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ExecutiveReport — Board Deck Generator</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #e6edf3; min-height: 100vh; }}
    .header {{ background: linear-gradient(135deg, #161b22 0%, #1a1520 100%); border-bottom: 1px solid #30363d; padding: 20px 40px; }}
    .logo {{ font-size: 24px; font-weight: 700; color: #d2a8ff; }}
    .tagline {{ color: #8b949e; font-size: 14px; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 40px 24px; display: grid; gap: 24px; }}
    .form-section {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 24px; }}
    .form-section h2 {{ font-size: 16px; margin-bottom: 16px; font-weight: 600; }}
    textarea {{ width: 100%; height: 280px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 14px; color: #e6edf3; font-family: monospace; font-size: 12px; line-height: 1.5; resize: vertical; }}
    textarea:focus {{ outline: none; border-color: #d2a8ff; }}
    .btn {{ background: #6e40c9; color: #fff; border: 1px solid #8957e5; border-radius: 6px; padding: 10px 20px; font-size: 14px; font-weight: 600; cursor: pointer; }}
    .btn:hover {{ background: #8957e5; }}
    .example-btn {{ background: transparent; border: 1px solid #30363d; color: #8b949e; font-size: 12px; padding: 6px 12px; border-radius: 6px; cursor: pointer; margin-left: 12px; }}
    .error {{ background: #2d1b1e; border: 1px solid #f85149; color: #f85149; border-radius: 6px; padding: 14px 18px; }}
  </style>
</head>
<body>
  <div class="header">
    <div class="logo">&#128202; ExecutiveReport</div>
    <div class="tagline">Board Deck Generator — transforms raw metrics into C-suite narrative</div>
  </div>
  <div class="container">
    <div class="form-section">
      <h2>&#128196; Raw Metrics JSON
        <button class="example-btn" onclick="loadExample()">Load Q1 example metrics</button>
      </h2>
      <form method="post" action="/generate">
        <textarea name="metrics_input" id="metrics_input" placeholder="Paste your metrics JSON (cloud spend, utilization %, incident count, migration progress, security scores...)...">{safe_input}</textarea>
        <div style="margin-top:16px">
          <button type="submit" class="btn">&#128202; Generate Board Report</button>
        </div>
      </form>
    </div>
    {error_block}
    {results_block}
  </div>
  <script>
    function loadExample() {{
      document.getElementById('metrics_input').value = `{safe_example}`;
    }}
  </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return HTMLResponse(render_page())


@app.post("/generate", response_class=HTMLResponse)
async def generate(request: Request, metrics_input: str = Form(...)):
    result = None
    error = ""

    if not metrics_input.strip():
        error = "Please paste metrics JSON."
    else:
        try:
            generator = get_generator()
            result = generator.generate(metrics_input)
        except Exception as exc:
            error = f"Report generation failed: {exc}"

    return HTMLResponse(render_page(metrics_input, result, error))


@app.get("/health")
async def health():
    return {"status": "ok", "module": "executivereport"}
