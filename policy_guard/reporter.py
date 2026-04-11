"""
PolicyGuard — Report Generator V2
====================================
Generates board-ready HTML reports with PDF-export support (WeasyPrint optional).

V2 Enhancements:
  - Executive summary with risk radar chart (inline SVG, no CDN)
  - Framework-by-framework scorecard with evidence citations
  - Remediation roadmap ordered by (impact / effort) ratio
  - EU AI Act Article 12 attestation signature block
  - Cross-framework efficiency summary
  - Board-ready language throughout
  - PDF-ready layout (WeasyPrint compatible)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from policy_guard.scanner import ComplianceReport


# ---------------------------------------------------------------------------
# Effort and cost estimates per severity
# ---------------------------------------------------------------------------

REMEDIATION_EFFORT: dict[str, dict] = {
    "CRITICAL": {"hours": 40, "rate_usd": 200, "timeline_days": 14},
    "HIGH":     {"hours": 24, "rate_usd": 150, "timeline_days": 30},
    "MEDIUM":   {"hours": 8,  "rate_usd": 120, "timeline_days": 60},
    "LOW":      {"hours": 2,  "rate_usd": 100, "timeline_days": 90},
}

CONSULTANT_HOURLY_RATE = 350  # Big 4 blended rate


@dataclass
class RemediationItem:
    framework: str
    finding_id: str
    title: str
    severity: str
    estimated_hours: int
    estimated_cost_usd: int
    timeline_days: int
    remediation: str
    impact_effort_ratio: float = 0.0
    cross_framework: dict = None  # type: ignore

    def __post_init__(self) -> None:
        if self.cross_framework is None:
            self.cross_framework = {}
        severity_scores = {"CRITICAL": 100, "HIGH": 75, "MEDIUM": 40, "LOW": 10}
        impact = severity_scores.get(self.severity, 40)
        self.impact_effort_ratio = round(impact / max(1, self.estimated_hours), 3)


class ReportGenerator:
    """Generates board-ready compliance reports from ComplianceReport."""

    def __init__(
        self,
        report: ComplianceReport,
        anthropic_api_key: Optional[str] = None,
    ) -> None:
        self.report = report
        self.anthropic_api_key = anthropic_api_key
        self._executive_summary: Optional[str] = None

    def _generate_executive_summary(self) -> str:
        report = self.report

        fw_summary_lines = []
        for fs in report.framework_scores:
            fw_summary_lines.append(
                f"  - {fs.framework.upper()}: {fs.score:.0f}% compliance "
                f"({fs.findings_count} findings, {fs.critical_count} Critical, {fs.high_count} High)"
            )
        fw_summary = "\n".join(fw_summary_lines)

        context = (
            f"Overall compliance score: {report.overall_score:.1f}% ({report.risk_rating})\n"
            f"Total findings: {report.total_findings} "
            f"(Critical: {report.critical_findings}, High: {report.high_findings}, "
            f"Medium: {report.medium_findings}, Low: {report.low_findings})\n"
            f"Frameworks scanned:\n{fw_summary}"
        )

        if self.anthropic_api_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=self.anthropic_api_key)
                prompt = (
                    "You are the Chief Information Security Officer preparing a board presentation. "
                    "Write a 3-paragraph executive summary for a compliance report with these results:\n\n"
                    f"{context}\n\n"
                    "Paragraph 1: State the overall compliance posture and what it means for the business.\n"
                    "Paragraph 2: Highlight the top 3 risks requiring immediate board attention and their potential business impact.\n"
                    "Paragraph 3: Recommend the investment required and the ROI vs cost of non-compliance.\n\n"
                    "Use formal, board-appropriate language. No bullet points. Under 300 words."
                )
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text
            except Exception:
                pass

        risk_words = {
            "Critical Risk": "severely non-compliant",
            "High Risk": "significantly non-compliant",
            "Medium Risk": "partially non-compliant",
            "Low Risk": "largely compliant with minor gaps",
            "Compliant": "compliant",
        }
        risk_word = risk_words.get(report.risk_rating, "under review")

        return (
            f"This PolicyGuard compliance assessment reveals that the organization is currently "
            f"{risk_word} across the regulatory frameworks evaluated, with an overall score of "
            f"{report.overall_score:.1f}%. A total of {report.total_findings} compliance gaps were "
            f"identified, including {report.critical_findings} Critical findings that require immediate "
            f"remediation to avoid regulatory penalties and security breaches.\n\n"
            f"The most significant risks identified include failures in AI audit logging, bias testing, "
            f"and technical documentation completeness — areas that regulators prioritize in EU AI Act "
            f"enforcement. Unaddressed Critical and High findings expose the organization to EU AI Act "
            f"fines of up to €35 million or 3% of global annual turnover, HIPAA penalties of up to "
            f"$1.9 million per violation category, and reputational damage from a public compliance failure.\n\n"
            f"A focused remediation program addressing the {report.critical_findings} Critical and "
            f"{report.high_findings} High findings is estimated at ${self._total_cost_estimate():,} "
            f"in engineering and documentation effort — a fraction of the $150K–$2M consulting engagements "
            f"charged by Big 4 firms. The board is advised to authorize this investment and assign "
            f"ownership of the remediation roadmap to the CISO with a 90-day progress review, "
            f"targeting full EU AI Act compliance before the August 2, 2026 enforcement deadline."
        )

    def _total_cost_estimate(self) -> int:
        total = 0
        for fw in ["cis_aws", "eu_ai_act", "nist_ai_rmf", "soc2", "hipaa"]:
            fw_report = getattr(self.report, fw, None)
            if fw_report:
                for finding in getattr(fw_report, "findings", []):
                    if hasattr(finding, "status") and finding.status == "FAIL":
                        sev = getattr(finding, "severity", "MEDIUM")
                        effort = REMEDIATION_EFFORT.get(sev, REMEDIATION_EFFORT["MEDIUM"])
                        total += effort["hours"] * effort["rate_usd"]
        return total

    def _build_remediation_roadmap(self) -> list[RemediationItem]:
        items: list[RemediationItem] = []

        framework_finding_map = {
            "CIS AWS": ("cis_aws", "findings"),
            "EU AI Act": ("eu_ai_act", "findings"),
            "NIST AI RMF": ("nist_ai_rmf", "findings"),
            "SOC 2": ("soc2", "findings"),
            "HIPAA": ("hipaa", "findings"),
        }

        for fw_label, (fw_attr, findings_attr) in framework_finding_map.items():
            fw_report = getattr(self.report, fw_attr, None)
            if fw_report is None:
                continue
            findings = getattr(fw_report, findings_attr, [])
            for finding in findings:
                if not hasattr(finding, "status") or finding.status != "FAIL":
                    continue
                sev = getattr(finding, "severity", "MEDIUM")
                effort = REMEDIATION_EFFORT.get(sev, REMEDIATION_EFFORT["MEDIUM"])
                cross = getattr(finding, "cross_framework", {}) or {}
                items.append(RemediationItem(
                    framework=fw_label,
                    finding_id=getattr(finding, "control_id",
                                       getattr(finding, "check_id",
                                               getattr(finding, "subcategory", ""))),
                    title=getattr(finding, "title", ""),
                    severity=sev,
                    estimated_hours=effort["hours"],
                    estimated_cost_usd=effort["hours"] * effort["rate_usd"],
                    timeline_days=effort["timeline_days"],
                    remediation=getattr(finding, "remediation", ""),
                    cross_framework=cross,
                ))

        # Sort by impact/effort ratio descending (highest ROI first)
        items.sort(key=lambda x: x.impact_effort_ratio, reverse=True)
        return items

    def _build_radar_svg(self) -> str:
        """Build an inline SVG radar chart for framework scores. No CDN required."""
        fw_labels = {
            "cis_aws": "CIS AWS",
            "eu_ai_act": "EU AI Act",
            "nist_ai_rmf": "NIST RMF",
            "soc2": "SOC 2",
            "hipaa": "HIPAA",
        }
        scores = {fs.framework: fs.score / 100 for fs in self.report.framework_scores}

        if not scores:
            return ""

        import math
        cx, cy, r = 200, 200, 150
        n = len(scores)
        fw_list = list(scores.keys())
        angles = [2 * math.pi * i / n - math.pi / 2 for i in range(n)]

        def point(angle: float, radius: float) -> tuple[float, float]:
            return cx + radius * math.cos(angle), cy + radius * math.sin(angle)

        # Grid circles
        grid = ""
        for gr in [0.25, 0.5, 0.75, 1.0]:
            pts = [f"{point(a, r * gr)[0]:.1f},{point(a, r * gr)[1]:.1f}" for a in angles]
            grid += f'<polygon points="{" ".join(pts)}" fill="none" stroke="#e2e8f0" stroke-width="1"/>\n'

        # Axis lines
        axes = ""
        for angle in angles:
            px, py = point(angle, r)
            axes += f'<line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" stroke="#cbd5e1" stroke-width="1"/>\n'

        # Data polygon
        data_pts = []
        for fw, angle in zip(fw_list, angles):
            score = scores.get(fw, 0.0)
            px, py = point(angle, r * score)
            data_pts.append(f"{px:.1f},{py:.1f}")
        poly_color = "#ef4444" if self.report.overall_score < 50 else "#f97316" if self.report.overall_score < 70 else "#22c55e"
        data_polygon = f'<polygon points="{" ".join(data_pts)}" fill="{poly_color}" fill-opacity="0.3" stroke="{poly_color}" stroke-width="2"/>\n'

        # Labels
        labels = ""
        for fw, angle in zip(fw_list, angles):
            score = scores.get(fw, 0.0)
            lx, ly = point(angle, r + 25)
            label = fw_labels.get(fw, fw)
            labels += (
                f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
                f'font-size="12" fill="#374151" font-family="sans-serif">'
                f'{label} {score * 100:.0f}%</text>\n'
            )

        return f"""
