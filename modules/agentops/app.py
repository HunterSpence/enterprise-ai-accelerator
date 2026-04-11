"""
AgentOps — Multi-Agent Orchestration Monitor
FastAPI app: define a goal + context → watch Claude orchestrate specialized sub-agents
Run: uvicorn app:app --reload --port 8005
"""

import os

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from orchestrator import AgentOrchestrator

load_dotenv()

app = FastAPI(title="AgentOps — Multi-Agent Monitor", version="1.0.0")

_orchestrator = None

EXAMPLE_TASK = "Perform a comprehensive cloud transformation assessment for our AWS environment"
EXAMPLE_CONTEXT = """{
  "environment": "Production AWS us-east-1",
  "monthly_spend": 284000,
  "workloads": 47,
  "migrated_to_cloud": 18,
  "security_score": 62,
  "open_critical_findings": 5,
  "compute_utilization_avg": 31,
  "reserved_instance_coverage": 38,
  "compliance_frameworks": ["SOC2", "PCI-DSS"],
  "top_services": ["EC2", "RDS", "S3", "Lambda", "EKS"],
  "incidents_last_30d": {"P1": 2, "P2": 8},
  "budget_variance": "+22%"
}"""

AGENT_COLORS = {
    "security_agent": ("#f85149", "#2d1b1e", "&#128737;", "Security Agent"),
    "cost_agent": ("#d29922", "#1e1600", "&#128184;", "FinOps Agent"),
    "migration_agent": ("#3fb950", "#0d1a10", "&#127758;", "Migration Agent"),
    "reporting_agent": ("#d2a8ff", "#1a1228", "&#128202;", "Executive Report Agent"),
}


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


def render_execution_trace(result) -> str:
    if not result:
        return ""

    # Agent call cards
    calls_html = ""
    for i, call in enumerate(result.agent_calls, 1):
        color, bg, icon, label = AGENT_COLORS.get(
            call.agent_name,
            ("#58a6ff", "#0d1523", "&#129302;", call.agent_name)
        )
        # Format result as bullet points
        lines = call.result.strip().split("\n")
        result_html = "".join(
            f'<div style="padding:4px 0;font-size:13px;color:#c9d1d9;line-height:1.5">{line}</div>'
            for line in lines if line.strip()
        )
        calls_html += f"""
        <div style="border:1px solid {color};border-left:4px solid {color};border-radius:8px;padding:16px 20px;background:{bg};margin-bottom:16px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
            <div style="display:flex;align-items:center;gap:10px">
              <span style="font-size:18px">{icon}</span>
              <div>
                <div style="font-size:13px;font-weight:700;color:{color}">{label}</div>
                <div style="font-size:11px;color:#8b949e">Agent #{i} · {call.duration_ms}ms</div>
              </div>
            </div>
            <div style="background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:4px 10px;font-size:11px;color:#8b949e">
              tool_use
            </div>
          </div>
          <div style="background:#0d1117;border-radius:4px;padding:10px 12px;margin-bottom:10px;font-size:12px;color:#8b949e">
            <span style="color:#58a6ff">task:</span> {call.task_input[:120]}{"..." if len(call.task_input) > 120 else ""}
          </div>
          <div style="background:#0d1117;border-radius:4px;padding:12px;border:1px solid #21262d">
            {result_html}
          </div>
        </div>"""

    # Agent badges
    agent_badges = ""
    for agent in result.agents_invoked:
        color, bg, icon, label = AGENT_COLORS.get(agent, ("#58a6ff", "#0d1523", "&#129302;", agent))
        agent_badges += f'<span style="display:inline-flex;align-items:center;gap:6px;background:{bg};border:1px solid {color};border-radius:16px;padding:4px 12px;font-size:12px;color:{color};font-weight:600">{icon} {label}</span>'

    # Orchestration plan
    plan_html = ""
    if result.orchestration_plan:
        plan_html = f"""
        <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px 20px;margin-bottom:20px">
          <div style="font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">ORCHESTRATOR REASONING</div>
          <p style="font-size:13px;color:#c9d1d9;line-height:1.6;white-space:pre-wrap">{result.orchestration_plan}</p>
        </div>"""

    # Final synthesis
    synthesis_html = ""
    if result.final_synthesis:
        lines = result.final_synthesis.strip().split("\n")
        synthesis_content = "".join(
            f'<p style="margin-bottom:8px;font-size:14px;color:#c9d1d9;line-height:1.6">{line}</p>'
            for line in lines if line.strip()
        )
        synthesis_html = f"""
        <div style="background:#0d1a10;border:1px solid #238636;border-radius:8px;padding:20px 24px">
          <div style="font-size:12px;color:#3fb950;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px">
            &#10003; FINAL SYNTHESIS — Orchestrator Output
          </div>
          {synthesis_content}
        </div>"""

    return f"""
    <div style="display:grid;gap:20px">
      <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px 24px">
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
          <div>
            <div style="font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Execution Complete</div>
            <div style="font-size:18px;font-weight:700;color:#e6edf3">{len(result.agent_calls)} agents · {result.total_duration_ms:,}ms</div>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:8px">{agent_badges}</div>
        </div>
      </div>
      {plan_html}
      <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px 24px">
        <div style="font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:16px">
          AGENT EXECUTION TRACE
        </div>
        {calls_html}
      </div>
      {synthesis_html}
    </div>"""


