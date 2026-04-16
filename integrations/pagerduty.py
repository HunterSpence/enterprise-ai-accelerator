"""
integrations/pagerduty.py — PagerDuty Events API v2 adapter.

Sends trigger events using the Events API v2 (free tier — no paid plan needed).
By default only fires on critical severity; configurable via fire_on parameter.

Env vars:
    EAA_PAGERDUTY_ROUTING_KEY  Integration/routing key from PD service integration
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from integrations.base import Finding, IntegrationAdapter, IntegrationResult

logger = logging.getLogger(__name__)

_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

# PagerDuty severity values accepted by Events API v2
_PD_SEVERITY: dict[str, str] = {
    "critical": "critical",
    "high":     "error",
    "medium":   "warning",
    "low":      "info",
    "info":     "info",
}

_DEFAULT_FIRE_ON = frozenset({"critical"})


class PagerDutyEventsAdapter(IntegrationAdapter):
    """
    Sends PagerDuty alert events via Events API v2 (free tier compatible).

    Args:
        routing_key: PD Integration/Routing key from the service integration page.
        fire_on:     Set of severities that trigger an alert. Default: {"critical"}.
                     Pass {"critical", "high"} to also page on high-severity findings.
        dry_run:     Return success without HTTP calls.
        timeout:     HTTP timeout seconds.
    """

    name = "pagerduty"

    def __init__(
        self,
        routing_key: str,
        fire_on: set[str] | None = None,
        dry_run: bool = False,
        timeout: float = 10.0,
    ) -> None:
        self.routing_key = routing_key
        self.fire_on = fire_on if fire_on is not None else set(_DEFAULT_FIRE_ON)
        self.dry_run = dry_run
        self.timeout = timeout

    def _should_fire(self, finding: Finding) -> bool:
        return finding.severity in self.fire_on

    def _build_payload(self, finding: Finding) -> dict[str, Any]:
        custom_details: dict[str, Any] = {
            "module": finding.module,
            "description": finding.description[:1000],
        }
        if finding.resource_id:
            custom_details["resource_id"] = finding.resource_id
        if finding.tags:
            custom_details["tags"] = finding.tags
        if finding.remediation:
            custom_details["remediation"] = finding.remediation[:500]
        custom_details["finding_id"] = finding.id

        payload: dict[str, Any] = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "dedup_key": finding.id,  # idempotency — same finding won't re-page
            "payload": {
                "summary": f"[{finding.severity.upper()}] {finding.title}",
                "severity": _PD_SEVERITY.get(finding.severity, "warning"),
                "source": f"eaa:{finding.module}",
                "custom_details": custom_details,
            },
        }

        if finding.resource_id:
            payload["payload"]["component"] = finding.resource_id

        return payload

    async def send(self, finding: Finding) -> IntegrationResult:
        if self.dry_run:
            return IntegrationResult.dry(f"pagerduty:{finding.id}", adapter=self.name)

        if not self._should_fire(finding):
            logger.debug(
                "PagerDutyEventsAdapter: skipping severity=%s (fire_on=%s)",
                finding.severity,
                self.fire_on,
            )
            return IntegrationResult.success(
                f"pagerduty:skipped:{finding.severity}", adapter=self.name
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    _EVENTS_URL,
                    json=self._build_payload(finding),
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:200]
            msg = f"PagerDuty HTTP {exc.response.status_code}: {body}"
            logger.error("PagerDutyEventsAdapter: %s", msg)
            return IntegrationResult.failure(msg, adapter=self.name)
        except Exception as exc:
            logger.error("PagerDutyEventsAdapter unexpected error: %s", exc)
            return IntegrationResult.failure(str(exc), adapter=self.name)

        dedup_key = data.get("dedup_key", "")
        logger.info("PagerDutyEventsAdapter: triggered event %s", dedup_key)
        return IntegrationResult.success(f"pagerduty:{dedup_key}", adapter=self.name)
