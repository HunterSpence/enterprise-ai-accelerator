"""
nl_interface.py — Natural language cost Q&A powered by Claude.

Stateful conversation: retains context across questions in a session.
Claude Haiku for simple queries, Sonnet for complex root cause analysis.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .cost_tracker import SpendData
from .anomaly_detector import Anomaly
from .optimizer import OptimizationPlan


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class ConversationSession:
    """Maintains conversation history for stateful Q&A."""
    session_id: str
    messages: list[Message] = field(default_factory=list)
    spend_context_injected: bool = False

    def add_user(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))

    def add_assistant(self, content: str) -> None:
        self.messages.append(Message(role="assistant", content=content))

    def to_api_messages(self) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def clear(self) -> None:
        self.messages.clear()
        self.spend_context_injected = False


@dataclass
class NLAnswer:
    """Response from the NL interface."""
    question: str
    answer: str
    model_used: str
    input_tokens: int
    output_tokens: int
    session_id: str


# ---------------------------------------------------------------------------
# NLInterface
# ---------------------------------------------------------------------------

class NLInterface:
    """
    Claude-powered natural language cost analyst.

    Usage:
        nl = NLInterface(anthropic_api_key="sk-ant-...", spend_data=data)
        session = nl.new_session()
        answer = nl.ask("Why did my bill spike on Tuesday?", session)
        print(answer.answer)

        # Follow-up (stateful — session remembers context)
        answer2 = nl.ask("What about EC2 specifically?", session)
    """

    SYSTEM_PROMPT = """You are a senior FinOps engineer and cloud cost analyst with 10+ years of experience optimizing AWS infrastructure costs. You have access to detailed spend data for the organization.

Your role:
- Answer cost questions in plain English that both engineers and CFOs can understand
- Be specific: use exact dollar amounts, percentages, service names, and dates from the data
- Lead with the direct answer (Pyramid Principle: conclusion first)
- Provide 2-3 supporting data points
- Always end with a concrete, actionable recommendation
- If asked about optimization, quantify the savings opportunity in dollars

