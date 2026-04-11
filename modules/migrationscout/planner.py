"""
MigrationScout — Claude-powered workload migration planner.
Groups workloads into migration waves, classifies with 6R framework,
estimates effort, scores risk, and resolves dependencies.
"""

import json
import os
import csv
import io
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are a cloud migration architect with 15 years of enterprise migration experience
at AWS Professional Services and Big 4 consulting firms. You have delivered hundreds of cloud migrations
ranging from 50 to 10,000 workloads.

Your job is to analyze a workload inventory and produce a structured migration plan using the 6R framework:
- Rehost: Lift and shift to IaaS (EC2). Fastest, minimal change.
- Replatform: Lift, tinker, shift. Move to managed services (RDS, ECS) with minor optimization.
- Refactor: Re-architect for cloud-native. Containers, serverless, microservices.
- Rearchitect: Full redesign for cloud-native patterns.
- Retire: Decommission — no longer needed.
- Retain: Keep on-premises — not ready or not worth migrating.

Wave planning principles:
- Wave 1: Low complexity, low dependency, high value quick wins (Rehost candidates, standalone services)
- Wave 2: Medium complexity, some dependencies, core business workloads (Replatform candidates)
- Wave 3: High complexity, many dependencies, business-critical or legacy systems requiring Refactor/Rearchitect

Always respond with valid JSON only. No markdown fences."""


@dataclass
class MigrationPlan:
    total_workloads: int = 0
    total_effort_weeks: float = 0.0
    estimated_months: int = 0
    wave_1: list = field(default_factory=list)
    wave_2: list = field(default_factory=list)
    wave_3: list = field(default_factory=list)
    strategy_breakdown: dict = field(default_factory=dict)
    risk_register: list = field(default_factory=list)
    executive_summary: str = ""
    raw_plan: str = ""


class MigrationPlanner:
    def __init__(self, model: Optional[str] = None):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-opus-4-6")

    def plan(self, inventory_input: str) -> MigrationPlan:
        """
        Generate a migration plan from a workload inventory.

        Args:
            inventory_input: CSV or JSON string of workloads
                CSV columns: name, type, description, dependencies, size_gb
                JSON: list of objects with same fields
        """
        workloads_text = self._normalize_input(inventory_input)

        prompt = f"""Analyze this workload inventory and produce a migration plan with wave grouping,
6R classification, effort estimates, and risk register.

WORKLOAD INVENTORY:
{workloads_text[:6000]}

Return ONLY valid JSON with this exact structure:
{{
  "total_workloads": <integer>,
  "total_effort_weeks": <float>,
  "estimated_months": <integer>,
  "wave_1": ["workload_name", ...],
  "wave_2": ["workload_name", ...],
  "wave_3": ["workload_name", ...],
  "strategy_breakdown": {{
    "Rehost": <count>,
    "Replatform": <count>,
    "Refactor": <count>,
    "Rearchitect": <count>,
    "Retire": <count>,
    "Retain": <count>
  }},
  "risk_register": [
    {{
      "workload": "<name>",
      "risk": "<risk description>",
      "mitigation": "<mitigation action>"
    }}
  ],
  "executive_summary": "<3-4 sentences summarizing the migration plan, total effort, key risks, and expected business outcomes>"
}}"""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text
        return self._parse(raw)

    def _normalize_input(self, text: str) -> str:
        text = text.strip()
        # Try JSON first
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return json.dumps(data, indent=2)
        except (json.JSONDecodeError, ValueError):
            pass
        # Return as-is (CSV or plain text)
        return text

    def _parse(self, raw: str) -> MigrationPlan:
        try:
            text = raw.strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            return MigrationPlan(
                total_workloads=int(data.get("total_workloads", 0)),
                total_effort_weeks=float(data.get("total_effort_weeks", 0)),
                estimated_months=int(data.get("estimated_months", 0)),
                wave_1=data.get("wave_1", []),
                wave_2=data.get("wave_2", []),
                wave_3=data.get("wave_3", []),
                strategy_breakdown=data.get("strategy_breakdown", {}),
                risk_register=data.get("risk_register", []),
                executive_summary=data.get("executive_summary", ""),
                raw_plan=raw,
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return MigrationPlan(
                executive_summary=raw[:500],
                raw_plan=raw,
            )
