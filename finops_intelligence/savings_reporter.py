"""
finops_intelligence/savings_reporter.py
=========================================

SavingsReporter — consolidates RI/SP, right-sizing, and carbon recommendations
into a single CFO-ready executive savings report.

Uses core.AIClient with Haiku 4.5 (MODEL_WORKER) to generate a one-paragraph
narrative summary — cached via the result_cache parameter if provided.

No new dependencies — uses existing anthropic, pandas, json (stdlib).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Haiku model constant (mirrors core.models.MODEL_WORKER)
# ---------------------------------------------------------------------------

_HAIKU_MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Opportunity dataclass (unified view across all saving types)
# ---------------------------------------------------------------------------

@dataclass
class SavingsOpportunity:
    """Unified savings opportunity for cross-module ranking."""

    opportunity_id: str
    category: str           # 'ri_sp' | 'rightsizing' | 'carbon' | 'combined'
    resource_group: str
    description: str
    monthly_savings_usd: float
    upfront_cost_usd: float
    effort_level: str       # 'low' | 'medium' | 'high'
    risk: str               # 'low' | 'medium' | 'high'
    breakeven_months: float
    priority_score: float   # computed: savings_usd / (effort * risk penalty)


@dataclass
class ExecutiveSavingsReport:
    """Top-level output from SavingsReporter.generate()."""

    report_date: str
    current_monthly_spend_usd: float
    total_achievable_savings_usd: float
    savings_pct: float
    co2e_reduction_kg_monthly: float
    top_opportunities: list[SavingsOpportunity] = field(default_factory=list)
    ri_sp_summary: dict[str, Any] = field(default_factory=dict)
    rightsizing_summary: dict[str, Any] = field(default_factory=dict)
    carbon_summary: dict[str, Any] = field(default_factory=dict)
    ai_narrative: str = ""
    warnings: list[str] = field(default_factory=list)

    def render_json(self) -> str:
        """Render the report as pretty-printed JSON."""
        return json.dumps({
            "report_date": self.report_date,
            "current_monthly_spend_usd": round(self.current_monthly_spend_usd, 2),
            "total_achievable_savings_usd": round(self.total_achievable_savings_usd, 2),
            "savings_pct": round(self.savings_pct, 1),
            "co2e_reduction_kg_monthly": round(self.co2e_reduction_kg_monthly, 2),
            "ai_narrative": self.ai_narrative,
            "top_10_opportunities": [
                {
                    "rank": i + 1,
                    "category": op.category,
                    "resource_group": op.resource_group,
                    "description": op.description,
                    "monthly_savings_usd": round(op.monthly_savings_usd, 2),
                    "effort": op.effort_level,
                    "risk": op.risk,
                    "breakeven_months": round(op.breakeven_months, 1),
                }
                for i, op in enumerate(self.top_opportunities[:10])
            ],
            "ri_sp_summary": self.ri_sp_summary,
            "rightsizing_summary": self.rightsizing_summary,
            "carbon_summary": self.carbon_summary,
            "warnings": self.warnings,
        }, indent=2)

    def render_markdown(self) -> str:
        """Render the report as CFO-ready Markdown."""
        lines: list[str] = []
        lines.append("# FinOps Executive Savings Report")
        lines.append(f"\nGenerated: {self.report_date}")
        lines.append("\n---\n")
        lines.append("## Summary")
        lines.append(f"\n| Metric | Value |")
        lines.append("| --- | --- |")
        lines.append(f"| Current Monthly Spend | ${self.current_monthly_spend_usd:,.0f} |")
        lines.append(f"| Total Achievable Savings | ${self.total_achievable_savings_usd:,.0f}/mo |")
        lines.append(f"| Savings % | {self.savings_pct:.1f}% |")
        lines.append(f"| CO2e Reduction | {self.co2e_reduction_kg_monthly:,.0f} kg/mo |")

        if self.ai_narrative:
            lines.append("\n## Executive Summary\n")
            lines.append(self.ai_narrative)

        lines.append("\n---\n")
        lines.append("## Top 10 Savings Opportunities\n")
        lines.append("| Rank | Category | Description | Monthly Savings | Effort | Risk | Breakeven |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for i, op in enumerate(self.top_opportunities[:10], 1):
            lines.append(
                f"| {i} | {op.category} | {op.description[:60]} | "
                f"${op.monthly_savings_usd:,.0f} | {op.effort_level} | {op.risk} | "
                f"{op.breakeven_months:.0f}mo |"
            )

        if self.ri_sp_summary:
            lines.append("\n---\n")
            lines.append("## RI / Savings Plans\n")
            lines.append(f"- Recommendations: {self.ri_sp_summary.get('count', 0)}")
            lines.append(f"- Projected savings: ${self.ri_sp_summary.get('total_savings_monthly_usd', 0):,.0f}/mo")
            lines.append(f"- Total upfront: ${self.ri_sp_summary.get('total_upfront_usd', 0):,.0f}")

        if self.rightsizing_summary:
            lines.append("\n---\n")
            lines.append("## Right-Sizing\n")
            lines.append(f"- Instances flagged: {self.rightsizing_summary.get('count', 0)}")
            lines.append(f"- Over-provisioned: {self.rightsizing_summary.get('over_provisioned', 0)}")
            lines.append(f"- Idle: {self.rightsizing_summary.get('idle', 0)}")
            lines.append(f"- Projected savings: ${self.rightsizing_summary.get('total_savings_monthly_usd', 0):,.0f}/mo")

        if self.carbon_summary:
            lines.append("\n---\n")
            lines.append("## Carbon Footprint\n")
            lines.append(f"- Total fleet emissions: {self.carbon_summary.get('total_kgco2e_monthly', 0):,.0f} kgCO2e/mo")
            lines.append(f"- Green migration savings: {self.carbon_summary.get('green_migration_savings_kg', 0):,.0f} kgCO2e/mo")

        if self.warnings:
            lines.append("\n---\n")
            lines.append("## Warnings\n")
            for w in self.warnings:
                lines.append(f"- {w}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# SavingsReporter
# ---------------------------------------------------------------------------

_EFFORT_MAP = {"low": 1.0, "medium": 2.0, "high": 4.0}
_RISK_PENALTY = {"low": 1.0, "medium": 0.7, "high": 0.4}


class SavingsReporter:
    """Consolidates RI/SP, right-sizing, and carbon data into an executive report.

    Usage::

        reporter = SavingsReporter()
        report = await reporter.generate(
            ri_recs=analysis.recommendations,
            rightsize_recs=sizing_recs,
            carbon_report=carbon_report,
            current_monthly_spend=340_000,
        )
        print(report.render_markdown())
    """

    def __init__(
        self,
        ai_client: Optional[Any] = None,
        result_cache: Optional[Any] = None,
    ) -> None:
        """
        Args:
            ai_client: core.AIClient instance. If None, narrative generation is skipped.
            result_cache: Optional mapping (dict-like) for caching AI narrative keyed
                          by a hash of the report metrics. Pass any dict subclass.
        """
        self._ai_client = ai_client
        self._result_cache = result_cache if result_cache is not None else {}

    async def generate(
        self,
        ri_recs: list[Any],
        rightsize_recs: list[Any],
        carbon_report: Optional[Any] = None,
        current_monthly_spend: float = 0.0,
    ) -> ExecutiveSavingsReport:
        """Produce the consolidated executive savings report.

        Args:
            ri_recs: list[Recommendation] from RISPOptimizer.
            rightsize_recs: list[RightSizingRec] from RightSizer.
            carbon_report: CarbonReport from CarbonTracker (optional).
            current_monthly_spend: Known total monthly cloud spend (USD).

        Returns:
            ExecutiveSavingsReport ready for render_markdown() or render_json().
        """
        report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        warnings: list[str] = []

        # ------------------------------------------------------------------
        # RI/SP summary
        # ------------------------------------------------------------------
        ri_sp_summary: dict[str, Any] = {}
        ri_opportunities: list[SavingsOpportunity] = []
        if ri_recs:
            total_ri_savings = sum(getattr(r, "projected_savings_monthly", 0) for r in ri_recs)
            total_ri_upfront = sum(getattr(r, "upfront_cost", 0) for r in ri_recs)
            ri_sp_summary = {
                "count": len(ri_recs),
                "total_savings_monthly_usd": round(total_ri_savings, 2),
                "total_upfront_usd": round(total_ri_upfront, 2),
            }
            # Convert top RI recs to opportunities
            seen_groups: set[str] = set()
            for rec in sorted(ri_recs, key=lambda r: getattr(r, "projected_savings_monthly", 0), reverse=True):
                key = f"{getattr(rec, 'resource_group', '')}_{getattr(rec, 'commitment_type', '')}"
                if key in seen_groups:
                    continue
                seen_groups.add(key)
                effort = "low" if "no_upfront" in getattr(rec, "commitment_type", "") else "medium"
                risk = getattr(rec, "utilization_risk", "medium")
                savings = getattr(rec, "projected_savings_monthly", 0)
                upfront = getattr(rec, "upfront_cost", 0)
                breakeven = getattr(rec, "breakeven_months", 0)
                score = savings * _RISK_PENALTY.get(risk, 1.0) / _EFFORT_MAP.get(effort, 2.0)
                ri_opportunities.append(SavingsOpportunity(
                    opportunity_id=f"ri_{key[:30]}",
                    category="ri_sp",
                    resource_group=getattr(rec, "resource_group", ""),
                    description=f"{getattr(rec, 'commitment_type', '')} for {getattr(rec, 'instance_family', '')} in {getattr(rec, 'region', '')}",
                    monthly_savings_usd=round(savings, 2),
                    upfront_cost_usd=round(upfront, 2),
                    effort_level=effort,
                    risk=risk,
                    breakeven_months=round(breakeven, 1),
                    priority_score=round(score, 2),
                ))

        # ------------------------------------------------------------------
        # Right-sizing summary
        # ------------------------------------------------------------------
        rightsizing_summary: dict[str, Any] = {}
        rs_opportunities: list[SavingsOpportunity] = []
        if rightsize_recs:
            total_rs_savings = sum(getattr(r, "projected_monthly_savings", 0) for r in rightsize_recs)
            over_count = sum(1 for r in rightsize_recs if getattr(r, "classification", "") == "over_provisioned")
            idle_count = sum(1 for r in rightsize_recs if getattr(r, "classification", "") == "idle")
            under_count = sum(1 for r in rightsize_recs if getattr(r, "classification", "") == "under_provisioned")
            rightsizing_summary = {
                "count": len(rightsize_recs),
                "over_provisioned": over_count,
                "idle": idle_count,
                "under_provisioned": under_count,
                "total_savings_monthly_usd": round(total_rs_savings, 2),
            }
            for rec in rightsize_recs[:20]:  # top 20 for ranking
                classification = getattr(rec, "classification", "over_provisioned")
                effort = "low" if classification == "idle" else "medium"
                risk = getattr(rec, "risk", "low")
                savings = getattr(rec, "projected_monthly_savings", 0)
                score = savings * _RISK_PENALTY.get(risk, 1.0) / _EFFORT_MAP.get(effort, 2.0)
                rs_opportunities.append(SavingsOpportunity(
                    opportunity_id=f"rs_{getattr(rec, 'resource_id', '')[:30]}",
                    category="rightsizing",
                    resource_group=getattr(rec, "resource_id", ""),
                    description=f"{getattr(rec, 'current_type', '')} -> {getattr(rec, 'recommended_type', '')} ({classification.replace('_',' ')})",
                    monthly_savings_usd=round(savings, 2),
                    upfront_cost_usd=0.0,
                    effort_level=effort,
                    risk=risk,
                    breakeven_months=0.0,
                    priority_score=round(score, 2),
                ))

        # ------------------------------------------------------------------
        # Carbon summary
        # ------------------------------------------------------------------
        carbon_summary: dict[str, Any] = {}
        carbon_co2e_reduction = 0.0
        if carbon_report is not None:
            total_co2e = getattr(carbon_report, "total_monthly_kgco2e", 0.0)
            green_ops = getattr(carbon_report, "green_migration_opportunities", [])
            green_savings = sum(getattr(op, "savings_kgco2e_monthly", 0) for op in green_ops)
            carbon_co2e_reduction = green_savings
            carbon_summary = {
                "total_kgco2e_monthly": round(total_co2e, 2),
                "total_tco2e_monthly": round(total_co2e / 1000, 4),
                "green_migration_opportunities": len(green_ops),
                "green_migration_savings_kg": round(green_savings, 2),
                "optimization_suggestions": getattr(carbon_report, "optimization_suggestions", []),
            }

        # ------------------------------------------------------------------
        # Unified top 10 ranking
        # ------------------------------------------------------------------
        all_opps = ri_opportunities + rs_opportunities
        all_opps.sort(key=lambda o: o.priority_score, reverse=True)
        top_10 = all_opps[:10]

        # ------------------------------------------------------------------
        # Totals
        # ------------------------------------------------------------------
        total_savings = (
            sum(op.monthly_savings_usd for op in ri_opportunities)
            + sum(op.monthly_savings_usd for op in rs_opportunities)
        )
        if current_monthly_spend <= 0:
            # Derive from RI data if available
            if ri_recs:
                current_monthly_spend = sum(getattr(r, "current_monthly_cost", 0) for r in ri_recs)
        savings_pct = (total_savings / current_monthly_spend * 100) if current_monthly_spend > 0 else 0.0

        # ------------------------------------------------------------------
        # AI narrative (Haiku 4.5, cached)
        # ------------------------------------------------------------------
        narrative = ""
        if self._ai_client is not None and total_savings > 0:
            cache_key = f"narrative_{round(total_savings):.0f}_{round(current_monthly_spend):.0f}_{round(carbon_co2e_reduction):.0f}"
            if cache_key in self._result_cache:
                narrative = self._result_cache[cache_key]
            else:
                narrative = await self._generate_narrative(
                    current_monthly_spend=current_monthly_spend,
                    total_savings=total_savings,
                    savings_pct=savings_pct,
                    ri_count=len(ri_recs),
                    rs_count=len(rightsize_recs),
                    co2e_reduction_kg=carbon_co2e_reduction,
                    top_opportunity=top_10[0] if top_10 else None,
                )
                self._result_cache[cache_key] = narrative

        report = ExecutiveSavingsReport(
            report_date=report_date,
            current_monthly_spend_usd=round(current_monthly_spend, 2),
            total_achievable_savings_usd=round(total_savings, 2),
            savings_pct=round(savings_pct, 1),
            co2e_reduction_kg_monthly=round(carbon_co2e_reduction, 2),
            top_opportunities=top_10,
            ri_sp_summary=ri_sp_summary,
            rightsizing_summary=rightsizing_summary,
            carbon_summary=carbon_summary,
            ai_narrative=narrative,
            warnings=warnings,
        )
        logger.info(
            "SavingsReporter: $%.0f/mo savings identified (%.1f%% of $%.0f/mo spend)",
            total_savings, savings_pct, current_monthly_spend,
        )
        return report

    async def _generate_narrative(
        self,
        current_monthly_spend: float,
        total_savings: float,
        savings_pct: float,
        ri_count: int,
        rs_count: int,
        co2e_reduction_kg: float,
        top_opportunity: Optional[SavingsOpportunity],
    ) -> str:
        """Call Haiku 4.5 to write a CFO-ready paragraph."""
        system = (
            "You are a FinOps analyst writing a one-paragraph executive summary for a CFO. "
            "Be specific about dollar amounts and percentages. No bullet points. "
            "Max 120 words. Professional, direct tone."
        )
        top_op_text = (
            f"The single highest-priority action is: {top_opportunity.description} "
            f"(${top_opportunity.monthly_savings_usd:,.0f}/mo, {top_opportunity.effort_level} effort)."
            if top_opportunity else ""
        )
        user = (
            f"Current cloud spend: ${current_monthly_spend:,.0f}/month. "
            f"Identified {ri_count} RI/SP recommendations and {rs_count} right-sizing opportunities "
            f"totalling ${total_savings:,.0f}/month in achievable savings ({savings_pct:.1f}% reduction). "
            f"Carbon reduction potential: {co2e_reduction_kg:,.0f} kgCO2e/month. "
            f"{top_op_text} "
            "Write a CFO-ready executive summary paragraph."
        )
        try:
            response = await self._ai_client.raw.messages.create(
                model=_HAIKU_MODEL,
                max_tokens=256,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text.strip()
        except Exception as exc:
            logger.warning("AI narrative generation failed: %s", exc)
            return (
                f"Analysis identified ${total_savings:,.0f}/month in achievable savings "
                f"({savings_pct:.1f}% of ${current_monthly_spend:,.0f}/month spend) "
                f"across {ri_count} commitment optimisations and {rs_count} right-sizing actions."
            )
