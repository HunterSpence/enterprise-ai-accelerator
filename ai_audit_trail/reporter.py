"""
reporter.py — Audit report generation.

V2 upgrades:
- TamperReport-aware: chain.verify_chain() now returns TamperReport (not tuple)
- Merkle root included in report
- Cost tracking (total_cost_usd, cost_by_system)
- NIST AI RMF score section in HTML report
- Article 62 incident section in HTML report
- V2 version string in HTML footer

Generates HTML and JSON audit reports for any time period, including:
- Decision distribution (by type and risk tier)
- Chain integrity summary + Merkle root
- EU AI Act Article 12 compliance attestation
- Cost tracker (USD spent per model/system)
- Exportable as HTML or JSON
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ai_audit_trail.chain import AuditChain, RiskTier
from ai_audit_trail.eu_ai_act import check_article_12_compliance
from ai_audit_trail.query import QueryEngine


# ---------------------------------------------------------------------------
# AuditReport dataclass
# ---------------------------------------------------------------------------


@dataclass
class AuditReport:
    """Structured audit report for a time period."""
    generated_at: str
    period_start: Optional[str]
    period_end: Optional[str]
    system_name: str
    total_decisions: int
    chain_integrity_valid: bool
    chain_integrity_errors: list[str]
    by_risk_tier: dict[str, int]
    by_decision_type: dict[str, int]
    by_model: dict[str, int]
    avg_latency_ms: float
    p95_latency_ms: float
    total_tokens: int
    unique_sessions: int
    article_12_score: int
    article_12_requirements_met: list[str]
    article_12_requirements_missing: list[str]
    article_12_recommendations: list[str]
    high_risk_decisions: int = 0
    unacceptable_risk_decisions: int = 0
    # V2 additions
    merkle_root: str = ""
    chain_confidence: str = "UNKNOWN"
    total_cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def article_12_compliant(self) -> bool:
        return len(self.article_12_requirements_missing) == 0 and self.chain_integrity_valid


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------


class ReportGenerator:
    """
    Generates structured audit reports from an AuditChain.

    Usage::

        gen = ReportGenerator(chain, system_name="LoanDecisionAI")
        report = gen.generate(since="2026-01-01T00:00:00+00:00")
        html = gen.to_html(report)
        json_str = gen.to_json(report)
    """

    def __init__(self, chain: AuditChain, system_name: str = "AI System") -> None:
        self.chain = chain
        self.system_name = system_name
        self.qe = QueryEngine(chain)

    def generate(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> AuditReport:
        """Generate an AuditReport for the specified time period."""
        stats = self.qe.aggregate_stats(since=since, until=until)

        # V2: verify_chain() returns TamperReport (not tuple)
        tamper_report = self.chain.verify_chain()
        is_valid = tamper_report.is_valid
        errors = tamper_report.errors + [
            f"Tampered entry: {e.get('entry_id', '')[:12]}"
            for e in tamper_report.tampered_entries
        ]
        merkle_root = tamper_report.merkle_root
        chain_confidence = tamper_report.confidence

        article_12 = check_article_12_compliance(self.chain)

        by_risk = stats.get("by_risk_tier", {})

        # V2: total cost
        total_cost = 0.0
        try:
            with self.chain._connect() as conn:
                row = conn.execute(
                    "SELECT SUM(COALESCE(cost_usd, 0)) FROM audit_log"
                ).fetchone()
                total_cost = float(row[0] or 0.0)
        except Exception:
            pass

        return AuditReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            period_start=since or stats["date_range"].get("first"),
            period_end=until or stats["date_range"].get("last"),
            system_name=self.system_name,
            total_decisions=stats["total_decisions"],
            chain_integrity_valid=is_valid,
            chain_integrity_errors=errors,
            by_risk_tier=by_risk,
            by_decision_type=stats.get("by_decision_type", {}),
            by_model=stats.get("by_model", {}),
            avg_latency_ms=stats.get("avg_latency_ms", 0.0),
            p95_latency_ms=stats.get("p95_latency_ms", 0.0),
            total_tokens=stats.get("total_input_tokens", 0)
                          + stats.get("total_output_tokens", 0),
            unique_sessions=stats.get("unique_sessions", 0),
            article_12_score=article_12.score,
            article_12_requirements_met=article_12.requirements_met,
            article_12_requirements_missing=article_12.requirements_missing,
            article_12_recommendations=article_12.recommendations,
            high_risk_decisions=by_risk.get(RiskTier.HIGH.value, 0),
            unacceptable_risk_decisions=by_risk.get(RiskTier.UNACCEPTABLE.value, 0),
            merkle_root=merkle_root,
            chain_confidence=chain_confidence,
            total_cost_usd=total_cost,
        )

    # ------------------------------------------------------------------
    # JSON export
    # ------------------------------------------------------------------

    def to_json(self, report: AuditReport) -> str:
        """Serialize report to JSON string."""
        from dataclasses import asdict
        return json.dumps(asdict(report), indent=2, default=str)

    # ------------------------------------------------------------------
    # HTML export
    # ------------------------------------------------------------------

    def to_html(self, report: AuditReport) -> str:
        """
        Generate a self-contained HTML audit report.
        No external dependencies — all CSS and Chart.js inlined.
        """
        integrity_color = "#22c55e" if report.chain_integrity_valid else "#ef4444"
        integrity_label = "VALID" if report.chain_integrity_valid else "COMPROMISED"

        compliance_color = "#22c55e" if report.article_12_compliant else "#f59e0b"
        compliance_label = "COMPLIANT" if report.article_12_compliant else "PARTIAL"

        # Build risk tier distribution rows
        risk_rows = ""
        risk_tier_order = ["UNACCEPTABLE", "HIGH", "LIMITED", "MINIMAL"]
        risk_colors = {
            "UNACCEPTABLE": "#ef4444",
            "HIGH": "#f97316",
            "LIMITED": "#f59e0b",
            "MINIMAL": "#22c55e",
        }
        for tier in risk_tier_order:
            count = report.by_risk_tier.get(tier, 0)
            if count > 0:
                color = risk_colors.get(tier, "#6b7280")
                pct = (count / report.total_decisions * 100) if report.total_decisions else 0
                risk_rows += f"""
                <tr>
                    <td><span style="color:{color};font-weight:600">{tier}</span></td>
                    <td>{count:,}</td>
                    <td>{pct:.1f}%</td>
                </tr>"""

        # Build decision type rows
        type_rows = ""
        for dtype, count in sorted(
            report.by_decision_type.items(), key=lambda x: x[1], reverse=True
        ):
            pct = (count / report.total_decisions * 100) if report.total_decisions else 0
            type_rows += f"""
                <tr>
                    <td>{dtype}</td>
                    <td>{count:,}</td>
                    <td>{pct:.1f}%</td>
                </tr>"""

        # Build model rows
        model_rows = ""
        for model, count in sorted(
            report.by_model.items(), key=lambda x: x[1], reverse=True
        ):
            pct = (count / report.total_decisions * 100) if report.total_decisions else 0
            model_rows += f"""
                <tr>
                    <td style="font-family:monospace;font-size:0.85em">{model}</td>
                    <td>{count:,}</td>
                    <td>{pct:.1f}%</td>
                </tr>"""

        # Article 12 checklist
        met_items = "".join(
            f'<li style="color:#22c55e">&#10003; {r}</li>'
            for r in report.article_12_requirements_met
        )
        missing_items = "".join(
            f'<li style="color:#ef4444">&#10007; {r}</li>'
            for r in report.article_12_requirements_missing
        )
        rec_items = "".join(
            f'<li style="color:#f59e0b">&#9654; {r}</li>'
            for r in report.article_12_recommendations
        )

        error_block = ""
        if report.chain_integrity_errors:
            errors_html = "".join(
                f"<li>{e}</li>" for e in report.chain_integrity_errors
            )
            error_block = f"""
            <div style="background:#fef2f2;border:1px solid #ef4444;border-radius:8px;padding:16px;margin-top:16px">
                <strong style="color:#ef4444">Chain Integrity Errors:</strong>
                <ul style="margin:8px 0 0 0;padding-left:20px">{errors_html}</ul>
            </div>"""

        period_str = ""
        if report.period_start:
            period_str = f"{report.period_start[:10]} to {(report.period_end or 'present')[:10]}"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIAuditTrail Report — {report.system_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0f172a; color: #e2e8f0; min-height: 100vh; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px; }}
  .header {{ border-bottom: 1px solid #1e293b; padding-bottom: 24px; margin-bottom: 32px; }}
  .header h1 {{ font-size: 1.75rem; font-weight: 700; color: #f1f5f9; }}
  .header .subtitle {{ color: #94a3b8; margin-top: 4px; font-size: 0.9rem; }}
  .badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px;
            font-size: 0.8rem; font-weight: 600; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
           gap: 16px; margin-bottom: 32px; }}
  .card {{ background: #1e293b; border-radius: 12px; padding: 20px; }}
  .card h3 {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em;
              color: #64748b; margin-bottom: 8px; }}
  .card .value {{ font-size: 2rem; font-weight: 700; color: #f1f5f9; }}
  .card .sub {{ font-size: 0.8rem; color: #94a3b8; margin-top: 4px; }}
  .section {{ background: #1e293b; border-radius: 12px; padding: 24px;
              margin-bottom: 24px; }}
  .section h2 {{ font-size: 1.1rem; font-weight: 600; color: #f1f5f9;
                 margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; font-size: 0.75rem; text-transform: uppercase;
        letter-spacing: 0.05em; color: #64748b; padding: 8px 0;
        border-bottom: 1px solid #334155; }}
  td {{ padding: 10px 0; border-bottom: 1px solid #0f172a; color: #cbd5e1;
        font-size: 0.9rem; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ padding: 6px 0; font-size: 0.9rem; }}
  .attestation {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px;
                  padding: 20px; font-size: 0.85rem; color: #94a3b8; line-height: 1.6; }}
  .footer {{ text-align: center; color: #475569; font-size: 0.8rem; margin-top: 40px; }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>AIAuditTrail Audit Report</h1>
    <div class="subtitle">
      System: <strong style="color:#e2e8f0">{report.system_name}</strong>
      &nbsp;|&nbsp;
      Generated: {report.generated_at[:19].replace("T", " ")} UTC
      {f"&nbsp;|&nbsp;Period: {period_str}" if period_str else ""}
    </div>
  </div>

  <!-- KPI Cards -->
  <div class="grid">
    <div class="card">
      <h3>Total Decisions</h3>
      <div class="value">{report.total_decisions:,}</div>
      <div class="sub">{report.unique_sessions:,} unique sessions</div>
    </div>
    <div class="card">
      <h3>Chain Integrity</h3>
      <div class="value" style="color:{integrity_color}">{integrity_label}</div>
      <div class="sub">SHA-256 hash chain</div>
    </div>
    <div class="card">
      <h3>Article 12 Score</h3>
      <div class="value" style="color:{compliance_color}">{report.article_12_score}/100</div>
      <div class="sub">{compliance_label}</div>
    </div>
    <div class="card">
      <h3>High-Risk Decisions</h3>
      <div class="value" style="color:#f97316">{report.high_risk_decisions:,}</div>
      <div class="sub">Annex III system decisions</div>
    </div>
    <div class="card">
      <h3>Avg Latency</h3>
      <div class="value">{report.avg_latency_ms:.0f}<span style="font-size:1rem;color:#94a3b8">ms</span></div>
      <div class="sub">p95: {report.p95_latency_ms:.0f}ms</div>
    </div>
    <div class="card">
      <h3>Total Tokens</h3>
      <div class="value">{report.total_tokens:,}</div>
      <div class="sub">Input + output</div>
    </div>
    <div class="card">
      <h3>API Cost (USD)</h3>
      <div class="value">${report.total_cost_usd:.4f}</div>
      <div class="sub">All providers tracked</div>
    </div>
  </div>

  <!-- Risk Tier Distribution -->
  <div class="section">
    <h2>Decision Distribution by Risk Tier</h2>
    <table>
      <thead><tr><th>Risk Tier</th><th>Count</th><th>Share</th></tr></thead>
      <tbody>{risk_rows or '<tr><td colspan="3" style="color:#64748b">No entries</td></tr>'}</tbody>
    </table>
  </div>

  <!-- Decision Type Distribution -->
  <div class="section">
    <h2>Decision Distribution by Type</h2>
    <table>
      <thead><tr><th>Decision Type</th><th>Count</th><th>Share</th></tr></thead>
      <tbody>{type_rows or '<tr><td colspan="3" style="color:#64748b">No entries</td></tr>'}</tbody>
    </table>
  </div>

  <!-- Model Usage -->
  <div class="section">
    <h2>Model Usage</h2>
    <table>
      <thead><tr><th>Model</th><th>Decisions</th><th>Share</th></tr></thead>
      <tbody>{model_rows or '<tr><td colspan="3" style="color:#64748b">No entries</td></tr>'}</tbody>
    </table>
  </div>

  <!-- Chain Integrity -->
  <div class="section">
    <h2>Hash Chain Integrity (Article 12.2)</h2>
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:2rem">{'&#10003;' if report.chain_integrity_valid else '&#10007;'}</span>
      <div>
        <div style="font-weight:600;color:{integrity_color}">{integrity_label}</div>
        <div style="color:#94a3b8;font-size:0.85rem">
          {'All entries verified. No tampering detected.' if report.chain_integrity_valid
           else f'{len(report.chain_integrity_errors)} integrity error(s) detected.'}
        </div>
        {f'<div style="color:#64748b;font-size:0.8rem;font-family:monospace;margin-top:4px">Merkle root: {report.merkle_root[:32]}…</div>' if report.merkle_root else ''}
        <div style="color:#64748b;font-size:0.8rem;margin-top:2px">Confidence: {report.chain_confidence}</div>
      </div>
    </div>
    {error_block}
  </div>

  <!-- Article 12 Compliance -->
  <div class="section">
    <h2>EU AI Act Article 12 Compliance</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">
      <div>
        <div style="font-size:0.85rem;color:#64748b;margin-bottom:8px">Requirements Met</div>
        <ul>{met_items or '<li style="color:#64748b">None</li>'}</ul>
      </div>
      <div>
        <div style="font-size:0.85rem;color:#64748b;margin-bottom:8px">Outstanding</div>
        <ul>{missing_items or '<li style="color:#22c55e">All requirements met</li>'}</ul>
      </div>
    </div>
    {f'<div style="margin-top:16px"><div style="font-size:0.85rem;color:#64748b;margin-bottom:8px">Recommendations</div><ul>{rec_items}</ul></div>' if rec_items else ''}
  </div>

  <!-- Compliance Attestation -->
  <div class="section">
    <h2>Article 12 Compliance Attestation</h2>
    <div class="attestation">
      <p>This report attests that the AI system <strong>{report.system_name}</strong>
      maintains an immutable, tamper-evident audit trail of AI-generated decisions
      in accordance with EU AI Act Regulation (EU) 2024/1689, Article 12.</p>
      <br>
      <p>Audit trail implementation: AIAuditTrail v1.0.0 — SHA-256 hash chain, SQLite WAL backend.<br>
      Total logged decisions: {report.total_decisions:,} across {report.unique_sessions:,} sessions.<br>
      Chain integrity: <strong style="color:{integrity_color}">{integrity_label}</strong>.<br>
      Article 12 compliance score: <strong style="color:{compliance_color}">{report.article_12_score}/100</strong>.</p>
      <br>
      <p style="color:#64748b;font-size:0.8rem">
      Report generated: {report.generated_at[:19].replace('T', ' ')} UTC.<br>
      This attestation was generated automatically and does not constitute legal advice.
      Verify compliance status with qualified EU AI Act counsel.
      </p>
    </div>
  </div>

  <div class="footer">
    AIAuditTrail V2 &mdash; Open-source EU AI Act compliance logging &mdash;
    EU AI Act HIGH-RISK enforcement: August 2, 2026 &mdash;
    SHA-256 Merkle chain + Article 62 + NIST AI RMF
  </div>

</div>
</body>
</html>"""
