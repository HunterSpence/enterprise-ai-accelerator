"""
PolicyGuard — Main Compliance Scanner
======================================
Orchestrates async parallel scanning across all frameworks and aggregates
results into a unified ComplianceReport with weighted risk scoring.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from policy_guard.frameworks.cis_aws import CISAWSScanner, CISAWSReport
from policy_guard.frameworks.eu_ai_act import EUAIActScanner, EUAIActReport
from policy_guard.frameworks.nist_ai_rmf import NISTAIRMFScanner, NISTAIRMFReport
from policy_guard.frameworks.soc2 import SOC2Scanner, SOC2Report
from policy_guard.frameworks.hipaa import HIPAAScanner, HIPAAReport

console = Console()

# Risk weights — how much each framework contributes to total score.
# EU AI Act and CIS AWS are weighted highest for most enterprise contexts.
FRAMEWORK_WEIGHTS: dict[str, float] = {
    "cis_aws": 0.25,
    "eu_ai_act": 0.30,
    "nist_ai_rmf": 0.20,
    "soc2": 0.15,
    "hipaa": 0.10,
}


@dataclass
class ScanConfig:
    """Configuration for a PolicyGuard scan run."""

    # AWS config
    aws_region: str = "us-east-1"
    aws_profile: Optional[str] = None
    mock_mode: bool = True  # True = no real AWS calls; safe for demo

    # Which frameworks to include
    run_cis_aws: bool = True
    run_eu_ai_act: bool = True
    run_nist_ai_rmf: bool = True
    run_soc2: bool = True
    run_hipaa: bool = True

    # AI system metadata (for EU AI Act + NIST)
    ai_systems: list[dict] = field(default_factory=list)

    # Report output
    output_dir: str = "./policyguard_reports"
    generate_pdf: bool = True

    # Anthropic API key for Claude-powered narrative generation (optional)
    anthropic_api_key: Optional[str] = None


@dataclass
class FrameworkScore:
    framework: str
    score: float           # 0.0 – 100.0
    findings_count: int
    critical_count: int
    high_count: int
    weight: float
    weighted_score: float  # score * weight


@dataclass
class ComplianceReport:
    """Unified compliance report aggregating all framework results."""

    scan_id: str
    timestamp: datetime
    config: ScanConfig

    # Per-framework results
    cis_aws: Optional[CISAWSReport] = None
    eu_ai_act: Optional[EUAIActReport] = None
    nist_ai_rmf: Optional[NISTAIRMFReport] = None
    soc2: Optional[SOC2Report] = None
    hipaa: Optional[HIPAAReport] = None

    # Aggregated scores
    framework_scores: list[FrameworkScore] = field(default_factory=list)
    overall_score: float = 0.0      # weighted average, 0–100
    risk_rating: str = "Unknown"    # Critical / High / Medium / Low / Compliant

    # Totals
    total_findings: int = 0
    critical_findings: int = 0
    high_findings: int = 0
    medium_findings: int = 0
    low_findings: int = 0

    scan_duration_seconds: float = 0.0

    def compute_totals(self) -> None:
        """Aggregate counts and compute overall score from framework scores."""
        for fs in self.framework_scores:
            if fs.framework == "cis_aws" and self.cis_aws:
                self.total_findings += self.cis_aws.total_findings
                self.critical_findings += self.cis_aws.critical_count
                self.high_findings += self.cis_aws.high_count
                self.medium_findings += self.cis_aws.medium_count
                self.low_findings += self.cis_aws.low_count
            elif fs.framework == "eu_ai_act" and self.eu_ai_act:
                self.total_findings += self.eu_ai_act.total_findings
                self.critical_findings += self.eu_ai_act.critical_count
                self.high_findings += self.eu_ai_act.high_count
                self.medium_findings += self.eu_ai_act.medium_count
                self.low_findings += self.eu_ai_act.low_count
            elif fs.framework == "nist_ai_rmf" and self.nist_ai_rmf:
                self.total_findings += self.nist_ai_rmf.total_findings
                self.critical_findings += self.nist_ai_rmf.critical_count
                self.high_findings += self.nist_ai_rmf.high_count
                self.medium_findings += self.nist_ai_rmf.medium_count
                self.low_findings += self.nist_ai_rmf.low_count
            elif fs.framework == "soc2" and self.soc2:
                self.total_findings += self.soc2.total_findings
                self.critical_findings += self.soc2.critical_count
                self.high_findings += self.soc2.high_count
                self.medium_findings += self.soc2.medium_count
                self.low_findings += self.soc2.low_count
            elif fs.framework == "hipaa" and self.hipaa:
                self.total_findings += self.hipaa.total_findings
                self.critical_findings += self.hipaa.critical_count
                self.high_findings += self.hipaa.high_count
                self.medium_findings += self.hipaa.medium_count
                self.low_findings += self.hipaa.low_count

        if self.framework_scores:
            self.overall_score = sum(
                fs.weighted_score for fs in self.framework_scores
            ) / sum(fs.weight for fs in self.framework_scores)

        if self.overall_score >= 90:
            self.risk_rating = "Compliant"
        elif self.overall_score >= 75:
            self.risk_rating = "Low Risk"
        elif self.overall_score >= 60:
            self.risk_rating = "Medium Risk"
        elif self.overall_score >= 40:
            self.risk_rating = "High Risk"
        else:
            self.risk_rating = "Critical Risk"


class ComplianceScanner:
    """
    Main orchestrator. Runs all enabled framework scanners in parallel (async)
    and returns a unified ComplianceReport.
    """

    def __init__(self, config: ScanConfig) -> None:
        self.config = config

    async def scan(self) -> ComplianceReport:
        """Run all enabled frameworks in parallel. Returns ComplianceReport."""
        import uuid

        start = time.monotonic()
        report = ComplianceReport(
            scan_id=str(uuid.uuid4())[:8].upper(),
            timestamp=datetime.utcnow(),
            config=self.config,
        )

        tasks: dict[str, asyncio.Task] = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            master = progress.add_task(
                "[bold cyan]PolicyGuard — Scanning frameworks...", total=5
            )

            async def run_framework(name: str, coro) -> tuple[str, object]:
                result = await coro
                progress.advance(master)
                return name, result

            active_tasks = []

            if self.config.run_cis_aws:
                scanner = CISAWSScanner(
                    region=self.config.aws_region,
                    profile=self.config.aws_profile,
                    mock=self.config.mock_mode,
                )
                active_tasks.append(
                    run_framework("cis_aws", scanner.scan())
                )

            if self.config.run_eu_ai_act:
                scanner = EUAIActScanner(
                    ai_systems=self.config.ai_systems,
                    mock=self.config.mock_mode,
                )
                active_tasks.append(
                    run_framework("eu_ai_act", scanner.scan())
                )

            if self.config.run_nist_ai_rmf:
                scanner = NISTAIRMFScanner(
                    ai_systems=self.config.ai_systems,
                    mock=self.config.mock_mode,
                )
                active_tasks.append(
                    run_framework("nist_ai_rmf", scanner.scan())
                )

            if self.config.run_soc2:
                scanner = SOC2Scanner(
                    ai_systems=self.config.ai_systems,
                    mock=self.config.mock_mode,
                )
                active_tasks.append(
                    run_framework("soc2", scanner.scan())
                )

            if self.config.run_hipaa:
                scanner = HIPAAScanner(
                    ai_systems=self.config.ai_systems,
                    mock=self.config.mock_mode,
                )
                active_tasks.append(
                    run_framework("hipaa", scanner.scan())
                )

            results = await asyncio.gather(*active_tasks)

        # Attach per-framework reports
        for name, result in results:
            if name == "cis_aws":
                report.cis_aws = result
            elif name == "eu_ai_act":
                report.eu_ai_act = result
            elif name == "nist_ai_rmf":
                report.nist_ai_rmf = result
            elif name == "soc2":
                report.soc2 = result
            elif name == "hipaa":
                report.hipaa = result

        # Build per-framework scores
        for fw_name, weight in FRAMEWORK_WEIGHTS.items():
            fw_report = getattr(report, fw_name, None)
            if fw_report is None:
                continue
            score = fw_report.compliance_score
            fs = FrameworkScore(
                framework=fw_name,
                score=score,
                findings_count=fw_report.total_findings,
                critical_count=fw_report.critical_count,
                high_count=fw_report.high_count,
                weight=weight,
                weighted_score=score * weight,
            )
            report.framework_scores.append(fs)

        report.compute_totals()
        report.scan_duration_seconds = time.monotonic() - start

        return report

    def print_summary(self, report: ComplianceReport) -> None:
        """Print a Rich summary table to stdout."""
        console.print()
        console.rule("[bold cyan]PolicyGuard Compliance Report")
        console.print(
            f"[dim]Scan ID:[/dim] {report.scan_id}  "
            f"[dim]Time:[/dim] {report.timestamp.strftime('%Y-%m-%d %H:%M UTC')}  "
            f"[dim]Duration:[/dim] {report.scan_duration_seconds:.1f}s"
        )
        console.print()

        # Framework scores table
        table = Table(title="Framework Compliance Scores", show_header=True, header_style="bold magenta")
        table.add_column("Framework", style="cyan", no_wrap=True)
        table.add_column("Score", justify="right")
        table.add_column("Findings", justify="right")
        table.add_column("Critical", justify="right", style="red")
        table.add_column("High", justify="right", style="yellow")
        table.add_column("Weight", justify="right", style="dim")

        score_colors = {
            range(0, 50): "red",
            range(50, 70): "yellow",
            range(70, 85): "bright_yellow",
            range(85, 101): "green",
        }

        def score_color(score: float) -> str:
            for r, color in score_colors.items():
                if int(score) in r:
                    return color
            return "white"

        framework_labels = {
            "cis_aws": "CIS AWS Foundations",
            "eu_ai_act": "EU AI Act",
            "nist_ai_rmf": "NIST AI RMF",
            "soc2": "SOC 2 Type II",
            "hipaa": "HIPAA",
        }

        for fs in report.framework_scores:
            color = score_color(fs.score)
            table.add_row(
                framework_labels.get(fs.framework, fs.framework),
                f"[{color}]{fs.score:.0f}%[/{color}]",
                str(fs.findings_count),
                str(fs.critical_count),
                str(fs.high_count),
                f"{fs.weight:.0%}",
            )

        console.print(table)
        console.print()

        # Overall score
        overall_color = score_color(report.overall_score)
        risk_color = {
            "Compliant": "green",
            "Low Risk": "bright_yellow",
            "Medium Risk": "yellow",
            "High Risk": "red",
            "Critical Risk": "bold red",
        }.get(report.risk_rating, "white")

        console.print(
            f"  [bold]Overall Compliance Score:[/bold] "
            f"[{overall_color}]{report.overall_score:.1f}%[/{overall_color}]   "
            f"[bold]Risk Rating:[/bold] [{risk_color}]{report.risk_rating}[/{risk_color}]"
        )
        console.print(
            f"  [bold]Total Findings:[/bold] {report.total_findings}   "
            f"[red]Critical: {report.critical_findings}[/red]   "
            f"[yellow]High: {report.high_findings}[/yellow]   "
            f"Medium: {report.medium_findings}   "
            f"[dim]Low: {report.low_findings}[/dim]"
        )
        console.print()


# Alias for test compatibility
PolicyGuardScanner = ComplianceScanner
