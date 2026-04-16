"""
integrations/servicenow.py — ServiceNow Incident adapter.

POSTs to the Table API (/api/now/table/incident) on a free Personal Developer
Instance (PDI). Basic auth (user + password).

Env vars:
    EAA_SNOW_INSTANCE_URL  e.g. https://dev12345.service-now.com
    EAA_SNOW_USER          admin (or any user with itil role)
    EAA_SNOW_PASSWORD      password
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from integrations.base import Finding, IntegrationAdapter, IntegrationResult

logger = logging.getLogger(__name__)

# ServiceNow urgency/impact: 1=High, 2=Medium, 3=Low
_URGENCY_MAP: dict[str, int] = {
    "critical": 1,
    "high":     1,
    "medium":   2,
    "low":      3,
    "info":     3,
}

_IMPACT_MAP: dict[str, int] = {
    "critical": 1,
    "high":     2,
    "medium":   2,
    "low":      3,
    "info":     3,
}

# ServiceNow priority is typically derived from urgency + impact, but we set it
# directly as well for older PDI configurations.
_PRIORITY_MAP: dict[str, int] = {
    "critical": 1,  # Critical
    "high":     2,  # High
    "medium":   3,  # Moderate
    "low":      4,  # Low
    "info":     5,  # Planning
}

_CATEGORY = "Software"
_SUBCATEGORY = "AI Compliance"
_CALLER_ID = "admin"  # default; PDIs have this user


def _build_description(finding: Finding) -> str:
    lines = [
        finding.description,
        "",
        f"Module: {finding.module}",
        f"Severity: {finding.severity.upper()}",
    ]
    if finding.resource_id:
        lines.append(f"Resource: {finding.resource_id}")
    if finding.remediation:
        lines.extend(["", "Remediation:", finding.remediation])
    if finding.tags:
        lines.append(f"Tags: {', '.join(finding.tags)}")
    lines.extend(["", f"Finding ID: {finding.id}"])
    return "\n".join(lines)


class ServiceNowAdapter(IntegrationAdapter):
    """
    Creates a ServiceNow incident for each finding via Table API.

    Args:
        instance_url:   Full URL to your PDI, e.g. https://dev12345.service-now.com
        user:           ServiceNow username
        password:       ServiceNow password
        caller_id:      The sys_id or username to set as caller. Default "admin".
        assignment_group: Optional assignment group name.
        dry_run:        Return success without HTTP calls.
        timeout:        HTTP timeout seconds.
    """

    name = "servicenow"

    def __init__(
        self,
        instance_url: str,
        user: str,
        password: str,
        caller_id: str = _CALLER_ID,
        assignment_group: str | None = None,
        dry_run: bool = False,
        timeout: float = 20.0,
    ) -> None:
        self.instance_url = instance_url.rstrip("/")
        self.caller_id = caller_id
        self.assignment_group = assignment_group
        self.dry_run = dry_run
        self.timeout = timeout
        self._auth = (user, password)

    def _build_payload(self, finding: Finding) -> dict[str, Any]:
        short_desc = f"[{finding.severity.upper()}] {finding.title}"[:160]
        payload: dict[str, Any] = {
            "short_description": short_desc,
            "description": _build_description(finding),
            "urgency": str(_URGENCY_MAP.get(finding.severity, 2)),
            "impact": str(_IMPACT_MAP.get(finding.severity, 2)),
            "priority": str(_PRIORITY_MAP.get(finding.severity, 3)),
            "category": _CATEGORY,
            "subcategory": _SUBCATEGORY,
            "caller_id": self.caller_id,
            # Custom fields — store module + finding id in correlation fields
            "correlation_id": finding.id,
            "correlation_display": f"eaa:{finding.module}",
        }
        if self.assignment_group:
            payload["assignment_group"] = self.assignment_group
        return payload

    async def send(self, finding: Finding) -> IntegrationResult:
        if self.dry_run:
            return IntegrationResult.dry(f"snow:{finding.id}", adapter=self.name)

        url = f"{self.instance_url}/api/now/table/incident"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                auth=self._auth,
                headers=headers,
                timeout=self.timeout,
            ) as client:
                response = await client.post(url, json=self._build_payload(finding))
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            msg = f"ServiceNow HTTP {exc.response.status_code}: {body}"
            logger.error("ServiceNowAdapter: %s", msg)
            return IntegrationResult.failure(msg, adapter=self.name)
        except Exception as exc:
            logger.error("ServiceNowAdapter unexpected error: %s", exc)
            return IntegrationResult.failure(str(exc), adapter=self.name)

        result_data = data.get("result", {})
        sys_id = result_data.get("sys_id", "")
        number = result_data.get("number", "")
        ref_url = (
            f"{self.instance_url}/nav_to.do?uri=incident.do?sys_id={sys_id}"
            if sys_id
            else f"{self.instance_url}/incident/{number}"
        )
        logger.info("ServiceNowAdapter: created incident %s", number)
        return IntegrationResult.success(ref_url, adapter=self.name)
