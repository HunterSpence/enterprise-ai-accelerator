"""
integrations/teams.py — Microsoft Teams Incoming Webhook adapter.

Posts a MessageCard to a Teams Incoming Webhook. Works with any free O365
personal account or any Teams workspace with the Incoming Webhook connector.

Env var: EAA_TEAMS_WEBHOOK_URL
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from integrations.base import Finding, IntegrationAdapter, IntegrationResult

logger = logging.getLogger(__name__)

# Severity → Teams theme color (hex, no #)
_COLORS: dict[str, str] = {
    "critical": "CC0000",
    "high":     "E03E2D",
    "medium":   "F0A500",
    "low":      "F5D020",
    "info":     "A0A0A0",
}


def _build_card(finding: Finding) -> dict[str, Any]:
    color = _COLORS.get(finding.severity, "A0A0A0")
    title = f"[{finding.severity.upper()}] {finding.title}"

    facts: list[dict[str, str]] = [
        {"name": "Severity", "value": finding.severity.upper()},
        {"name": "Module",   "value": finding.module},
    ]
    if finding.resource_id:
        facts.append({"name": "Resource", "value": finding.resource_id})
    if finding.tags:
        facts.append({"name": "Tags", "value": ", ".join(finding.tags)})
    facts.append({"name": "Finding ID", "value": finding.id})
    facts.append({
        "name": "Detected",
        "value": finding.created_at.strftime("%Y-%m-%d %H:%M UTC"),
    })

    sections: list[dict[str, Any]] = [
        {
            "activityTitle": title,
            "activitySubtitle": finding.module,
            "facts": facts,
            "text": finding.description[:1000],
        }
    ]

    if finding.remediation:
        sections.append({
            "title": "Remediation",
            "text": finding.remediation[:1000],
        })

    card: dict[str, Any] = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": title,
        "title": title,
        "sections": sections,
    }
    return card


class TeamsWebhookAdapter(IntegrationAdapter):
    """
    Posts a Teams MessageCard via Incoming Webhook.

    Args:
        webhook_url: Teams Incoming Webhook URL.
        dry_run:     Return success without HTTP calls.
        timeout:     HTTP timeout seconds.
    """

    name = "teams"

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
            return IntegrationResult.dry(f"teams:{finding.id}", adapter=self.name)

        card = _build_card(finding)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.webhook_url,
                    json=card,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:200]
            msg = f"Teams HTTP {exc.response.status_code}: {body}"
            logger.error("TeamsWebhookAdapter: %s", msg)
            return IntegrationResult.failure(msg, adapter=self.name)
        except Exception as exc:
            logger.error("TeamsWebhookAdapter unexpected error: %s", exc)
            return IntegrationResult.failure(str(exc), adapter=self.name)

        return IntegrationResult.success("teams:ok", adapter=self.name)
