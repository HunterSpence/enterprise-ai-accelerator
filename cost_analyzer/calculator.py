"""
CostAnalyzer — AI-Powered Cloud Cost Optimization Engine

Quantifies cloud spend waste and projects savings from recommended
architecture changes. Built for the question every CFO asks:
"What's the ROI of this engagement?"

Typical findings: 18-26% spend reduction potential in enterprise
environments. This module identifies where that money is.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()


@dataclass
class CostFinding:
    category: str           # Compute, Storage, Network, Licensing, etc.
    resource: str           # Specific resource or resource group
    current_monthly: float  # Current spend
    optimized_monthly: float
    savings_monthly: float
    savings_pct: float
    action: str             # What to do
    effort: str             # Low / Medium / High
    risk: str               # Low / Medium / High
    payback_days: int       # Days to break even on implementation cost


@dataclass
class CostAnalysisResult:
    total_monthly_spend: float = 0.0
    total_waste_monthly: float = 0.0
    total_savings_monthly: float = 0.0
    total_savings_annual: float = 0.0
    savings_percentage: float = 0.0
    
    quick_wins: list[CostFinding] = field(default_factory=list)      # Low effort, high savings
    medium_term: list[CostFinding] = field(default_factory=list)     # Medium effort
    strategic: list[CostFinding] = field(default_factory=list)       # High effort, large savings
    
    roi_months: float = 0.0             # Months to ROI on optimization work
    three_year_savings: float = 0.0
    executive_summary: str = ""
    financial_narrative: str = ""       # 2-3 sentences for CFO
    confidence_level: str = ""          # High / Medium / Low with rationale

    def print_summary(self):
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        
        console = Console()
        console.print(Panel(
            f"[bold green]${self.total_savings_annual:,.0f}[/bold green] annual savings potential\n"
            f"({self.savings_percentage:.1f}% of current ${self.total_monthly_spend:,.0f}/mo spend)\n\n"
            f"{self.financial_narrative}",
            title="[bold]CostAnalyzer — Financial Impact",
            border_style="green"
        ))
        
        if self.quick_wins:
            table = Table(title="Quick Wins (implement in <30 days)")
            table.add_column("Resource", style="cyan")
            table.add_column("Action", style="white")
            table.add_column("Monthly Savings", style="green")
            table.add_column("Risk", style="yellow")
            for f in self.quick_wins[:5]:
                table.add_row(f.resource, f.action[:60], f"${f.savings_monthly:,.0f}", f.risk)
            console.print(table)
        
        console.print(f"\n[bold]3-year savings projection:[/bold] ${self.three_year_savings:,.0f}")
        console.print(f"[bold]ROI payback period:[/bold] {self.roi_months:.1f} months")


class CostAnalyzer:
    """
    Analyzes cloud infrastructure for cost waste using Claude.
    
    Identifies:
    - Oversized/idle compute (typically 40-60% of waste)
    - Unoptimized storage (lifecycle policies, tiers)
    - Network egress inefficiencies
    - Reserved instance / Savings Plan opportunities
    - Licensing optimization
    - Multi-region redundancy waste
    """
    
    SYSTEM_PROMPT = """You are a cloud FinOps specialist and certified cost optimization architect with 
experience across AWS, Azure, and GCP. You've led cloud cost optimization programs for Fortune 500 
companies and consistently identify 18-30% spend reduction opportunities.

When analyzing cloud costs you:
1. Quantify findings in actual dollar amounts (monthly and annual)
2. Separate quick wins (low effort) from strategic initiatives (high effort)
3. Calculate realistic payback periods based on implementation complexity
4. Account for risk — some savings have operational tradeoffs
5. Focus on what a CFO or VP Finance would approve in a budget meeting

Your output drives business decisions. Be conservative in estimates rather than optimistic.
You respond in valid JSON only."""
    
    def __init__(self, model: Optional[str] = None):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-opus-4-6")
    
    def analyze(self, infrastructure_description: str, monthly_spend: Optional[float] = None) -> CostAnalysisResult:
        """
        Analyze infrastructure for cost optimization opportunities.
        
        Args:
            infrastructure_description: Architecture description, AWS Cost Explorer export,
                                        or resource inventory
            monthly_spend: Known monthly spend (used to calibrate percentages)
        
        Returns:
            CostAnalysisResult with quantified savings opportunities
        """
        prompt = self._build_prompt(infrastructure_description, monthly_spend)
        message = self.client.messages.create(
            model=self.model,
            max_tokens=6144,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        return self._parse_response(message.content[0].text)
    
    def _build_prompt(self, description: str, monthly_spend: Optional[float]) -> str:
        spend_context = f"\nKNOWN MONTHLY SPEND: ${monthly_spend:,.0f}" if monthly_spend else ""
        return f"""Analyze the following cloud infrastructure for cost optimization opportunities.
{spend_context}

INFRASTRUCTURE:
{description[:6000]}

Return ONLY valid JSON:
{{
  "total_monthly_spend": <estimated or known monthly spend>,
  "total_waste_monthly": <identifiable waste per month>,
  "total_savings_monthly": <achievable savings per month>,
  "total_savings_annual": <annual savings>,
  "savings_percentage": <pct of total spend>,
  "quick_wins": [
    {{
      "category": "Compute|Storage|Network|Licensing|Other",
      "resource": "specific resource name",
      "current_monthly": <float>,
      "optimized_monthly": <float>,
      "savings_monthly": <float>,
      "savings_pct": <float>,
      "action": "specific action to take",
      "effort": "Low|Medium|High",
      "risk": "Low|Medium|High",
      "payback_days": <int>
    }}
  ],
  "medium_term": [],
  "strategic": [],
  "roi_months": <float>,
  "three_year_savings": <float>,
  "executive_summary": "2-3 sentences for a board meeting",
  "financial_narrative": "One sentence with the headline number and what drives it",
  "confidence_level": "High|Medium|Low — one sentence rationale"
}}"""
    
    def _parse_response(self, raw: str) -> CostAnalysisResult:
        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            data = json.loads(clean)
            
            def parse_findings(items):
                return [CostFinding(
                    category=f.get("category", ""),
                    resource=f.get("resource", ""),
                    current_monthly=f.get("current_monthly", 0),
                    optimized_monthly=f.get("optimized_monthly", 0),
                    savings_monthly=f.get("savings_monthly", 0),
                    savings_pct=f.get("savings_pct", 0),
                    action=f.get("action", ""),
                    effort=f.get("effort", "Medium"),
                    risk=f.get("risk", "Medium"),
                    payback_days=f.get("payback_days", 90)
                ) for f in items]
            
            return CostAnalysisResult(
                total_monthly_spend=data.get("total_monthly_spend", 0),
                total_waste_monthly=data.get("total_waste_monthly", 0),
                total_savings_monthly=data.get("total_savings_monthly", 0),
                total_savings_annual=data.get("total_savings_annual", 0),
                savings_percentage=data.get("savings_percentage", 0),
                quick_wins=parse_findings(data.get("quick_wins", [])),
                medium_term=parse_findings(data.get("medium_term", [])),
                strategic=parse_findings(data.get("strategic", [])),
                roi_months=data.get("roi_months", 0),
                three_year_savings=data.get("three_year_savings", 0),
                executive_summary=data.get("executive_summary", ""),
                financial_narrative=data.get("financial_narrative", ""),
                confidence_level=data.get("confidence_level", "")
            )
        except (json.JSONDecodeError, KeyError):
            return CostAnalysisResult(executive_summary=raw[:500])
