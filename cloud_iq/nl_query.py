"""
Natural language query interface for CloudIQ.

Translates plain English questions into infrastructure insights using Claude,
with the full InfrastructureSnapshot and CostReport as context.
Maintains conversation state within a session.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from cloud_iq.cost_analyzer import CostReport
from cloud_iq.scanner import InfrastructureSnapshot

logger = logging.getLogger(__name__)

try:
    import anthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    question: str
    answer: str
    supporting_data: list[dict[str, Any]]
    model_used: str
    tokens_used: int
    timestamp: datetime


@dataclass
class ConversationTurn:
    role: str  # "user" | "assistant"
    content: str


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------


def _build_infrastructure_context(snapshot: InfrastructureSnapshot) -> str:
    """Serialize snapshot to a compact JSON context suitable for LLM injection."""
    context: dict[str, Any] = {
        "account_id": snapshot.account_id,
        "scanned_at": snapshot.scanned_at.isoformat(),
        "regions": snapshot.regions,
        "total_estimated_monthly_cost_usd": snapshot.total_estimated_monthly_cost,
        "resource_counts": snapshot.resource_counts,
        "ec2_instances": [
            {
                "id": i.instance_id,
                "type": i.instance_type,
                "state": i.state,
                "region": i.region,
                "monthly_cost": i.estimated_monthly_cost,
                "name": i.tags.get("Name", ""),
                "env": i.tags.get("Environment", i.tags.get("Env", "")),
            }
            for i in snapshot.ec2_instances[:50]
        ],
        "rds_instances": [
            {
                "id": r.db_instance_id,
                "class": r.db_instance_class,
                "engine": r.engine,
                "status": r.status,
                "monthly_cost": r.estimated_monthly_cost,
                "multi_az": r.multi_az,
                "encrypted": r.encrypted,
            }
            for r in snapshot.rds_instances[:20]
        ],
        "lambda_functions": [
            {
                "name": f.function_name,
                "runtime": f.runtime,
                "memory_mb": f.memory_mb,
                "region": f.region,
            }
            for f in snapshot.lambda_functions[:30]
        ],
        "s3_buckets": [
            {
                "name": b.name,
                "region": b.region,
                "versioning": b.versioning,
                "encryption": b.encryption,
                "public_access_blocked": b.public_access_blocked,
                "monthly_cost": b.estimated_monthly_cost,
            }
            for b in snapshot.s3_buckets[:30]
        ],
        "eks_clusters": [
            {
                "name": c.cluster_name,
                "version": c.kubernetes_version,
                "status": c.status,
                "node_groups": len(c.node_groups),
                "monthly_cost": c.estimated_monthly_cost,
            }
            for c in snapshot.eks_clusters
        ],
        "unattached_ebs_volumes": [
            {
                "id": v.volume_id,
                "size_gb": v.size_gb,
                "region": v.region,
                "monthly_cost": v.estimated_monthly_cost,
            }
            for v in snapshot.ebs_volumes
            if v.attached_instance is None
        ],
        "idle_elastic_ips": [
            {
                "ip": e.public_ip,
                "region": e.region,
                "monthly_cost": e.estimated_monthly_cost,
            }
            for e in snapshot.elastic_ips
            if e.is_idle
        ],
    }
    return json.dumps(context, indent=2, default=str)


def _build_cost_context(report: CostReport | None) -> str:
    if not report:
        return "{}"
    context: dict[str, Any] = {
        "report_date": report.report_date.isoformat(),
        "monthly_avg_cost_usd": report.monthly_avg_cost,
        "total_identified_waste_usd": report.total_identified_waste,
        "total_rightsizing_savings_usd": report.total_rightsizing_savings,
        "annual_savings_opportunity_usd": report.annual_savings_opportunity,
        "top_cost_drivers": [
            {
                "service": d.service,
                "monthly_cost": d.monthly_cost,
                "percentage": d.percentage_of_total,
            }
            for d in report.top_cost_drivers[:10]
        ],
        "top_waste_items": [
            {
                "category": w.category,
                "resource_id": w.resource_id,
                "region": w.region,
                "monthly_waste_usd": w.estimated_monthly_waste,
                "severity": w.severity,
                "description": w.description,
                "recommendation": w.recommendation,
            }
            for w in report.waste_items[:20]
        ],
        "rightsizing_recommendations": [
            {
                "instance_id": r.instance_id,
                "current_type": r.instance_type,
                "recommended_type": r.recommended_instance_type,
                "monthly_savings_usd": r.monthly_savings,
                "avg_cpu_pct": r.avg_cpu_utilization,
                "confidence": r.confidence,
            }
            for r in report.rightsizing_recommendations[:10]
        ],
    }
    return json.dumps(context, indent=2, default=str)


SYSTEM_PROMPT = """\
You are CloudIQ, an expert AWS cloud infrastructure analyst. You have access to a
complete real-time snapshot of an AWS account's infrastructure and cost data.

