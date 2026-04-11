"""
MigrationScout — Workload Migration Planner
FastAPI app: upload CSV/JSON workload inventory → get wave-based migration roadmap
Run: uvicorn app:app --reload --port 8002
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from planner import MigrationPlanner

load_dotenv()

app = FastAPI(title="MigrationScout — Workload Migration Planner", version="1.0.0")

_planner = None

EXAMPLE_WORKLOADS = """name,type,description,dependencies,size_gb
ERP-SAP,enterprise_app,SAP ERP system for financials,Oracle-DB,500
Oracle-DB,database,Oracle 19c primary database,,2000
WebApp-Frontend,web,Customer-facing React application,API-Gateway,50
API-Gateway,middleware,Kong API gateway,Auth-Service,20
Auth-Service,microservice,OAuth2 authentication service,Oracle-DB,10
Email-Service,microservice,Internal SMTP relay,,5
HR-Workday,saas_integration,Workday HCM integration,Oracle-DB,100
Legacy-Billing,legacy_app,COBOL billing system on mainframe,,50
DataWarehouse,analytics,Teradata data warehouse,Oracle-DB,8000
ETL-Pipeline,batch,Nightly ETL jobs,DataWarehouse Oracle-DB,30
CRM-Salesforce,saas_integration,Salesforce CRM connector,API-Gateway,20
File-Share,storage,Windows file server SMB shares,,5000
DevTools-Jenkins,devops,Jenkins CI/CD server,,200
Monitoring-Nagios,monitoring,Nagios infrastructure monitoring,,50
Backup-Veeam,backup,Veeam backup infrastructure,File-Share,1000"""

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MigrationScout — Migration Planner</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #e6edf3; min-height: 100vh; }}
    .header {{ background: linear-gradient(135deg, #161b22 0%, #1a2a1a 100%); border-bottom: 1px solid #30363d; padding: 20px 40px; }}
    .logo {{ font-size: 24px; font-weight: 700; color: #3fb950; }}
    .tagline {{ color: #8b949e; font-size: 14px; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 40px 24px; }}
    .form-section {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 24px; margin-bottom: 32px; }}
    .form-section h2 {{ font-size: 16px; margin-bottom: 16px; font-weight: 600; }}
    textarea {{ width: 100%; height: 260px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 14px; color: #e6edf3; font-family: monospace; font-size: 12px; line-height: 1.5; resize: vertical; }}
    textarea:focus {{ outline: none; border-color: #3fb950; }}
    .btn {{ display: inline-flex; align-items: center; gap: 8px; background: #238636; color: #fff; border: 1px solid #2ea043; border-radius: 6px; padding: 10px 20px; font-size: 14px; font-weight: 600; cursor: pointer; }}
    .btn:hover {{ background: #2ea043; }}
    .example-btn {{ background: transparent; border: 1px solid #30363d; color: #8b949e; font-size: 12px; padding: 6px 12px; border-radius: 6px; cursor: pointer; margin-left: 12px; }}
    .error {{ background: #2d1b1e; border: 1px solid #f85149; color: #f85149; border-radius: 6px; padding: 14px 18px; margin-bottom: 24px; }}
    .results {{ display: grid; gap: 24px; }}
    .summary-box {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px 24px; }}
    .summary-box h3 {{ font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }}
    .summary-box p {{ font-size: 14px; color: #c9d1d9; line-height: 1.6; }}
    .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
    .stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; text-align: center; }}
    .stat .label {{ font-size: 11px; color: #8b949e; text-transform: uppercase; margin-bottom: 8px; }}
    .stat .value {{ font-size: 32px; font-weight: 700; color: #3fb950; }}
    .stat .sub {{ font-size: 12px; color: #8b949e; }}
    .wave {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px 24px; }}
    .wave h3 {{ font-size: 14px; font-weight: 600; margin-bottom: 16px; }}
    .wave-1 h3 {{ color: #3fb950; border-left: 3px solid #3fb950; padding-left: 10px; }}
    .wave-2 h3 {{ color: #58a6ff; border-left: 3px solid #58a6ff; padding-left: 10px; }}
    .wave-3 h3 {{ color: #d29922; border-left: 3px solid #d29922; padding-left: 10px; }}
    .workload-list {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .workload-chip {{ background: #0d1117; border: 1px solid #30363d; border-radius: 16px; padding: 4px 12px; font-size: 12px; color: #c9d1d9; }}
    .risk-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    .risk-table th {{ text-align: left; padding: 8px 12px; color: #8b949e; font-weight: 600; border-bottom: 1px solid #30363d; }}
    .risk-table td {{ padding: 8px 12px; border-bottom: 1px solid #21262d; color: #c9d1d9; }}
    .badge {{ display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; }}
    .badge-rehost {{ background: #1a2d1a; color: #3fb950; }}
    .badge-replatform {{ background: #1a2535; color: #58a6ff; }}
    .badge-refactor {{ background: #2d2a16; color: #d29922; }}
    .badge-retire {{ background: #2d1b1e; color: #f85149; }}
    .badge-retain {{ background: #1f1f1f; color: #8b949e; }}
    .badge-rearchitect {{ background: #2a1a2d; color: #d2a8ff; }}
    @media (max-width: 700px) {{ .stats {{ grid-template-columns: 1fr 1fr; }} }}
  </style>
</head>
<body>
  <div class="header">
    <div class="logo">&#127758; MigrationScout</div>
    <div class="tagline">AI Migration Planner — wave planning, risk scoring, dependency resolution</div>
  </div>
  <div class="container">
    <div class="form-section">
      <h2>&#128196; Workload Inventory (CSV or JSON)
        <button class="example-btn" onclick="loadExample()">Load 15-workload example</button>
      </h2>
      <form method="post" action="/plan">
        <textarea name="inventory" id="inventory" placeholder="Paste CSV with columns: name,type,description,dependencies,size_gb

Or JSON array: [{name, type, description, dependencies, size_gb}, ...]">{inventory}</textarea>
        <div style="margin-top:16px">
          <button type="submit" class="btn">&#128640; Generate Migration Plan</button>
        </div>
      </form>
    </div>

    {error_block}

    {results_block}
  </div>
  <script>
    const example = `{example}`;
    function loadExample() {{
      document.getElementById('inventory').value = example;
    }}
  </script>
</body>
</html>"""


