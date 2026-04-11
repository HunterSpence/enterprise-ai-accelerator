"""
PolicyGuard — IaC Governance & Policy Checker
FastAPI app: paste Terraform/CloudFormation → get policy violations with severity + fixes
Run: uvicorn app:app --reload --port 8003
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from checker import PolicyChecker

load_dotenv()

app = FastAPI(title="PolicyGuard — IaC Policy Checker", version="1.0.0")

_checker = None

EXAMPLE_TERRAFORM = '''# Intentionally misconfigured Terraform for demo purposes
resource "aws_s3_bucket" "user_data" {
  bucket = "company-user-data-prod"
  acl    = "public-read"

  tags = {
    Name = "user-data"
  }
}

resource "aws_db_instance" "primary" {
  identifier        = "prod-mysql"
  engine            = "mysql"
  instance_class    = "db.t3.medium"
  username          = "admin"
  password          = "admin123"
  publicly_accessible = true
  storage_encrypted = false
  multi_az          = false
  skip_final_snapshot = true
}

resource "aws_security_group" "web" {
  name = "web-sg"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_user" "app_user" {
  name = "app-service-user"
  # No MFA policy attached
}'''


def severity_color(sev: str) -> str:
    s = sev.upper()
    if s == "CRITICAL":
        return "#f85149"
    if s == "HIGH":
        return "#e3a341"
    if s == "MEDIUM":
        return "#58a6ff"
    return "#3fb950"


def severity_bg(sev: str) -> str:
    s = sev.upper()
    if s == "CRITICAL":
        return "#2d1b1e"
    if s == "HIGH":
        return "#1e1600"
    if s == "MEDIUM":
        return "#0d1523"
    return "#0d1a10"


def render_page(iac_input: str = "", result=None, error: str = "") -> str:
    error_block = f'<div class="error">&#9888; {error}</div>' if error else ""

    results_block = ""
    if result:
        score_color = "#3fb950" if result.compliance_score >= 80 else "#d29922" if result.compliance_score >= 60 else "#f85149"

        violations_html = ""
        all_violations = result.violations
        for v in all_violations:
            sev = v.get("severity", "MEDIUM")
            color = severity_color(sev)
            bg = severity_bg(sev)
            fix_block = ""
            if v.get("fix"):
                fix_block = f'<pre style="background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:10px;margin-top:8px;font-size:11px;overflow-x:auto;color:#e6edf3">{v["fix"]}</pre>'
            violations_html += f"""
            <div style="border:1px solid #30363d;border-left:3px solid {color};border-radius:6px;padding:14px;background:{bg};margin-bottom:10px">
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
                <span style="background:{bg};color:{color};font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;border:1px solid {color}">{sev}</span>
                <span style="font-size:13px;font-weight:600;color:#e6edf3">{v.get("rule","")}</span>
              </div>
              <div style="font-size:13px;color:#c9d1d9;margin-bottom:4px">{v.get("description","")}</div>
              <div style="font-size:12px;color:#8b949e">Resource: <code style="color:#79c0ff">{v.get("resource","")}</code></div>
              {fix_block}
            </div>"""

        summary_html = ""
        if result.executive_summary:
            summary_html = f"""
            <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px 24px;margin-bottom:20px">
              <div style="font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">Executive Summary</div>
              <p style="font-size:14px;color:#c9d1d9;line-height:1.6">{result.executive_summary}</p>
            </div>"""

        results_block = f"""
        <div style="display:grid;gap:20px">
          {summary_html}
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">
            <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;text-align:center">
              <div style="font-size:11px;color:#8b949e;text-transform:uppercase;margin-bottom:8px">Compliance Score</div>
              <div style="font-size:36px;font-weight:700;color:{score_color}">{result.compliance_score}<span style="font-size:18px;color:#8b949e">/100</span></div>
            </div>
            <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;text-align:center">
              <div style="font-size:11px;color:#8b949e;text-transform:uppercase;margin-bottom:8px">Violations Found</div>
              <div style="font-size:36px;font-weight:700;color:#f85149">{len(result.violations)}</div>
            </div>
            <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;text-align:center">
              <div style="font-size:11px;color:#8b949e;text-transform:uppercase;margin-bottom:8px">Fix Time Est.</div>
              <div style="font-size:36px;font-weight:700;color:#d29922">{result.remediation_days}<span style="font-size:18px;color:#8b949e">d</span></div>
            </div>
          </div>
          <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px 24px">
            <h3 style="font-size:14px;font-weight:600;margin-bottom:16px">&#128680; Policy Violations</h3>
            {violations_html if violations_html else '<p style="color:#8b949e;font-size:14px">No violations found.</p>'}
          </div>
        </div>"""

    safe_input = iac_input.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_example = EXAMPLE_TERRAFORM.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PolicyGuard — IaC Policy Checker</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #e6edf3; min-height: 100vh; }}
    .header {{ background: linear-gradient(135deg, #161b22 0%, #1a1a2e 100%); border-bottom: 1px solid #30363d; padding: 20px 40px; }}
    .logo {{ font-size: 24px; font-weight: 700; color: #d2a8ff; }}
    .tagline {{ color: #8b949e; font-size: 14px; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 40px 24px; display: grid; gap: 24px; }}
    .form-section {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 24px; }}
    .form-section h2 {{ font-size: 16px; margin-bottom: 16px; font-weight: 600; }}
    textarea {{ width: 100%; height: 300px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 14px; color: #e6edf3; font-family: monospace; font-size: 12px; line-height: 1.5; resize: vertical; }}
    textarea:focus {{ outline: none; border-color: #d2a8ff; }}
    .btn {{ display: inline-flex; align-items: center; gap: 8px; background: #6e40c9; color: #fff; border: 1px solid #8957e5; border-radius: 6px; padding: 10px 20px; font-size: 14px; font-weight: 600; cursor: pointer; }}
    .btn:hover {{ background: #8957e5; }}
    .example-btn {{ background: transparent; border: 1px solid #30363d; color: #8b949e; font-size: 12px; padding: 6px 12px; border-radius: 6px; cursor: pointer; margin-left: 12px; }}
    .error {{ background: #2d1b1e; border: 1px solid #f85149; color: #f85149; border-radius: 6px; padding: 14px 18px; }}
  </style>
</head>
<body>
  <div class="header">
    <div class="logo">&#128737; PolicyGuard</div>
    <div class="tagline">IaC Policy Checker — CRITICAL/HIGH/MEDIUM violations with remediation code</div>
  </div>
  <div class="container">
    <div class="form-section">
      <h2>&#128196; Terraform / CloudFormation Input
        <button class="example-btn" onclick="loadExample()">Load misconfigured Terraform example</button>
      </h2>
      <form method="post" action="/check">
        <textarea name="iac_input" id="iac_input" placeholder="Paste your Terraform HCL or CloudFormation YAML/JSON...">{safe_input}</textarea>
        <div style="margin-top:16px">
          <button type="submit" class="btn">&#128737; Check Policies</button>
        </div>
      </form>
    </div>
    {error_block}
    {results_block}
  </div>
  <script>
    function loadExample() {{
      document.getElementById('iac_input').value = `{safe_example}`;
    }}
  </script>
</body>
</html>"""


def get_checker() -> PolicyChecker:
    global _checker
    if _checker is None:
        _checker = PolicyChecker()
    return _checker


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return HTMLResponse(render_page())


@app.post("/check", response_class=HTMLResponse)
async def check(request: Request, iac_input: str = Form(...)):
    result = None
    error = ""

    if not iac_input.strip():
        error = "Please paste Terraform HCL or CloudFormation template."
    else:
        try:
            checker = get_checker()
            result = checker.check(iac_input)
        except Exception as exc:
            error = f"Policy check failed: {exc}"

    return HTMLResponse(render_page(iac_input, result, error))


@app.get("/health")
async def health():
    return {"status": "ok", "module": "policyguard"}
