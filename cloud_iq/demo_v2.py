"""
CloudIQ V2 — Multi-Scene Cinematic Demo

Run with: python -m cloud_iq.demo_v2

Zero credentials required. All data is realistic mock from demo_data.py.
Scenes:
  1. Live scan animation with resource discovery ticker
  2. Anomaly alert fires mid-scan — NAT Gateway cost spike detected
  3. ML forecast: budget exhaustion in 47 days
  4. NL query: "Which team is spending the most on data transfer?"
  5. Terraform generation + security diff side-by-side
  6. Multi-cloud aggregate view (AWS + Azure + GCP)
  7. K8s intelligence — namespace cost attribution
  8. Executive summary — $47,800/mo waste, 18-month ROI

Press ENTER between scenes or run with --fast for no-pause mode.
"""

from __future__ import annotations

import asyncio
import random
import sys
import time
from datetime import datetime, timedelta, timezone

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
from rich.text import Text

console = Console(width=120)
FAST = "--fast" in sys.argv


def _pause(msg: str = "Press ENTER to continue...") -> None:
    if FAST:
        time.sleep(0.3)
        return
    console.print(f"\n[dim]{msg}[/dim]")
    input()


def _fmt_usd(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v:,.0f}"
    return f"${v:.2f}"


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------


def _header_panel(title: str, subtitle: str = "") -> Panel:
    content = Text(title, style="bold cyan", justify="center")
    if subtitle:
        content.append(f"\n{subtitle}", style="dim")
    return Panel(content, style="cyan", padding=(0, 2))


def _separator(label: str) -> None:
    console.print()
    console.print(Rule(f"[bold cyan] {label} [/bold cyan]", style="cyan"))
    console.print()


# ---------------------------------------------------------------------------
# Scene 1: Live scan animation
# ---------------------------------------------------------------------------