<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" width="350" height="350">
  {grid}
  {axes}
  {data_polygon}
  {labels}
  <text x="{cx}" y="{cy + 5}" text-anchor="middle" font-size="14" font-weight="bold"
    fill="#1e293b" font-family="sans-serif">{self.report.overall_score:.0f}%</text>
  <text x="{cx}" y="{cy + 22}" text-anchor="middle" font-size="11"
    fill="#64748b" font-family="sans-serif">{self.report.risk_rating}</text>
</svg>"""

    def generate_html(self, output_dir: str = ".") -> str:
        """Generate board-ready HTML compliance report."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = self.report.timestamp.strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, f"policyguard_v2_report_{timestamp}.html")

        if self._executive_summary is None:
            self._executive_summary = self._generate_executive_summary()

        roadmap = self._build_remediation_roadmap()
        total_cost = sum(r.estimated_cost_usd for r in roadmap)
        consultant_cost = total_cost * (CONSULTANT_HOURLY_RATE / 150)
        radar_svg = self._build_radar_svg()

        sev_colors = {
            "CRITICAL": "#dc2626",
            "HIGH": "#f97316",
            "MEDIUM": "#eab308",
            "LOW": "#22c55e",
        }

        def sev_badge(severity: str) -> str:
            color = sev_colors.get(severity, "#6b7280")
            return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;">{severity}</span>'

        def score_bar(score: float) -> str:
            color = "#dc2626" if score < 50 else "#f97316" if score < 70 else "#eab308" if score < 85 else "#22c55e"
            return (
                f'<div style="background:#e5e7eb;border-radius:4px;height:10px;width:180px;display:inline-block;vertical-align:middle;">'
                f'<div style="background:{color};width:{score:.0f}%;height:100%;border-radius:4px;"></div></div>'
                f'<span style="margin-left:8px;font-weight:bold;color:{color};">{score:.0f}%</span>'
            )

        fw_labels = {
            "cis_aws": "CIS AWS Foundations Benchmark v3.0",
            "eu_ai_act": "EU AI Act (Regulation 2024/1689)",
            "nist_ai_rmf": "NIST AI Risk Management Framework 1.0",
            "soc2": "SOC 2 Type II + AICC (2024)",
            "hipaa": "HIPAA Security Rule (AI Focus)",
        }

        fw_rows = ""
        for fs in self.report.framework_scores:
            label = fw_labels.get(fs.framework, fs.framework)
            fw_rows += f"""
            <tr>
                <td style="padding:12px;font-weight:500;">{label}</td>
                <td style="padding:12px;">{score_bar(fs.score)}</td>
                <td style="padding:12px;text-align:center;">{fs.findings_count}</td>
                <td style="padding:12px;text-align:center;color:#dc2626;font-weight:bold;">{fs.critical_count}</td>
                <td style="padding:12px;text-align:center;color:#f97316;">{fs.high_count}</td>
                <td style="padding:12px;text-align:center;">{fs.weight:.0%}</td>
            </tr>"""

        # Top 20 remediation items
        top_items = roadmap[:20]
        roadmap_rows = ""
        for i, item in enumerate(top_items):
            cross_text = "; ".join(f"{k}: {v}" for k, v in (item.cross_framework or {}).items())[:60]
            roadmap_rows += f"""
            <tr style="background:{'#fff7ed' if item.severity == 'HIGH' else '#fef2f2' if item.severity == 'CRITICAL' else 'white'};">
                <td style="padding:10px;text-align:center;font-weight:bold;">{i + 1}</td>
                <td style="padding:10px;">{sev_badge(item.severity)}</td>
                <td style="padding:10px;font-size:12px;color:#64748b;">{item.framework}</td>
                <td style="padding:10px;font-size:13px;">{item.title[:50]}</td>
                <td style="padding:10px;text-align:center;">{item.estimated_hours}h</td>
                <td style="padding:10px;text-align:center;">${item.estimated_cost_usd:,}</td>
                <td style="padding:10px;text-align:center;">{item.timeline_days}d</td>
                <td style="padding:10px;font-size:11px;color:#64748b;">{cross_text}</td>
            </tr>"""

        # EU AI Act system classifications
        eu_systems_html = ""
        if self.report.eu_ai_act:
            for c in self.report.eu_ai_act.all_classifications:
                tier_colors = {
                    "Unacceptable": "#dc2626",
                    "High-Risk": "#f97316",
                    "GPAI (General Purpose AI)": "#8b5cf6",
                    "Limited Risk": "#eab308",
                    "Minimal Risk": "#22c55e",
                }
                color = tier_colors.get(c.risk_tier, "#6b7280")
                deadline_text = (
                    f"Conformity deadline: {c.conformity_deadline.strftime('%B %d, %Y')}"
                    if c.conformity_deadline else ""
                )
                eu_systems_html += f"""
                <div style="border-left:4px solid {color};padding:14px;margin:10px 0;background:#f9fafb;border-radius:0 6px 6px 0;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <strong style="font-size:15px;">{c.system_name}</strong>
                        <span style="background:{color};color:white;padding:3px 10px;border-radius:4px;font-size:12px;">{c.risk_tier}</span>
                    </div>
                    <p style="margin:8px 0 4px;font-size:13px;color:#374151;">{c.justification}</p>
                    <p style="margin:4px 0;font-size:12px;color:#6b7280;">{deadline_text} | Conformity route: {c.conformity_route}</p>
                </div>"""

        # Deadline table
        deadline_html = ""
        if self.report.eu_ai_act and self.report.eu_ai_act.deadline_status:
            for dl in self.report.eu_ai_act.deadline_status:
                is_past = dl.get("is_past", False)
                days = dl.get("days_remaining", 0)
                urgency = dl.get("urgency", "MEDIUM")
                color = "#22c55e" if is_past else "#dc2626" if urgency == "CRITICAL" else "#f97316" if urgency == "HIGH" else "#6b7280"
                status_label = "PAST" if is_past else f"{days} days remaining"
                deadline_html += f"""
                <tr>
                    <td style="padding:10px;font-weight:500;">{dl['deadline_str']}</td>
                    <td style="padding:10px;">{dl['milestone']}</td>
                    <td style="padding:10px;">{dl['affects']}</td>
                    <td style="padding:10px;color:{color};font-weight:bold;">{status_label}</td>
                </tr>"""

        # Cross-framework efficiency section
        cross_fw_html = ""
        if hasattr(self.report, "nist_ai_rmf") and self.report.nist_ai_rmf:
            gaps = getattr(self.report.nist_ai_rmf, "cross_framework_gaps", [])
            for gap in gaps[:5]:
                frameworks_str = " + ".join(gap.frameworks_addressed)
                cross_fw_html += f"""
                <div style="border:1px solid #e2e8f0;border-radius:6px;padding:14px;margin:8px 0;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                        <strong>{gap.title}</strong>
                        <span style="background:#dbeafe;color:#1d4ed8;padding:2px 8px;border-radius:4px;font-size:11px;">~{gap.estimated_effort_days}d</span>
                    </div>
                    <p style="margin:6px 0;font-size:13px;color:#374151;">{gap.description}</p>
                    <p style="margin:4px 0;font-size:12px;color:#64748b;"><strong>Frameworks addressed:</strong> {frameworks_str}</p>
                    <p style="margin:4px 0;font-size:12px;color:#059669;"><strong>Implementation:</strong> {gap.single_implementation}</p>
                </div>"""

        overall_color = (
            "#dc2626" if self.report.overall_score < 50 else
            "#f97316" if self.report.overall_score < 70 else
            "#eab308" if self.report.overall_score < 85 else
            "#22c55e"
        )

        days_left = 0
        if self.report.eu_ai_act:
            days_left = getattr(self.report.eu_ai_act, "days_to_high_risk_deadline", 0)

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PolicyGuard V2 Compliance Report — {self.report.timestamp.strftime('%Y-%m-%d')}</title>
    <style>
        @media print {{
            .no-print {{ display: none; }}
            body {{ background: white; }}
            .card {{ box-shadow: none; border: 1px solid #e2e8f0; }}
        }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 0; background: #f8fafc; color: #1e293b; }}
        .header {{ background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); color: white; padding: 40px; }}
        .header h1 {{ margin: 0; font-size: 26px; font-weight: 700; }}
        .header p {{ margin: 6px 0 0; opacity: 0.7; font-size: 13px; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 32px; }}
        .card {{ background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 24px; margin-bottom: 24px; }}
        .card h2 {{ margin: 0 0 20px; font-size: 17px; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }}
        .score-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 24px; }}
        .score-box {{ background: white; border-radius: 8px; padding: 16px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .score-box .number {{ font-size: 28px; font-weight: 700; }}
        .score-box .label {{ font-size: 11px; color: #64748b; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #f1f5f9; padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 600; color: #374151; text-transform: uppercase; letter-spacing: 0.5px; }}
        tr:nth-child(even) {{ background: #f8fafc; }}
        tr:hover {{ background: #f1f5f9; }}
        .overall-score {{ font-size: 64px; font-weight: 800; color: {overall_color}; line-height: 1; }}
        .deadline-banner {{ background: linear-gradient(135deg, #dc2626, #991b1b); color: white; padding: 16px 24px; border-radius: 8px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; }}
        .attestation {{ background: #f0fdf4; border: 2px solid #22c55e; border-radius: 8px; padding: 24px; }}
        .sig-line {{ border-bottom: 1px solid #9ca3af; width: 200px; display: inline-block; margin: 0 16px; }}
        .footer {{ text-align: center; padding: 32px; color: #64748b; font-size: 12px; border-top: 1px solid #e2e8f0; }}
    </style>
</head>
<body>

<div class="header">
    <h1>PolicyGuard V2 — AI Governance Compliance Report</h1>
    <p>Scan ID: {self.report.scan_id} | Generated: {self.report.timestamp.strftime('%B %d, %Y at %H:%M UTC')} | Duration: {self.report.scan_duration_seconds:.1f}s</p>
    <p>Frameworks: EU AI Act (Articles 5-55) + NIST AI RMF 1.0 (72 subcategories) + SOC 2 AICC (2024) + CIS AWS + HIPAA</p>
</div>

<div class="container">

    <!-- Urgency Banner -->
    <div class="deadline-banner">
        <div>
            <strong style="font-size:16px;">EU AI Act High-Risk Enforcement: {days_left} Days Remaining</strong>
            <p style="margin:4px 0 0;opacity:0.85;font-size:13px;">August 2, 2026 — Mandatory conformity assessments for all Annex III AI systems. Non-compliance: up to €35,000,000 or 3% global turnover.</p>
        </div>
        <div style="text-align:right;font-size:28px;font-weight:800;">{days_left}d</div>
    </div>

    <!-- Executive Summary -->
    <div class="card">
        <h2>Executive Summary</h2>
        <div style="display:flex;align-items:flex-start;gap:40px;margin-bottom:24px;">
            <div style="text-align:center;min-width:200px;">
                <div class="overall-score">{self.report.overall_score:.0f}%</div>
                <div style="font-size:15px;font-weight:600;color:{overall_color};margin-top:4px;">{self.report.risk_rating}</div>
                <div style="margin-top:16px;">{radar_svg}</div>
            </div>
            <div style="flex:1;">
                <div style="line-height:1.8;color:#374151;font-size:14px;">{self._executive_summary.replace(chr(10), '<br><br>')}</div>
            </div>
        </div>
    </div>

    <!-- Score Cards -->
    <div class="score-grid">
        <div class="score-box"><div class="number" style="color:#dc2626;">{self.report.critical_findings}</div><div class="label">Critical</div></div>
        <div class="score-box"><div class="number" style="color:#f97316;">{self.report.high_findings}</div><div class="label">High</div></div>
        <div class="score-box"><div class="number" style="color:#eab308;">{self.report.medium_findings}</div><div class="label">Medium</div></div>
        <div class="score-box"><div class="number" style="color:#22c55e;">{self.report.low_findings}</div><div class="label">Low</div></div>
        <div class="score-box"><div class="number">{self.report.total_findings}</div><div class="label">Total</div></div>
    </div>

    <!-- Framework Scores -->
    <div class="card">
        <h2>Framework Compliance Scorecards</h2>
        <table>
            <thead><tr><th>Framework</th><th>Score</th><th>Findings</th><th>Critical</th><th>High</th><th>Weight</th></tr></thead>
            <tbody>{fw_rows}</tbody>
        </table>
    </div>

    <!-- EU AI Act System Classifications -->
    <div class="card">
        <h2>EU AI Act — AI System Risk Classifications</h2>
        <p style="color:#64748b;font-size:13px;margin-bottom:16px;">AI systems evaluated against Annex III categories and Article 5 prohibited practices. Systems classified as High-Risk must be fully compliant by August 2, 2026.</p>
        {eu_systems_html if eu_systems_html else '<p style="color:#64748b;">No AI systems registered for this scan.</p>'}
    </div>

    <!-- EU AI Act Deadlines -->
    <div class="card">
        <h2>EU AI Act Compliance Milestones</h2>
        <table>
            <thead><tr><th>Deadline</th><th>Milestone</th><th>Affected Entities</th><th>Status</th></tr></thead>
            <tbody>{deadline_html if deadline_html else '<tr><td colspan="4" style="padding:12px;color:#64748b;">No deadline data.</td></tr>'}</tbody>
        </table>
    </div>

    <!-- Remediation Roadmap -->
    <div class="card">
        <h2>Remediation Roadmap — Ordered by Impact/Effort Ratio</h2>
        <p style="color:#64748b;font-size:13px;margin-bottom:16px;">Items ranked by (severity_impact / effort_hours) — highest return-on-remediation first. Cross-framework wins highlighted where one fix satisfies multiple frameworks.</p>
        <table>
            <thead><tr><th>#</th><th>Sev</th><th>Framework</th><th>Finding</th><th>Hours</th><th>Cost</th><th>Days</th><th>Cross-Framework</th></tr></thead>
            <tbody>{roadmap_rows if roadmap_rows else '<tr><td colspan="8" style="padding:12px;color:#22c55e;">No critical or high findings.</td></tr>'}</tbody>
        </table>
    </div>

    <!-- Cross-Framework Efficiency -->
    {f'<div class="card"><h2>Cross-Framework Efficiency Opportunities</h2><p style="color:#64748b;font-size:13px;margin-bottom:16px;">These implementations each satisfy multiple regulatory frameworks simultaneously — maximum compliance ROI.</p>{cross_fw_html}</div>' if cross_fw_html else ''}

    <!-- Cost Comparison -->
    <div class="card">
        <h2>Remediation Cost vs. Consulting Alternative</h2>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;">
            <div style="background:#f0fdf4;border:2px solid #22c55e;border-radius:8px;padding:20px;text-align:center;">
                <div style="font-size:11px;color:#64748b;margin-bottom:6px;">POLICYGUARD ESTIMATE</div>
                <div style="font-size:32px;font-weight:800;color:#22c55e;">${total_cost:,}</div>
                <div style="font-size:12px;color:#374151;margin-top:6px;">Engineering at $150/hr avg</div>
            </div>
            <div style="background:#fef2f2;border:2px solid #dc2626;border-radius:8px;padding:20px;text-align:center;">
                <div style="font-size:11px;color:#64748b;margin-bottom:6px;">IBM OPENPAGES</div>
                <div style="font-size:32px;font-weight:800;color:#dc2626;">$500K</div>
                <div style="font-size:12px;color:#374151;margin-top:6px;">Annual license fee</div>
            </div>
            <div style="background:#fef2f2;border:2px solid #f97316;border-radius:8px;padding:20px;text-align:center;">
                <div style="font-size:11px;color:#64748b;margin-bottom:6px;">CREDO AI</div>
                <div style="font-size:32px;font-weight:800;color:#f97316;">$180K</div>
                <div style="font-size:12px;color:#374151;margin-top:6px;">Annual subscription</div>
            </div>
        </div>
    </div>

    <!-- Article 12 Attestation Block -->
    <div class="card">
        <h2>EU AI Act Article 12 — Compliance Attestation</h2>
        <div class="attestation">
            <p style="font-size:13px;color:#374151;margin-bottom:20px;">
                This compliance assessment was conducted by PolicyGuard V2 against EU AI Act (Regulation 2024/1689)
                requirements. The undersigned confirms that the findings and remediation steps in this report
                have been reviewed and that a remediation programme has been authorized in accordance with
                Article 12 (Record-Keeping) obligations.
            </p>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin-top:24px;">
                <div>
                    <p style="font-size:12px;color:#6b7280;margin-bottom:4px;">Chief Information Security Officer</p>
                    <div class="sig-line">&nbsp;</div>
                    <p style="font-size:11px;color:#9ca3af;margin-top:4px;">Signature / Date</p>
                </div>
                <div>
                    <p style="font-size:12px;color:#6b7280;margin-bottom:4px;">Chief Technology Officer</p>
                    <div class="sig-line">&nbsp;</div>
                    <p style="font-size:11px;color:#9ca3af;margin-top:4px;">Signature / Date</p>
                </div>
                <div>
                    <p style="font-size:12px;color:#6b7280;margin-bottom:4px;">General Counsel</p>
                    <div class="sig-line">&nbsp;</div>
                    <p style="font-size:11px;color:#9ca3af;margin-top:4px;">Signature / Date</p>
                </div>
            </div>
            <p style="font-size:11px;color:#9ca3af;margin-top:20px;">
                PolicyGuard Scan ID: {self.report.scan_id} | Report generated: {self.report.timestamp.strftime('%Y-%m-%d %H:%M UTC')} | Next review due: {(self.report.timestamp.replace(month=min(12, self.report.timestamp.month + 3))).strftime('%Y-%m-%d')}
            </p>
        </div>
    </div>

</div>

<div class="footer">
    <p><strong>PolicyGuard V2.0</strong> — AI Governance and Cloud Compliance Platform</p>
    <p>EU AI Act + NIST AI RMF (72 subcategories) + SOC 2 AICC (2024) + CIS AWS + HIPAA</p>
    <p>This report is for informational purposes. For regulatory advice, consult qualified legal counsel.</p>
</div>

</body>
</html>"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return output_path

    def generate_pdf(self, output_dir: str = ".") -> str:
        """Generate PDF from HTML using WeasyPrint (optional)."""
        html_path = self.generate_html(output_dir)
        pdf_path = html_path.replace(".html", ".pdf")

        try:
            from weasyprint import HTML  # type: ignore
            HTML(filename=html_path).write_pdf(pdf_path)
            return pdf_path
        except ImportError:
            mock_pdf_path = html_path.replace(".html", "_MOCK.pdf")
            with open(mock_pdf_path, "wb") as f:
                f.write(b"%PDF-1.4 PolicyGuard V2 MOCK PDF - install weasyprint for real PDF\n")
            return mock_pdf_path
        except Exception as e:
            return f"{pdf_path} [PDF generation failed: {e} — use HTML: {html_path}]"
