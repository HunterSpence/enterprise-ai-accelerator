"""
CloudIQ — AI-Powered Cloud Architecture Analyzer

Analyzes AWS configurations, Terraform state, or architecture descriptions
using Claude to produce security findings, cost recommendations, and
migration readiness scores.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AnalysisResult:
    """Structured output from a CloudIQ analysis."""
    security_score: int  # 0-100
    cost_score: int      # 0-100 (higher = more optimized)
    migration_readiness: int  # 0-100
    
    critical_findings: list[str] = field(default_factory=list)
    high_findings: list[str] = field(default_factory=list)
    medium_findings: list[str] = field(default_factory=list)
    
    cost_waste_monthly: float = 0.0
    cost_recommendations: list[str] = field(default_factory=list)
    
    recommendations: list[str] = field(default_factory=list)
    migration_blockers: list[str] = field(default_factory=list)
    
    executive_summary: str = ""
    raw_analysis: str = ""

    def print_summary(self):
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        
        console = Console()
        console.print(Panel(self.executive_summary, title="[bold]CloudIQ Analysis", border_style="blue"))
        
        table = Table(title="Scores")
        table.add_column("Dimension", style="cyan")
        table.add_column("Score", style="green")
        table.add_row("Security Posture", f"{self.security_score}/100")
        table.add_row("Cost Optimization", f"{self.cost_score}/100")
        table.add_row("Migration Readiness", f"{self.migration_readiness}/100")
        console.print(table)
        
        if self.critical_findings:
            console.print("\n[bold red]Critical Findings:")
            for f in self.critical_findings:
                console.print(f"  ⚠️  {f}")
        
        if self.cost_waste_monthly > 0:
            console.print(f"\n[bold yellow]Estimated monthly waste: ${self.cost_waste_monthly:,.0f}")


class CloudIQAnalyzer:
    """
    Analyzes cloud architecture configurations using Claude.
    
    Supports:
    - AWS config JSON (from aws configservice)
    - Terraform state files
    - Architecture descriptions (natural language)
    - CSV/JSON resource inventories
    """
    
    SYSTEM_PROMPT = """You are a senior cloud architect and security specialist with 15 years of experience 
at Big 4 consulting firms. You have deep expertise in AWS, Azure, and GCP security, cost optimization, 
and cloud migration strategy.

When analyzing cloud configurations, you:
1. Identify security vulnerabilities with specific CVE references where applicable
2. Quantify cost waste with actual dollar estimates
3. Score configurations objectively on a 0-100 scale
4. Provide actionable, prioritized recommendations
5. Flag migration blockers that would prevent cloud-native adoption

You respond in valid JSON only. No markdown, no prose outside the JSON structure."""

    def __init__(self, model: Optional[str] = None):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-opus-4-6")
    
    def analyze(self, config_input: str | dict, context: str = "") -> AnalysisResult:
        """
        Analyze a cloud configuration.
        
        Args:
            config_input: AWS config JSON, Terraform state, or text description
            context: Additional context (company size, compliance requirements, etc.)
        
        Returns:
            AnalysisResult with scores, findings, and recommendations
        """
        if isinstance(config_input, dict):
            config_str = json.dumps(config_input, indent=2)
        else:
            config_str = str(config_input)
        
        prompt = self._build_prompt(config_str, context)
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        raw = message.content[0].text
        return self._parse_response(raw)
    
    def analyze_file(self, file_path: str | Path, context: str = "") -> AnalysisResult:
        """Analyze a config file (JSON, HCL, YAML, or text)."""
        path = Path(file_path)
        content = path.read_text()
        
        if path.suffix == ".json":
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                pass
        
        return self.analyze(content, context)
    
    def _build_prompt(self, config: str, context: str) -> str:
        prompt = f"""Analyze the following cloud configuration and return a JSON response.

CONFIGURATION:
{config[:8000]}  
"""
        if context:
            prompt += f"\nADDITIONAL CONTEXT:\n{context}\n"
        
        prompt += """
Return ONLY valid JSON with this exact structure:
{
  "security_score": <0-100>,
  "cost_score": <0-100>,
  "migration_readiness": <0-100>,
  "critical_findings": ["finding1", "finding2"],
  "high_findings": ["finding1", "finding2"],
  "medium_findings": ["finding1", "finding2"],
  "cost_waste_monthly": <estimated USD/month>,
  "cost_recommendations": ["action1", "action2"],
  "recommendations": ["prioritized action1", "action2"],
  "migration_blockers": ["blocker1", "blocker2"],
  "executive_summary": "2-3 sentence summary for non-technical stakeholders"
}"""
        return prompt
    
    def _parse_response(self, raw: str) -> AnalysisResult:
        try:
            # Strip markdown code blocks if present
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            
            data = json.loads(clean)
            return AnalysisResult(
                security_score=data.get("security_score", 0),
                cost_score=data.get("cost_score", 0),
                migration_readiness=data.get("migration_readiness", 0),
                critical_findings=data.get("critical_findings", []),
                high_findings=data.get("high_findings", []),
                medium_findings=data.get("medium_findings", []),
                cost_waste_monthly=data.get("cost_waste_monthly", 0.0),
                cost_recommendations=data.get("cost_recommendations", []),
                recommendations=data.get("recommendations", []),
                migration_blockers=data.get("migration_blockers", []),
                executive_summary=data.get("executive_summary", ""),
                raw_analysis=raw
            )
        except (json.JSONDecodeError, KeyError) as e:
            # Fallback: return raw analysis as summary
            return AnalysisResult(
                security_score=0,
                cost_score=0,
                migration_readiness=0,
                executive_summary=raw[:500],
                raw_analysis=raw
            )