def scene_1_scan() -> None:
    _separator("Scene 1 of 8  —  Infrastructure Discovery Scan")
    console.print(
        Panel(
            "[bold white]Initiating CloudIQ scan against AcmeCorp AWS account "
            "[bold yellow]123456789012[/bold yellow][/bold white]\n"
            "[dim]Regions: us-east-1, us-west-2, eu-west-1[/dim]",
            title="[bold cyan]CloudIQ v2.0.0[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()

    stages = [
        ("STS",         "Authenticating with AWS STS",               3,   0.12),
        ("EC2",         "Scanning EC2 instances (6 found)",          12,  0.08),
        ("RDS",         "Scanning RDS instances (3 found)",          8,   0.07),
        ("EKS",         "Scanning EKS clusters + node groups",       18,  0.10),
        ("EBS",         "Enumerating EBS volumes (3 unattached!)",   20,  0.07),
        ("S3",          "Scanning S3 buckets (3 found)",             8,   0.06),
        ("Lambda",      "Scanning Lambda functions (2 found)",       4,   0.05),
        ("VPC",         "VPC topology + NAT gateway audit",          12,  0.12),
        ("ElastiCache", "Scanning ElastiCache clusters",             6,   0.06),
        ("EIP",         "Elastic IP audit (2 idle found)",           4,   0.05),
        ("Cost",        "Pulling 90-day Cost Explorer data",         30,  0.15),
        ("ML",          "Running Isolation Forest anomaly detection",40,  0.18),
        ("Forecast",    "Generating 90-day Prophet forecast",        20,  0.14),
        ("Terraform",   "Comparing live state vs Terraform plan",    22,  0.10),
        ("Report",      "Assembling CloudIQ report",                 100, 0.05),
    ]

    with Progress(
        SpinnerColumn(spinner_name="dots12"),
        TextColumn("[bold cyan]{task.description:<48}[/bold cyan]"),
        BarColumn(bar_width=32, style="cyan", complete_style="bold green"),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Initialising...", total=100)
        for service, label, pct_end, delay in stages:
            progress.update(task, description=f"[{service}] {label}")
            current = progress.tasks[0].completed
            steps = max(1, pct_end - int(current))
            for _ in range(steps):
                progress.advance(task, 1)
                time.sleep(delay / steps * (0.5 + random.random()))

    console.print()
    console.print(
        Panel(
            "[bold green]Scan complete in 18.4 seconds[/bold green]\n"
            "Resources discovered: [bold]247[/bold] across 3 regions\n"
            "Cost data: 90-day history loaded\n"
            "Anomaly engine: 8 anomalies flagged\n"
            "Terraform drift: [bold red]14 unmanaged resources[/bold red]",
            title="[bold green]Scan Complete[/bold green]",
            border_style="green",
        )
    )
    _pause()


# ---------------------------------------------------------------------------
# Scene 2: Anomaly alert fires
# ---------------------------------------------------------------------------


def scene_2_anomaly() -> None:
    _separator("Scene 2 of 8  —  ML Anomaly Alert — NAT Gateway Spike")

    console.print(
        Panel(
            "[bold red]:rotating_light:  CRITICAL ANOMALY DETECTED  :rotating_light:[/bold red]",
            border_style="red",
            padding=(0, 2),
        )
    )
    console.print()

    table = Table(
        title="Isolation Forest — Top Anomalies (this scan)",
        box=box.ROUNDED,
        border_style="red",
        show_lines=True,
        header_style="bold white on dark_red",
    )
    table.add_column("Alert ID", style="dim", width=10)
    table.add_column("Resource", style="bold", width=32)
    table.add_column("Type", width=20)
    table.add_column("Region", width=12)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Cost/mo", justify="right", style="bold red", width=10)
    table.add_column("Severity", width=10)

    alerts = [
        ("A-001", "vpc-0a1b2c3d4e5f6001", "NAT Gateway x5", "us-east-1", 0.97, 16_060, "CRITICAL"),
        ("A-002", "prod-analytics-dwh", "RDS r5.4xlarge", "us-east-1", 0.89, 8_820, "CRITICAL"),
        ("A-003", "i-0dead0000000dead2", "EC2 r5.4xlarge", "us-west-2", 0.84, 1_008, "CRITICAL"),
        ("A-004", "i-0dead0000000dead1", "EC2 m5.2xlarge", "us-east-1", 0.76, 384, "HIGH"),
        ("A-005", "vol-0orphan000000002", "EBS 1000GB", "us-west-2", 0.71, 100, "HIGH"),
        ("A-006", "us-east-1/snapshots", "EBS Snapshots", "us-east-1", 0.68, 1_840, "HIGH"),
        ("A-007", "vol-0orphan000000001", "EBS 500GB", "us-east-1", 0.59, 50, "MEDIUM"),
        ("A-008", "eipalloc-0a1b2c0001", "Elastic IP", "us-east-1", 0.41, 4, "LOW"),
    ]

    severity_styles = {
        "CRITICAL": "bold red",
        "HIGH": "bold yellow",
        "MEDIUM": "bold orange3",
        "LOW": "dim",
    }

    for alert_id, resource, rtype, region, score, cost, severity in alerts:
        style = severity_styles.get(severity, "")
        score_bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        table.add_row(
            alert_id,
            resource,
            rtype,
            region,
            f"[{style}]{score:.2f}[/{style}] {score_bar[:5]}",
            _fmt_usd(cost),
            f"[{style}]{severity}[/{style}]",
        )

    console.print(table)
    console.print()

    console.print(
        Panel(
            "[bold white]Alert A-001 Detail:[/bold white]\n\n"
            "[yellow]VPC vpc-0a1b2c3d4e5f6001 has 5 NAT Gateways costing $16,060/mo.[/yellow]\n\n"
            "Isolation Forest score [bold red]0.97[/bold red] — cost pattern is 9.4 sigma above "
            "fleet mean across all 10 cost dimensions.\n\n"
            "Root cause: Data transfer costs have grown 22.4% MoM. "
            "3 of 5 NAT gateways carry <2% of traffic but 100% of their base cost.\n\n"
            "[bold green]Recommended fix:[/bold green]\n"
            "  1. Create S3 + DynamoDB VPC endpoints → -$11,200/mo\n"
            "  2. Consolidate 5 NAT GWs to 2 (one per primary AZ) → -$1,093/mo\n"
            "  3. Total savings: $12,293/mo | Annual: $147,516\n\n"
            "[dim]Slack alert sent to #cloud-cost-ops | Jira CLOUD-847 created | "
            "PagerDuty P2 paged[/dim]",
            title="[bold red]:rotating_light: A-001 NAT Gateway Overuse — CRITICAL[/bold red]",
            border_style="red",
        )
    )
    _pause()


# ---------------------------------------------------------------------------
# Scene 3: ML forecast
# ---------------------------------------------------------------------------


def scene_3_forecast() -> None:
    _separator("Scene 3 of 8  —  ML Cost Forecast — Budget Exhaustion Warning")

    base_cost = 154_200.0
    monthly_growth = 0.062  # 6.2% MoM growth trend
    budget = 500_000.0

    console.print(
        Panel(
            f"[bold]Monthly burn rate:[/bold] [bold red]{_fmt_usd(base_cost)}[/bold red]  "
            f"[dim](+6.2% MoM trend, 30-day EWMA)[/dim]\n"
            f"[bold]Monthly budget:[/bold] [bold green]{_fmt_usd(budget)}[/bold green]\n"
            f"[bold]Budget exhaustion:[/bold] [bold red]47 days from today[/bold red]",
            title="[bold cyan]Prophet Forecast — 90-Day Outlook[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()

    table = Table(
        title="90-Day Cost Forecast (P10 / P50 / P90 confidence bands)",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold white on dark_blue",
        show_lines=False,
    )
    table.add_column("Month", width=12)
    table.add_column("P10 (optimistic)", justify="right", style="green", width=18)
    table.add_column("P50 (base case)", justify="right", style="bold yellow", width=18)
    table.add_column("P90 (pessimistic)", justify="right", style="red", width=18)
    table.add_column("vs Budget", justify="right", width=14)
    table.add_column("Status", width=12)

    rows = [
        ("Month +1",  base_cost * 1.04,  base_cost * 1.062, base_cost * 1.085, budget),
        ("Month +2",  base_cost * 1.08,  base_cost * 1.127, base_cost * 1.178, budget),
        ("Month +3",  base_cost * 1.12,  base_cost * 1.197, base_cost * 1.282, budget),
    ]

    for month, p10, p50, p90, bud in rows:
        vs_budget_pct = (p50 / bud * 100)
        if vs_budget_pct >= 95:
            status = "[bold red]AT RISK[/bold red]"
            bud_style = "bold red"
        elif vs_budget_pct >= 80:
            status = "[yellow]WARNING[/yellow]"
            bud_style = "yellow"
        else:
            status = "[green]ON TRACK[/green]"
            bud_style = "green"
        table.add_row(
            month,
            _fmt_usd(p10),
            _fmt_usd(p50),
            _fmt_usd(p90),
            f"[{bud_style}]{vs_budget_pct:.1f}%[/{bud_style}]",
            status,
        )

    console.print(table)
    console.print()

    # What-if scenarios
    what_if = Table(
        title="What-If Analysis — Savings if Recommendations Implemented",
        box=box.SIMPLE_HEAVY,
        border_style="green",
        header_style="bold white on dark_green",
    )
    what_if.add_column("Scenario", width=40)
    what_if.add_column("Monthly Savings", justify="right", style="bold green", width=18)
    what_if.add_column("New Monthly Cost", justify="right", width=18)
    what_if.add_column("Budget Exhaustion", width=20)
    what_if.add_column("Payback", width=12)

    scenarios = [
        ("Top 3 recommendations only",          14_200, base_cost - 14_200, "Never", "1.5 mo"),
        ("Reserved instances — top 10 EC2",     8_400,  base_cost - 8_400,  "189 days", "12 mo"),
        ("Spot fleet for batch workloads",       6_100,  base_cost - 6_100,  "72 days", "0.5 mo"),
        ("All recommendations implemented",     47_800, base_cost - 47_800, "Never", "2 mo"),
    ]

    for name, savings, new_cost, exhaustion, payback in scenarios:
        color = "bold green" if exhaustion == "Never" else ("yellow" if int(exhaustion.split()[0]) > 60 else "red")
        what_if.add_row(
            name,
            _fmt_usd(savings),
            _fmt_usd(new_cost),
            f"[{color}]{exhaustion}[/{color}]",
            payback,
        )

    console.print(what_if)
    _pause()


# ---------------------------------------------------------------------------
# Scene 4: Natural language query
# ---------------------------------------------------------------------------


def scene_4_nl_query() -> None:
    _separator("Scene 4 of 8  —  Natural Language Query Engine")

    queries_and_answers = [
        (
            "Which team is spending the most on data transfer?",
            "The data-eng team is responsible for the highest data transfer costs at "
            "$8,200/mo (44% of total $18,800/mo transfer spend). This is driven by "
            "prod-analytics-dwh (db.r5.4xlarge) performing nightly full-table exports "
            "from RDS to S3 over the public internet rather than a VPC endpoint.\n\n"
            "Second highest: backend team at $5,100/mo — mostly outbound traffic from "
            "prod-api-server-01/02 (i-0a1b2c3d4e5f60001, i-0a1b2c3d4e5f60002).\n\n"
            "RECOMMENDATION: Create an S3 VPC Gateway Endpoint (free) to route all "
            "RDS→S3 traffic within AWS — eliminates ~$11,200/mo in NAT processing charges.",
        ),
        (
            "Show me all resources not tagged with a CostCenter",
            "5 resources are missing the CostCenter tag:\n"
            "• vol-0orphan000000002 (EBS 1TB, us-west-2) — $100/mo\n"
            "• vol-0orphan000000003 (EBS 200GB, eu-west-1) — $16/mo\n"
            "• eipalloc-0a1b2c0001 (Elastic IP, us-east-1) — $3.60/mo\n"
            "• eipalloc-0a1b2c0002 (Elastic IP, us-east-1) — $3.60/mo\n"
            "• acmecorp-prod-assets (S3 bucket) — missing Environment tag also\n\n"
            "Total monthly cost of untagged resources: $123.20\n"
            "All are candidates for Shadow IT review — none appear in Terraform state.",
        ),
        (
            "What's our biggest single cost reduction opportunity?",
            "The largest single opportunity is NAT Gateway consolidation:\n\n"
            "vpc-0a1b2c3d4e5f6001 has 5 NAT Gateways generating $16,060/mo\n"
            "($1,642/mo fixed + $14,418/mo data processing at $0.045/GB).\n\n"
            "Root cause: No VPC endpoints configured for S3 or DynamoDB. "
            "All AWS service API traffic routes through NAT gateways unnecessarily.\n\n"
            "Fix in 2 steps:\n"
            "1. terraform apply -target=aws_vpc_endpoint.s3 (free, routes S3 traffic internally)\n"
            "2. terraform apply -target=aws_vpc_endpoint.dynamodb (free)\n\n"
            "Expected savings: $11,200/mo (70% reduction). "
            "Full consolidation to 2 NAT GWs saves additional $1,093/mo.\n"
            "Total: $12,293/mo | $147,516/year | 0 downtime risk.",
        ),
    ]

    for i, (question, answer) in enumerate(queries_and_answers, 1):
        console.print(
            Panel(
                f"[bold white]:speech_balloon: Query {i} of {len(queries_and_answers)}[/bold white]\n\n"
                f"[bold cyan]{question}[/bold cyan]",
                border_style="cyan",
                title="[cyan]NL Query Engine (Claude)[/cyan]",
            )
        )

        # Simulate streaming
        console.print("\n[dim]Analysing infrastructure context...[/dim] ", end="")
        time.sleep(0.4 if FAST else 1.2)
        console.print("[green]done[/green]\n")

        console.print(
            Panel(
                answer,
                title="[green]CloudIQ Response[/green]",
                border_style="green",
                padding=(1, 2),
            )
        )
        console.print()
        if i < len(queries_and_answers):
            time.sleep(0.2 if FAST else 0.8)

    _pause()


# ---------------------------------------------------------------------------
# Scene 5: Terraform generation + security diff
# ---------------------------------------------------------------------------


def scene_5_terraform() -> None:
    _separator("Scene 5 of 8  —  Terraform Generation + Security Hardening")

    console.print(
        "[bold]Generating Terraform for:[/bold] prod-analytics-dwh (RDS r5.4xlarge)\n"
        "[dim]Comparing current AWS state vs generated Terraform plan...[/dim]\n"
    )

    old_code = '''\
# CURRENT (manually provisioned — no IaC)
resource "aws_db_instance" "analytics" {
  identifier     = "prod-analytics-dwh"
  engine         = "postgres"
  instance_class = "db.r5.4xlarge"
  storage_encrypted    = false  ← UNENCRYPTED
  publicly_accessible  = true   ← PUBLIC!
  deletion_protection  = false  ← NO PROTECTION
  backup_retention_period = 1   ← TOO SHORT
  skip_final_snapshot  = true   ← DANGEROUS
  performance_insights_enabled = false
}'''

    new_code = '''\
# CLOUDIQ V2 GENERATED (security-hardened)
resource "aws_db_instance" "prod_analytics_dwh" {
  identifier     = "prod-analytics-dwh"
  engine         = "postgres"
  instance_class = "db.r5.4xlarge"  # → db.r5.xlarge saves $2,205/mo
  kms_key_id            = data.aws_kms_key.rds.arn  ← KMS encrypted
  publicly_accessible   = false  ← PRIVATE ONLY
  deletion_protection   = true   ← PROTECTED
  backup_retention_period = 14   ← 2-WEEK RETENTION
  skip_final_snapshot   = false  ← SAFE DELETION
  performance_insights_enabled = true   ← MONITORING ON
  monitoring_interval   = 60
  monitoring_role_arn   = aws_iam_role.rds_enhanced_monitoring.arn
  # estimated: $2,940/mo current | $735/mo recommended
}'''

    layout = Layout()
    layout.split_row(
        Layout(
            Panel(
                old_code,
                title="[bold red]Before (Shadow IT / Manual)[/bold red]",
                border_style="red",
                style="red",
            ),
            name="left",
        ),
        Layout(
            Panel(
                new_code,
                title="[bold green]After (CloudIQ Generated)[/bold green]",
                border_style="green",
                style="green",
            ),
            name="right",
        ),
    )

    console.print(layout)
    console.print()

    findings_table = Table(
        title="Security Findings Fixed by Terraform Adoption",
        box=box.ROUNDED,
        border_style="yellow",
        header_style="bold white on dark_orange3",
        show_lines=True,
    )
    findings_table.add_column("Finding", width=36)
    findings_table.add_column("Before", justify="center", width=18)
    findings_table.add_column("After", justify="center", width=18)
    findings_table.add_column("Compliance", width=18)

    findings = [
        ("Storage encryption", "[bold red]None[/bold red]", "[bold green]AES-256 KMS[/bold green]", "SOC2, PCI-DSS"),
        ("Public access", "[bold red]Internet-facing[/bold red]", "[bold green]VPC-only[/bold green]", "CIS AWS 4.2"),
        ("Deletion protection", "[bold red]Off[/bold red]", "[bold green]On[/bold green]", "Best practice"),
        ("Backup retention", "[bold red]1 day[/bold red]", "[bold green]14 days[/bold green]", "SOC2 CC6.1"),
        ("Performance Insights", "[bold red]Off[/bold red]", "[bold green]7-day window[/bold green]", "Observability"),
        ("Enhanced monitoring", "[bold red]Off[/bold red]", "[bold green]60s interval[/bold green]", "SRE best practice"),
        ("Final snapshot", "[bold red]Skip[/bold red]", "[bold green]Auto-snapshot[/bold green]", "DR requirement"),
    ]

    for finding, before, after, compliance in findings:
        findings_table.add_row(finding, before, after, compliance)

    console.print(findings_table)

    console.print()
    console.print(
        Panel(
            "Generated files: backend.tf, versions.tf, main.tf, variables.tf,\n"
            "  modules/rds/main.tf, modules/rds/variables.tf, modules/rds/outputs.tf,\n"
            "  terraform.tfvars.example\n\n"
            "[bold yellow]Atlantis workflow:[/bold yellow] PR #847 created → plan runs automatically → "
            "requires 2 approvals → applies on merge",
            title="[bold green]Terraform Output[/bold green]",
            border_style="green",
        )
    )
    _pause()


# ---------------------------------------------------------------------------
# Scene 6: Multi-cloud view
# ---------------------------------------------------------------------------


def scene_6_multicloud() -> None:
    _separator("Scene 6 of 8  —  Multi-Cloud Aggregate View")

    table = Table(
        title="Multi-Cloud Cost Intelligence — AcmeCorp (All Accounts)",
        box=box.DOUBLE_EDGE,
        border_style="blue",
        header_style="bold white on navy_blue",
        show_lines=True,
    )
    table.add_column("Provider", width=10)
    table.add_column("Account", width=28)
    table.add_column("Monthly Cost", justify="right", style="bold", width=14)
    table.add_column("Waste", justify="right", style="red", width=12)
    table.add_column("Waste %", justify="right", width=10)
    table.add_column("Resources", justify="right", width=10)
    table.add_column("Top Service", width=26)

    rows = [
        ("AWS",   "123456789012 (AcmeCorp Prod)", 154_200, 47_800, 31.0, 247, "EKS/EC2 Nodes $68,400"),
        ("Azure", "AcmeCorp-Prod West US 2",       55_200, 12_400, 22.5,  94, "Virtual Machines $24,600"),
        ("GCP",   "acmecorp-gcp (us-central1)",    20_400,  5_600, 27.5,  63, "Compute Engine $8,200"),
    ]

    totals_monthly = sum(r[2] for r in rows)
    totals_waste = sum(r[3] for r in rows)

    provider_colors = {"AWS": "bold yellow", "Azure": "bold blue", "GCP": "bold green"}

    for provider, account, monthly, waste, waste_pct, resources, top in rows:
        color = provider_colors.get(provider, "white")
        waste_color = "bold red" if waste_pct > 30 else ("yellow" if waste_pct > 20 else "green")
        table.add_row(
            f"[{color}]{provider}[/{color}]",
            account,
            _fmt_usd(monthly),
            _fmt_usd(waste),
            f"[{waste_color}]{waste_pct:.1f}%[/{waste_color}]",
            str(resources),
            top,
        )

    # Totals row
    total_waste_pct = totals_waste / totals_monthly * 100
    table.add_row(
        "[bold white]TOTAL[/bold white]",
        "[dim]3 providers, 3 accounts[/dim]",
        f"[bold]{_fmt_usd(totals_monthly)}[/bold]",
        f"[bold red]{_fmt_usd(totals_waste)}[/bold red]",
        f"[bold red]{total_waste_pct:.1f}%[/bold red]",
        "[bold]404[/bold]",
        "[dim]—[/dim]",
        style="on grey23",
    )

    console.print(table)
    console.print()

    breakdown = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    breakdown.add_column(width=30)
    breakdown.add_column(width=40)
    breakdown.add_column(width=30)

    aws_bar_len = int(154_200 / totals_monthly * 40)
    azure_bar_len = int(55_200 / totals_monthly * 40)
    gcp_bar_len = int(20_400 / totals_monthly * 40)

    breakdown.add_row(
        "[bold yellow]AWS[/bold yellow]",
        "[yellow]" + "█" * aws_bar_len + "[/yellow]",
        f"[yellow]{154_200 / totals_monthly * 100:.1f}% ({_fmt_usd(154_200)})[/yellow]",
    )
    breakdown.add_row(
        "[bold blue]Azure[/bold blue]",
        "[blue]" + "█" * azure_bar_len + "[/blue]",
        f"[blue]{55_200 / totals_monthly * 100:.1f}% ({_fmt_usd(55_200)})[/blue]",
    )
    breakdown.add_row(
        "[bold green]GCP[/bold green]",
        "[green]" + "█" * gcp_bar_len + "[/green]",
        f"[green]{20_400 / totals_monthly * 100:.1f}% ({_fmt_usd(20_400)})[/green]",
    )

    console.print(Panel(breakdown, title="[bold]Spend Distribution[/bold]", border_style="blue"))
    _pause()


# ---------------------------------------------------------------------------
# Scene 7: Kubernetes intelligence
# ---------------------------------------------------------------------------


def scene_7_kubernetes() -> None:
    _separator("Scene 7 of 8  —  Kubernetes / EKS Intelligence")

    from cloud_iq.k8s_analyzer import K8sAnalyzer

    analyzer = K8sAnalyzer(mock=True)
    report = analyzer.analyze("prod-eks-01", "us-east-1")

    console.print(
        Panel(
            f"Cluster: [bold cyan]{report.cluster_name}[/bold cyan] | "
            f"Region: [bold]{report.region}[/bold] | "
            f"Nodes: [bold]{report.node_count}[/bold] | "
            f"Pods: [bold]{report.pod_count}[/bold] | "
            f"Cost: [bold red]{_fmt_usd(report.total_cluster_monthly_cost_usd)}/mo[/bold red]",
            title="[bold cyan]EKS Cluster Overview[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()

    ns_table = Table(
        title="Namespace Cost Attribution",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold white on dark_cyan",
        show_lines=True,
    )
    ns_table.add_column("Namespace", width=18)
    ns_table.add_column("Team", width=14)
    ns_table.add_column("Pods", justify="right", width=8)
    ns_table.add_column("CPU Req (cores)", justify="right", width=16)
    ns_table.add_column("Mem Req (GB)", justify="right", width=14)
    ns_table.add_column("Monthly Cost", justify="right", style="bold", width=14)
    ns_table.add_column("CPU Efficiency", justify="right", width=16)

    for ns in report.namespace_allocations:
        eff_color = "green" if ns.cpu_efficiency_pct > 60 else ("yellow" if ns.cpu_efficiency_pct > 30 else "bold red")
        ns_table.add_row(
            ns.namespace,
            ns.team or "—",
            str(ns.pod_count),
            f"{ns.cpu_request_cores:.1f}",
            f"{ns.memory_request_gb:.1f}",
            _fmt_usd(ns.monthly_cost_usd),
            f"[{eff_color}]{ns.cpu_efficiency_pct:.0f}%[/{eff_color}]",
        )

    console.print(ns_table)
    console.print()

    hpa_table = Table(
        title=f"HPA Recommendations — {_fmt_usd(sum(r.estimated_monthly_savings_usd for r in report.hpa_recommendations))}/mo savings",
        box=box.ROUNDED,
        border_style="green",
        header_style="bold white on dark_green",
        show_lines=True,
    )
    hpa_table.add_column("Deployment", width=22)
    hpa_table.add_column("Namespace", width=14)
    hpa_table.add_column("Current", justify="right", width=10)
    hpa_table.add_column("HPA Range", justify="center", width=14)
    hpa_table.add_column("Peak CPU", justify="right", width=10)
    hpa_table.add_column("Off-Peak CPU", justify="right", width=14)
    hpa_table.add_column("Savings/mo", justify="right", style="bold green", width=12)

    for hpa in report.hpa_recommendations:
        hpa_table.add_row(
            hpa.deployment_name,
            hpa.namespace,
            f"{hpa.current_replicas} replicas",
            f"{hpa.recommended_min_replicas}–{hpa.recommended_max_replicas}",
            f"[red]{hpa.peak_cpu_pct:.0f}%[/red]",
            f"[green]{hpa.off_peak_cpu_pct:.0f}%[/green]",
            _fmt_usd(hpa.estimated_monthly_savings_usd),
        )

    console.print(hpa_table)
    console.print()

    savings = report.total_monthly_savings_opportunity_usd
    console.print(
        Panel(
            f"[bold green]Total EKS savings opportunity: {_fmt_usd(savings)}/mo "
            f"({_fmt_usd(savings * 12)}/year)[/bold green]\n"
            f"  Node rightsizing: {_fmt_usd(sum(r.monthly_savings_usd for r in report.node_rightsizing))}/mo\n"
            f"  HPA automation: {_fmt_usd(sum(r.estimated_monthly_savings_usd for r in report.hpa_recommendations))}/mo\n"
            f"  Unused PVCs: {_fmt_usd(sum(p.monthly_cost_usd for p in report.unused_pvcs))}/mo",
            title="[bold green]EKS Optimisation Summary[/bold green]",
            border_style="green",
        )
    )
    _pause()


# ---------------------------------------------------------------------------
# Scene 8: Executive summary
# ---------------------------------------------------------------------------


def scene_8_executive() -> None:
    _separator("Scene 8 of 8  —  Executive Summary")

    total_monthly_spend = 229_800.0   # AWS + Azure + GCP
    total_waste = 65_800.0            # All providers
    aws_waste = 47_800.0
    annual_waste = total_waste * 12
    roi_months = 2.0

    console.print(
        Panel(
            Align.center(
                Text(
                    "CloudIQ V2 — Executive Cost Intelligence Report\n"
                    "AcmeCorp Infrastructure Audit\n"
                    f"Generated: {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
                    style="bold white",
                    justify="center",
                )
            ),
            style="bold",
            border_style="gold1",
            padding=(1, 4),
        )
    )
    console.print()

    kpi_table = Table(
        box=box.DOUBLE,
        border_style="gold1",
        show_header=False,
        padding=(0, 3),
    )
    kpi_table.add_column("Metric", style="bold white", width=40)
    kpi_table.add_column("Value", style="bold", width=30)
    kpi_table.add_column("Context", style="dim", width=36)

    kpis = [
        ("Total monthly cloud spend (3 providers)", f"[bold red]{_fmt_usd(total_monthly_spend)}/mo[/bold red]", "AWS 67% | Azure 24% | GCP 9%"),
        ("Identified monthly waste", f"[bold red]{_fmt_usd(total_waste)}/mo[/bold red]", f"{total_waste/total_monthly_spend*100:.0f}% of total spend"),
        ("Annual savings opportunity", f"[bold green]{_fmt_usd(annual_waste)}/yr[/bold green]", "If all recommendations implemented"),
        ("AWS waste (largest provider)", f"[red]{_fmt_usd(aws_waste)}/mo[/red]", "NAT GWs + idle EC2 + oversized RDS"),
        ("Critical findings (immediate action)", "[bold red]3[/bold red]", "NAT GW $16K, RDS $8.8K, idle EC2 $1K"),
        ("Estimated implementation time", "[green]4-6 weeks[/green]", "Low-risk changes only, no downtime"),
        ("CloudIQ ROI payback period", f"[bold green]{roi_months} months[/bold green]", "Tool cost vs annual savings delivered"),
        ("Security findings resolved", "[bold green]14[/bold green]", "Unencrypted EBS/RDS, public endpoints"),
        ("Terraform coverage after adoption", "[bold green]100%[/bold green]", "All 247 AWS resources in IaC"),
    ]

    for metric, value, context in kpis:
        kpi_table.add_row(metric, value, context)

    console.print(kpi_table)
    console.print()

    roadmap = Table(
        title="Recommended 90-Day Implementation Roadmap",
        box=box.ROUNDED,
        border_style="green",
        header_style="bold white on dark_green",
        show_lines=True,
    )
    roadmap.add_column("Phase", width=10)
    roadmap.add_column("Actions", width=48)
    roadmap.add_column("Savings/mo", justify="right", style="bold green", width=12)
    roadmap.add_column("Effort", width=10)
    roadmap.add_column("Risk", width=8)

    phases = [
        ("Week 1-2", "VPC endpoints for S3 + DynamoDB (5 mins each)", "$11,200", "Low", "Zero"),
        ("Week 2-3", "Terminate idle EC2 + release Elastic IPs", "$1,399", "Low", "Zero"),
        ("Week 3-4", "RDS downsize prod-analytics-dwh → r5.xlarge", "$2,205", "Medium", "Low"),
        ("Week 4-6", "EBS snapshot lifecycle + delete orphaned volumes", "$1,840", "Low", "Zero"),
        ("Month 2",  "Deploy HPA for api-gateway + report-generator", "$4,260", "Medium", "Low"),
        ("Month 3",  "EKS node group rightsizing (data-pipeline-ng)", "$2,718", "Medium", "Medium"),
    ]

    for phase, action, savings, effort, risk in phases:
        risk_color = "green" if risk == "Zero" else ("yellow" if risk == "Low" else "red")
        roadmap.add_row(
            phase,
            action,
            savings,
            effort,
            f"[{risk_color}]{risk}[/{risk_color}]",
        )

    console.print(roadmap)
    console.print()

    console.print(
        Panel(
            "[bold white]CloudIQ V2 demonstrates:[/bold white]\n\n"
            "  :white_check_mark:  Multi-cloud cost intelligence (AWS + Azure + GCP)\n"
            "  :white_check_mark:  ML-powered anomaly detection (Isolation Forest + Prophet)\n"
            "  :white_check_mark:  Production-grade FastAPI with WebSocket streaming\n"
            "  :white_check_mark:  Security-hardened IaC generation (Terraform V2)\n"
            "  :white_check_mark:  Kubernetes namespace cost attribution + HPA recommendations\n"
            "  :white_check_mark:  Enterprise integrations: Slack, Jira, PagerDuty, Grafana\n"
            "  :white_check_mark:  Natural language query engine (Claude-backed)\n\n"
            "[dim]Built by Hunter Spence — 4 years Accenture Infrastructure Transformation\n"
            "AWS Certified Cloud Practitioner | Available for senior AI/Cloud roles[/dim]",
            title="[bold gold1]Why CloudIQ V2[/bold gold1]",
            border_style="gold1",
            padding=(1, 2),
        )
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    console.print()
    console.print(
        Panel(
            Align.center(
                "[bold cyan]CloudIQ V2[/bold cyan]\n"
                "[bold white]Enterprise Multi-Cloud Intelligence Platform[/bold white]\n\n"
                "[dim]8 scenes | Zero credentials required | Run with --fast for no-pause mode[/dim]"
            ),
            border_style="cyan",
            padding=(1, 4),
        )
    )
    console.print()

    if not FAST:
        console.print("[dim]Press ENTER to begin...[/dim]")
        input()

    scene_1_scan()
    scene_2_anomaly()
    scene_3_forecast()
    scene_4_nl_query()
    scene_5_terraform()
    scene_6_multicloud()
    scene_7_kubernetes()
    scene_8_executive()

    console.print()
    console.print(
        Rule("[bold cyan] End of CloudIQ V2 Demo [/bold cyan]", style="cyan")
    )
    console.print()


if __name__ == "__main__":
    main()
