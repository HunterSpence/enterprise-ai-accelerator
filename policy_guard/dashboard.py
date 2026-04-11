"""
PolicyGuard — Compliance Dashboard
=====================================
Rich terminal dashboard with live updates.

Features:
  - Compliance score gauges per framework (CIS, EU AI Act, NIST, SOC2, HIPAA)
  - Trending: compliance score over last 5 scans
  - Top 10 open findings sorted by risk × effort
  - Days until next EU AI Act milestone countdown
  - Recently registered AI systems with risk tiers
  - Live scan progress feed

Run standalone: python -m policy_guard.dashboard
Or import DashboardRenderer for use in demo.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich import box


console = Console()

# ---------------------------------------------------------------------------
# Score rendering helpers
# ---------------------------------------------------------------------------

def _score_color(score: float) -> str:
    if score >= 85:
        return "green"
    elif score >= 70:
        return "yellow"
    elif score >= 50:
        return "orange3"
    else:
        return "red"


def _gauge_bar(score: float, width: int = 20) -> str:
    """ASCII gauge bar for terminal display."""
    filled = int(score / 100 * width)
    empty = width - filled
    color = _score_color(score)
    bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"
    return f"{bar} [{color}]{score:.0f}%[/{color}]"


def _risk_badge(risk_tier: str) -> str:
    colors = {
        "Unacceptable": "bold white on red",
        "High-Risk": "bold white on red3",
        "GPAI (General Purpose AI)": "bold white on purple",
        "Limited Risk": "bold black on yellow",
        "Minimal Risk": "bold white on green",
        "High Risk": "bold white on red3",
        "Critical Risk": "bold white on red",
        "Medium Risk": "bold black on yellow",
        "Low Risk": "bold black on green3",
        "Compliant": "bold white on green",
    }
    color = colors.get(risk_tier, "white")
    return f"[{color}] {risk_tier} [/{color}]"


# ---------------------------------------------------------------------------
# Simulated historical scan data for trending
# ---------------------------------------------------------------------------

HISTORICAL_SCANS = [
    {"date": "2026-01-15", "overall": 34.0, "eu_ai_act": 22.0, "nist": 18.0, "soc2": 28.0, "cis": 61.0, "hipaa": 42.0},
    {"date": "2026-02-01", "overall": 41.0, "eu_ai_act": 28.0, "nist": 24.0, "soc2": 33.0, "cis": 65.0, "hipaa": 48.0},
    {"date": "2026-02-15", "overall": 49.0, "eu_ai_act": 35.0, "nist": 30.0, "soc2": 40.0, "cis": 70.0, "hipaa": 54.0},
    {"date": "2026-03-01", "overall": 55.0, "eu_ai_act": 42.0, "nist": 36.0, "soc2": 46.0, "cis": 74.0, "hipaa": 60.0},
    {"date": "2026-04-11", "overall": 63.0, "eu_ai_act": 51.0, "nist": 42.0, "soc2": 52.0, "cis": 78.0, "hipaa": 66.0},
]


# ---------------------------------------------------------------------------
# Dashboard panels
# ---------------------------------------------------------------------------

def _make_header_panel(days_to_deadline: int) -> Panel:
    urgency_color = "red bold" if days_to_deadline < 120 else "yellow"
    return Panel(
        Align.center(
            f"[bold cyan]PolicyGuard v2.0[/bold cyan]  |  [dim]AI Governance & Compliance Platform[/dim]\n"
            f"[{urgency_color}]EU AI Act High-Risk Deadline: {days_to_deadline} days away — August 2, 2026[/{urgency_color}]",
        ),
        border_style="cyan",
        padding=(0, 2),
    )


def _make_framework_scores_panel(scores: dict[str, float]) -> Panel:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    table.add_column("Framework", style="cyan", width=32)
    table.add_column("Score", width=32)
    table.add_column("Status", width=14)

    framework_labels = {
        "eu_ai_act": "EU AI Act (Regulation 2024/1689)",
        "nist_ai_rmf": "NIST AI RMF 1.0",
        "soc2": "SOC 2 Type II + AICC (2024)",
        "cis_aws": "CIS AWS Foundations v3.0",
        "hipaa": "HIPAA Security Rule",
    }

    statuses = {
        range(0, 50): ("[red]Critical[/red]", "red"),
        range(50, 70): ("[yellow]High Risk[/yellow]", "yellow"),
        range(70, 85): ("[orange3]Medium[/orange3]", "orange3"),
        range(85, 101): ("[green]Compliant[/green]", "green"),
    }

    def get_status(s: float) -> str:
        for r, (label, _) in statuses.items():
            if int(s) in r:
                return label
        return "Unknown"

    for fw_key, label in framework_labels.items():
        score = scores.get(fw_key, 0.0)
        table.add_row(label, _gauge_bar(score), get_status(score))

    return Panel(table, title="[bold]Framework Compliance Scores[/bold]", border_style="blue")


def _make_trending_panel(historical: list[dict]) -> Panel:
    """Sparkline-style trending for last 5 scans."""
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    table.add_column("Date", width=12)
    table.add_column("Overall", width=14)
    table.add_column("EU AI Act", width=14)
    table.add_column("NIST", width=12)
    table.add_column("SOC2", width=12)
    table.add_column("Trend", width=8)

    prev_overall = None
    for scan in historical:
        overall = scan["overall"]
        trend_arrow = ""
        if prev_overall is not None:
            delta = overall - prev_overall
            if delta > 0:
                trend_arrow = f"[green]+{delta:.0f}[/green]"
            elif delta < 0:
                trend_arrow = f"[red]{delta:.0f}[/red]"
            else:
                trend_arrow = "[dim]--[/dim]"

        color = _score_color(overall)
        table.add_row(
            scan["date"],
            f"[{color}]{overall:.0f}%[/{color}]",
            f"{scan['eu_ai_act']:.0f}%",
            f"{scan['nist']:.0f}%",
            f"{scan['soc2']:.0f}%",
            trend_arrow,
        )
        prev_overall = overall

    return Panel(table, title="[bold]Compliance Trend — Last 5 Scans[/bold]", border_style="magenta")


def _make_top_findings_panel(findings: list[dict]) -> Panel:
    """Top 10 findings sorted by risk_score × effort_score."""
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    table.add_column("Sev", width=8)
    table.add_column("Framework", width=14)
    table.add_column("Finding", width=42)
    table.add_column("Risk×Effort", justify="right", width=10)

    sev_colors = {"CRITICAL": "red", "HIGH": "orange3", "MEDIUM": "yellow", "LOW": "green"}

    for f in findings[:10]:
        sev = f.get("severity", "MEDIUM")
        color = sev_colors.get(sev, "white")
        risk_effort = f.get("risk_effort_score", 0)
        table.add_row(
            f"[{color}]{sev[:4]}[/{color}]",
            f"[dim]{f.get('framework', '')[:12]}[/dim]",
            f["title"][:42],
            f"[bold]{risk_effort}[/bold]",
        )

    return Panel(table, title="[bold]Top Open Findings — Ranked by Impact × Effort[/bold]", border_style="red")


def _make_ai_systems_panel(systems: list[dict]) -> Panel:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    table.add_column("System", style="cyan", width=22)
    table.add_column("Risk Tier", width=26)
    table.add_column("Articles Due", width=18)
    table.add_column("Deadline", width=12)

    for s in systems:
        tier = s.get("risk_tier", "Unknown")
        deadline = s.get("deadline", "—")
        articles = s.get("articles_failing", 0)
        table.add_row(
            s["name"],
            _risk_badge(tier),
            f"[red]{articles} failing[/red]" if articles > 0 else "[green]0 failing[/green]",
            deadline,
        )

    return Panel(table, title="[bold]Registered AI Systems[/bold]", border_style="yellow")


def _make_countdown_panel(days: int) -> Panel:
    progress_pct = max(0, min(100, (365 - days) / 365 * 100))
    color = "red bold" if days < 120 else "orange3" if days < 180 else "yellow"

    bar_width = 40
    filled = int(progress_pct / 100 * bar_width)
    empty = bar_width - filled
    bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"

    content = (
        f"[bold]EU AI Act High-Risk Enforcement[/bold]\n\n"
        f"  {bar}\n\n"
        f"  [{color}]{days} days remaining[/{color}]  |  August 2, 2026\n\n"
        f"  [dim]Non-compliance penalty: up to €35,000,000 or 3% global turnover[/dim]\n"
        f"  [dim]IBM OpenPages: $500K/yr  |  Credo AI: $180K/yr  |  PolicyGuard: $0[/dim]"
    )
    return Panel(content, title="[bold red]Enforcement Countdown[/bold red]", border_style="red")


# ---------------------------------------------------------------------------
# Synthetic summary data for standalone dashboard
# ---------------------------------------------------------------------------

def _generate_demo_summary() -> dict:
    """Generate demo data for standalone dashboard display."""
    from policy_guard.frameworks.eu_ai_act import days_until_enforcement

    scores = {
        "eu_ai_act": 51.0,
        "nist_ai_rmf": 42.0,
        "soc2": 52.0,
        "cis_aws": 78.0,
        "hipaa": 66.0,
    }

    findings = [
        {"severity": "CRITICAL", "framework": "EU AI Act", "title": "Art.12: No audit logging on HiringAI", "risk_effort_score": 980},
        {"severity": "CRITICAL", "framework": "SOC2", "title": "AICC-4: AI decision logging absent", "risk_effort_score": 960},
        {"severity": "CRITICAL", "framework": "EU AI Act", "title": "Art.10: Bias testing never performed", "risk_effort_score": 920},
        {"severity": "CRITICAL", "framework": "SOC2", "title": "AICC-12: No AI incident response plan", "risk_effort_score": 900},
        {"severity": "HIGH", "framework": "NIST", "title": "GOVERN-1.1: No AI governance policy", "risk_effort_score": 800},
        {"severity": "HIGH", "framework": "EU AI Act", "title": "Art.14: No human oversight mechanism", "risk_effort_score": 780},
        {"severity": "HIGH", "framework": "SOC2", "title": "AICC-7: No bias fairness controls", "risk_effort_score": 760},
        {"severity": "HIGH", "framework": "EU AI Act", "title": "Art.11: Tech doc 15% complete (need 100%)", "risk_effort_score": 740},
        {"severity": "HIGH", "framework": "NIST", "title": "MEASURE-2.3: Bias testing not conducted", "risk_effort_score": 720},
        {"severity": "HIGH", "framework": "CIS AWS", "title": "1.4: MFA not enabled on root account", "risk_effort_score": 700},
    ]

    ai_systems = [
        {"name": "HiringAI", "risk_tier": "High-Risk", "articles_failing": 6, "deadline": "Aug 2, 2026"},
        {"name": "CreditScoreAI", "risk_tier": "High-Risk", "articles_failing": 7, "deadline": "Aug 2, 2026"},
        {"name": "CustomerSupportLLM", "risk_tier": "GPAI (General Purpose AI)", "articles_failing": 3, "deadline": "Aug 2, 2025"},
        {"name": "DiagnosticAI", "risk_tier": "High-Risk", "articles_failing": 4, "deadline": "Aug 2, 2026"},
    ]

    return {
        "scores": scores,
        "findings": findings,
        "ai_systems": ai_systems,
        "days_to_deadline": days_until_enforcement("high_risk_systems"),
    }


# ---------------------------------------------------------------------------
# Dashboard renderer
# ---------------------------------------------------------------------------

class DashboardRenderer:
    """Renders the PolicyGuard compliance dashboard."""

    def __init__(self, report=None) -> None:
        self.report = report

    def render_static(self) -> None:
        """Render a static dashboard snapshot (for use after scanning)."""
        data = self._extract_data()
        days = data["days_to_deadline"]

        console.print()
        console.print(_make_header_panel(days))
        console.print()
        console.print(_make_framework_scores_panel(data["scores"]))
        console.print()
        console.print(_make_trending_panel(HISTORICAL_SCANS))
        console.print()

        # Two columns: findings + AI systems
        findings_panel = _make_top_findings_panel(data["findings"])
        systems_panel = _make_ai_systems_panel(data["ai_systems"])
        console.print(Columns([findings_panel, systems_panel], equal=True))
        console.print()
        console.print(_make_countdown_panel(days))
        console.print()

    async def render_live(self, duration_seconds: int = 10) -> None:
        """Render a live dashboard that updates every second."""
        data = self._extract_data()
        days = data["days_to_deadline"]

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="main"),
            Layout(name="footer", size=7),
        )
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )
        layout["left"].split_column(
            Layout(name="scores"),
            Layout(name="findings"),
        )
        layout["right"].split_column(
            Layout(name="systems"),
            Layout(name="trend"),
        )

        layout["header"].update(_make_header_panel(days))
        layout["scores"].update(_make_framework_scores_panel(data["scores"]))
        layout["findings"].update(_make_top_findings_panel(data["findings"]))
        layout["systems"].update(_make_ai_systems_panel(data["ai_systems"]))
        layout["trend"].update(_make_trending_panel(HISTORICAL_SCANS[-3:]))
        layout["footer"].update(_make_countdown_panel(days))

        with Live(layout, console=console, refresh_per_second=1, screen=True):
            await asyncio.sleep(duration_seconds)

    def _extract_data(self) -> dict:
        if self.report is None:
            return _generate_demo_summary()

        from policy_guard.frameworks.eu_ai_act import days_until_enforcement

        scores: dict[str, float] = {}
        for fs in getattr(self.report, "framework_scores", []):
            scores[fs.framework] = fs.score

        # Build top findings
        findings: list[dict] = []
        severity_scores = {"CRITICAL": 100, "HIGH": 75, "MEDIUM": 40, "LOW": 10}
        effort_scores = {"CRITICAL": 9.8, "HIGH": 8.0, "MEDIUM": 5.0, "LOW": 2.0}

        for fw in ["cis_aws", "eu_ai_act", "nist_ai_rmf", "soc2", "hipaa"]:
            fw_report = getattr(self.report, fw, None)
            if not fw_report:
                continue
            for f in getattr(fw_report, "findings", []):
                if getattr(f, "status", "") == "FAIL":
                    sev = getattr(f, "severity", "MEDIUM")
                    findings.append({
                        "severity": sev,
                        "framework": fw.replace("_", " ").upper()[:12],
                        "title": getattr(f, "title", "")[:42],
                        "risk_effort_score": int(severity_scores.get(sev, 40) * effort_scores.get(sev, 5.0)),
                    })
        findings.sort(key=lambda x: x["risk_effort_score"], reverse=True)

        # AI systems
        ai_systems: list[dict] = []
        eu_report = getattr(self.report, "eu_ai_act", None)
        if eu_report:
            for cls in getattr(eu_report, "all_classifications", []):
                failing = sum(
                    1 for a in getattr(eu_report, "article_assessments", [])
                    if getattr(a, "status", "") in ("FAIL", "PARTIAL")
                    and getattr(a, "article_id", "").startswith("Art.")
                )
                ai_systems.append({
                    "name": cls.system_name,
                    "risk_tier": cls.risk_tier,
                    "articles_failing": failing,
                    "deadline": cls.conformity_deadline.strftime("%b %d, %Y") if cls.conformity_deadline else "—",
                })

        return {
            "scores": scores,
            "findings": findings,
            "ai_systems": ai_systems,
            "days_to_deadline": days_until_enforcement("high_risk_systems"),
        }


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

async def _run_dashboard() -> None:
    renderer = DashboardRenderer()
    console.print("[dim]Loading PolicyGuard compliance dashboard...[/dim]")
    await asyncio.sleep(0.5)
    renderer.render_static()


def main() -> None:
    try:
        _module_dir = Path(__file__).resolve().parent.parent
        if str(_module_dir) not in sys.path:
            sys.path.insert(0, str(_module_dir))
        asyncio.run(_run_dashboard())
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard closed.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
