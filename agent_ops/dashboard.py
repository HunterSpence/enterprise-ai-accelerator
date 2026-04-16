"""
agent_ops/dashboard.py

Terminal dashboard using the `rich` library.
Shows live agent status, progress, activity log, and final results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from agent_ops.agents import AgentStatus


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

_THEME = Theme(
    {
        "pending": "dim white",
        "running": "bold cyan",
        "done": "bold green",
        "failed": "bold red",
        "coordinator": "bold magenta",
        "header": "bold white on dark_blue",
        "section": "bold yellow",
    }
)

_STATUS_ICONS = {
    AgentStatus.PENDING: "[pending]○[/pending]",
    AgentStatus.RUNNING: "[running]◉[/running]",
    AgentStatus.DONE: "[done]●[/done]",
    AgentStatus.FAILED: "[failed]✗[/failed]",
}

_AGENT_DESCRIPTIONS = {
    "ArchitectureAgent": "AWS infrastructure analysis (CloudIQ)",
    "MigrationAgent":    "6R workload migration planning",
    "ComplianceAgent":   "CIS/SOC2/GDPR/PCI compliance audit",
    "ReportAgent":       "Executive briefing synthesis",
    "Coordinator":       "Opus coordinator — task decomposition",
}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@dataclass
class _AgentState:
    name: str
    status: AgentStatus = AgentStatus.PENDING
    findings_count: int = 0
    duration: float = 0.0
    detail: str = ""


class Dashboard:
    """
    Live terminal dashboard for an AgentOps pipeline run.

    Usage:
        dash = Dashboard()
        with dash.live_context():
            # call dash.update_agent(...) as events arrive
            result = await orchestrator.run_pipeline(...)
        dash.render_final(result)
    """

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console(theme=_THEME)
        self._agents: dict[str, _AgentState] = {
            name: _AgentState(name=name)
            for name in [
                "Coordinator",
                "ArchitectureAgent",
                "MigrationAgent",
                "ComplianceAgent",
                "ReportAgent",
            ]
        }
        self._activity_log: list[str] = []
        self._pipeline_start = time.monotonic()
        self._live: Live | None = None

    # ------------------------------------------------------------------
    # Event handlers (called by orchestrator callbacks)
    # ------------------------------------------------------------------

    def on_activity(self, activity: Any) -> None:
        """Receive an AgentActivity and update display state."""
        agent = activity.agent
        event = activity.event

        if agent not in self._agents:
            self._agents[agent] = _AgentState(name=agent)

        state = self._agents[agent]

        if event == "started":
            state.status = AgentStatus.RUNNING
            state.detail = activity.detail
        elif event == "completed":
            state.status = AgentStatus.DONE
            state.detail = activity.detail
            # Extract findings count from detail like "12 findings"
            parts = activity.detail.split()
            if parts and parts[0].isdigit():
                state.findings_count = int(parts[0])
        elif event == "failed":
            state.status = AgentStatus.FAILED
            state.detail = activity.detail

        state.duration = time.monotonic() - self._pipeline_start

        ts = activity.timestamp
        icon = {"started": "[cyan]→[/cyan]", "completed": "[green]✓[/green]", "failed": "[red]✗[/red]"}.get(event, " ")
        self._activity_log.append(f"[dim]{ts}[/dim] {icon} [bold]{agent}[/bold]: {activity.detail or event}")

        if self._live:
            self._live.update(self._build_layout())

    # ------------------------------------------------------------------
    # Live context
    # ------------------------------------------------------------------

    def live_context(self) -> Live:
        self._pipeline_start = time.monotonic()
        self._live = Live(
            self._build_layout(),
            console=self._console,
            refresh_per_second=4,
            transient=False,
        )
        return self._live

    # ------------------------------------------------------------------
    # Final render
    # ------------------------------------------------------------------

    def render_final(self, result: Any) -> None:
        """Print the complete results table after pipeline completion."""
        self._console.print()
        self._console.rule("[section]PIPELINE COMPLETE[/section]")
        self._console.print()

        # Status banner
        status_color = {"success": "green", "partial": "yellow", "failed": "red"}.get(result.status, "white")
        self._console.print(
            Panel(
                f"[bold {status_color}]{result.status.upper()}[/bold {status_color}]  "
                f"  {result.total_duration_seconds:.1f}s total  "
                f"  {result.total_findings} findings  "
                f"  Health Score: {result.overall_health_score}/100",
                title="[header]PIPELINE RESULT[/header]",
                border_style=status_color,
            )
        )

        # Coordinator plan
        if result.coordinator_plan:
            self._console.print(
                Panel(
                    result.coordinator_plan,
                    title="[section]Coordinator Work Plan (Claude Opus)[/section]",
                    border_style="magenta",
                )
            )

        # Agent results table
        agent_table = Table(
            title="Agent Results",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold white on dark_blue",
        )
        agent_table.add_column("Agent", style="bold", width=22)
        agent_table.add_column("Status", width=10)
        agent_table.add_column("Findings", justify="right", width=10)
        agent_table.add_column("Duration", justify="right", width=10)
        agent_table.add_column("Key Detail", width=50)

        for name, agent_result in result.agent_results.items():
            status_icon = _STATUS_ICONS.get(agent_result.status, "?")
            duration_str = f"{agent_result.duration_seconds:.1f}s"
            key_detail = (agent_result.findings[0][:60] if agent_result.findings else agent_result.error or "")
            agent_table.add_row(
                name,
                status_icon,
                str(len(agent_result.findings)),
                duration_str,
                key_detail,
            )

        self._console.print(agent_table)

        # Executive summary
        if result.executive_summary:
            self._console.print(
                Panel(
                    result.executive_summary,
                    title="[section]Executive Summary[/section]",
                    border_style="green",
                )
            )

        # Top risks
        if result.top_risks:
            risk_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
            risk_table.add_column("", width=2)
            risk_table.add_column("Risk")
            for i, risk in enumerate(result.top_risks, 1):
                risk_table.add_row(f"[red]{i}.[/red]", risk)
            self._console.print(
                Panel(risk_table, title="[section]Top Risks[/section]", border_style="red")
            )

        # Quick wins
        if result.quick_wins:
            qw_text = "\n".join(f"  [green]→[/green] {w}" for w in result.quick_wins)
            self._console.print(
                Panel(qw_text, title="[section]Quick Wins (30-Day)[/section]", border_style="cyan")
            )

        # 90-day roadmap
        if result.roadmap_90_day:
            roadmap_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
            roadmap_table.add_column("Phase", style="bold", width=20)
            roadmap_table.add_column("Actions")
            for phase in result.roadmap_90_day:
                actions = "\n".join(f"• {a}" for a in phase.get("actions", []))
                roadmap_table.add_row(phase.get("phase", ""), actions)
            self._console.print(
                Panel(roadmap_table, title="[section]90-Day Roadmap[/section]", border_style="yellow")
            )

        self._console.print()

    # ------------------------------------------------------------------
    # Internal layout builder
    # ------------------------------------------------------------------

    def _build_layout(self) -> Panel:
        elapsed = time.monotonic() - self._pipeline_start

        # Agent status grid
        status_table = Table(box=box.SIMPLE, show_header=True, header_style="bold white")
        status_table.add_column("Agent", width=22)
        status_table.add_column("Model", width=14)
        status_table.add_column("Status", width=10)
        status_table.add_column("Detail", width=40)

        model_map = {
            "Coordinator": "claude-opus-4-7",
            "ArchitectureAgent": "claude-haiku-4-5",
            "MigrationAgent": "claude-haiku-4-5",
            "ComplianceAgent": "claude-haiku-4-5",
            "ReportAgent": "claude-haiku-4-5",
        }

        for name, state in self._agents.items():
            icon = _STATUS_ICONS.get(state.status, "?")
            model = model_map.get(name, "")
            status_table.add_row(name, f"[dim]{model}[/dim]", icon, f"[dim]{state.detail[:38]}[/dim]")

        # Activity log (last 8 entries)
        log_entries = self._activity_log[-8:]
        log_text = "\n".join(log_entries) if log_entries else "[dim]Waiting for agents...[/dim]"

        combined = Table.grid(padding=1)
        combined.add_column()
        combined.add_row(status_table)
        combined.add_row(Text(f"\nActivity Log  ({elapsed:.1f}s elapsed)", style="bold yellow"))
        combined.add_row(Text(log_text))

        return Panel(
            combined,
            title="[header]  AgentOps — Multi-Agent Orchestration Monitor  [/header]",
            border_style="dark_blue",
        )
