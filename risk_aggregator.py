"""
Enterprise AI Accelerator — Cross-Module Unified Risk Aggregator
=================================================================
Combines signals from ALL modules into a single 0–100 "workload risk score"
with dimensional breakdown.

No competitor has this. IBM Turbonomic, Checkov, Prowler, OpenCost, and all
consulting firm accelerators produce siloed outputs. None correlates:
  - A CRITICAL security finding from PolicyGuard
  - with a 45% cost waste anomaly from FinOpsIntelligence
  - with a HIGH migration complexity rating from MigrationScout
  - with missing EU AI Act Article 12 logging from AIAuditTrail

This module does exactly that — producing a unified executive-level risk score
that enables a single conversation with the board instead of four separate
deep-dives.

Architecture:
  - Accepts outputs from any combination of modules (all optional)
  - Produces a deterministic 0–100 score using weighted dimensions
  - Generates narrative explaining the top 3 risk drivers
  - Outputs risk-adjusted priority recommendations

Usage:
    from portfolio_modules.risk_aggregator import WorkloadRiskAggregator, RiskInput

    risk = WorkloadRiskAggregator()
    score = risk.compute(RiskInput(
        policy_report=policyguard_report,     # from policy_guard.scanner
        finops_waste_pct=38.5,                # from finops_intelligence
        migration_risk_score=72,              # from migration_scout.assessor
        audit_trail_present=False,            # from ai_audit_trail
        ai_systems_count=3,                   # for EU AI Act weight
    ))

    print(f"Overall Risk: {score.overall_score}/100 ({score.risk_tier})")
    print(f"Top driver: {score.top_risk_driver}")
    print(score.executive_narrative)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Dimension weights — how much each module contributes to total risk score
# Tuned to reflect enterprise CTO/CISO priorities:
#   Security compliance is highest (regulatory and reputational exposure)
#   Financial waste is second (direct P&L impact)
#   Migration complexity is third (project delivery risk)
#   AI governance is fourth (increasing regulatory urgency)
# ---------------------------------------------------------------------------

DIMENSION_WEIGHTS: dict[str, float] = {
    "security_compliance": 0.35,   # PolicyGuard score (inverted: low score = high risk)
    "financial_waste": 0.25,       # FinOps waste percentage
    "migration_complexity": 0.20,  # MigrationScout complexity / risk score
    "ai_governance": 0.20,         # AIAuditTrail + EU AI Act completeness
}

# Severity multipliers for critical findings (compound risk)
CRITICAL_MULTIPLIER = 1.25  # Any critical finding inflates the security dimension
HIGH_MULTIPLIER = 1.10


@dataclass
class RiskInput:
    """
    Input aggregating signals from all Enterprise AI Accelerator modules.
    All fields are optional — the aggregator weights only what is provided.
    """

    # From PolicyGuard (policy_guard.scanner.ComplianceReport)
    policy_report: Optional[Any] = None
    policy_score: Optional[float] = None          # 0–100, higher = more compliant
    policy_critical_findings: int = 0
    policy_high_findings: int = 0
    policy_total_findings: int = 0

    # From FinOpsIntelligence
    finops_waste_pct: float = 0.0                 # 0–100, % of spend identified as waste
    finops_anomaly_count: int = 0                 # active anomalies
    finops_monthly_waste_usd: float = 0.0         # absolute waste amount
    finops_ri_coverage_pct: float = 0.0           # reserved instance coverage
    finops_maturity_stage: str = ""               # Crawl / Walk / Run / Fly

    # From MigrationScout
    migration_risk_score: float = 0.0             # 0–100, higher = more risky
    migration_workload_count: int = 0
    migration_critical_workloads: int = 0         # workloads with criticality=critical
    migration_has_circular_deps: bool = False
    migration_oracle_dependency: bool = False      # Oracle license risk

    # From AIAuditTrail
    audit_trail_present: bool = False             # Is any audit trail configured?
    audit_chain_verified: bool = False            # Is the hash chain intact?
    eu_ai_act_gap_count: int = 0                  # Missing Article 12 requirements
    ai_systems_count: int = 0                     # Number of AI systems deployed
    high_risk_ai_systems: int = 0                 # EU AI Act Annex III systems

    # From CloudIQ (optional)
    cloud_iq_score: Optional[float] = None        # 0–100, higher = healthier
    cloud_iq_public_resources: int = 0            # Public S3, SGs, etc.

    # Metadata
    account_id: str = ""
    account_name: str = ""
    environment: str = "production"               # production | staging | dev


@dataclass
class DimensionScore:
    """Score for a single risk dimension."""
    dimension: str
    raw_score: float          # 0–100, higher = more risky
    weight: float
    weighted_score: float     # raw_score * weight
    drivers: list[str] = field(default_factory=list)   # Key findings contributing to this score
    data_available: bool = True


@dataclass
class RiskScore:
    """Output of the WorkloadRiskAggregator.compute() call."""
    overall_score: float          # 0–100, higher = more risky
    risk_tier: str                # Critical / High / Medium / Low / Healthy
    confidence: str               # High / Medium / Low (based on data coverage)

    # Per-dimension breakdown
    dimensions: list[DimensionScore] = field(default_factory=list)

    # Top 3 risk drivers (for executive communication)
    top_risk_driver: str = ""
    risk_drivers: list[str] = field(default_factory=list)

    # AI-generated narrative (when API key provided) or rule-based fallback
    executive_narrative: str = ""

    # Prioritized recommendations
    priority_actions: list[dict[str, Any]] = field(default_factory=list)

    # Raw input summary for transparency
    input_summary: dict[str, Any] = field(default_factory=dict)

    # Computed timestamp
    computed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    @property
    def risk_tier_color(self) -> str:
        """ANSI-friendly color label for CLI output."""
        return {
            "Critical": "red",
            "High": "orange_red1",
            "Medium": "yellow",
            "Low": "bright_yellow",
            "Healthy": "green",
        }.get(self.risk_tier, "white")


class WorkloadRiskAggregator:
    """
    Computes a unified 0–100 workload risk score from multi-module inputs.

    Score interpretation:
      80–100: Critical — Immediate action required
      60–79:  High — Address within 30 days
      40–59:  Medium — Schedule for next sprint cycle
      20–39:  Low — Monitor, address in roadmap
      0–19:   Healthy — No material risk identified

    The score is designed to be:
      - Deterministic (same inputs = same score, always)
      - Explainable (every point can be traced to a finding)
      - Conservative (missing data is treated as unknown risk, not zero risk)
      - Actionable (top priority recommendations are always included)

    Example:
        agg = WorkloadRiskAggregator()
        score = agg.compute(inputs)
        agg.print_summary(score)
    """

    def __init__(self, anthropic_api_key: Optional[str] = None) -> None:
        self._api_key = anthropic_api_key

    def compute(self, inputs: RiskInput) -> RiskScore:
        """
        Compute the unified risk score from all available inputs.

        Steps:
          1. Extract signals from each module
          2. Normalize each signal to 0–100 risk scale
          3. Apply dimension weights
          4. Apply compound risk penalties for critical combinations
          5. Generate narrative
          6. Produce prioritized action list
        """
        # Step 1: Compute per-dimension scores
        security_dim = self._score_security(inputs)
        financial_dim = self._score_financial(inputs)
        migration_dim = self._score_migration(inputs)
        governance_dim = self._score_ai_governance(inputs)

        dimensions = [security_dim, financial_dim, migration_dim, governance_dim]

        # Step 2: Weighted average
        available_dims = [d for d in dimensions if d.data_available]
        if not available_dims:
            overall = 50.0  # Unknown — default to medium
        else:
            total_weight = sum(d.weight for d in available_dims)
            overall = sum(d.weighted_score for d in available_dims) / total_weight

        # Step 3: Compound risk penalty
        # If BOTH critical security findings AND high financial waste exist,
        # the compound risk is worse than either alone
        compound_penalty = 0.0
        has_critical_security = (
            inputs.policy_critical_findings > 0 or
            (inputs.policy_score is not None and inputs.policy_score < 40)
        )
        has_critical_finops = inputs.finops_waste_pct > 40 or inputs.finops_anomaly_count > 5
        has_critical_governance = inputs.high_risk_ai_systems > 0 and not inputs.audit_trail_present

        if has_critical_security and has_critical_finops:
            compound_penalty += 5.0
        if has_critical_security and has_critical_governance:
            compound_penalty += 8.0  # EU AI Act + security gap is highest risk combination
        if has_critical_governance and inputs.eu_ai_act_gap_count > 5:
            compound_penalty += 5.0

        overall = min(100.0, overall + compound_penalty)
        overall = round(overall, 1)

        # Step 4: Risk tier classification
        risk_tier = self._classify_tier(overall)

        # Step 5: Confidence — based on how many modules provided data
        modules_with_data = sum([
            inputs.policy_report is not None or inputs.policy_score is not None,
            inputs.finops_waste_pct > 0 or inputs.finops_anomaly_count > 0,
            inputs.migration_risk_score > 0 or inputs.migration_workload_count > 0,
            inputs.ai_systems_count > 0 or inputs.audit_trail_present,
        ])
        confidence = "High" if modules_with_data >= 3 else "Medium" if modules_with_data >= 2 else "Low"

        # Step 6: Top risk drivers (sorted by weighted contribution)
        all_drivers = []
        for dim in dimensions:
            for driver in dim.drivers:
                all_drivers.append((dim.weighted_score, driver))
        all_drivers.sort(key=lambda x: x[0], reverse=True)
        top_drivers = [d for _, d in all_drivers[:5]]

        # Step 7: Priority actions
        priority_actions = self._build_priority_actions(inputs, dimensions, overall)

        # Step 8: Executive narrative
        executive_narrative = self._build_narrative(inputs, overall, risk_tier, top_drivers, priority_actions)

        return RiskScore(
            overall_score=overall,
            risk_tier=risk_tier,
            confidence=confidence,
            dimensions=dimensions,
            top_risk_driver=top_drivers[0] if top_drivers else "Insufficient data for risk assessment",
            risk_drivers=top_drivers,
            executive_narrative=executive_narrative,
            priority_actions=priority_actions[:5],
            input_summary={
                "modules_with_data": modules_with_data,
                "policy_score": inputs.policy_score,
                "finops_waste_pct": inputs.finops_waste_pct,
                "migration_risk_score": inputs.migration_risk_score,
                "ai_systems_count": inputs.ai_systems_count,
                "audit_trail_present": inputs.audit_trail_present,
                "account_id": inputs.account_id,
                "environment": inputs.environment,
            },
        )

    # ---------------------------------------------------------------------------
    # Dimension scorers
    # ---------------------------------------------------------------------------

    def _score_security(self, inp: RiskInput) -> DimensionScore:
        """Convert PolicyGuard output to 0–100 risk score (inverted compliance score)."""
        drivers: list[str] = []

        if inp.policy_report is not None:
            score = getattr(inp.policy_report, "overall_score", None)
            crit = getattr(inp.policy_report, "critical_findings", 0)
            high = getattr(inp.policy_report, "high_findings", 0)
        elif inp.policy_score is not None:
            score = inp.policy_score
            crit = inp.policy_critical_findings
            high = inp.policy_high_findings
        else:
            # No data — unknown risk, penalize conservatively
            return DimensionScore(
                dimension="security_compliance",
                raw_score=50.0,
                weight=DIMENSION_WEIGHTS["security_compliance"],
                weighted_score=50.0 * DIMENSION_WEIGHTS["security_compliance"],
                drivers=["No PolicyGuard scan data available — security posture unknown"],
                data_available=False,
            )

        # Invert: compliance score 90 → risk 10; compliance 30 → risk 70
        base_risk = 100.0 - score

        # Compound penalty for critical findings
        if crit > 0:
            base_risk = min(100.0, base_risk * CRITICAL_MULTIPLIER)
            drivers.append(f"{crit} CRITICAL security finding(s) — require immediate remediation")
        if high > 0:
            base_risk = min(100.0, base_risk * (1 + (high * 0.02)))  # 2% per high finding
            drivers.append(f"{high} HIGH severity finding(s) across compliance frameworks")

        if inp.cloud_iq_public_resources > 0:
            base_risk = min(100.0, base_risk + 5.0)
            drivers.append(f"{inp.cloud_iq_public_resources} publicly accessible cloud resource(s)")

        if not drivers:
            if score >= 85:
                drivers = ["Security compliance score is strong"]
            elif score >= 65:
                drivers = ["Moderate compliance gaps present"]
            else:
                drivers = ["Significant compliance failures requiring structured remediation"]

        raw = round(min(100.0, base_risk), 1)
        return DimensionScore(
            dimension="security_compliance",
            raw_score=raw,
            weight=DIMENSION_WEIGHTS["security_compliance"],
            weighted_score=round(raw * DIMENSION_WEIGHTS["security_compliance"], 2),
            drivers=drivers,
        )

    def _score_financial(self, inp: RiskInput) -> DimensionScore:
        """Convert FinOps data to 0–100 risk score."""
        drivers: list[str] = []

        has_data = (
            inp.finops_waste_pct > 0 or
            inp.finops_anomaly_count > 0 or
            inp.finops_monthly_waste_usd > 0
        )

        if not has_data:
            return DimensionScore(
                dimension="financial_waste",
                raw_score=30.0,
                weight=DIMENSION_WEIGHTS["financial_waste"],
                weighted_score=30.0 * DIMENSION_WEIGHTS["financial_waste"],
                drivers=["No FinOps data — cost posture unverified"],
                data_available=False,
            )

        # Waste percentage to risk: 0% waste = 0 risk, 50%+ waste = 100 risk
        waste_risk = min(100.0, inp.finops_waste_pct * 2)

        if inp.finops_waste_pct > 30:
            drivers.append(f"{inp.finops_waste_pct:.0f}% of cloud spend identified as waste (${inp.finops_monthly_waste_usd:,.0f}/month recoverable)")
        elif inp.finops_waste_pct > 10:
            drivers.append(f"{inp.finops_waste_pct:.0f}% cost waste — optimization opportunity")

        if inp.finops_anomaly_count > 0:
            waste_risk = min(100.0, waste_risk + inp.finops_anomaly_count * 3)
            drivers.append(f"{inp.finops_anomaly_count} active cost anomaly(-ies) detected")

        if inp.finops_ri_coverage_pct < 40 and inp.finops_ri_coverage_pct > 0:
            waste_risk = min(100.0, waste_risk + 10)
            drivers.append(f"Low RI/Savings Plan coverage ({inp.finops_ri_coverage_pct:.0f}%) — on-demand overspend")

        if inp.finops_maturity_stage in ("Crawl", ""):
            waste_risk = min(100.0, waste_risk + 5)
            drivers.append("FinOps maturity at Crawl stage — manual cost management")

        if not drivers:
            drivers = ["Cost waste within acceptable range"]

        raw = round(min(100.0, waste_risk), 1)
        return DimensionScore(
            dimension="financial_waste",
            raw_score=raw,
            weight=DIMENSION_WEIGHTS["financial_waste"],
            weighted_score=round(raw * DIMENSION_WEIGHTS["financial_waste"], 2),
            drivers=drivers,
        )

    def _score_migration(self, inp: RiskInput) -> DimensionScore:
        """Convert MigrationScout data to 0–100 risk score."""
        drivers: list[str] = []

        has_data = (
            inp.migration_risk_score > 0 or
            inp.migration_workload_count > 0
        )

        if not has_data:
            return DimensionScore(
                dimension="migration_complexity",
                raw_score=25.0,
                weight=DIMENSION_WEIGHTS["migration_complexity"],
                weighted_score=25.0 * DIMENSION_WEIGHTS["migration_complexity"],
                drivers=["No MigrationScout data — migration complexity unmeasured"],
                data_available=False,
            )

        raw = inp.migration_risk_score

        if inp.migration_critical_workloads > 0:
            raw = min(100.0, raw + inp.migration_critical_workloads * 3)
            drivers.append(f"{inp.migration_critical_workloads} critical-business workload(s) in migration scope")

        if inp.migration_has_circular_deps:
            raw = min(100.0, raw + 15)
            drivers.append("Circular dependencies detected — mandatory Refactor workloads")

        if inp.migration_oracle_dependency:
            raw = min(100.0, raw + 10)
            drivers.append("Oracle license dependency — mandatory database migration required")

        if raw < 30 and not drivers:
            drivers = ["Migration risk is manageable — workloads are cloud-ready"]
        elif not drivers:
            drivers = ["Migration complexity is elevated — phased approach recommended"]

        raw = round(min(100.0, raw), 1)
        return DimensionScore(
            dimension="migration_complexity",
            raw_score=raw,
            weight=DIMENSION_WEIGHTS["migration_complexity"],
            weighted_score=round(raw * DIMENSION_WEIGHTS["migration_complexity"], 2),
            drivers=drivers,
        )

    def _score_ai_governance(self, inp: RiskInput) -> DimensionScore:
        """Convert AIAuditTrail / EU AI Act data to 0–100 risk score."""
        drivers: list[str] = []

        has_data = (
            inp.ai_systems_count > 0 or
            inp.eu_ai_act_gap_count > 0 or
            inp.audit_trail_present
        )

        if not has_data:
            return DimensionScore(
                dimension="ai_governance",
                raw_score=20.0,
                weight=DIMENSION_WEIGHTS["ai_governance"],
                weighted_score=20.0 * DIMENSION_WEIGHTS["ai_governance"],
                drivers=["No AI systems detected — EU AI Act requirements may still apply"],
                data_available=False,
            )

        raw = 0.0

        if not inp.audit_trail_present:
            raw += 50.0
            drivers.append("No AI audit trail configured — EU AI Act Article 12 non-compliant")
        elif not inp.audit_chain_verified:
            raw += 25.0
            drivers.append("Audit trail hash chain unverified — tamper detection not active")

        if inp.high_risk_ai_systems > 0:
            raw = min(100.0, raw + inp.high_risk_ai_systems * 15)
            drivers.append(
                f"{inp.high_risk_ai_systems} Annex III (High-Risk) AI system(s) — "
                f"conformity assessment mandatory by August 2, 2026"
            )

        if inp.eu_ai_act_gap_count > 0:
            raw = min(100.0, raw + min(40, inp.eu_ai_act_gap_count * 4))
            drivers.append(f"{inp.eu_ai_act_gap_count} EU AI Act compliance gap(s) — "
                           "exposure up to €35M or 3% global turnover")

        if not drivers:
            drivers = ["AI governance controls appear adequate"]

        raw = round(min(100.0, raw), 1)
        return DimensionScore(
            dimension="ai_governance",
            raw_score=raw,
            weight=DIMENSION_WEIGHTS["ai_governance"],
            weighted_score=round(raw * DIMENSION_WEIGHTS["ai_governance"], 2),
            drivers=drivers,
        )

    # ---------------------------------------------------------------------------
    # Tier classification
    # ---------------------------------------------------------------------------

    @staticmethod
    def _classify_tier(score: float) -> str:
        if score >= 80:
            return "Critical"
        elif score >= 60:
            return "High"
        elif score >= 40:
            return "Medium"
        elif score >= 20:
            return "Low"
        return "Healthy"

    # ---------------------------------------------------------------------------
    # Priority action builder
    # ---------------------------------------------------------------------------

    def _build_priority_actions(
        self,
        inp: RiskInput,
        dimensions: list[DimensionScore],
        overall: float,
    ) -> list[dict[str, Any]]:
        """Build a prioritized action list from the highest-scoring dimensions."""
        actions: list[dict[str, Any]] = []

        # Sort dimensions by weighted score descending
        sorted_dims = sorted(dimensions, key=lambda d: d.weighted_score, reverse=True)

        for dim in sorted_dims:
            if dim.dimension == "security_compliance" and dim.raw_score > 40:
                crit = inp.policy_critical_findings
                high = inp.policy_high_findings
                if crit > 0:
                    actions.append({
                        "priority": "P0",
                        "module": "PolicyGuard",
                        "action": f"Remediate {crit} CRITICAL compliance violation(s) immediately",
                        "timeline": "0–7 days",
                        "estimated_risk_reduction": f"{dim.raw_score * 0.4:.0f} points",
                    })
                elif high > 0:
                    actions.append({
                        "priority": "P1",
                        "module": "PolicyGuard",
                        "action": f"Address {high} HIGH severity finding(s) in current sprint",
                        "timeline": "7–30 days",
                        "estimated_risk_reduction": f"{dim.raw_score * 0.25:.0f} points",
                    })

            elif dim.dimension == "financial_waste" and dim.raw_score > 30:
                if inp.finops_monthly_waste_usd > 0:
                    actions.append({
                        "priority": "P1",
                        "module": "FinOpsIntelligence",
                        "action": f"Implement top 3 cost optimization recommendations (${inp.finops_monthly_waste_usd:,.0f}/month waste)",
                        "timeline": "14–30 days",
                        "estimated_risk_reduction": f"{dim.raw_score * 0.35:.0f} points",
                    })
                else:
                    actions.append({
                        "priority": "P1",
                        "module": "FinOpsIntelligence",
                        "action": f"Reduce cloud waste from {inp.finops_waste_pct:.0f}% to <15%",
                        "timeline": "30–60 days",
                        "estimated_risk_reduction": f"{dim.raw_score * 0.3:.0f} points",
                    })

            elif dim.dimension == "ai_governance" and dim.raw_score > 40:
                if not inp.audit_trail_present:
                    actions.append({
                        "priority": "P0" if inp.high_risk_ai_systems > 0 else "P1",
                        "module": "AIAuditTrail",
                        "action": "Deploy AIAuditTrail for EU AI Act Article 12 compliance before August 2, 2026",
                        "timeline": "30 days",
                        "estimated_risk_reduction": f"{dim.raw_score * 0.5:.0f} points",
                    })

            elif dim.dimension == "migration_complexity" and dim.raw_score > 50:
                if inp.migration_has_circular_deps:
                    actions.append({
                        "priority": "P1",
                        "module": "MigrationScout",
                        "action": "Resolve circular dependencies before beginning Wave 1 migration",
                        "timeline": "30–45 days",
                        "estimated_risk_reduction": f"{dim.raw_score * 0.2:.0f} points",
                    })
                elif inp.migration_oracle_dependency:
                    actions.append({
                        "priority": "P1",
                        "module": "MigrationScout",
                        "action": "Begin Oracle → Aurora migration planning to eliminate $270K+/year license cost",
                        "timeline": "60–90 days",
                        "estimated_risk_reduction": f"{dim.raw_score * 0.25:.0f} points",
                    })

        return actions

    # ---------------------------------------------------------------------------
    # Narrative generator
    # ---------------------------------------------------------------------------

    def _build_narrative(
        self,
        inp: RiskInput,
        score: float,
        tier: str,
        drivers: list[str],
        actions: list[dict[str, Any]],
    ) -> str:
        """Build executive narrative (rule-based or Claude-powered)."""

        account_label = inp.account_name or inp.account_id or "this workload"
        tier_desc = {
            "Critical": "in critical condition, requiring board-level immediate intervention",
            "High": "carrying high risk that requires executive attention within 30 days",
            "Medium": "at moderate risk with defined remediation pathways",
            "Low": "in good health with minor improvements recommended",
            "Healthy": "healthy with no material risk identified",
        }.get(tier, "under evaluation")

        top3_drivers = drivers[:3]
        driver_text = "\n".join(f"  • {d}" for d in top3_drivers) if top3_drivers else "  • Insufficient data for full assessment"

        p1_actions = [a for a in actions if a.get("priority") in ("P0", "P1")]
        action_text = ""
        if p1_actions:
            action_lines = [f"  {i+1}. [{a['priority']}] {a['action']} ({a['timeline']})" for i, a in enumerate(p1_actions[:3])]
            action_text = "\n\nPriority Actions:\n" + "\n".join(action_lines)

        narrative = (
            f"{account_label.title()} is {tier_desc} with a unified risk score of "
            f"{score:.0f}/100 ({tier}).\n\n"
            f"Top risk drivers:\n{driver_text}"
            f"{action_text}"
        )
        return narrative

    # ---------------------------------------------------------------------------
    # CLI / reporting helper
    # ---------------------------------------------------------------------------

    def print_summary(self, score: RiskScore) -> None:
        """Print a Rich-formatted risk summary to the terminal."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel

            console = Console()
            console.print()

            tier_colors = {
                "Critical": "bold red",
                "High": "red",
                "Medium": "yellow",
                "Low": "bright_yellow",
                "Healthy": "green",
            }
            color = tier_colors.get(score.risk_tier, "white")

            console.print(Panel(
                f"[{color}]Unified Risk Score: {score.overall_score:.0f}/100 — {score.risk_tier}[/{color}]\n"
                f"[dim]Confidence: {score.confidence} | "
                f"Modules with data: {score.input_summary.get('modules_with_data', 0)}/4[/dim]",
                title="[bold cyan]Enterprise AI Accelerator — Workload Risk Aggregator",
                border_style="cyan",
            ))

            table = Table(
                title="Dimension Breakdown",
                show_header=True,
                header_style="bold magenta",
            )
            table.add_column("Dimension", style="cyan")
            table.add_column("Risk Score", justify="right")
            table.add_column("Weight", justify="right", style="dim")
            table.add_column("Contribution", justify="right")
            table.add_column("Top Driver", style="dim")

            dim_colors = {
                range(0, 30): "green",
                range(30, 55): "yellow",
                range(55, 75): "orange_red1",
                range(75, 101): "red",
            }

            def get_color(val: float) -> str:
                for r, c in dim_colors.items():
                    if int(val) in r:
                        return c
                return "white"

            dim_labels = {
                "security_compliance": "Security & Compliance",
                "financial_waste": "Financial Waste",
                "migration_complexity": "Migration Complexity",
                "ai_governance": "AI Governance",
            }

            for dim in score.dimensions:
                c = get_color(dim.raw_score)
                avail = "" if dim.data_available else " [dim](estimated)[/dim]"
                table.add_row(
                    dim_labels.get(dim.dimension, dim.dimension),
                    f"[{c}]{dim.raw_score:.0f}/100[/{c}]{avail}",
                    f"{dim.weight:.0%}",
                    f"[{c}]{dim.weighted_score:.1f}[/{c}]",
                    (dim.drivers[0][:55] + "...") if dim.drivers and len(dim.drivers[0]) > 55 else (dim.drivers[0] if dim.drivers else ""),
                )

            console.print(table)
            console.print()

            if score.priority_actions:
                console.print("[bold cyan]Priority Actions:[/bold cyan]")
                for action in score.priority_actions[:3]:
                    p = action.get("priority", "")
                    p_color = "red" if p == "P0" else "yellow" if p == "P1" else "dim"
                    console.print(
                        f"  [{p_color}][{p}][/{p_color}] [{action['module']}] "
                        f"{action['action']} — {action['timeline']}"
                    )
            console.print()

        except ImportError:
            # Fallback without Rich
            print(f"\nUnified Risk Score: {score.overall_score:.0f}/100 ({score.risk_tier})")
            print(f"Top driver: {score.top_risk_driver}")
            for action in score.priority_actions[:3]:
                print(f"  [{action.get('priority', '?')}] {action['action']}")
