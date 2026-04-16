"""
integrations/slack.py — Slack Incoming Webhook adapter.

Posts color-coded Block Kit messages. Works with any free Slack workspace
Incoming Webhook — no OAuth, no API key, just the webhook URL.

Env var: EAA_SLACK_WEBHOOK_URL
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from integrations.base import Finding, IntegrationAdapter, IntegrationResult

logger = logging.getLogger(__name__)

# Severity → sidebar color
_COLORS: dict[str, str] = {
    "critical": "#CC0000",
    "high":     "#E03E2D",
    "medium":   "#F0A500",
    "low":      "#F5D020",
    "info":     "#A0A0A0",
}

# Severity → emoji prefix for the title
_EMOJI: dict[str, str] = {
    "critical": ":red_circle:",
    "high":     ":large_orange_circle:",
    "medium":   ":large_yellow_circle:",
    "low":      ":white_circle:",
    "info":     ":information_source:",
}


def _build_blocks(finding: Finding) -> list[dict[str, Any]]:
    emoji = _EMOJI.get(finding.severity, ":white_circle:")
    color = _COLORS.get(finding.severity, "#A0A0A0")

    header_text = f"{emoji} *[{finding.severity.upper()}]* {finding.title}"

    fields: list[dict[str, Any]] = [
        {
            "type": "mrkdwn",
            "text": f"*Module*\n`{finding.module}`",
        },
        {
            "type": "mrkdwn",
            "text": f"*Severity*\n`{finding.severity.upper()}`",
        },
    ]

    if finding.resource_id:
        fields.append({
            "type": "mrkdwn",
            "text": f"*Resource*\n`{finding.resource_id}`",
        })

    if finding.tags:
        fields.append({
            "type": "mrkdwn",
            "text": f"*Tags*\n{', '.join(f'`{t}`' for t in finding.tags)}",
        })

    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": header_text},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": finding.description[:2900],  # Slack field limit
            },
        },
        {
            "type": "section",
            "fields": fields,
        },
    ]

    if finding.remediation:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Remediation*\n{finding.remediation[:1000]}",
            },
        })

    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f"ID: `{finding.id}` | "
                    f"{finding.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
                ),
            }
        ],
    })

    # Slack's attachment for color sidebar (blocks API doesn't support color natively)
    return blocks, color


class SlackWebhookAdapter(IntegrationAdapter):
    """
    Posts an Incoming Webhook message with Block Kit + color attachment sidebar.

    Args:
        webhook_url: Slack Incoming Webhook URL (starts with https://hooks.slack.com/services/...)
        dry_run: If True, returns success without making HTTP calls.
        timeout: HTTP timeout in seconds.
    """

    name = "slack"

    def __init__(
        self,
        webhook_url: str,
        dry_run: bool = False,
        timeout: float = 10.0,
    ) -> None:
        self.webhook_url = webhook_url
        self.dry_run = dry_run
        self.timeout = timeout

    async def send(self, finding: Finding) -> IntegrationResult:
        if self.dry_run:
            return IntegrationResult.dry(f"slack:{finding.id}", adapter=self.name)

        blocks, color = _build_blocks(finding)

        # Slack Incoming Webhook accepts `attachments` for color sidebar
        payload: dict[str, Any] = {
            "attachments": [
                {
                    "color": color,
                    "blocks": blocks,
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            msg = f"Slack HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.error("SlackWebhookAdapter: %s", msg)
            return IntegrationResult.failure(msg, adapter=self.name)
        except Exception as exc:
            logger.error("SlackWebhookAdapter: %s", exc)
            return IntegrationResult.failure(str(exc), adapter=self.name)

        return IntegrationResult.success("slack:ok", adapter=self.name)
