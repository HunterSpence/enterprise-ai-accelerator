"""
CloudIQ V2 — Slack integration.

Posts anomaly alerts and weekly cost digests to Slack via webhook.
Fully async using httpx. Supports Block Kit formatting for rich messages.

Usage:
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/services/...")
    await notifier.post_anomaly_alert(alert)
    await notifier.post_weekly_digest(summary)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from cloud_iq.models import AnomalyAlert, Severity

logger = logging.getLogger(__name__)

SEVERITY_EMOJI: dict[str, str] = {
    "critical": ":rotating_light:",
    "high": ":warning:",
    "medium": ":large_yellow_circle:",
    "low": ":information_source:",
}

SEVERITY_COLOR: dict[str, str] = {
    "critical": "#FF0000",
    "high": "#FF6B00",
    "medium": "#FFD700",
    "low": "#36A64F",
}


class SlackNotifier:
    """
    Async Slack notifier for CloudIQ anomaly alerts and cost digests.

    All methods are async and use httpx for non-blocking HTTP. The class
    is designed for use inside FastAPI background tasks or asyncio workers.
    """

    def __init__(
        self,
        webhook_url: str,
        channel: str | None = None,
        timeout_seconds: float = 10.0,
        dry_run: bool = False,
    ) -> None:
        self._webhook_url = webhook_url
        self._channel = channel
        self._timeout = timeout_seconds
        self._dry_run = dry_run

    async def post_anomaly_alert(self, alert: AnomalyAlert) -> bool:
        """
        Post a cost anomaly alert to Slack with Block Kit formatting.

        Returns True on success, False on failure (does not raise).
        """
        emoji = SEVERITY_EMOJI.get(alert.severity.value, ":bell:")
        color = SEVERITY_COLOR.get(alert.severity.value, "#808080")

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} CloudIQ Cost Anomaly — {alert.severity.value.upper()}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Resource:*\n`{alert.resource_id}`"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{alert.resource_type}"},
                    {"type": "mrkdwn", "text": f"*Region:*\n{alert.region}"},
                    {"type": "mrkdwn", "text": f"*Cost Impact:*\n${alert.cost_impact_usd:,.0f}/mo"},
                    {"type": "mrkdwn", "text": f"*Anomaly Score:*\n{alert.anomaly_score:.2f} / 1.00"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Detected:*\n{alert.detected_at.strftime('%Y-%m-%d %H:%M UTC')}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Description:*\n{alert.description}"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View in CloudIQ"},
                        "style": "primary" if alert.severity == Severity.CRITICAL else "default",
                        "url": f"https://cloudiq.example.com/alerts/{alert.alert_id}",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Acknowledge"},
                        "value": f"ack:{alert.alert_id}",
                    },
                ],
            },
        ]

        payload: dict[str, Any] = {
            "attachments": [
                {
                    "color": color,
                    "blocks": blocks,
                    "fallback": f"CloudIQ Alert: {alert.description}",
                }
            ]
        }

        if self._channel:
            payload["channel"] = self._channel

        return await self._post(payload)

    async def post_weekly_digest(
        self,
        account_id: str,
        total_monthly_cost: float,
        total_waste: float,
        top_recommendations: list[dict[str, Any]],
        anomaly_count: int,
    ) -> bool:
        """Post a weekly cost digest summary with top recommendations."""
        waste_pct = (total_waste / total_monthly_cost * 100) if total_monthly_cost else 0

        rec_lines = "\n".join(
            f"• {r.get('category', 'Unknown')}: *${r.get('monthly_waste_usd', 0):,.0f}/mo* — {r.get('resource_id', '')}"
            for r in top_recommendations[:5]
        )

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":bar_chart: CloudIQ Weekly Cost Digest",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Account:*\n`{account_id}`"},
                    {"type": "mrkdwn", "text": f"*Monthly Spend:*\n${total_monthly_cost:,.0f}"},
                    {"type": "mrkdwn", "text": f"*Identified Waste:*\n${total_waste:,.0f} ({waste_pct:.1f}%)"},
                    {"type": "mrkdwn", "text": f"*New Anomalies:*\n{anomaly_count} this week"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Top Recommendations:*\n{rec_lines or '_No new recommendations_'}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Generated by CloudIQ at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                    }
                ],
            },
        ]

        return await self._post({"blocks": blocks})

    async def post_budget_warning(
        self,
        account_id: str,
        budget_usd: float,
        current_spend_usd: float,
        exhaustion_date: datetime | None,
    ) -> bool:
        """Post a budget exhaustion warning."""
        pct_used = (current_spend_usd / budget_usd * 100) if budget_usd else 0
        exhaustion_str = (
            exhaustion_date.strftime("%B %d, %Y")
            if exhaustion_date
            else "unknown"
        )

        text = (
            f":money_with_wings: *Budget Warning* — Account `{account_id}`\n"
            f"Current spend: ${current_spend_usd:,.0f} ({pct_used:.1f}% of ${budget_usd:,.0f} budget)\n"
            f"At current burn rate, budget exhaustion projected: *{exhaustion_str}*"
        )

        return await self._post({"text": text})

    async def _post(self, payload: dict[str, Any]) -> bool:
        """Send a payload to the Slack webhook URL."""
        if self._dry_run:
            logger.info("slack_dry_run", payload_keys=list(payload.keys()))
            return True

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._webhook_url,
                    json=payload,
                )
                if response.status_code == 200:
                    return True
                logger.warning(
                    "slack_post_failed",
                    status=response.status_code,
                    body=response.text[:200],
                )
                return False
        except Exception as exc:
            logger.error("slack_post_error", error=str(exc))
            return False
