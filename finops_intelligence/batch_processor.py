"""
finops_intelligence/batch_processor.py
======================================

Bulk anomaly-explanation processor backed by the Anthropic Message Batches API.

Problem:
At enterprise scale, a monthly FinOps review can surface hundreds of cost
anomalies — each one needs a plain-English explanation, a root-cause
hypothesis, and a remediation recommendation. Running them serially through
real-time inference is slow and costs full list price.

Solution:
Batch them. Anthropic's Messages Batches API processes up to 10,000
requests async and charges 50% of standard pricing. We build each request
with a forced tool call (structured output) so the downstream dashboard
can render without brittle string parsing.

Usage:

    batcher = AnomalyBatchProcessor()
    batch = await batcher.submit(anomalies)          # anomalies: list[dict]
    # ... poll or wait ...
    results = await batcher.collect(batch["id"])
    for anomaly_id, explanation in results.items():
        print(anomaly_id, explanation["root_cause"])
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from core import AIClient, MODEL_WORKER
from core.ai_client import BatchRequest


_EXPLANATION_SCHEMA = {
    "type": "object",
    "required": ["root_cause", "explanation", "recommended_action", "severity"],
    "properties": {
        "root_cause": {"type": "string"},
        "explanation": {
            "type": "string",
            "description": "Plain-English description for a non-technical stakeholder.",
        },
        "recommended_action": {"type": "string"},
        "severity": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
        },
        "potential_monthly_savings_usd": {"type": "number", "minimum": 0},
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
    },
}


_BATCH_SYSTEM_PROMPT = (
    "You are a FinOps analyst explaining a cloud cost anomaly. "
    "Given the anomaly record (service, resource, cost delta, time window), "
    "produce a structured explanation for the FinOps dashboard. "
    "Be specific about what drove the spike and what action would reduce "
    "the recurring cost. If data is insufficient for a confident call, say so."
)


@dataclass
class AnomalyBatchResult:
    anomaly_id: str
    status: str
    root_cause: str = ""
    explanation: str = ""
    recommended_action: str = ""
    severity: str = ""
    confidence: str = ""
    potential_monthly_savings_usd: float = 0.0
    error: str | None = None


class AnomalyBatchProcessor:
    """Submit FinOps cost anomalies to Anthropic Batches API and collect results."""

    def __init__(self, ai: AIClient | None = None, model: str = MODEL_WORKER) -> None:
        self._ai = ai or AIClient(default_model=model)
        self._model = model

    def _build_requests(self, anomalies: list[dict[str, Any]]) -> list[BatchRequest]:
        requests: list[BatchRequest] = []
        for idx, anomaly in enumerate(anomalies):
            custom_id = str(anomaly.get("id") or anomaly.get("anomaly_id") or f"anomaly_{idx}")
            user_content = (
                "Explain this cost anomaly:\n\n"
                f"```json\n{json.dumps(anomaly, indent=2, default=str)}\n```"
            )
            requests.append(BatchRequest(
                custom_id=custom_id,
                model=self._model,
                system=_BATCH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=512,
                tools=[{
                    "name": "emit_anomaly_explanation",
                    "description": "Return the structured anomaly explanation.",
                    "input_schema": _EXPLANATION_SCHEMA,
                }],
                tool_choice={"type": "tool", "name": "emit_anomaly_explanation"},
            ))
        return requests

    async def submit(self, anomalies: list[dict[str, Any]]) -> dict[str, Any]:
        """Submit the batch. Returns the batch metadata (including ``id``)."""
        requests = self._build_requests(anomalies)
        return await self._ai.submit_batch(requests)

    async def collect(
        self,
        batch_id: str,
        *,
        poll_interval_s: float = 5.0,
        timeout_s: float = 3600.0,
    ) -> dict[str, AnomalyBatchResult]:
        """Poll the batch until complete, then return ``{custom_id: result}``."""
        elapsed = 0.0
        while elapsed < timeout_s:
            batch = await self._ai.retrieve_batch(batch_id)
            status = batch.get("processing_status") or batch.get("status")
            if status in ("ended", "completed", "canceled", "failed"):
                return await self._fetch_results(batch)
            await asyncio.sleep(poll_interval_s)
            elapsed += poll_interval_s
        raise TimeoutError(f"Batch {batch_id} did not complete within {timeout_s}s")

    async def _fetch_results(self, batch: dict[str, Any]) -> dict[str, AnomalyBatchResult]:
        """Turn a completed batch object into dict of structured results.

        Anthropic exposes per-request results via a streaming results file.
        We read them through the underlying AsyncAnthropic client; if the
        results endpoint is unavailable (older SDK) we fall back to an empty
        map so the caller gets a clear signal rather than a silent crash.
        """
        results: dict[str, AnomalyBatchResult] = {}
        batch_id = batch.get("id", "")

        client = self._ai.raw
        try:
            stream = await client.messages.batches.results(batch_id)
        except Exception as exc:  # pragma: no cover - SDK-specific
            return {"__error__": AnomalyBatchResult(anomaly_id="__error__", status="failed", error=str(exc))}

        async for entry in stream:
            entry_dict = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
            custom_id = entry_dict.get("custom_id", "unknown")
            result = entry_dict.get("result", {}) or {}
            r_type = result.get("type")

            if r_type == "succeeded":
                message = result.get("message", {}) or {}
                data = _extract_tool_input(message, "emit_anomaly_explanation")
                results[custom_id] = AnomalyBatchResult(
                    anomaly_id=custom_id,
                    status="succeeded",
                    root_cause=data.get("root_cause", ""),
                    explanation=data.get("explanation", ""),
                    recommended_action=data.get("recommended_action", ""),
                    severity=data.get("severity", ""),
                    confidence=data.get("confidence", ""),
                    potential_monthly_savings_usd=float(
                        data.get("potential_monthly_savings_usd", 0) or 0
                    ),
                )
            else:
                err = result.get("error", {}) or {}
                results[custom_id] = AnomalyBatchResult(
                    anomaly_id=custom_id,
                    status=r_type or "failed",
                    error=err.get("message") or json.dumps(err, default=str),
                )

        return results


def _extract_tool_input(message: dict[str, Any], tool_name: str) -> dict[str, Any]:
    """Pull the structured tool-use input out of a batch result message."""
    for block in message.get("content", []) or []:
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            return block.get("input", {}) or {}
    return {}