def render_page(task: str = "", context: str = "", result=None, error: str = "") -> str:
    error_block = f'<div style="background:#2d1b1e;border:1px solid #f85149;color:#f85149;border-radius:6px;padding:14px 18px">&#9888; {error}</div>' if error else ""
    results_block = render_execution_trace(result) if result else ""

    safe_task = task.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_context = context.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AgentOps — Multi-Agent Monitor</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #e6edf3; min-height: 100vh; }}
    .header {{ background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%); border-bottom: 1px solid #30363d; padding: 20px 40px; }}
    .logo {{ font-size: 24px; font-weight: 700; background: linear-gradient(135deg, #58a6ff, #d2a8ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
    .tagline {{ color: #8b949e; font-size: 14px; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 40px 24px; display: grid; gap: 24px; }}
    .form-section {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 24px; }}
    .form-section h2 {{ font-size: 16px; margin-bottom: 6px; font-weight: 600; }}
    .form-section .sub {{ font-size: 13px; color: #8b949e; margin-bottom: 16px; }}
    input[type=text] {{ width: 100%; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 12px 14px; color: #e6edf3; font-size: 14px; }}
    input[type=text]:focus {{ outline: none; border-color: #58a6ff; }}
    textarea {{ width: 100%; height: 180px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 14px; color: #e6edf3; font-family: monospace; font-size: 12px; line-height: 1.5; resize: vertical; }}
    textarea:focus {{ outline: none; border-color: #58a6ff; }}
    label {{ font-size: 13px; font-weight: 600; color: #8b949e; display: block; margin-bottom: 6px; }}
    .field {{ margin-bottom: 16px; }}
    .btn {{ background: linear-gradient(135deg, #1f6feb, #388bfd); color: #fff; border: 1px solid #388bfd; border-radius: 6px; padding: 12px 24px; font-size: 14px; font-weight: 600; cursor: pointer; transition: opacity 0.2s; }}
    .btn:hover {{ opacity: 0.85; }}
    .example-btn {{ background: transparent; border: 1px solid #30363d; color: #8b949e; font-size: 12px; padding: 6px 12px; border-radius: 6px; cursor: pointer; margin-left: 12px; }}
    .arch-diagram {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px 24px; }}
    .arch-diagram pre {{ font-size: 12px; color: #58a6ff; line-height: 1.5; font-family: monospace; }}
  </style>
</head>
<body>
  <div class="header">
    <div class="logo">&#129302; AgentOps</div>
    <div class="tagline">Multi-Agent Orchestration Monitor — Claude as orchestrator, specialized sub-agents as tools</div>
  </div>
  <div class="container">
    <div class="arch-diagram">
      <pre>User Task → Orchestrator (Claude) → [tool_use: security_agent | cost_agent | migration_agent | reporting_agent]
                    ↑                              ↓
                    └─── tool_results ─────────────┘
                    ↓
             Final Synthesis</pre>
    </div>
    <div class="form-section">
      <h2>&#127760; Task Definition
        <button class="example-btn" onclick="loadExample()">Load example</button>
      </h2>
      <p class="sub">Define a goal for the orchestrator. Claude will decompose it and dispatch specialized agents.</p>
      <form method="post" action="/run">
        <div class="field">
          <label>Goal / Task</label>
          <input type="text" name="task" value="{safe_task}" placeholder="e.g., Perform a comprehensive cloud transformation assessment for our AWS environment">
        </div>
        <div class="field">
          <label>Context / Data (optional JSON or text)</label>
          <textarea name="context" placeholder="Paste relevant context: current infrastructure state, metrics, constraints...">{safe_context}</textarea>
        </div>
        <button type="submit" class="btn">&#9654; Run Orchestration</button>
      </form>
    </div>
    {error_block}
    {results_block}
  </div>
  <script>
    function loadExample() {{
      document.querySelector('input[name=task]').value = `{EXAMPLE_TASK}`;
      document.querySelector('textarea[name=context]').value = `{EXAMPLE_CONTEXT.replace(chr(96), "'")}`;
    }}
  </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return HTMLResponse(render_page())


@app.post("/run", response_class=HTMLResponse)
async def run(request: Request, task: str = Form(...), context: str = Form("")):
    result = None
    error = ""

    if not task.strip():
        error = "Please provide a task for the orchestrator."
    else:
        try:
            orchestrator = get_orchestrator()
            result = orchestrator.orchestrate(task.strip(), context.strip())
        except Exception as exc:
            error = f"Orchestration failed: {exc}"

    return HTMLResponse(render_page(task, context, result, error))


@app.get("/health")
async def health():
    return {"status": "ok", "module": "agentops"}
