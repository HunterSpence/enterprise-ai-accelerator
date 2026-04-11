"""
MigrationScout — AI-Powered Cloud Migration Planner

Classifies workloads using the 6R framework (Rehost, Replatform, Refactor,
Rearchitect, Retire, Retain), estimates effort, scores complexity, and
generates a phased migration roadmap with risk register.
"""

import json
import os
import csv
import io
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from enum import Enum

import anthropic
from dotenv import load_dotenv

load_dotenv()


class MigrationStrategy(str, Enum):
    REHOST = "Rehost"       # Lift and shift
    REPLATFORM = "Replatform"  # Lift, tinker, and shift
    REFACTOR = "Refactor"   # Re-architect
    REARCHITECT = "Rearchitect"  # Full redesign
    RETIRE = "Retire"       # Decommission
    RETAIN = "Retain"       # Keep on-premises


@dataclass
class Workload:
    name: str
    description: str
    strategy: Optional[MigrationStrategy] = None
    complexity_score: int = 0  # 1-10
    effort_weeks: float = 0.0
    priority: int = 0  # 1=high, 2=medium, 3=low
    phase: int = 1
    dependencies: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class MigrationPlan:
    workloads: list[Workload] = field(default_factory=list)
    total_effort_weeks: float = 0.0
    estimated_duration_months: int = 0
    summary: str = ""
    executive_summary: str = ""
    phase_1_workloads: list[str] = field(default_factory=list)
    phase_2_workloads: list[str] = field(default_factory=list)
    phase_3_workloads: list[str] = field(default_factory=list)
    risk_register: list[dict] = field(default_factory=list)
    quick_wins: list[str] = field(default_factory=list)
    migration_blockers: list[str] = field(default_factory=list)

    def strategy_breakdown(self) -> dict:
        breakdown = {s.value: 0 for s in MigrationStrategy}
        for w in self.workloads:
            if w.strategy:
                breakdown[w.strategy.value] += 1
        return {k: v for k, v in breakdown.items() if v > 0}

    def print_summary(self):
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        
        console = Console()
        console.print(Panel(self.executive_summary, title="[bold]MigrationScout Plan", border_style="green"))
        
        console.print(f"\n[bold]Total workloads:[/bold] {len(self.workloads)}")
        console.print(f"[bold]Total effort:[/bold] {self.total_effort_weeks:.0f} weeks")
        console.print(f"[bold]Estimated duration:[/bold] {self.estimated_duration_months} months")
        
        breakdown = self.strategy_breakdown()
        table = Table(title="Strategy Breakdown")
        table.add_column("Strategy", style="cyan")
        table.add_column("Count", style="green")
        for strategy, count in breakdown.items():
            table.add_row(strategy, str(count))
        console.print(table)
        
        if self.quick_wins:
            console.print("\n[bold green]Quick Wins (Phase 1):")
            for w in self.quick_wins[:5]:
                console.print(f"  ✅ {w}")


class MigrationPlanner:
    """
    Plans cloud migrations using Claude's reasoning capabilities.
    
    Supports:
    - CSV workload inventory
    - JSON workload list
    - Natural language description
    """
    
    SYSTEM_PROMPT = """You are a cloud migration architect with 15 years of experience leading 
migrations at AWS, Google Cloud, and Azure. You specialize in the 6R migration framework 
(Rehost, Replatform, Refactor, Rearchitect, Retire, Retain).

For each workload you:
1. Classify it with the most appropriate 6R strategy
2. Score complexity 1-10 based on dependencies, tech stack, and business criticality
3. Estimate effort in person-weeks
4. Identify dependencies and sequencing requirements
5. Flag risks and mitigation strategies
6. Prioritize for phased migration (quick wins first)

You respond in valid JSON only."""
    
    def __init__(self, model: Optional[str] = None):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-opus-4-6")
    
    def plan(self, inventory: str | list[dict], context: str = "") -> MigrationPlan:
        """
        Generate a migration plan from a workload inventory.
        
        Args:
            inventory: CSV string, JSON list, or text description of workloads
            context: Additional context (target cloud, timeline, constraints)
        
        Returns:
            MigrationPlan with classified workloads and phased roadmap
        """
        if isinstance(inventory, list):
            inventory_str = json.dumps(inventory, indent=2)
        else:
            inventory_str = str(inventory)
        
        prompt = self._build_prompt(inventory_str, context)
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        raw = message.content[0].text
        return self._parse_response(raw)
    
    def plan_from_csv(self, csv_path: str | Path, context: str = "") -> MigrationPlan:
        """Plan from a CSV file with columns: name, description, [tech_stack], [team_size], [criticality]"""
        content = Path(csv_path).read_text()
        return self.plan(content, context)
    
    def _build_prompt(self, inventory: str, context: str) -> str:
        prompt = f"""Plan a cloud migration for the following workload inventory.

WORKLOAD INVENTORY:
{inventory[:6000]}
"""
        if context:
            prompt += f"\nMIGRATION CONTEXT:\n{context}\n"
        
        prompt += """
Return ONLY valid JSON with this structure:
{
  "workloads": [
    {
      "name": "string",
      "strategy": "Rehost|Replatform|Refactor|Rearchitect|Retire|Retain",
      "complexity_score": <1-10>,
      "effort_weeks": <float>,
      "priority": <1|2|3>,
      "phase": <1|2|3>,
      "dependencies": ["workload_name"],
      "risks": ["risk1", "risk2"],
      "rationale": "one sentence why this strategy"
    }
  ],
  "total_effort_weeks": <float>,
  "estimated_duration_months": <int>,
  "phase_1_workloads": ["name1", "name2"],
  "phase_2_workloads": ["name1", "name2"],
  "phase_3_workloads": ["name1", "name2"],
  "quick_wins": ["workload names for Phase 1 quick wins"],
  "migration_blockers": ["blocker1", "blocker2"],
  "risk_register": [{"risk": "string", "likelihood": "High|Medium|Low", "impact": "High|Medium|Low", "mitigation": "string"}],
  "executive_summary": "3-4 sentences for executive stakeholders",
  "summary": "Technical summary of the migration approach"
}"""
        return prompt
    
    def _parse_response(self, raw: str) -> MigrationPlan:
        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            
            data = json.loads(clean)
            workloads = [
                Workload(
                    name=w["name"],
                    description=w.get("rationale", ""),
                    strategy=MigrationStrategy(w["strategy"]) if w.get("strategy") else None,
                    complexity_score=w.get("complexity_score", 5),
                    effort_weeks=w.get("effort_weeks", 2.0),
                    priority=w.get("priority", 2),
                    phase=w.get("phase", 2),
                    dependencies=w.get("dependencies", []),
                    risks=w.get("risks", []),
                    rationale=w.get("rationale", "")
                )
                for w in data.get("workloads", [])
            ]
            
            return MigrationPlan(
                workloads=workloads,
                total_effort_weeks=data.get("total_effort_weeks", 0),
                estimated_duration_months=data.get("estimated_duration_months", 0),
                summary=data.get("summary", ""),
                executive_summary=data.get("executive_summary", ""),
                phase_1_workloads=data.get("phase_1_workloads", []),
                phase_2_workloads=data.get("phase_2_workloads", []),
                phase_3_workloads=data.get("phase_3_workloads", []),
                risk_register=data.get("risk_register", []),
                quick_wins=data.get("quick_wins", []),
                migration_blockers=data.get("migration_blockers", [])
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return MigrationPlan(executive_summary=raw[:500])