Tone: Direct, data-driven, no fluff. Think McKinsey analyst, not sales engineer.
Format: Use bullet points for lists of 3+ items. Keep responses under 300 words unless a detailed breakdown is explicitly requested."""

    def __init__(
        self,
        anthropic_api_key: str | None = None,
        spend_data: SpendData | None = None,
        anomalies: list[Anomaly] | None = None,
        optimization_plan: OptimizationPlan | None = None,
        default_model: str = "claude-haiku-4-5",
        complex_model: str = "claude-sonnet-4-6",
    ) -> None:
        self.api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.spend_data = spend_data
        self.anomalies = anomalies or []
        self.optimization_plan = optimization_plan
        self.default_model = default_model
        self.complex_model = complex_model
        self._client: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_context(
        self,
        spend_data: SpendData,
        anomalies: list[Anomaly] | None = None,
        optimization_plan: OptimizationPlan | None = None,
    ) -> None:
        """Update the spend context (call before asking questions)."""
        self.spend_data = spend_data
        self.anomalies = anomalies or []
        self.optimization_plan = optimization_plan

    def new_session(self, session_id: str | None = None) -> ConversationSession:
        """Create a new conversation session."""
        import uuid
        return ConversationSession(
            session_id=session_id or str(uuid.uuid4())[:8]
        )

    def ask(
        self,
        question: str,
        session: ConversationSession | None = None,
        model: str | None = None,
    ) -> NLAnswer:
        """
        Ask a cost question. Returns NLAnswer with the response.
        If session is provided, maintains conversation history.
        """
        if not self.api_key:
            return self._mock_answer(question, session)

        client = self._get_client()

        # On first message, inject spend context as system context
        if session is None:
            session = self.new_session()

        context_block = ""
        if not session.spend_context_injected and self.spend_data:
            context_block = self._build_context_block()
            session.spend_context_injected = True

        # Classify query complexity to choose model
        use_model = model or self._classify_model(question)

        # Build user message (with context on first message)
        user_content = question
        if context_block:
            user_content = f"{context_block}\n\n---\n\nQuestion: {question}"

        session.add_user(user_content)

        try:
            response = client.messages.create(
                model=use_model,
                max_tokens=600,
                system=self.SYSTEM_PROMPT,
                messages=session.to_api_messages(),
            )
            answer_text = response.content[0].text.strip()
            session.add_assistant(answer_text)

            return NLAnswer(
                question=question,
                answer=answer_text,
                model_used=use_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                session_id=session.session_id,
            )

        except Exception as exc:
            fallback = self._rule_based_answer(question)
            session.add_assistant(fallback)
            return NLAnswer(
                question=question,
                answer=fallback,
                model_used="fallback",
                input_tokens=0,
                output_tokens=0,
                session_id=session.session_id,
            )

    def ask_batch(
        self,
        questions: list[str],
        shared_session: bool = True,
    ) -> list[NLAnswer]:
        """
        Ask multiple questions, optionally sharing a session for context continuity.
        """
        session = self.new_session() if shared_session else None
        answers: list[NLAnswer] = []
        for q in questions:
            s = session if shared_session else None
            answers.append(self.ask(q, session=s))
        return answers

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def _build_context_block(self) -> str:
        """Build a compact JSON context block from spend data for Claude."""
        if not self.spend_data:
            return ""

        # Top 15 services by spend
        top_services = [
            {"service": s.service, "total_spend": round(s.total, 2)}
            for s in self.spend_data.top_services(15)
        ]

        # Daily spend (last 30 days only to save tokens)
        daily_totals = self.spend_data.spend_by_date()
        recent_dates = sorted(daily_totals.keys())[-30:]
        daily_summary = {
            str(d): round(daily_totals[d], 2)
            for d in recent_dates
        }

        # Top anomalies summary
        anomaly_summary = [
            {
                "date": str(a.detected_at),
                "service": a.service,
                "delta": a.formatted_delta,
                "severity": a.severity.value,
                "explanation": a.explanation[:200] if a.explanation else "",
            }
            for a in self.anomalies[:5]
        ]

        # Optimization summary
        opt_summary = None
        if self.optimization_plan:
            top_opps = self.optimization_plan.top_opportunities(5)
            opt_summary = {
                "total_monthly_savings": self.optimization_plan.total_monthly_savings,
                "ri_sp_coverage_pct": self.optimization_plan.ri_sp_coverage_pct,
                "top_opportunities": [
                    {
                        "title": o.title,
                        "savings_monthly": o.savings_monthly,
                        "type": o.type.value,
                    }
                    for o in top_opps
                ],
            }

        context = {
            "account": {
                "id": self.spend_data.account_id,
                "name": self.spend_data.account_name,
                "query_period": f"{self.spend_data.query_start} to {self.spend_data.query_end}",
                "total_spend": self.spend_data.total_spend,
                "mtd_spend": self.spend_data.mtd_spend,
                "projected_monthly": self.spend_data.projected_monthly,
                "currency": self.spend_data.currency,
            },
            "top_services": top_services,
            "daily_spend_last_30d": daily_summary,
            "anomalies": anomaly_summary,
            "optimization": opt_summary,
            "tag_coverage": {
                "coverage_pct": self.spend_data.tag_coverage.coverage_pct if self.spend_data.tag_coverage else None,
                "untagged_spend": self.spend_data.tag_coverage.untagged_spend if self.spend_data.tag_coverage else None,
            },
        }

        return f"## AWS Cost Intelligence Context\n\n```json\n{json.dumps(context, indent=2, default=str)}\n```"

    def _classify_model(self, question: str) -> str:
        """Use Sonnet for complex analysis, Haiku for simple factual queries."""
        complex_keywords = [
            "why", "root cause", "explain", "analyze", "forecast",
            "recommend", "strategy", "what if", "compare", "optimize",
            "should we", "best way", "biggest", "most expensive",
        ]
        q_lower = question.lower()
        if any(kw in q_lower for kw in complex_keywords):
            return self.complex_model
        return self.default_model

    # ------------------------------------------------------------------
    # Rule-based fallback (no API key needed)
    # ------------------------------------------------------------------

    def _rule_based_answer(self, question: str) -> str:
        """Rule-based answers when Claude API is unavailable."""
        q_lower = question.lower()

        if self.spend_data:
            data = self.spend_data
            top = data.top_services(3)
            top_str = ", ".join(f"{s.service} (${s.total:,.0f})" for s in top)

            if any(w in q_lower for w in ["spike", "increase", "went up", "why did"]):
                anomalies = self.anomalies[:2]
                if anomalies:
                    a = anomalies[0]
                    return (
                        f"The largest cost anomaly detected: {a.service} on {a.detected_at} "
                        f"({a.formatted_delta}, severity: {a.severity.value}). "
                        f"{a.explanation or 'Review CloudWatch metrics for that date.'}"
                    )

            if any(w in q_lower for w in ["biggest", "most", "top", "largest"]):
                return f"Your top 3 cost drivers: {top_str}. These account for the majority of your total spend of ${data.total_spend:,.0f}."

            if any(w in q_lower for w in ["waste", "idle", "unused", "savings"]):
                if self.optimization_plan:
                    plan = self.optimization_plan
                    return (
                        f"${plan.total_monthly_savings:,.0f}/month in identified savings: "
                        f"${plan.waste_monthly:,.0f} waste elimination, "
                        f"${plan.rightsizing_monthly:,.0f} rightsizing, "
                        f"${plan.commitment_monthly:,.0f} from RI/SP optimization."
                    )

            if any(w in q_lower for w in ["reserved", "savings plan", "ri", "commitment"]):
                if self.optimization_plan:
                    return (
                        f"Current RI/SP coverage: {self.optimization_plan.ri_sp_coverage_pct:.0f}% "
                        f"(industry benchmark: 70%). "
                        f"Estimated monthly savings from better commitment coverage: "
                        f"${self.optimization_plan.commitment_monthly:,.0f}."
                    )

            if any(w in q_lower for w in ["forecast", "next month", "will spend", "projection"]):
                return (
                    f"Based on current trajectory: projected monthly spend is "
                    f"${data.projected_monthly:,.0f} "
                    f"(month-to-date: ${data.mtd_spend:,.0f}). "
                    "Use the Forecaster module for 30/60/90-day projections with confidence intervals."
                )

        return (
            "I need spend data context to answer cost questions accurately. "
            "Ensure CostTracker has been run and data has been loaded into the session."
        )

    def _mock_answer(self, question: str, session: ConversationSession | None) -> NLAnswer:
        """Return a rule-based answer without calling Claude."""
        answer = self._rule_based_answer(question)
        if session:
            session.add_user(question)
            session.add_assistant(answer)
        return NLAnswer(
            question=question,
            answer=answer,
            model_used="rule-based",
            input_tokens=0,
            output_tokens=0,
            session_id=session.session_id if session else "no-session",
        )

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client
