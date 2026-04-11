"""
dashboard.py — Rich terminal dashboard for FinOps Intelligence.

Live spend overview, anomaly alerts, forecast panel, and optimization opportunities.
CFO summary line: "You spent $X this month. $Y is waste. Fix these 3 things."
"""

from __future__ import annotations

from datetime import date
from typing import Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text
from rich import box

from .cost_tracker import SpendData
from .anomaly_detector import Anomaly, AnomalySeverity
from .forecaster import ForecastResult, BurnRateResult
from .optimizer import OptimizationPlan


# ---------------------------------------------------------------------------
# Color scheme
# ---------------------------------------------------------------------------

SEVERITY_COLORS = {
    AnomalySeverity.CRITICAL: "bold red",
    AnomalySeverity.HIGH: "red",
    AnomalySeverity.MEDIUM: "yellow",
    AnomalySeverity.LOW: "dim yellow",
}

STATUS_COLORS = {
    "ON_TRACK": "green",
    "AT_RISK": "yellow",
    "OVER_BUDGET": "bold red",
}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class Dashboard:
    """
    Rich terminal dashboard. Renders all FinOps Intelligence data in one view.

    Usage:
        dash = Dashboard(spend_data, anomalies, forecast, burn_rate, optimization_plan)
        dash.render()         # single static render
        dash.render_live()    # live-updating (press Ctrl+C to exit)
    """

    def __init__(
        self,
        spend_data: SpendData,
        anomalies: list[Anomaly] | None = None,
        forecast: ForecastResult | None = None,
        burn_rate: BurnRateResult | None = None,
        optimization_plan: OptimizationPlan | None = None,
        console: Console | None = None,
    ) -> None:
        self.spend_data = spend_data
        self.anomalies = anomalies or []
        self.forecast = forecast
        self.burn_rate = burn_rate
        self.optimization_plan = optimization_plan
        self.console = console or Console()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self) -> None:
        """Render the full dashboard as a static snapshot."""
        self.console.print()
        self.console.print(self._build_header())
        self.console.print()
        self.console.print(self._build_cfo_summary_panel())
        self.console.print()

        # Two-column layout: spend table + anomalies
        self.console.print(self._build_spend_table())
        self.console.print()
        self.console.print(self._build_anomaly_panel())
        self.console.print()
        self.console.print(self._build_forecast_panel())
        self.console.print()
        self.console.print(self._build_optimization_panel())
        self.console.print()
        self.console.print(self._build_tag_coverage_panel())

    def render_compact(self) -> None:
        """Render compact summary (for CI/logging environments)."""
        self.console.print(self._build_cfo_summary_panel())
        self.console.print(self._build_spend_table())

    # ------------------------------------------------------------------
    # Panel builders
    # ------------------------------------------------------------------

    def _build_header(self) -> Panel:
        title_text = Text()
        title_text.append("FinOps Intelligence", style="bold cyan")
        title_text.append("  |  ", style="dim")
        title_text.append(f"Account: {self.spend_data.account_name}", style="white")
        title_text.append("  |  ", style="dim")
        title_text.append(f"As of {date.today()}", style="dim")

        subtitle = Text()
        subtitle.append("Open-source cloud cost optimization  |  ", style="dim")
        subtitle.append("Replaces CloudZero / IBM Cloudability ($50K+/year)", style="italic dim")

        combined = Text()
        combined.append_text(title_text)
        combined.append("\n")
        combined.append_text(subtitle)

        return Panel(combined, box=box.DOUBLE_EDGE, style="bold")

    def _build_cfo_summary_panel(self) -> Panel:
        """The CFO summary line: key numbers at a glance."""
        spend = self.spend_data
        lines: list[Text] = []

        # Line 1: Monthly spend
        l1 = Text()
        l1.append("Total spend (", style="white")
        l1.append(f"{spend.query_start} – {spend.query_end}", style="dim")
        l1.append("): ", style="white")
        l1.append(f"${spend.total_spend:,.0f}", style="bold cyan")
        lines.append(l1)

        # Line 2: MTD + projected
        l2 = Text()
        l2.append("Month-to-date: ", style="white")
        l2.append(f"${spend.mtd_spend:,.0f}", style="cyan")
        if spend.projected_monthly:
            l2.append("  |  Projected month-end: ", style="dim")
            l2.append(f"${spend.projected_monthly:,.0f}", style="yellow")
        lines.append(l2)

        # Line 3: Burn rate
        if self.burn_rate:
            br = self.burn_rate
            status_color = STATUS_COLORS.get(br.budget_status, "white")
            l3 = Text()
            l3.append("Budget status: ", style="white")
            l3.append(br.budget_status.replace("_", " "), style=status_color)
            l3.append(f"  ({br.pct_of_budget:.1f}% of ${br.monthly_budget:,.0f} budget)", style="dim")
            if br.budget_exhaustion_date:
                l3.append(f"  |  Budget exhausted: {br.budget_exhaustion_date}", style="bold red")
            lines.append(l3)

        # Line 4: Anomalies detected
        if self.anomalies:
            critical = sum(1 for a in self.anomalies if a.severity == AnomalySeverity.CRITICAL)
            high = sum(1 for a in self.anomalies if a.severity == AnomalySeverity.HIGH)
            l4 = Text()
            l4.append("Anomalies: ", style="white")
            if critical:
                l4.append(f"{critical} CRITICAL ", style="bold red")
            if high:
                l4.append(f"{high} HIGH ", style="red")
            l4.append(f"({len(self.anomalies)} total detected)", style="dim")
            lines.append(l4)

        # Line 5: Optimization opportunity
        if self.optimization_plan:
            plan = self.optimization_plan
            l5 = Text()
            l5.append("Savings identified: ", style="white")
            l5.append(f"${plan.total_monthly_savings:,.0f}/month", style="bold green")
            l5.append(f" (${plan.total_annual_savings:,.0f}/year)  |  ", style="green")
            l5.append(f"{len(plan.opportunities)} opportunities", style="dim")
            lines.append(l5)
            # The killer CFO line
            top3 = plan.top_opportunities(3)
            top3_titles = "; ".join(f"({i+1}) {o.title[:50]}..." if len(o.title) > 50 else f"({i+1}) {o.title}" for i, o in enumerate(top3))
            l6 = Text()
            l6.append("Fix these 3 things: ", style="bold white")
            l6.append(top3_titles, style="dim")
            lines.append(l6)

        combined = Text("\n").join(lines)
        return Panel(combined, title="[bold]CFO Summary[/bold]", border_style="cyan", padding=(1, 2))

    def _build_spend_table(self) -> Panel:
        """Top 10 services by cost with bar chart."""
        table = Table(
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="bold cyan",
            expand=True,
        )
        table.add_column("Rank", justify="right", style="dim", width=4)
        table.add_column("Service", style="white", min_width=30)
        table.add_column("Total Spend", justify="right", style="cyan", width=14)
        table.add_column("% of Total", justify="right", width=10)
        table.add_column("Spend Bar", min_width=30)

        top_services = self.spend_data.top_services(10)
        max_spend = top_services[0].total if top_services else 1
        total = self.spend_data.total_spend or 1

        for i, svc in enumerate(top_services, 1):
            pct = svc.total / total * 100
            bar_width = int(svc.total / max_spend * 28)
            bar = "█" * bar_width + "░" * (28 - bar_width)

            # Color top 3 differently
            color = "bold cyan" if i <= 1 else ("cyan" if i <= 3 else "dim white")

            table.add_row(
                str(i),
                svc.service,
                f"${svc.total:,.0f}",
                f"{pct:.1f}%",
                Text(bar, style=color),
            )

        return Panel(table, title="[bold]Top 10 Services by Spend[/bold]", border_style="blue")

    def _build_anomaly_panel(self) -> Panel:
        """Anomaly alerts table."""
        if not self.anomalies:
            return Panel(
                Text("No anomalies detected.", style="green"),
                title="[bold]Anomaly Alerts[/bold]",
                border_style="green",
            )

        table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold", expand=True)
        table.add_column("Severity", width=10)
        table.add_column("Date", width=12)
        table.add_column("Service", min_width=25)
        table.add_column("Amount", justify="right", width=12)
        table.add_column("Delta", justify="right", width=16)
        table.add_column("Z-Score", justify="right", width=8)
        table.add_column("Confidence", justify="right", width=10)

        for anomaly in self.anomalies[:8]:
            color = SEVERITY_COLORS[anomaly.severity]
            table.add_row(
                Text(anomaly.severity.value, style=color),
                str(anomaly.detected_at),
                anomaly.service[:35],
                f"${anomaly.amount:,.0f}",
                Text(anomaly.formatted_delta, style="red" if anomaly.delta > 0 else "green"),
                f"{anomaly.zscore:.1f}σ",
                f"{anomaly.confidence:.0%}",
            )

        # Show explanation for top anomaly
        extra = Text()
        if self.anomalies and self.anomalies[0].explanation:
            top = self.anomalies[0]
            extra.append(f"\nTop anomaly explanation:\n", style="bold")
            extra.append(top.explanation, style="italic dim")

        combined = Text()
        # Can't easily stack Table + Text in Panel, so just return table
        border_color = "red" if any(a.severity == AnomalySeverity.CRITICAL for a in self.anomalies) else "yellow"

        return Panel(table, title="[bold]Anomaly Alerts[/bold]", border_style=border_color)

    def _build_forecast_panel(self) -> Panel:
        """30-day forecast summary."""
        if not self.forecast:
            return Panel(
                Text("No forecast data available. Run forecaster.forecast() first.", style="dim"),
                title="[bold]30-Day Forecast[/bold]",
                border_style="blue",
            )

        fc = self.forecast
        lines: list[Text] = []

        # Headline numbers
        l1 = Text()
        l1.append("Predicted spend (next 30 days): ", style="white")
        l1.append(f"${fc.total_predicted:,.0f}", style="bold yellow")
        l1.append(f"  (P10: ${fc.total_lower:,.0f} – P90: ${fc.total_upper:,.0f})", style="dim")
        lines.append(l1)

        l2 = Text()
        l2.append("Trend: ", style="white")
        trend_color = "red" if fc.trend == "increasing" else ("green" if fc.trend == "decreasing" else "yellow")
        l2.append(fc.trend.upper(), style=trend_color)
        if fc.trend_pct_per_month != 0:
            sign = "+" if fc.trend_pct_per_month > 0 else ""
            l2.append(f"  ({sign}{fc.trend_pct_per_month:.1f}%/month)", style="dim")
        lines.append(l2)

        l3 = Text()
        l3.append("Model: ", style="white")
        l3.append(fc.model_used, style="dim")
        l3.append("  |  MAPE: ", style="white")
        mape_color = "green" if fc.mape < 0.08 else ("yellow" if fc.mape < 0.15 else "red")
        l3.append(f"{fc.mape:.1%}", style=mape_color)
        l3.append("  |  End date: ", style="white")
        l3.append(str(fc.end_date), style="dim")
        lines.append(l3)

        # Sparkline (last 10 forecast points)
        if fc.daily_forecast:
            points = fc.daily_forecast[-10:]
            max_val = max(p.predicted for p in points) or 1
            spark_chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
            spark = ""
            for p in points:
                idx = int(p.predicted / max_val * 7)
                spark += spark_chars[min(idx, 7)]
            l4 = Text()
            l4.append("10-day sparkline: ", style="white")
            l4.append(spark, style="yellow")
            l4.append(f"  (${points[-1].predicted:,.0f}/day at end)", style="dim")
            lines.append(l4)

        combined = Text("\n").join(lines)
        return Panel(combined, title="[bold]30-Day Spend Forecast[/bold]", border_style="yellow", padding=(1, 2))

    def _build_optimization_panel(self) -> Panel:
        """Top optimization opportunities."""
        if not self.optimization_plan:
            return Panel(
                Text("No optimization analysis available. Run optimizer.analyze() first.", style="dim"),
                title="[bold]Optimization Opportunities[/bold]",
                border_style="green",
            )

        plan = self.optimization_plan
        table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold green", expand=True)
        table.add_column("#", justify="right", width=3)
        table.add_column("Opportunity", min_width=40)
        table.add_column("Type", width=18)
        table.add_column("Savings/mo", justify="right", width=12)
        table.add_column("Effort", width=8)
        table.add_column("Risk", width=8)
        table.add_column("Confidence", justify="right", width=10)

        type_colors = {
            "SAVINGS_PLAN": "bold green",
            "RIGHTSIZING": "cyan",
            "WASTE_ELIMINATION": "yellow",
            "GRAVITON_MIGRATION": "magenta",
            "RESERVED_INSTANCE": "green",
            "SPOT_INSTANCE": "blue",
        }
        effort_colors = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red"}

        for opp in plan.top_opportunities(5):
            type_color = type_colors.get(opp.type.value, "white")
            effort_color = effort_colors.get(opp.effort, "white")
            risk_color = effort_colors.get(opp.risk, "white")

            title_short = opp.title[:50] + ("..." if len(opp.title) > 50 else "")
            table.add_row(
                str(opp.priority),
                title_short,
                Text(opp.type.value.replace("_", " "), style=type_color),
                Text(f"${opp.savings_monthly:,.0f}", style="bold green"),
                Text(opp.effort, style=effort_color),
                Text(opp.risk, style=risk_color),
                f"{opp.confidence:.0%}",
            )

        # Summary footer
        summary = Text()
        summary.append("\nTotal: ", style="bold")
        summary.append(f"${plan.total_monthly_savings:,.0f}/month", style="bold green")
        summary.append(f" = ${plan.total_annual_savings:,.0f}/year  |  ", style="green")
        summary.append(f"RI/SP coverage: {plan.ri_sp_coverage_pct:.0f}% ", style="yellow")
        summary.append("(target: 70%)", style="dim")

        return Panel(
            Text.assemble(summary, "\n"),
            title=(
                f"[bold green]Optimization Opportunities — "
                f"${plan.total_monthly_savings:,.0f}/month identified[/bold green]"
            ),
            border_style="green",
        )

    def _build_tag_coverage_panel(self) -> Panel:
        """Tag compliance panel."""
        tc = self.spend_data.tag_coverage
        if not tc:
            return Panel(
                Text("No tag coverage data available.", style="dim"),
                title="[bold]Tag Coverage[/bold]",
                border_style="dim",
            )

        lines: list[Text] = []

        l1 = Text()
        l1.append("Tag coverage: ", style="white")
        coverage_color = "green" if tc.coverage_pct >= 80 else ("yellow" if tc.coverage_pct >= 60 else "red")
        l1.append(f"{tc.coverage_pct:.0f}%", style=coverage_color)
        l1.append(f"  ({tc.tagged_resources:,} / {tc.total_resources:,} resources tagged)", style="dim")
        lines.append(l1)

        l2 = Text()
        l2.append("Unallocatable spend: ", style="white")
        l2.append(f"${tc.untagged_spend:,.0f}", style="red" if tc.untagged_spend > 10_000 else "yellow")
        l2.append(f"  ({tc.untaggable_spend_pct:.1f}% structurally untaggable by AWS)", style="dim")
        lines.append(l2)

        if tc.suggestions:
            l3 = Text()
            l3.append(f"Auto-tag suggestions: {len(tc.suggestions)} patterns identified", style="dim")
            lines.append(l3)

        combined = Text("\n").join(lines)
        border_color = "green" if tc.coverage_pct >= 80 else ("yellow" if tc.coverage_pct >= 60 else "red")
        return Panel(combined, title="[bold]Tag Coverage & Allocation[/bold]", border_style=border_color, padding=(1, 2))
