"""
Rich terminal dashboard for CloudIQ.

Displays cost distribution, waste items, drift summary, and resource counts
in a live terminal layout. Exports to self-contained HTML reports.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
from rich.text import Text

from cloud_iq.cost_analyzer import CostReport, WasteItem
from cloud_iq.scanner import InfrastructureSnapshot

console = Console()

SEVERITY_COLORS = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "green",
    "optimized": "bright_green",
}

SEVERITY_ICONS = {
    "critical": "[red]CRITICAL[/red]",
    "high": "[red]HIGH[/red]",
    "medium": "[yellow]MEDIUM[/yellow]",
    "low": "[green]LOW[/green]",
}


def _format_usd(amount: float) -> str:
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}K"
    return f"${amount:.2f}"


def _severity_badge(severity: str) -> str:
    return SEVERITY_ICONS.get(severity, severity.upper())


# ---------------------------------------------------------------------------
# Panel builders
# ---------------------------------------------------------------------------


def _make_header(snapshot: InfrastructureSnapshot, report: CostReport | None) -> Panel:
    scanned_ago = ""
    delta = datetime.now(timezone.utc) - snapshot.scanned_at
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        scanned_ago = f"{minutes}m ago"
    else:
        scanned_ago = f"{int(minutes // 60)}h {minutes % 60}m ago"

    lines = [
        f"[bold cyan]Account:[/bold cyan] {snapshot.account_id}   "
        f"[bold cyan]Regions:[/bold cyan] {', '.join(snapshot.regions)}   "
        f"[bold cyan]Scanned:[/bold cyan] {scanned_ago}",
    ]
    if report:
        savings = report.total_monthly_savings_opportunity
        lines.append(
            f"[bold green]Monthly Cost:[/bold green] {_format_usd(report.monthly_avg_cost)}   "
            f"[bold yellow]Identified Waste:[/bold yellow] {_format_usd(report.total_identified_waste)}   "
            f"[bold bright_green]Savings Opportunity:[/bold bright_green] {_format_usd(savings)}/mo  "
            f"[bold bright_green]({_format_usd(savings * 12)}/yr)[/bold bright_green]"
        )
    return Panel(
        "\n".join(lines),
        title="[bold white]CloudIQ — Infrastructure Intelligence[/bold white]",
        border_style="cyan",
        padding=(0, 1),
    )


def _make_resource_counts(snapshot: InfrastructureSnapshot) -> Panel:
    counts = snapshot.resource_counts
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Service", style="cyan")
    table.add_column("Count", justify="right", style="bold white")
    table.add_column("Est. Monthly Cost", justify="right", style="green")

    service_costs: dict[str, float] = {
        "EC2 Instances": sum(
            i.estimated_monthly_cost for i in snapshot.ec2_instances
        ),
        "RDS Instances": sum(
            r.estimated_monthly_cost for r in snapshot.rds_instances
        ),
        "Lambda Functions": sum(
            f.estimated_monthly_cost for f in snapshot.lambda_functions
        ),
        "S3 Buckets": sum(b.estimated_monthly_cost for b in snapshot.s3_buckets),
        "EBS Volumes": sum(
            v.estimated_monthly_cost for v in snapshot.ebs_volumes
        ),
        "EKS Clusters": sum(
            c.estimated_monthly_cost for c in snapshot.eks_clusters
        ),
        "ElastiCache": sum(
            c.estimated_monthly_cost for c in snapshot.elasticache_clusters
        ),
        "VPCs (NAT GWs)": sum(
            v.estimated_monthly_cost for v in snapshot.vpcs
        ),
        "Idle Elastic IPs": sum(
            e.estimated_monthly_cost for e in snapshot.elastic_ips if e.is_idle
        ),
    }
    service_to_count = {
        "EC2 Instances": counts.get("ec2_instances", 0),
        "RDS Instances": counts.get("rds_instances", 0),
        "Lambda Functions": counts.get("lambda_functions", 0),
        "S3 Buckets": counts.get("s3_buckets", 0),
        "EBS Volumes": counts.get("ebs_volumes", 0),
        "EKS Clusters": counts.get("eks_clusters", 0),
        "ElastiCache": counts.get("elasticache_clusters", 0),
        "VPCs (NAT GWs)": counts.get("vpcs", 0),
        "Idle Elastic IPs": sum(1 for e in snapshot.elastic_ips if e.is_idle),
    }
    for service, cost in sorted(
        service_costs.items(), key=lambda x: x[1], reverse=True
    ):
        count = service_to_count.get(service, 0)
        if count == 0 and cost == 0:
            continue
        table.add_row(service, str(count), _format_usd(cost))

    return Panel(table, title="Resource Inventory", border_style="blue")


def _make_cost_breakdown(report: CostReport | None) -> Panel:
    if not report or not report.top_cost_drivers:
        return Panel(
            "[dim]No Cost Explorer data available.[/dim]\n"
            "[dim]Ensure the IAM role has ce:GetCostAndUsage permission.[/dim]",
            title="Cost Breakdown (90-day avg)",
            border_style="yellow",
        )

    max_cost = max((d.monthly_cost for d in report.top_cost_drivers), default=1)
    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("Service", style="cyan", min_width=30)
    table.add_column("Monthly Avg", justify="right", style="bold white", min_width=12)
    table.add_column("% of Total", justify="right", style="dim", min_width=8)
    table.add_column("Bar", min_width=20)

    for driver in report.top_cost_drivers:
        bar_width = int((driver.monthly_cost / max_cost) * 20)
        bar_filled = "█" * bar_width
        bar_empty = "░" * (20 - bar_width)
        color = (
            "red"
            if driver.percentage_of_total > 40
            else "yellow"
            if driver.percentage_of_total > 20
            else "green"
        )
        table.add_row(
            driver.service,
            _format_usd(driver.monthly_cost),
            f"{driver.percentage_of_total:.1f}%",
            f"[{color}]{bar_filled}[/][dim]{bar_empty}[/]",
        )

    return Panel(
        table,
        title=f"Cost Breakdown (90-day avg) — Total: {_format_usd(report.monthly_avg_cost)}/mo",
        border_style="yellow",
    )


def _make_waste_panel(report: CostReport | None) -> Panel:
    if not report or not report.waste_items:
        return Panel(
            "[bold green]No waste detected.[/bold green]",
            title="Waste Detection",
            border_style="green",
        )

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("Severity", min_width=10)
    table.add_column("Category", style="cyan", min_width=25)
    table.add_column("Resource", min_width=22)
    table.add_column("Region", min_width=12)
    table.add_column("Monthly Waste", justify="right", style="bold red", min_width=14)

    for item in report.waste_items[:15]:
        table.add_row(
            _severity_badge(item.severity),
            item.category,
            item.resource_id,
            item.region,
            _format_usd(item.estimated_monthly_waste),
        )

    total = report.total_identified_waste
    return Panel(
        table,
        title=f"Waste Detection — {len(report.waste_items)} items ({_format_usd(total)}/mo)",
        border_style="red",
    )


def _make_rightsizing_panel(report: CostReport | None) -> Panel:
    if not report or not report.rightsizing_recommendations:
        return Panel(
            "[bold green]No rightsizing opportunities detected.[/bold green]",
            title="Rightsizing Recommendations",
            border_style="green",
        )

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("Instance", style="cyan", min_width=20)
    table.add_column("Current Type", min_width=14)
    table.add_column("Recommended", style="green", min_width=14)
    table.add_column("Avg CPU %", justify="right", min_width=10)
    table.add_column("Savings/mo", justify="right", style="bold green", min_width=12)
    table.add_column("Confidence", min_width=10)

    for rec in report.rightsizing_recommendations[:10]:
        conf_color = (
            "green"
            if rec.confidence == "HIGH"
            else "yellow"
            if rec.confidence == "MEDIUM"
            else "dim"
        )
        table.add_row(
            rec.instance_id,
            rec.instance_type,
            rec.recommended_instance_type,
            f"{rec.avg_cpu_utilization:.1f}%",
            _format_usd(rec.monthly_savings),
            f"[{conf_color}]{rec.confidence}[/{conf_color}]",
        )

    total = report.total_rightsizing_savings
    return Panel(
        table,
        title=f"Rightsizing — {len(report.rightsizing_recommendations)} instances ({_format_usd(total)}/mo)",
        border_style="bright_green",
    )


def _make_security_panel(snapshot: InfrastructureSnapshot) -> Panel:
    issues: list[tuple[str, str]] = []

    unencrypted_rds = [
        r.db_instance_id
        for r in snapshot.rds_instances
        if not r.encrypted
    ]
    if unencrypted_rds:
        issues.append((
            "[red]CRITICAL[/red]",
            f"{len(unencrypted_rds)} RDS instance(s) without encryption at rest: "
            + ", ".join(unencrypted_rds[:3])
            + ("..." if len(unencrypted_rds) > 3 else ""),
        ))

    public_rds = [
        r.db_instance_id
        for r in snapshot.rds_instances
        if r.publicly_accessible
    ]
    if public_rds:
        issues.append((
            "[red]CRITICAL[/red]",
            f"{len(public_rds)} RDS instance(s) publicly accessible: "
            + ", ".join(public_rds[:3]),
        ))

    public_s3 = [b.name for b in snapshot.s3_buckets if not b.public_access_blocked]
    if public_s3:
        issues.append((
            "[red]HIGH[/red]",
            f"{len(public_s3)} S3 bucket(s) without public access block: "
            + ", ".join(public_s3[:3])
            + ("..." if len(public_s3) > 3 else ""),
        ))

    if snapshot.iam_summary:
        iam = snapshot.iam_summary
        if iam.users_without_mfa:
            issues.append((
                "[yellow]MEDIUM[/yellow]",
                f"{len(iam.users_without_mfa)} IAM user(s) without MFA: "
                + ", ".join(iam.users_without_mfa[:3]),
            ))
        if iam.access_keys_not_rotated:
            issues.append((
                "[yellow]MEDIUM[/yellow]",
                f"{len(iam.access_keys_not_rotated)} access key(s) not rotated in 90 days",
            ))
        if iam.overprivileged_roles:
            issues.append((
                "[yellow]MEDIUM[/yellow]",
                f"{len(iam.overprivileged_roles)} role(s) with AdministratorAccess: "
                + ", ".join(iam.overprivileged_roles[:3]),
            ))

    if not issues:
        return Panel(
            "[bold green]No critical security issues detected.[/bold green]",
            title="Security Posture",
            border_style="green",
        )

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Severity", min_width=12)
    table.add_column("Finding")
    for severity, finding in issues:
        table.add_row(severity, finding)

    return Panel(
        table,
        title=f"Security Posture — {len(issues)} finding(s)",
        border_style="red" if any("CRITICAL" in i[0] for i in issues) else "yellow",
    )


# ---------------------------------------------------------------------------
# Main dashboard class
# ---------------------------------------------------------------------------


class Dashboard:
    """
    Rich terminal dashboard for CloudIQ infrastructure intelligence.

    Renders a live, color-coded view of cost, waste, security, and
    rightsizing data. Can also export a self-contained HTML report.
    """

    def __init__(
        self,
        snapshot: InfrastructureSnapshot,
        cost_report: CostReport | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._report = cost_report

    def render(self) -> None:
        """Render the full dashboard to the terminal (static, no live refresh)."""
        c = Console()
        c.print()
        c.print(_make_header(self._snapshot, self._report))
        c.print()

        c.print(Rule("[bold cyan]Infrastructure Overview[/bold cyan]"))
        c.print()
        c.print(_make_resource_counts(self._snapshot))
        c.print()

        if self._report:
            c.print(Rule("[bold yellow]Cost Intelligence[/bold yellow]"))
            c.print()
            c.print(_make_cost_breakdown(self._report))
            c.print()

            c.print(Rule("[bold red]Waste Detection[/bold red]"))
            c.print()
            c.print(_make_waste_panel(self._report))
            c.print()

            c.print(Rule("[bold bright_green]Rightsizing[/bold bright_green]"))
            c.print()
            c.print(_make_rightsizing_panel(self._report))
            c.print()

        c.print(Rule("[bold red]Security Posture[/bold red]"))
        c.print()
        c.print(_make_security_panel(self._snapshot))
        c.print()

        if self._report:
            total_opp = self._report.total_monthly_savings_opportunity
            c.print(
                Panel(
                    f"[bold bright_green]Total monthly savings opportunity: "
                    f"{_format_usd(total_opp)}/mo  ({_format_usd(total_opp * 12)}/yr)[/bold bright_green]\n"
                    f"[dim]Run CloudIQ in --terraform mode to generate the IaC to fix these issues.[/dim]",
                    border_style="bright_green",
                    title="Summary",
                )
            )

    def export_html(self, output_path: str | Path) -> Path:
        """
        Export the dashboard as a self-contained HTML report.

        The report includes all findings, sorted by impact, and is suitable
        for sharing with stakeholders who don't have terminal access.
        """
        path = Path(output_path)
        snapshot = self._snapshot
        report = self._report

        resource_rows = ""
        for service, count in sorted(
            snapshot.resource_counts.items(), key=lambda x: x[1], reverse=True
        ):
            if count > 0:
                resource_rows += (
                    f"<tr><td>{html.escape(service.replace('_', ' ').title())}</td>"
                    f"<td>{count}</td></tr>\n"
                )

        cost_rows = ""
        if report:
            for driver in report.top_cost_drivers:
                pct = driver.percentage_of_total
                bar_width = int(pct * 2)
                cost_rows += (
                    f"<tr><td>{html.escape(driver.service)}</td>"
                    f"<td>${driver.monthly_cost:,.0f}</td>"
                    f"<td>{pct:.1f}%</td>"
                    f'<td><div class="bar" style="width:{bar_width}px"></div></td></tr>\n'
                )

        waste_rows = ""
        if report:
            for item in report.waste_items:
                sev_class = item.severity
                waste_rows += (
                    f'<tr class="sev-{sev_class}">'
                    f"<td>{item.severity.upper()}</td>"
                    f"<td>{html.escape(item.category)}</td>"
                    f"<td><code>{html.escape(item.resource_id)}</code></td>"
                    f"<td>{html.escape(item.region)}</td>"
                    f"<td>${item.estimated_monthly_waste:,.2f}</td>"
                    f"<td>{html.escape(item.recommendation)}</td></tr>\n"
                )

        rs_rows = ""
        if report:
            for rec in report.rightsizing_recommendations:
                rs_rows += (
                    f"<tr><td><code>{html.escape(rec.instance_id)}</code></td>"
                    f"<td>{html.escape(rec.instance_type)}</td>"
                    f"<td>{html.escape(rec.recommended_instance_type)}</td>"
                    f"<td>{rec.avg_cpu_utilization:.1f}%</td>"
                    f"<td>${rec.monthly_savings:,.2f}</td>"
                    f"<td>{html.escape(rec.confidence)}</td></tr>\n"
                )

        monthly_waste = f"${report.total_identified_waste:,.0f}" if report else "N/A"
        monthly_savings = (
            f"${report.total_monthly_savings_opportunity:,.0f}" if report else "N/A"
        )
        annual_savings = (
            f"${report.annual_savings_opportunity:,.0f}" if report else "N/A"
        )

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CloudIQ Report — {html.escape(snapshot.account_id)}</title>
<style>
  :root {{
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2d3047;
    --text: #e2e8f0;
    --muted: #718096;
    --cyan: #63b3ed;
    --green: #68d391;
    --yellow: #f6e05e;
    --red: #fc8181;
    --critical: #e53e3e;
    --high: #dd6b20;
    --medium: #d69e2e;
    --low: #38a169;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; padding: 2rem; }}
  h1 {{ color: var(--cyan); font-size: 1.8rem; margin-bottom: 0.25rem; }}
  h2 {{ color: var(--cyan); font-size: 1.2rem; margin: 2rem 0 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }}
  .meta {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 2rem; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .kpi {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; }}
  .kpi-label {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  .kpi-value {{ font-size: 1.6rem; font-weight: bold; color: var(--green); margin-top: 0.25rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 2rem; background: var(--surface); border-radius: 8px; overflow: hidden; }}
  th {{ background: #252836; color: var(--cyan); text-align: left; padding: 0.75rem 1rem; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  td {{ padding: 0.65rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.9rem; }}
  tr:last-child td {{ border-bottom: none; }}
  code {{ background: #252836; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.85em; }}
  .bar {{ height: 8px; background: var(--yellow); border-radius: 4px; }}
  .sev-critical td:first-child {{ color: var(--critical); font-weight: bold; }}
  .sev-high td:first-child {{ color: var(--high); font-weight: bold; }}
  .sev-medium td:first-child {{ color: var(--medium); }}
  .sev-low td:first-child {{ color: var(--low); }}
  .badge {{ display: inline-block; padding: 0.2em 0.6em; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }}
  footer {{ margin-top: 3rem; color: var(--muted); font-size: 0.8rem; text-align: center; }}
</style>
</head>
<body>
<h1>CloudIQ Infrastructure Intelligence Report</h1>
<div class="meta">
  Account: <strong>{html.escape(snapshot.account_id)}</strong> &nbsp;|&nbsp;
  Regions: <strong>{html.escape(', '.join(snapshot.regions))}</strong> &nbsp;|&nbsp;
  Scanned: <strong>{snapshot.scanned_at.strftime('%Y-%m-%d %H:%M UTC')}</strong>
</div>

<div class="kpi-grid">
  <div class="kpi"><div class="kpi-label">Monthly Cost</div>
    <div class="kpi-value">{f'${report.monthly_avg_cost:,.0f}' if report else 'N/A'}</div></div>
  <div class="kpi"><div class="kpi-label">Identified Waste</div>
    <div class="kpi-value" style="color:var(--red)">{monthly_waste}</div></div>
  <div class="kpi"><div class="kpi-label">Savings Opportunity</div>
    <div class="kpi-value">{monthly_savings}/mo</div></div>
  <div class="kpi"><div class="kpi-label">Annual Savings</div>
    <div class="kpi-value">{annual_savings}</div></div>
  <div class="kpi"><div class="kpi-label">Total Resources</div>
    <div class="kpi-value">{sum(snapshot.resource_counts.values())}</div></div>
</div>

<h2>Resource Inventory</h2>
<table>
  <tr><th>Service</th><th>Count</th></tr>
  {resource_rows}
</table>

<h2>Cost Breakdown (Top 10 Services)</h2>
<table>
  <tr><th>Service</th><th>Monthly Avg</th><th>% of Total</th><th>Share</th></tr>
  {cost_rows if cost_rows else '<tr><td colspan="4" style="color:var(--muted)">Cost Explorer data not available</td></tr>'}
</table>

<h2>Waste Detection</h2>
<table>
  <tr><th>Severity</th><th>Category</th><th>Resource</th><th>Region</th><th>Waste/mo</th><th>Recommendation</th></tr>
  {waste_rows if waste_rows else '<tr><td colspan="6" style="color:var(--green)">No waste detected</td></tr>'}
</table>

<h2>Rightsizing Recommendations</h2>
<table>
  <tr><th>Instance</th><th>Current Type</th><th>Recommended</th><th>Avg CPU</th><th>Savings/mo</th><th>Confidence</th></tr>
  {rs_rows if rs_rows else '<tr><td colspan="6" style="color:var(--green)">No rightsizing opportunities</td></tr>'}
</table>

<footer>Generated by CloudIQ &nbsp;|&nbsp; {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</footer>
</body>
</html>"""

        path.write_text(html_content, encoding="utf-8")
        return path
