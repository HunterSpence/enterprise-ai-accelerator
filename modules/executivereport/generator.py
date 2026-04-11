"""
ExecutiveReport — Claude-powered board deck generator.
Transforms raw technical metrics into C-suite language with narrative,
key insights, risk flags, and recommended actions.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are a management consulting partner specializing in digital transformation and
cloud strategy. You have delivered board presentations at Fortune 500 companies for 20 years.

Your expertise: translating raw technical data into executive narratives that drive decisions.
You know that board members care about:
1. Financial impact — actual dollars, not percentages without context
2. Risk to business continuity — what could go wrong, probability, impact
3. Competitive positioning — are we ahead or behind the market?
4. Clear action items — what decision needs to be made, by when, with what investment?

You write with authority, brevity, and business context. You never use technical jargon without
translating it for a non-technical audience.

Always respond with valid JSON only. No markdown fences."""


@dataclass
class ExecutiveReport:
    title: str = ""
    executive_summary: str = ""
    key_findings: list = field(default_factory=list)
    key_metrics: dict = field(default_factory=dict)
    risks: list = field(default_factory=list)
    recommended_actions: list = field(default_factory=list)
    financial_narrative: str = ""
    raw_report: str = ""


class ReportGenerator:
    def __init__(self, model: Optional[str] = None):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-opus-4-6")

    def generate(self, metrics_input: str) -> ExecutiveReport:
        """
        Generate a board-ready executive report from raw metrics.

        Args:
            metrics_input: JSON string with metrics (cloud spend, utilization,
                          incident count, migration progress, security scores, etc.)

        Returns:
            ExecutiveReport with narrative, insights, risks, and recommendations
        """
        # Parse if JSON, otherwise use as-is
        try:
            metrics_data = json.loads(metrics_input)
            metrics_str = json.dumps(metrics_data, indent=2)
        except (json.JSONDecodeError, ValueError):
            metrics_str = metrics_input

        prompt = f"""Transform these raw technical metrics into a board-ready executive report.

The audience is: CEO, CFO, Board members — no technical background required.
Tone: Authoritative, clear, decisive. Lead with financial and business impact.

RAW METRICS:
{metrics_str[:6000]}

Return ONLY valid JSON with this structure:
{{
  "title": "<Board report title, e.g. 'Q1 2025 Cloud Transformation — Board Update'>",
  "executive_summary": "<3-4 sentences: current state, key achievement or concern, outlook. No jargon.>",
  "key_metrics": {{
    "<Metric Label>": "<formatted value with unit>",
    "<Metric Label>": "<formatted value with unit>"
  }},
  "key_findings": [
    "<finding with business context and dollar impact>",
    "<finding>",
    "<finding>",
    "<finding>",
    "<finding>"
  ],
  "risks": [
    {{
      "level": "<HIGH|MEDIUM|LOW>",
      "risk": "<risk title>",
      "impact": "<business impact in plain language>"
    }}
  ],
  "recommended_actions": [
    "<specific, time-bound action with owner and investment>",
    "<action>",
    "<action>"
  ],
  "financial_narrative": "<2-3 sentences on financial trajectory, burn rate vs. budget, and cost optimization opportunity>"
}}"""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text
        return self._parse(raw)

    def _parse(self, raw: str) -> ExecutiveReport:
        try:
            text = raw.strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            return ExecutiveReport(
                title=data.get("title", "Executive Report"),
                executive_summary=data.get("executive_summary", ""),
                key_findings=data.get("key_findings", []),
                key_metrics=data.get("key_metrics", {}),
                risks=data.get("risks", []),
                recommended_actions=data.get("recommended_actions", []),
                financial_narrative=data.get("financial_narrative", ""),
                raw_report=raw,
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return ExecutiveReport(
                title="Executive Report",
                executive_summary=raw[:500],
                raw_report=raw,
            )
