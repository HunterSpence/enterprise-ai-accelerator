"""
migration_scout/batch_classifier.py
===================================

Bulk 6R classifier backed by Anthropic Message Batches API.

Use when your migration inventory is big enough that you don't want 800
serial synchronous calls (e.g. a multi-BU enterprise with thousands of
workloads). Submitting a batch gets you 50% off standard pricing and
guaranteed throughput within 24 hours.

Produces one ``WorkloadClassification`` per workload, with a schema that
matches the real-time ``assessor.py`` output so downstream code can treat
real-time and batch results interchangeably.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from core import AIClient, MODEL_WORKER
from core.ai_client import BatchRequest


_CLASSIFIER_SCHEMA = {
    "type": "object",
    "required": ["workload_name", "strategy", "rationale", "effort", "risk"],
    "properties": {
        "workload_name": {"type": "string"},
        "strategy": {
            "type": "string",
            "enum": ["Retire", "Retain", "Rehost", "Replatform", "Repurchase", "Refactor"],
        },
        "rationale": {"type": "string"},
        "effort": {"type": "string", "enum": ["low", "medium", "high"]},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "estimated_weeks": {"type": "integer", "minimum": 0},
        "target_cloud": {
            "type": "string",
            "enum": ["aws", "azure", "gcp", "oci", "none"],
            "description": "Suggested target cloud (or 'none' if Retain/Retire).",
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "dependencies_to_migrate_first": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


_SYSTEM_PROMPT = (
    "You are an AWS/Azure/GCP migration strategist applying the 6R framework "
    "(Retire, Retain, Rehost, Replatform, Repurchase, Refactor). "
    "Classify the supplied workload and justify the strategy with concrete "
    "technical and business reasoning. Be conservative on effort estimates — "
    "prefer 'medium' to 'low' when there is schedule uncertainty."
)


@dataclass
class WorkloadClassification:
    workload_name: str
    status: str = "pending"
    strategy: str = ""
    rationale: str = ""
    effort: str = ""
    risk: str = ""
    estimated_weeks: int = 0
    target_cloud: str = "none"
    confidence: str = "medium"
    dependencies_to_migrate_first: list[str] = field(default_factory=list)
    error: str | None = None


class BatchClassifier:
    """Submit migration inventories to the Batches API for bulk 6R classification."""

    def __init__(self, ai: AIClient | None = None, model: str = MODEL_WORKER) -> None:
        self._ai = ai or AIClient(default_model=model)
        self._model = model

    def _build_requests(self, workloads: list[dict[str, Any]]) -> list[BatchRequest]:
        requests: list[BatchRequest] = []
        for idx, workload in enumerate(workloads):
            name = workload.get("name") or workload.get("workload_name") or f"workload_{idx}"
            custom_id = str(workload.get("id") or f"{name}_{idx}")
            user = (
                "Classify this workload using the 6R framework:\n\n"
                f"```json\n{json.dumps(workload, indent=2, default=str)}\n```"
            )
            requests.append(BatchRequest(
                custom_id=custom_id,
                model=self._model,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user}],
                max_tokens=768,
                tools=[{
                    "name": "emit_6r_classification",
                    "description": "Return the structured 6R classification for this workload.",
                    "input_schema": _CLASSIFIER_SCHEMA,
                }],
                tool_choice={"type": "tool", "name": "emit_6r_classification"},
            ))
        return requests

    async def submit(self, workloads: list[dict[str, Any]]) -> dict[str, Any]:
        requests = self._build_requests(workloads)
        return await self._ai.submit_batch(requests)

    async def collect(
        self,
        batch_id: str,
        *,
        poll_interval_s: float = 5.0,
        timeout_s: float = 7200.0,
    ) -> dict[str, WorkloadClassification]:
        elapsed = 0.0
        while elapsed < timeout_s:
            batch = await self._ai.retrieve_batch(batch_id)
            status = batch.get("processing_status") or batch.get("status")
            if status in ("ended", "completed", "canceled", "failed"):
                return await self._fetch_results(batch)
            await asyncio.sleep(poll_interval_s)
            elapsed += poll_interval_s
        raise TimeoutError(f"Batch {batch_id} did not complete within {timeout_s}s")

    async def _fetch_results(self, batch: dict[str, Any]) -> dict[str, WorkloadClassification]:
        out: dict[str, WorkloadClassification] = {}
        batch_id = batch.get("id", "")
        client = self._ai.raw
        try:
            stream = await client.messages.batches.results(batch_id)
        except Exception as exc:  # pragma: no cover
            return {"__error__": WorkloadClassification(workload_name="__error__", status="failed", error=str(exc))}

        async for entry in stream:
            entry_dict = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
            custom_id = entry_dict.get("custom_id", "unknown")
            result = entry_dict.get("result", {}) or {}
            r_type = result.get("type")
            if r_type == "succeeded":
                msg = result.get("message", {}) or {}
                data = _extract_tool_input(msg, "emit_6r_classification")
                out[custom_id] = WorkloadClassification(
                    workload_name=data.get("workload_name", custom_id),
                    status="succeeded",
                    strategy=data.get("strategy", ""),
                    rationale=data.get("rationale", ""),
                    effort=data.get("effort", ""),
                    risk=data.get("risk", ""),
                    estimated_weeks=int(data.get("estimated_weeks", 0) or 0),
                    target_cloud=data.get("target_cloud", "none"),
                    confidence=data.get("confidence", "medium"),
                    dependencies_to_migrate_first=data.get("dependencies_to_migrate_first", []),
                )
            else:
                err = result.get("error", {}) or {}
                out[custom_id] = WorkloadClassification(
                    workload_name=custom_id,
                    status=r_type or "failed",
                    error=err.get("message") or json.dumps(err, default=str),
                )
        return out


def _extract_tool_input(message: dict[str, Any], tool_name: str) -> dict[str, Any]:
    for block in message.get("content", []) or []:
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            return block.get("input", {}) or {}
    return {}