Your role is to answer questions about the infrastructure clearly and precisely,
always referencing specific resource IDs, dollar amounts, and concrete recommendations.

Guidelines:
- Lead with the direct answer, then provide supporting detail.
- Always cite specific resource names and IDs when available.
- Express costs in dollars to two decimal places.
- When recommending actions, be concrete: give the exact AWS CLI command or
  Terraform change if helpful.
- If a question is outside the scope of the provided infrastructure data, say so
  honestly rather than speculating.
- Format lists and tables using plain text — no markdown headers.
"""


# ---------------------------------------------------------------------------
# Query engine
# ---------------------------------------------------------------------------


class NLQueryEngine:
    """
    Stateful natural language query interface for AWS infrastructure.

    Maintains conversation history within a session so follow-up questions
    like "What about the RDS instances?" resolve correctly.
    """

    def __init__(
        self,
        snapshot: InfrastructureSnapshot,
        cost_report: CostReport | None = None,
        anthropic_api_key: str | None = None,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self._snapshot = snapshot
        self._cost_report = cost_report
        self._api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        self._history: list[ConversationTurn] = []
        self._query_log: list[QueryResult] = []

        self._infra_context = _build_infrastructure_context(snapshot)
        self._cost_context = _build_cost_context(cost_report)

        if not _ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic package is required for NLQueryEngine. "
                "Install it with: pip install anthropic"
            )
        if not self._api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Set it or pass anthropic_api_key= to NLQueryEngine."
            )

        self._client = anthropic.Anthropic(api_key=self._api_key)

    def _build_messages(self, question: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []

        # Inject infrastructure context on the first turn only
        if not self._history:
            context_injection = (
                f"Infrastructure snapshot:\n```json\n{self._infra_context}\n```\n\n"
                f"Cost analysis:\n```json\n{self._cost_context}\n```\n\n"
                f"Question: {question}"
            )
            messages.append({"role": "user", "content": context_injection})
        else:
            for turn in self._history:
                messages.append({"role": turn.role, "content": turn.content})
            messages.append({"role": "user", "content": question})

        return messages

    def query(self, question: str) -> QueryResult:
        """
        Answer a natural language question about the infrastructure.

        Maintains conversation state so follow-up questions work naturally.
        Returns a QueryResult with the answer and supporting data.
        """
        messages = self._build_messages(question)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        answer = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens

        # Update conversation history
        if not self._history:
            self._history.append(
                ConversationTurn(
                    role="user",
                    content=(
                        f"[Infrastructure context provided. See snapshot and cost data.]\n\n"
                        f"Question: {question}"
                    ),
                )
            )
        else:
            self._history.append(ConversationTurn(role="user", content=question))
        self._history.append(ConversationTurn(role="assistant", content=answer))

        # Extract supporting data references from the answer
        supporting_data = self._extract_resource_references(answer)

        result = QueryResult(
            question=question,
            answer=answer,
            supporting_data=supporting_data,
            model_used=self._model,
            tokens_used=tokens,
            timestamp=datetime.now(timezone.utc),
        )
        self._query_log.append(result)
        return result

    def _extract_resource_references(self, answer: str) -> list[dict[str, Any]]:
        """Pull out any resource IDs mentioned in the answer for cross-referencing."""
        import re

        resources: list[dict[str, Any]] = []
        instance_ids = re.findall(r"\bi-[0-9a-f]{8,17}\b", answer)
        for iid in set(instance_ids):
            matching = [
                i for i in self._snapshot.ec2_instances if i.instance_id == iid
            ]
            if matching:
                inst = matching[0]
                resources.append(
                    {
                        "type": "EC2 Instance",
                        "id": iid,
                        "instance_type": inst.instance_type,
                        "state": inst.state,
                        "monthly_cost": inst.estimated_monthly_cost,
                    }
                )

        db_ids = re.findall(r"\b[a-z][a-z0-9-]{2,62}(?=.*rds|.*db)\b", answer.lower())
        for db_id in set(db_ids):
            matching = [
                r for r in self._snapshot.rds_instances if r.db_instance_id == db_id
            ]
            if matching:
                inst = matching[0]
                resources.append(
                    {
                        "type": "RDS Instance",
                        "id": db_id,
                        "class": inst.db_instance_class,
                        "monthly_cost": inst.estimated_monthly_cost,
                    }
                )

        return resources

    def reset_conversation(self) -> None:
        """Clear conversation history while retaining infrastructure context."""
        self._history.clear()

    @property
    def conversation_turns(self) -> int:
        return len(self._history) // 2

    @property
    def query_history(self) -> list[QueryResult]:
        return list(self._query_log)
