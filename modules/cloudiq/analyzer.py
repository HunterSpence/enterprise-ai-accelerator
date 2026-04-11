"""
CloudIQ — Claude-powered cloud architecture analysis engine.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are a senior AWS Solutions Architect and cloud security specialist with 15 years
of experience at Big 4 consulting firms. You have deep expertise in AWS security posture management,
cost optimization, and enterprise cloud migration strategy.

Analyze cloud architectures with the rigor of a $500K consulting engagement:
1. Identify security vulnerabilities by name (e.g., "S3 bucket public ACL", "security group 0.0.0.0/0 ingress")
2. Quantify cost waste with realistic dollar estimates based on typical AWS pricing
3. Score objectively on 0-100 scales based on industry benchmarks
4. Give actionable, specific recommendations — not generic advice
5. Flag migration complexity blockers that would stall a cloud-native transition

Always respond with valid JSON only. No markdown fences, no prose outside the JSON."""


@dataclass
class AnalysisResult:
    security_score: int = 0          # 0-100
    cost_score: int = 0              # 0-100 (higher = more optimized)
    migration_complexity: int = 5    # 1-10
    critical_findings: list = field(default_factory=list)
    high_findings: list = field(default_factory=list)
    medium_findings: list = field(default_factory=list)
    cost_waste_monthly: float = 0.0
    cost_recommendations: list = field(default_factory=list)
    top_recommendations: list = field(default_factory=list)
    migration_blockers: list = field(default_factory=list)
    executive_summary: str = ""
    raw_analysis: str = ""


class CloudIQAnalyzer:
    def __init__(self, model: Optional[str] = None):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-opus-4-6")

    def analyze(self, config_input: str) -> AnalysisResult:
        """Analyze a cloud config (AWS JSON, Terraform HCL, or text description)."""
        prompt = f"""Analyze this cloud architecture as a senior AWS Solutions Architect. Identify:
1) Security vulnerabilities with specific resource names and severity
2) Cost optimization opportunities with estimated monthly savings
3) Migration complexity score (1-10, where 10 = extremely complex)
4) Top 3 actionable recommendations

ARCHITECTURE INPUT:
{config_input[:8000]}

Return ONLY valid JSON with this exact structure (no markdown, no extra text):
{{
  "security_score": <integer 0-100>,
  "cost_score": <integer 0-100, higher = more optimized>,
  "migration_complexity": <integer 1-10>,
  "critical_findings": ["<specific finding>", ...],
  "high_findings": ["<specific finding>", ...],
  "medium_findings": ["<specific finding>", ...],
  "cost_waste_monthly": <float USD/month>,
  "cost_recommendations": ["<action>", ...],
  "top_recommendations": ["<recommendation 1>", "<recommendation 2>", "<recommendation 3>"],
  "migration_blockers": ["<blocker>", ...],
  "executive_summary": "<2-3 sentences for non-technical stakeholders>"
}}"""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text
        return self._parse(raw)

    def _parse(self, raw: str) -> AnalysisResult:
        try:
            text = raw.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            return AnalysisResult(
                security_score=int(data.get("security_score", 0)),
                cost_score=int(data.get("cost_score", 0)),
                migration_complexity=int(data.get("migration_complexity", 5)),
                critical_findings=data.get("critical_findings", []),
                high_findings=data.get("high_findings", []),
                medium_findings=data.get("medium_findings", []),
                cost_waste_monthly=float(data.get("cost_waste_monthly", 0)),
                cost_recommendations=data.get("cost_recommendations", []),
                top_recommendations=data.get("top_recommendations", []),
                migration_blockers=data.get("migration_blockers", []),
                executive_summary=data.get("executive_summary", ""),
                raw_analysis=raw,
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return AnalysisResult(
                executive_summary=raw[:500],
                raw_analysis=raw,
            )
