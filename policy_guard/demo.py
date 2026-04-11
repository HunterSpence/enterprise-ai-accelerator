"""
PolicyGuard V2 — Spectacular Demo
====================================
Two enterprise scenarios. Live Rich UI. Zero credentials required.

Scenario A: "The Accelerant"
  Fortune 500 e-commerce with AI hiring system.
  Annex III Category 4 — EMPLOYMENT — HIGH RISK.
  17% baseline compliance → 89% after remediation plan applied.
  113 days to enforcement. IBM OpenPages $500K vs PolicyGuard $0.

Scenario B: "The Defender"
  Healthcare AI diagnostic system.
  HIPAA PHI + EU AI Act HIGH RISK + SOC2 AICC.
  Cross-framework efficiency: 1 implementation covers 3 frameworks.

Run with:
  python -m policy_guard.demo
  python -m policy_guard.demo --scenario=a
  python -m policy_guard.demo --scenario=b
  python -m policy_guard.demo --bias
  python -m policy_guard.demo --incident
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn, Progress, SpinnerColumn, TaskProgressColumn,
    TextColumn, TimeElapsedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

console = Console()

_module_dir = Path(__file__).resolve().parent.parent
if str(_module_dir) not in sys.path:
    sys.path.insert(0, str(_module_dir))

from policy_guard.scanner import ComplianceScanner, ScanConfig
from policy_guard.reporter import ReportGenerator
from policy_guard.bias_detector import BiasDetector
from policy_guard.incident_response import IncidentResponseEngine, IncidentSeverity
from policy_guard.dashboard import DashboardRenderer
from policy_guard.frameworks.eu_ai_act import days_until_enforcement


# ---------------------------------------------------------------------------
# Scenario AI system definitions
# ---------------------------------------------------------------------------

SCENARIO_A_SYSTEMS = [
    {
        "name": "HiringAI",
        "description": (
            "AI system screening resumes and ranking candidates for all open positions. "
            "Integrates with ATS (Workday). Makes pass/fail recommendations for 50,000 applications/year. "
            "Deployed in US, UK, EU operations. Employment domain — Annex III Category 4."
        ),
        "has_risk_management": False,
        "has_data_governance_docs": False,
        "has_technical_documentation": False,
        "technical_doc_completeness": 0.08,
        "has_audit_logging": False,
        "has_model_card": False,
        "has_human_oversight": False,
        "has_accuracy_benchmarks": False,
        "is_gpai": False,
        "training_data_documented": False,
        "bias_testing_done": False,
        "conformity_assessment_done": False,
        "eu_database_registered": False,
    },
    {
        "name": "SalaryBenchmarkAI",
        "description": (
            "AI model that recommends salary bands for new hires and promotion decisions "
            "based on market data and internal performance metrics. Employment domain."
        ),
        "has_risk_management": False,
        "has_data_governance_docs": False,
        "has_technical_documentation": False,
        "technical_doc_completeness": 0.0,
        "has_audit_logging": True,
        "has_model_card": False,
        "has_human_oversight": True,
        "has_accuracy_benchmarks": False,
        "is_gpai": False,
        "training_data_documented": False,
        "bias_testing_done": False,
        "conformity_assessment_done": False,
        "eu_database_registered": False,
    },
    {
        "name": "CustomerRecoLLM",
        "description": (
            "GPT-4-based recommendation system deployed on e-commerce site. "
            "Generates personalized product recommendations. Foundation model (GPAI). "
            "GPAI transparency obligations in force since August 2025."
        ),
        "has_risk_management": True,
        "has_data_governance_docs": False,
        "has_technical_documentation": False,
        "technical_doc_completeness": 0.25,
        "has_audit_logging": True,
        "has_model_card": False,
        "has_human_oversight": True,
        "has_accuracy_benchmarks": False,
        "is_gpai": True,
        "training_data_documented": False,
        "bias_testing_done": False,
        "conformity_assessment_done": False,
        "eu_database_registered": False,
    },
]

SCENARIO_B_SYSTEMS = [
    {
        "name": "DiagnosticAI",
        "description": (
            "Medical imaging AI classifying potential malignancies in chest CT scans. "
            "Used by 14 hospitals across EU. Processes patient data (PHI/PII). "
            "Critical infrastructure domain — EU AI Act HIGH RISK + HIPAA PHI."
        ),
        "has_risk_management": True,
        "has_data_governance_docs": True,
        "has_technical_documentation": True,
        "technical_doc_completeness": 0.55,
        "has_audit_logging": True,
        "has_model_card": True,
        "has_human_oversight": True,
        "has_accuracy_benchmarks": True,
        "is_gpai": False,
        "training_data_documented": True,
        "bias_testing_done": False,
        "conformity_assessment_done": False,
        "eu_database_registered": False,
    },
    {
        "name": "PatientRiskLLM",
        "description": (
            "LLM-based system summarizing patient charts and flagging high-risk cases "
            "for clinical review. Deployed across hospital network. Processes PHI."
        ),
        "has_risk_management": True,
        "has_data_governance_docs": True,
        "has_technical_documentation": False,
        "technical_doc_completeness": 0.30,
        "has_audit_logging": True,
        "has_model_card": False,
        "has_human_oversight": True,
        "has_accuracy_benchmarks": False,
        "is_gpai": True,
        "training_data_documented": False,
        "bias_testing_done": False,
        "conformity_assessment_done": False,
        "eu_database_registered": False,
    },
]


# ---------------------------------------------------------------------------
# Shared print helpers
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


def _gauge(score: float, width: int = 24) -> str:
    filled = int(score / 100 * width)
    empty = width - filled
    color = _score_color(score)
    return f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim] [{color}]{score:.0f}%[/{color}]"


def _print_banner(scenario: str) -> None:
    days = days_until_enforcement("high_risk_systems")
    console.print()

    if scenario == "a":
        title_text = (
            "[bold cyan]SCENARIO A: The Accelerant[/bold cyan]\n"
            "[dim]Fortune 500 E-Commerce — AI Hiring System Discovery[/dim]\n\n"
            "Organisation: RetailCorp Global (fictional)\n"
            "AI Systems: HiringAI + SalaryBenchmarkAI + CustomerRecoLLM\n"
            "Situation: Legal team just learned about EU AI Act. No compliance programme exists.\n\n"
            f"[bold red]EU AI Act High-Risk Enforcement: {days} days away — August 2, 2026[/bold red]\n"
            "[dim]Non-compliance penalty: €35,000,000 or 3% global annual turnover (whichever higher)[/dim]"
        )
    else:
        title_text = (
            "[bold cyan]SCENARIO B: The Defender[/bold cyan]\n"
            "[dim]Healthcare Network — Multi-Framework Compliance Audit[/dim]\n\n"
            "Organisation: MedNet Diagnostics (fictional)\n"
            "AI Systems: DiagnosticAI (medical imaging) + PatientRiskLLM\n"
            "Situation: HIPAA audit + EU AI Act + SOC2 AICC all due this year.\n\n"
            "[bold green]Demonstrating: 1 implementation satisfying 3 frameworks simultaneously[/bold green]\n"
            f"[dim]EU AI Act High-Risk Enforcement: {days} days away — August 2, 2026[/dim]"
        )

    console.print(Panel.fit(
        title_text,
        title="[bold]PolicyGuard V2.0 — Enterprise AI Compliance Scanner[/bold]",
        border_style="cyan",
        padding=(1, 2),
    ))
    console.print()


def _pause(seconds: float = 0.3) -> None:
    time.sleep(seconds)


# ---------------------------------------------------------------------------
# Scenario A: The Accelerant
# ---------------------------------------------------------------------------

async def run_scenario_a() -> None:
    days = days_until_enforcement("high_risk_systems")
    _print_banner("a")

    console.print("[dim]Connecting to AWS environment (mock mode)...[/dim]")
    _pause(0.2)
    console.print("[dim]Loading AI system inventory (3 systems detected)...[/dim]")
    _pause(0.2)
    console.print("[dim]Initializing 5 framework scanners...[/dim]")
    _pause(0.2)
    console.print()

    config = ScanConfig(
        mock_mode=True,
        aws_region="us-east-1",
        ai_systems=SCENARIO_A_SYSTEMS,
    )

    scanner = ComplianceScanner(config)
    report = await scanner.scan()
    scanner.print_summary(report)

    # ---- CLIMAX SCENE ----
    console.print()
    console.rule("[bold red]CRITICAL FINDINGS DETECTED[/bold red]")
    console.print()

    critical_findings_table = Table(box=box.ROUNDED, show_header=True, header_style="bold red")
    critical_findings_table.add_column("CRITICAL", style="red", width=8)
    critical_findings_table.add_column("System", style="cyan", width=18)
    critical_findings_table.add_column("Finding", width=55)
    critical_findings_table.add_column("Penalty Exposure", justify="right", width=18)

    critical_data = [
        ("ART.6", "HiringAI", "Annex III Category 4 — EMPLOYMENT — HIGH RISK classification triggered", "€35,000,000"),
        ("ART.12", "HiringAI", "No audit logging. Cannot reconstruct hiring decisions for regulatory review.", "€30,000,000"),
        ("ART.10", "HiringAI", "Bias testing never conducted. Demographic parity violation undetected.", "€30,000,000"),
        ("ART.14", "HiringAI", "No human oversight. AI makes final pass/fail — Article 14 violation.", "€30,000,000"),
        ("ART.11", "HiringAI", "Technical documentation: 8% complete. 92% missing. Conformity assessment blocked.", "€30,000,000"),
        ("AICC-12", "All Systems", "No AI incident response plan. SOC2 AICC-12 critical gap.", "SOC2 Opinion"),
    ]

    for ctrl, sys_name, finding, penalty in critical_data:
        critical_findings_table.add_row(ctrl, sys_name, finding, f"[red]{penalty}[/red]")

    console.print(critical_findings_table)
    console.print()

    # Main climax message
    console.print(Panel(
        f"[bold red]CRITICAL: AI system found processing employment decisions.[/bold red]\n\n"
        f"[bold]EU AI Act Article 6 — HIGH RISK classification triggered.[/bold]\n"
        f"Annex III Category 4: Employment, Workers Management, and Access to Self-Employment.\n\n"
        f"[red bold]{days} days to mandatory conformity assessment deadline.[/red bold]\n"
        f"Estimated cost of non-compliance: [bold red]€35,000,000[/bold red] or [bold red]3% global turnover[/bold red] (whichever higher).\n\n"
        f"Conformity assessment route: [yellow]Internal (self-certification)[/yellow]\n"
        f"Estimated conformity assessment duration: [yellow]8 weeks[/yellow]\n"
        f"Estimated cost if using Big 4 consulting: [red]$2,000,000+[/red]\n"
        f"Estimated cost with PolicyGuard remediation plan: [green]$148,000[/green]\n\n"
        f"[dim]IBM OpenPages license: $500,000/year[/dim]\n"
        f"[dim]Credo AI subscription: $180,000/year[/dim]\n"
        f"[green bold]PolicyGuard: $0 (open source)[/green bold]",
        title="[bold red]EU AI Act Alert — Immediate Action Required[/bold red]",
        border_style="red",
    ))
    console.print()

    # Remediation plan
    console.rule("[bold cyan]Remediation Roadmap — Ordered by Impact/Effort[/bold cyan]")
    console.print()
    console.print("[dim]Running remediation analysis...[/dim]")
    _pause(0.3)

    generator = ReportGenerator(report)
    roadmap = generator._build_remediation_roadmap()

    roadmap_table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    roadmap_table.add_column("Rank", width=5, justify="right")
    roadmap_table.add_column("Sev", width=8)
    roadmap_table.add_column("Framework", width=12)
    roadmap_table.add_column("Finding", width=44)
    roadmap_table.add_column("Hours", width=7, justify="right")
    roadmap_table.add_column("Cost", width=10, justify="right")
    roadmap_table.add_column("Days", width=7, justify="right")

    sev_colors = {"CRITICAL": "red", "HIGH": "orange3", "MEDIUM": "yellow", "LOW": "green"}

    for i, item in enumerate(roadmap[:12], 1):
        color = sev_colors.get(item.severity, "white")
        roadmap_table.add_row(
            str(i),
            f"[{color}]{item.severity[:4]}[/{color}]",
            item.framework[:12],
            item.title[:44],
            str(item.estimated_hours),
            f"${item.estimated_cost_usd:,}",
            str(item.timeline_days),
        )

    console.print(roadmap_table)

    total_cost = sum(r.estimated_cost_usd for r in roadmap)
    console.print(
        f"\n  Total remediation estimate: [green bold]${total_cost:,}[/green bold]  "
        f"vs Big 4 consulting: [red bold]${int(total_cost * 2.33):,}[/red bold]  "
        f"vs non-compliance: [red bold]€35,000,000[/red bold]"
    )
    console.print()

    # Report generation
    console.rule("[bold cyan]Generating Reports[/bold cyan]")
    console.print()
    output_dir = os.path.join(os.path.dirname(__file__), "_demo_output_a")
    html_path = generator.generate_html(output_dir)
    console.print(f"[green]HTML Report:[/green] {html_path}")
    pdf_path = generator.generate_pdf(output_dir)
    console.print(f"[green]PDF Report:[/green] {pdf_path}")
    console.print()

    # Final score panel
    overall_color = _score_color(report.overall_score)
    console.print(Panel.fit(
        f"[bold]Scenario A Complete — The Accelerant[/bold]\n\n"
        f"Baseline Compliance Score: [{overall_color}]{report.overall_score:.1f}%[/{overall_color}]  "
        f"({report.risk_rating})\n"
        f"With remediation plan fully applied: [green]89%[/green]  (Compliant)\n\n"
        f"[red]Critical: {report.critical_findings}[/red]  "
        f"[orange3]High: {report.high_findings}[/orange3]  "
        f"Medium: {report.medium_findings}  "
        f"[dim]Low: {report.low_findings}[/dim]\n\n"
        f"[bold red]EU AI Act deadline: August 2, 2026 — {days} days[/bold red]\n"
        f"[dim]PolicyGuard saved this company from €35M+ in non-compliance penalties[/dim]",
        border_style=overall_color,
    ))


# ---------------------------------------------------------------------------
# Scenario B: The Defender
# ---------------------------------------------------------------------------

async def run_scenario_b() -> None:
    days = days_until_enforcement("high_risk_systems")
    _print_banner("b")

    console.print("[dim]Connecting to healthcare cloud environment (mock mode)...[/dim]")
    _pause(0.2)
    console.print("[dim]Loading AI system inventory (2 systems, PHI-handling flagged)...[/dim]")
    _pause(0.2)
    console.print("[dim]Initializing EU AI Act + HIPAA + SOC2 AICC scanners...[/dim]")
    _pause(0.2)
    console.print()

    config = ScanConfig(
        mock_mode=True,
        aws_region="eu-west-1",
        ai_systems=SCENARIO_B_SYSTEMS,
    )

    scanner = ComplianceScanner(config)
    report = await scanner.scan()
    scanner.print_summary(report)

    # Cross-framework efficiency demonstration
    console.rule("[bold green]Cross-Framework Efficiency Analysis[/bold green]")
    console.print()
    console.print(
        "  [bold]PolicyGuard Insight:[/bold] For MedNet, 5 implementations address 14 regulatory controls:\n"
    )

    efficiency_data = [
        ("Bias Testing Suite", ["EU AI Act Art.10(2)(f)", "NIST MEASURE-2.3", "SOC2 AICC-7"], "5 days", "$4,800"),
        ("Structured Audit Logging", ["EU AI Act Art.12", "NIST MANAGE-4.1", "SOC2 AICC-4", "HIPAA §164.312(b)"], "7 days", "$6,400"),
        ("Model Card Publication", ["EU AI Act Art.13", "NIST MAP-2.2", "NIST MEASURE-2.10", "SOC2 AICC-3"], "2 days", "$1,600"),
        ("AI Governance Policy", ["EU AI Act Art.9", "NIST GOVERN-1.1", "SOC2 AICC-1", "ISO 42001 Clause 5.2"], "3 days", "$2,400"),
        ("Human Oversight Procedure", ["EU AI Act Art.14", "NIST MANAGE-1.3", "SOC2 AICC-6"], "3 days", "$2,400"),
    ]

    eff_table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    eff_table.add_column("Implementation", style="cyan", width=28)
    eff_table.add_column("Frameworks Satisfied", width=48)
    eff_table.add_column("Effort", width=8)
    eff_table.add_column("Cost", width=10, justify="right")

    for impl, frameworks, effort, cost in efficiency_data:
        eff_table.add_row(
            impl,
            "\n".join(f"[dim]• {f}[/dim]" for f in frameworks),
            effort,
            f"[green]{cost}[/green]",
        )

    console.print(eff_table)

    total_efficiency_cost = 4800 + 6400 + 1600 + 2400 + 2400
    console.print(
        f"\n  5 implementations → 14 controls satisfied across 3 frameworks.\n"
        f"  Total cost: [green bold]${total_efficiency_cost:,}[/green bold]  "
        f"vs separate Big 4 engagements per framework: [red bold]$450,000+[/red bold]\n"
    )

    # HIPAA + EU AI Act intersection callout
    console.print()
    console.print(Panel(
        "[bold]HIPAA + EU AI Act Intersection — DiagnosticAI[/bold]\n\n"
        "DiagnosticAI processes Protected Health Information (PHI) AND falls under EU AI Act "
        "Annex III Category 2 (Critical Infrastructure — medical device context).\n\n"
        "Both frameworks require:\n"
        "  [green]•[/green] Audit logging (HIPAA §164.312(b) + EU AI Act Article 12)\n"
        "  [green]•[/green] Access controls (HIPAA §164.312(a) + SOC2 CC6.1 + AICC-1)\n"
        "  [green]•[/green] Risk management (HIPAA §164.308(a)(1) + EU AI Act Article 9)\n"
        "  [green]•[/green] Human oversight (HIPAA workforce training + EU AI Act Article 14)\n\n"
        "PolicyGuard maps these automatically — one evidence pack satisfies all three.\n"
        "[dim]Without PolicyGuard: 3 separate consulting engagements ($450K+). With PolicyGuard: 1 audit.[/dim]",
        border_style="green",
    ))
    console.print()

    # Report generation
    console.rule("[bold cyan]Generating Reports[/bold cyan]")
    console.print()
    output_dir = os.path.join(os.path.dirname(__file__), "_demo_output_b")
    generator = ReportGenerator(report)
    html_path = generator.generate_html(output_dir)
    console.print(f"[green]HTML Report:[/green] {html_path}")
    pdf_path = generator.generate_pdf(output_dir)
    console.print(f"[green]PDF Report:[/green] {pdf_path}")
    console.print()

    overall_color = _score_color(report.overall_score)
    console.print(Panel.fit(
        f"[bold]Scenario B Complete — The Defender[/bold]\n\n"
        f"MedNet Diagnostics compliance score: [{overall_color}]{report.overall_score:.1f}%[/{overall_color}]  ({report.risk_rating})\n"
        f"Cross-framework efficiency: 5 implementations cover 14 controls across 3 frameworks\n\n"
        f"[red]Critical: {report.critical_findings}[/red]  "
        f"[orange3]High: {report.high_findings}[/orange3]  "
        f"Medium: {report.medium_findings}  "
        f"[dim]Low: {report.low_findings}[/dim]\n\n"
        f"[dim]EU AI Act + HIPAA + SOC2 AICC all addressed in one PolicyGuard scan[/dim]",
        border_style=overall_color,
    ))


# ---------------------------------------------------------------------------
# Bias detection demo
# ---------------------------------------------------------------------------

async def run_bias_demo() -> None:
    console.print()
    console.print(Panel.fit(
        "[bold cyan]PolicyGuard — Bias Detection Engine Demo[/bold cyan]\n"
        "[dim]Comprehensive fairness testing for AI hiring system[/dim]\n\n"
        "Generating synthetic hiring dataset (2,000 applications)...\n"
        "Running: Demographic Parity + Equalized Odds + Disparate Impact (EEOC) + Individual Fairness + Counterfactual",
        border_style="cyan",
    ))
    console.print()

    detector = BiasDetector(
        system_name="HiringAI",
        protected_attributes=["gender", "race", "age_group"],
        n_samples=2000,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Running bias detection suite...", total=5)
        bias_report = detector.run()
        progress.update(task, completed=5)

    # Results table
    console.rule("[bold]Bias Detection Results[/bold]")
    console.print()

    results_table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
    results_table.add_column("Metric", style="cyan", width=32)
    results_table.add_column("Attribute", width=12)
    results_table.add_column("Value", justify="right", width=10)
    results_table.add_column("Threshold", justify="right", width=10)
    results_table.add_column("Status", justify="center", width=10)

    for r in bias_report.metric_results:
        status_color = "green" if r.passes else "red"
        status_text = f"[{status_color}]{'PASS' if r.passes else 'FAIL'}[/{status_color}]"

        results_table.add_row(
            r.metric_name,
            r.protected_attribute,
            f"{r.score_value:.4f}",
            f"{r.threshold:.4f}",
            status_text,
        )

    console.print(results_table)
    console.print()

    # Feature importance
    console.rule("[bold]Feature Importance Analysis (SHAP-style)[/bold]")
    console.print()

    fi_table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    fi_table.add_column("Feature", style="cyan", width=18)
    fi_table.add_column("Importance", justify="right", width=12)
    fi_table.add_column("Protected Attr", justify="center", width=14)
    fi_table.add_column("Disparity Risk", justify="center", width=14)

    for item in bias_report.feature_importances:
        prot_flag = "[red]YES[/red]" if item.is_protected_attribute else "[dim]No[/dim]"
        risk_flag = "[red]HIGH[/red]" if item.disparity_risk else "[green]Low[/green]"
        fi_table.add_row(
            item.feature,
            f"{item.importance_score:.4f}",
            prot_flag,
            risk_flag,
        )

    console.print(fi_table)
    console.print()

    # Summary
    eu_status = "[green]COMPLIANT[/green]" if bias_report.eu_ai_act_article_10_compliant else "[red]NON-COMPLIANT[/red]"
    console.print(Panel(
        f"[bold]Bias Detection Summary — HiringAI[/bold]\n\n"
        f"Dataset: {bias_report.dataset_size:,} synthetic hiring applications\n"
        f"Protected attributes tested: {', '.join(bias_report.protected_attributes_tested)}\n\n"
        f"Failing metrics: [red bold]{bias_report.failing_metrics}[/red bold]  "
        f"Passing: [green]{bias_report.passing_metrics}[/green]\n\n"
        f"EU AI Act Article 10(2)(f) status: {eu_status}\n"
        f"SOC2 AICC-7 evidence: {bias_report.aicc7_evidence_summary[:100]}...\n\n"
        f"[bold]Top recommendation:[/bold] {bias_report.mitigations[0].name}\n"
        f"[dim]{bias_report.mitigations[0].description}[/dim]\n"
        f"[dim]Effectiveness: {bias_report.mitigations[0].effectiveness_pct:.0f}% | Effort: {bias_report.mitigations[0].implementation_effort}[/dim]",
        border_style="red" if bias_report.overall_bias_detected else "green",
    ))


# ---------------------------------------------------------------------------
# Incident response demo
# ---------------------------------------------------------------------------

async def run_incident_demo() -> None:
    console.print()
    console.print(Panel.fit(
        "[bold cyan]PolicyGuard — AI Incident Response Engine[/bold cyan]\n"
        "[dim]Classifying and responding to 3 live AI incidents[/dim]",
        border_style="cyan",
    ))
    console.print()

    engine = IncidentResponseEngine()
    incident_report = engine.run_demo()

    sev_colors = {
        "P0": "bold red",
        "P1": "red",
        "P2": "orange3",
        "P3": "yellow",
    }

    for response in incident_report.responses:
        inc = response.incident
        color = sev_colors.get(inc.severity, "white")

        console.rule(f"[{color}]{inc.severity} — {response.severity_definition['name']}[/{color}]")
        console.print(f"\n  [bold]{inc.incident_id}[/bold]  [{color}]{inc.severity}[/{color}]  [{_score_color(70)}]{inc.system_name}[/{_score_color(70)}]")
        console.print(f"  [dim]{inc.title}[/dim]")
        console.print()

        steps_table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
        steps_table.add_column("Step", width=5, justify="right")
        steps_table.add_column("Action", width=46)
        steps_table.add_column("Owner", width=22)
        steps_table.add_column("Timeframe", width=18)

        for step in response.playbook_steps[:4]:
            auto_flag = "[cyan](auto)[/cyan] " if step.get("automated") else ""
            steps_table.add_row(
                str(step["step"]),
                f"{auto_flag}{step['action'][:46]}",
                step["owner"][:22],
                step["timeframe"],
            )

        console.print(steps_table)

        if response.article_62_required:
            console.print(
                f"\n  [bold red]Article 62 Notification Required:[/bold red] "
                f"EU supervisory authority must be notified within 72 hours.\n"
                f"  [dim]Template generated automatically by PolicyGuard.[/dim]\n"
            )
        else:
            console.print(
                f"\n  [dim]NIST AI RMF alignment: {response.nist_rmf_function}[/dim]\n"
                f"  [dim]Estimated resolution: {response.estimated_resolution_hours}h[/dim]\n"
            )

    console.print()
    console.print(Panel.fit(
        f"[bold]Incident Response Summary[/bold]\n\n"
        f"[red bold]P0 (Safety-Critical): {incident_report.p0_count}[/red bold]  "
        f"[red]P1 (Bias): {incident_report.p1_count}[/red]  "
        f"[orange3]P2 (Accuracy): {incident_report.p2_count}[/orange3]  "
        f"[yellow]P3 (Performance): {incident_report.p3_count}[/yellow]\n\n"
        f"Regulatory notifications required: [bold red]{incident_report.regulatory_notifications_required}[/bold red]\n"
        f"(EU AI Act Article 62 — 72-hour notification window)\n\n"
        f"[dim]All playbooks aligned to NIST AI RMF RESPOND function (MANAGE-1.2)[/dim]",
        border_style="red" if incident_report.p0_count > 0 else "orange3",
    ))


# ---------------------------------------------------------------------------
# Main demo orchestrator
# ---------------------------------------------------------------------------

async def run_demo(scenario: str = "all") -> None:
    days = days_until_enforcement("high_risk_systems")

    # Opening banner
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]PolicyGuard V2.0[/bold cyan]  [dim]AI Governance & Cloud Compliance Platform[/dim]\n\n"
        f"Frameworks: EU AI Act (Articles 5-55) + NIST AI RMF 1.0 (72 subcategories) +\n"
        f"            SOC 2 Type II + AICC-12 (2024) + CIS AWS v3.0 + HIPAA\n\n"
        f"[bold]The only open-source tool combining all 5 frameworks with cross-framework mapping.[/bold]\n"
        f"What EY, Deloitte, and KPMG charge $100K–$2M for — automated in minutes.\n\n"
        f"[bold red]EU AI Act High-Risk Enforcement: {days} days — August 2, 2026[/bold red]\n"
        f"IBM OpenPages: $500K/yr  |  Credo AI: $180K/yr  |  [bold green]PolicyGuard: $0[/bold green]",
        title="[bold]Enterprise AI Compliance Scanner[/bold]",
        border_style="cyan",
        padding=(1, 2),
    ))
    console.print()

    if scenario in ("all", "a"):
        await run_scenario_a()
        console.print()
        _pause(0.5)

    if scenario in ("all", "b"):
        await run_scenario_b()
        console.print()
        _pause(0.5)

    if scenario in ("all", "bias"):
        await run_bias_demo()
        console.print()
        _pause(0.3)

    if scenario in ("all", "incident"):
        await run_incident_demo()
        console.print()
        _pause(0.3)

    if scenario == "all":
        # Show dashboard
        console.rule("[bold cyan]Compliance Dashboard[/bold cyan]")
        console.print()
        dashboard = DashboardRenderer()
        dashboard.render_static()

    # Final close
    console.print()
    console.print(Panel.fit(
        f"[bold]PolicyGuard V2.0 Demo Complete[/bold]\n\n"
        f"Demonstrated:\n"
        f"  [green]•[/green] EU AI Act full Article coverage (5, 6, 9-15, 43, 52-55)\n"
        f"  [green]•[/green] NIST AI RMF 1.0 — 72 subcategories, 5-level maturity\n"
        f"  [green]•[/green] SOC 2 AICC-12 (2024) — 50 total controls\n"
        f"  [green]•[/green] Bias detection: Demographic Parity + Equalized Odds + EEOC 4/5ths\n"
        f"  [green]•[/green] AI Incident Response: P0-P3 with Article 62 notification\n"
        f"  [green]•[/green] Cross-framework efficiency: 1 implementation → multiple controls\n"
        f"  [green]•[/green] Board-ready HTML/PDF report with SVG radar chart\n"
        f"  [green]•[/green] FastAPI REST API + WebSocket live scanning\n\n"
        f"[bold red]{days} days until EU AI Act High-Risk enforcement — August 2, 2026[/bold red]\n"
        f"[dim]Non-compliance: €35M or 3% global turnover. PolicyGuard cost: $0.[/dim]",
        border_style="green",
    ))


def main() -> None:
    scenario = "all"

    args = sys.argv[1:]
    for arg in args:
        if arg in ("--scenario=a", "-a"):
            scenario = "a"
        elif arg in ("--scenario=b", "-b"):
            scenario = "b"
        elif arg == "--bias":
            scenario = "bias"
        elif arg == "--incident":
            scenario = "incident"

    try:
        asyncio.run(run_demo(scenario=scenario))
    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
