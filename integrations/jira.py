"""
integrations/jira.py — Jira Cloud adapter (REST API v3).

Creates issues on Jira Cloud free tier. Uses basic auth (email + API token).
No Jira SDK needed — raw httpx.

Env vars:
    EAA_JIRA_BASE_URL   e.g. https://myorg.atlassian.net
    EAA_JIRA_EMAIL      user email for basic auth
    EAA_JIRA_API_TOKEN  Jira API token (not account password)
    EAA_JIRA_PROJECT    project key, e.g. EAA
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from integrations.base import Finding, IntegrationAdapter, IntegrationResult

logger = logging.getLogger(__name__)

# Severity → Jira priority name (standard Jira priority scheme)
_PRIORITY_MAP: dict[str, str] = {
    "critical": "Highest",
    "high":     "High",
    "medium":   "Medium",
    "low":      "Low",
    "info":     "Lowest",
}

# Jira issue type — Task works on all project types including Scrum/Kanban free
_ISSUE_TYPE = "Task"


def _adf_doc(text: str) -> dict[str, Any]:
    """Wrap plain text in Atlassian Document Format (ADF) paragraph."""
    return {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def _build_description(finding: Finding) -> dict[str, Any]:
    """Build a structured ADF description from finding fields."""
    parts: list[str] = [
        finding.description,
        "",
        f"Module: {finding.module}",
        f"Severity: {finding.severity.upper()}",
    ]
    if finding.resource_id:
        parts.append(f"Resource: {finding.resource_id}")
    if finding.remediation:
        parts.extend(["", "Remediation:", finding.remediation])
    if finding.tags:
        parts.append(f"Tags: {', '.join(finding.tags)}")
    parts.extend(["", f"Finding ID: {finding.id}"])
    return _adf_doc("\n".join(parts))


class JiraAdapter(IntegrationAdapter):
    """
    Creates a Jira Cloud issue for each finding via REST API v3.

    Args:
        base_url:    Jira Cloud base URL, e.g. https://myorg.atlassian.net
        email:       Atlassian account email (for basic auth)
        api_token:   Jira API token from id.atlassian.com/manage-profile/security/api-tokens
        project_key: Jira project key (e.g. "EAA")
        issue_type:  Jira issue type name. Default "Task".
        dry_run:     Return success without HTTP calls.
        timeout:     HTTP timeout seconds.
    """

    name = "jira"

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
        issue_type: str = _ISSUE_TYPE,
        dry_run: bool = False,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.project_key = project_key
        self.issue_type = issue_type
        self.dry_run = dry_run
        self.timeout = timeout

        # Basic auth header: base64(email:api_token)
        creds = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {creds}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _build_labels(self, finding: Finding) -> list[str]:
        labels = ["eaa", f"module-{finding.module}", f"severity-{finding.severity}"]
        for tag in finding.tags:
            safe_tag = tag.replace(" ", "-")[:50]
            labels.append(safe_tag)
        return labels

    def _build_payload(self, finding: Finding) -> dict[str, Any]:
        summary = f"[{finding.severity.upper()}] {finding.title}"[:255]
        return {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary,
                "description": _build_description(finding),
                "issuetype": {"name": self.issue_type},
                "priority": {"name": _PRIORITY_MAP.get(finding.severity, "Medium")},
                "labels": self._build_labels(finding),
            }
        }

    async def send(self, finding: Finding) -> IntegrationResult:
        if self.dry_run:
            return IntegrationResult.dry(f"jira:{finding.id}", adapter=self.name)

        url = f"{self.base_url}/rest/api/3/issue"
        payload = self._build_payload(finding)

        try:
            async with httpx.AsyncClient(
                headers=self._headers, timeout=self.timeout
            ) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            msg = f"Jira HTTP {exc.response.status_code}: {body}"
            logger.error("JiraAdapter: %s", msg)
            return IntegrationResult.failure(msg, adapter=self.name)
        except Exception as exc:
            logger.error("JiraAdapter unexpected error: %s", exc)
            return IntegrationResult.failure(str(exc), adapter=self.name)

        issue_key = data.get("key", "unknown")
        issue_url = f"{self.base_url}/browse/{issue_key}"
        logger.info("JiraAdapter: created issue %s", issue_key)
        return IntegrationResult.success(issue_url, adapter=self.name)
