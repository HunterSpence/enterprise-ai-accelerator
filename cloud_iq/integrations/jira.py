"""
CloudIQ V2 — Jira integration.

Creates Jira tickets for P1 waste recommendations so cloud cost findings
flow directly into engineering backlogs. Uses the Jira REST API v3.

API reference:
    https://developer.atlassian.com/cloud/jira/platform/rest/v3/

Usage:
    jira = JiraIntegration(
        base_url="https://your-org.atlassian.net",
        user_email="cloudiq@your-org.com",
        api_token="your-api-token",
        project_key="CLOUD",
    )
    ticket = await jira.create_recommendation_ticket(waste_item)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class JiraIntegration:
    """
    Jira Cloud REST API v3 integration for CloudIQ.

    Creates structured tickets with:
    - Summary prefixed with severity tag
    - Description with full finding details
    - Labels: cloudiq, cost-optimization, <severity>
    - Custom field: estimated monthly savings
    - Linked to parent epic if configured
    """

    PRIORITY_MAP: dict[str, str] = {
        "critical": "Highest",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }

    def __init__(
        self,
        base_url: str,
        user_email: str,
        api_token: str,
        project_key: str,
        epic_key: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (user_email, api_token)
        self._project_key = project_key
        self._epic_key = epic_key
        self._dry_run = dry_run

    async def create_recommendation_ticket(
        self,
        category: str,
        resource_id: str,
        resource_type: str,
        region: str,
        monthly_waste_usd: float,
        description: str,
        recommendation: str,
        severity: str,
        tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Create a Jira ticket for a cost waste finding.

        POST /rest/api/3/issue

        Returns the created issue dict with key, id, and self URL.
        """
        priority = self.PRIORITY_MAP.get(severity, "Medium")
        summary = f"[CloudIQ-{severity.upper()}] {category}: {resource_id} — ${monthly_waste_usd:,.0f}/mo waste"

        description_doc = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Finding Details"}],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "marks": [{"type": "strong"}],
                            "text": "Resource: ",
                        },
                        {"type": "text", "text": resource_id},
                    ],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "marks": [{"type": "strong"}],
                            "text": "Type: ",
                        },
                        {"type": "text", "text": resource_type},
                    ],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "marks": [{"type": "strong"}],
                            "text": "Region: ",
                        },
                        {"type": "text", "text": region},
                    ],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "marks": [{"type": "strong"}],
                            "text": f"Estimated Monthly Waste: ${monthly_waste_usd:,.2f}",
                        }
                    ],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "marks": [{"type": "strong"}],
                            "text": f"Estimated Annual Waste: ${monthly_waste_usd * 12:,.2f}",
                        }
                    ],
                },
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Description"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}],
                },
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Recommended Action"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": recommendation}],
                },
                *(
                    [
                        {
                            "type": "heading",
                            "attrs": {"level": 2},
                            "content": [{"type": "text", "text": "Resource Tags"}],
                        },
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": ", ".join(f"{k}={v}" for k, v in (tags or {}).items()),
                                }
                            ],
                        },
                    ]
                    if tags
                    else []
                ),
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "marks": [{"type": "em"}],
                            "text": f"Generated by CloudIQ on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                        }
                    ],
                },
            ],
        }

        labels = ["cloudiq", "cost-optimization", f"severity-{severity}"]
        if resource_type:
            labels.append(resource_type.lower().replace(" ", "-"))

        payload: dict[str, Any] = {
            "fields": {
                "project": {"key": self._project_key},
                "summary": summary,
                "description": description_doc,
                "issuetype": {"name": "Task"},
                "priority": {"name": priority},
                "labels": labels,
            }
        }

        if self._epic_key:
            payload["fields"]["customfield_10014"] = self._epic_key  # Epic Link

        if self._dry_run:
            logger.info("jira_dry_run", summary=summary, priority=priority)
            return {
                "key": f"{self._project_key}-DRY",
                "id": "0",
                "self": f"{self._base_url}/browse/{self._project_key}-DRY",
                "dry_run": True,
            }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self._base_url}/rest/api/3/issue",
                auth=self._auth,
                json=payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "jira_ticket_created",
                key=data.get("key"),
                monthly_waste=monthly_waste_usd,
                severity=severity,
            )
            return data

    async def add_comment(self, issue_key: str, comment: str) -> bool:
        """Add a plain-text comment to an existing issue."""
        if self._dry_run:
            return True

        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": comment}],
                    }
                ],
            }
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self._base_url}/rest/api/3/issue/{issue_key}/comment",
                auth=self._auth,
                json=payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            return response.status_code == 201

    async def transition_issue(self, issue_key: str, transition_name: str) -> bool:
        """
        Transition an issue to a new status (e.g., 'Done', 'In Progress').

        First fetches available transitions to find the matching ID.
        """
        if self._dry_run:
            return True

        async with httpx.AsyncClient(timeout=15) as client:
            trans_response = await client.get(
                f"{self._base_url}/rest/api/3/issue/{issue_key}/transitions",
                auth=self._auth,
            )
            trans_response.raise_for_status()
            transitions = trans_response.json().get("transitions", [])

            match = next(
                (t for t in transitions if t["name"].lower() == transition_name.lower()),
                None,
            )
            if not match:
                logger.warning("jira_transition_not_found", name=transition_name)
                return False

            do_response = await client.post(
                f"{self._base_url}/rest/api/3/issue/{issue_key}/transitions",
                auth=self._auth,
                json={"transition": {"id": match["id"]}},
            )
            return do_response.status_code == 204