def render_results(plan) -> str:
    if not plan:
        return ""

    waves_html = ""
    wave_data = [
        ("wave-1", "Wave 1 — Quick Wins (Low Risk, High Value)", plan.wave_1),
        ("wave-2", "Wave 2 — Core Workloads", plan.wave_2),
        ("wave-3", "Wave 3 — Complex / Deferred", plan.wave_3),
    ]
    for css_class, title, workloads in wave_data:
        if workloads:
            chips = "".join(f'<span class="workload-chip">{w}</span>' for w in workloads)
            waves_html += f'<div class="wave {css_class}"><h3>{title}</h3><div class="workload-list">{chips}</div></div>'

    strategy_html = ""
    if plan.strategy_breakdown:
        rows = ""
        for strategy, count in plan.strategy_breakdown.items():
            badge_cls = f"badge-{strategy.lower()}"
            rows += f'<tr><td><span class="badge {badge_cls}">{strategy}</span></td><td>{count} workloads</td></tr>'
        strategy_html = f"""
        <div class="wave">
          <h3 style="color:#e6edf3;border-left:3px solid #30363d;padding-left:10px;">6R Strategy Breakdown</h3>
          <table class="risk-table"><tbody>{rows}</tbody></table>
        </div>"""

    risk_rows = ""
    for r in plan.risk_register[:10]:
        risk_rows += f'<tr><td>{r.get("workload","")}</td><td>{r.get("risk","")}</td><td>{r.get("mitigation","")}</td></tr>'

    risk_html = ""
    if risk_rows:
        risk_html = f"""
        <div class="wave">
          <h3 style="color:#d29922;border-left:3px solid #d29922;padding-left:10px;">Risk Register</h3>
          <table class="risk-table">
            <thead><tr><th>Workload</th><th>Risk</th><th>Mitigation</th></tr></thead>
            <tbody>{risk_rows}</tbody>
          </table>
        </div>"""

    return f"""
    <div class="results">
      <div class="summary-box">
        <h3>EXECUTIVE SUMMARY</h3>
        <p>{plan.executive_summary}</p>
      </div>
      <div class="stats">
        <div class="stat"><div class="label">Workloads</div><div class="value">{plan.total_workloads}</div><div class="sub">analyzed</div></div>
        <div class="stat"><div class="label">Effort</div><div class="value">{plan.total_effort_weeks:.0f}</div><div class="sub">weeks total</div></div>
        <div class="stat"><div class="label">Duration</div><div class="value">{plan.estimated_months}</div><div class="sub">months est.</div></div>
        <div class="stat"><div class="label">Waves</div><div class="value">3</div><div class="sub">migration phases</div></div>
      </div>
      {waves_html}
      {strategy_html}
      {risk_html}
    </div>"""


def get_planner() -> MigrationPlanner:
    global _planner
    if _planner is None:
        _planner = MigrationPlanner()
    return _planner


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    html = HTML_PAGE.format(
        inventory="",
        error_block="",
        results_block="",
        example=EXAMPLE_WORKLOADS.replace("`", "\\`"),
    )
    return HTMLResponse(html)


@app.post("/plan", response_class=HTMLResponse)
async def plan(request: Request, inventory: str = Form(...)):
    error_block = ""
    results_block = ""
    plan_result = None

    if not inventory.strip():
        error_block = '<div class="error">&#9888; Please paste a workload inventory (CSV or JSON).</div>'
    else:
        try:
            planner = get_planner()
            plan_result = planner.plan(inventory)
            results_block = render_results(plan_result)
        except Exception as exc:
            error_block = f'<div class="error">&#9888; Planning failed: {exc}</div>'

    html = HTML_PAGE.format(
        inventory=inventory.replace("<", "&lt;").replace(">", "&gt;"),
        error_block=error_block,
        results_block=results_block,
        example=EXAMPLE_WORKLOADS.replace("`", "\\`"),
    )
    return HTMLResponse(html)


@app.get("/health")
async def health():
    return {"status": "ok", "module": "migrationscout"}
