"""
CloudIQ V2 — PagerDuty integration.

Pages the on-call engineer for critical cost spikes via the PagerDuty
Events API v2. Also supports resolving incidents when anomalies clear.

API reference:
    https://developer.pagerduty.com/api-reference/YXBpOjI3NDgyNjU-pager-duty-v2-events-api

Usage:
    pd = PagerDutyIntegration(
        integration_key="your-32-char-routing-key",
        dry_run=False,
    )
    incident_key = await pd.trigger_cost_spike(alert)
    await pd.resolve_incident(incident_key)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from cloud_iq.models import AnomalyAlert

logger = logging.getLogger(__name__)

PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

SEVERITY_MAP: dict[str, str] = {
    "critical": "critical",
    "high": "error",
    "medium": "warning",
    "low": "info",
}


class PagerDutyIntegration:
    """
    PagerDuty Events API v2 integration for critical cost anomalies.

    Only pages for critical/high severity by default to avoid alert fatigue.
    Deduplicated by resource_id + alert_id so the same spike doesn't page twice.
    """

    def __init__(
        self,
        integration_key: str,
        min_severity_to_page: str = "high",
        dry_run: bool = False,
    ) -> None:
        self._integration_key = integration_key
        self._min_severity = min_severity_to_page
        self._dry_run = dry_run

        self._sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def _should_page(self, severity: str) -> bool:
        """Return True if this severity level should trigger a page."""
        return (
            self._sev_order.get(severity, 4)
            <= self._sev_order.get(self._min_severity, 1)
        )

    def _dedup_key(self, resource_id: str, category: str) -> str:
        """
        Generate a stable dedup key so the same underlying issue
        doesn't create multiple open PagerDuty incidents.
        """
        raw = f"cloudiq:{resource_id}:{category}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    async def trigger_cost_spike(
        self,
        alert: AnomalyAlert,
        source: str = "cloudiq",
    ) -> str | None:
        """
        Fire a PagerDuty alert for a cost anomaly.

        Returns the dedup_key (incident key) on success, None on failure.
        Silently skips if severity is below the configured minimum.
        """
        if not self._should_page(alert.severity.value):
            logger.debug(
                "pagerduty_skip_low_severity",
                severity=alert.severity,
                min_severity=self._min_severity,
            )
            return None

        dedup_key = self._dedup_key(alert.resource_id, alert.description[:40])

        payload: dict[str, Any] = {
            "routing_key": self._integration_key,
            "event_action": "trigger",
            "dedup_key": dedup_key,
            "payload": {
                "summary": (
                    f"[CloudIQ {alert.severity.value.upper()}] "
                    f"{alert.resource_type} {alert.resource_id} — "
                    f"${alert.cost_impact_usd:,.0f}/mo anomaly in {alert.region}"
                ),
                "source": source,
                "severity": SEVERITY_MAP.get(alert.severity.value, "warning"),
                "timestamp": alert.detected_at.isoformat(),
                "component": alert.resource_type,
                "group": alert.region,
                "class": "cost_anomaly",
                "custom_details": {
                    "resource_id": alert.resource_id,
                    "region": alert.region,
                    "provider": alert.provider.value,
                    "anomaly_score": alert.anomaly_score,
                    "cost_impact_usd": alert.cost_impact_usd,
                    "description": alert.description,
                    "dimensions": alert.dimensions,
                },
            },
            "links": [
                {
                    "href": f"https://cloudiq.example.com/alerts/{alert.alert_id}",
                    "text": "View in CloudIQ",
                }
            ],
            "images": [],
        }

        if self._dry_run:
            logger.info(
                "pagerduty_dry_run",
                dedup_key=dedup_key,
                severity=alert.severity.value,
                resource=alert.resource_id,
            )
            return dedup_key

        return await self._send_event(payload, dedup_key)

    async def resolve_incident(self, dedup_key: str) -> bool:
        """
        Resolve a PagerDuty incident by dedup_key.

        Should be called when an anomaly clears (cost returns to baseline).
        """
        if self._dry_run:
            logger.info("pagerduty_resolve_dry_run", dedup_key=dedup_key)
            return True

        payload: dict[str, Any] = {
            "routing_key": self._integration_key,
            "event_action": "resolve",
            "dedup_key": dedup_key,
        }

        result = await self._send_event(payload, dedup_key)
        return result is not None

    async def acknowledge_incident(self, dedup_key: str) -> bool:
        """Acknowledge a PagerDuty incident (suppress further notifications)."""
        if self._dry_run:
            return True

        payload: dict[str, Any] = {
            "routing_key": self._integration_key,
            "event_action": "acknowledge",
            "dedup_key": dedup_key,
        }

        result = await self._send_event(payload, dedup_key)
        return result is not None

    async def _send_event(
        self, payload: dict[str, Any], dedup_key: str
    ) -> str | None:
        """Post to PagerDuty Events API v2. Returns dedup_key on success."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    PAGERDUTY_EVENTS_URL,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )

                if response.status_code in (200, 201, 202):
                    data = response.json()
                    logger.info(
                        "pagerduty_event_sent",
                        dedup_key=dedup_key,
                        status=data.get("status"),
                        message=data.get("message"),
                    )
                    return dedup_key

                logger.warning(
                    "pagerduty_send_failed",
                    status=response.status_code,
                    body=response.text[:200],
                )
                return None

        except Exception as exc:
            logger.error("pagerduty_send_error", error=str(exc))
            return None
