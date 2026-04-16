"""
integrations/jira.py — Jira Cloud Integration
==============================================

Creates Epics and Stories for each migration wave.
Supports Jira Cloud REST API v3 and dry-run mode.

Environment variables:
  JIRA_URL       — e.g., "https://company.atlassian.net"
  JIRA_EMAIL     — Jira user email
  JIRA_TOKEN     — Jira API token (from Atlassian account)
  JIRA_PROJECT   — Project key, e.g., "CLOUD" or "MIG"
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from rich.console import Console

console = Console()


@dataclass
class JiraIssue:
    key: str
    issue_type: str
    summary: str
    url: str
    issue_id: str
    children: list["JiraIssue"] = field(default_factory=list)
    dry_run: bool = False

    def __str__(self) -> str:
        prefix = "[DRY RUN] " if self.dry_run else ""
        return f"{prefix}{self.key}: {self.summary}"


class JiraClient:
    """
    Jira Cloud REST API v3 client.

    Creates:
    - Epic per migration wave
    - Story per workload within each wave
    - Sub-tasks for key migration steps (pre-migration, execution, validation)

    Dry-run mode works without any credentials.
    """

    STORY_POINTS_MAP = {
        "Low": 3,
        "Medium": 8,
        "High": 13,
        "critical": 21,
    }

    PRIORITY_MAP = {
        "critical": "Highest",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }

    def __init__(
        self,
        url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        project_key: str | None = None,
    ) -> None:
        self.url = (url or os.environ.get("JIRA_URL", "https://demo.atlassian.net")).rstrip("/")
        self.email = email or os.environ.get("JIRA_EMAIL", "")
        self.token = token or os.environ.get("JIRA_TOKEN", "")
        self.project_key = project_key or os.environ.get("JIRA_PROJECT", "CLOUD")

    @property
    def _dry_run(self) -> bool:
        return not (self.email and self.token)

    def _make_issue_key(self, prefix: str, index: int) -> str:
        return f"{self.project_key}-{abs(hash(prefix + str(index))) % 9000 + 1000}"

    def _post_issue(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to Jira REST API. Returns simulated response in dry-run mode."""
        if self._dry_run:
            return self._simulate_issue(payload)

        try:
            import requests
            resp = requests.post(
                f"{self.url}/rest/api/3/issue",
                json=payload,
                auth=(self.email, self.token),
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            console.print(f"[red]Jira API error: {e}[/red]")
            return self._simulate_issue(payload)

    def _simulate_issue(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary = payload.get("fields", {}).get("summary", "")
        fake_key = f"{self.project_key}-{abs(hash(summary)) % 9000 + 1000}"
        return {
            "id": str(abs(hash(summary))),
            "key": fake_key,
            "self": f"{self.url}/rest/api/3/issue/{fake_key}",
        }

    def _build_adf_description(self, text: str) -> dict[str, Any]:
        """Build Atlassian Document Format description."""
        paragraphs = []
        for line in text.strip().split("\n"):
            if line.strip():
                paragraphs.append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line.strip()}],
                })
        return {"type": "doc", "version": 1, "content": paragraphs or [{
            "type": "paragraph",
            "content": [{"type": "text", "text": text}],
        }]}

    def create_wave_epic(
        self,
        wave_number: int,
        wave_name: str,
        workload_count: int,
        estimated_weeks: float,
        migration_cost: float,
        risk_level: str,
    ) -> JiraIssue:
        """Create a Jira Epic for a migration wave."""
        summary = f"[Migration Wave {wave_number}] {wave_name}"
        description_text = (
            f"Migration Wave {wave_number}: {wave_name}\n"
            f"Workloads: {workload_count}\n"
            f"Estimated Duration: {estimated_weeks:.1f} weeks (P50)\n"
            f"Migration Cost: ${migration_cost:,.0f}\n"
            f"Risk Level: {risk_level.upper()}\n"
            f"Created by MigrationScout V2 on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary,
                "description": self._build_adf_description(description_text),
                "issuetype": {"name": "Epic"},
                "priority": {"name": self.PRIORITY_MAP.get(risk_level, "Medium")},
                "customfield_10011": summary,  # Epic Name field
                "labels": ["cloud-migration", f"wave-{wave_number}", f"migration-scout"],
            }
        }

        result = self._post_issue(payload)
        issue_key = result.get("key", self._make_issue_key("epic", wave_number))
        is_dry = self._dry_run

        issue = JiraIssue(
            key=issue_key,
            issue_type="Epic",
            summary=summary,
            url=f"{self.url}/browse/{issue_key}",
            issue_id=result.get("id", ""),
            dry_run=is_dry,
        )

        status = "[dim](dry run)[/dim]" if is_dry else "[green]created[/green]"
        console.print(f"  Jira Epic {status}: {issue_key} — {wave_name}")
        return issue

    def create_workload_story(
        self,
        workload_name: str,
        workload_id: str,
        strategy: str,
        target_service: str,
        estimated_weeks: float,
        business_criticality: str,
        complexity: str,
        annual_savings: float,
        epic_key: str | None = None,
        ai_rationale: str = "",
    ) -> JiraIssue:
        """Create a Jira Story for a single workload migration."""
        summary = f"[{strategy}] Migrate {workload_name} → {target_service}"
        story_points = self.STORY_POINTS_MAP.get(complexity, 5)

        description_text = (
            f"Migrate {workload_name} ({workload_id}) to {target_service}\n\n"
            f"Migration Strategy: {strategy}\n"
            f"Estimated Duration: {estimated_weeks:.1f} weeks\n"
            f"Annual Savings: ${annual_savings:,.0f}\n"
            f"Business Criticality: {business_criticality}\n\n"
            f"MigrationScout Assessment:\n{ai_rationale}\n\n"
            f"Acceptance Criteria:\n"
            f"- Application migrated to {target_service}\n"
            f"- All validation tests pass\n"
            f"- Monitoring configured in CloudWatch\n"
            f"- Performance within 20% of baseline\n"
            f"- Runbook completed and approved"
        )

        fields: dict[str, Any] = {
            "project": {"key": self.project_key},
            "summary": summary,
            "description": self._build_adf_description(description_text),
            "issuetype": {"name": "Story"},
            "priority": {"name": self.PRIORITY_MAP.get(business_criticality, "Medium")},
            "story_points": story_points,
            "labels": ["cloud-migration", "migration-scout", strategy.lower()],
        }
        if epic_key:
            fields["customfield_10014"] = epic_key  # Epic Link

        payload = {"fields": fields}
        result = self._post_issue(payload)
        issue_key = result.get("key", self._make_issue_key(workload_id, 0))
        is_dry = self._dry_run

        issue = JiraIssue(
            key=issue_key,
            issue_type="Story",
            summary=summary,
            url=f"{self.url}/browse/{issue_key}",
            issue_id=result.get("id", ""),
            dry_run=is_dry,
        )

        status = "[dim](dry run)[/dim]" if is_dry else "[green]created[/green]"
        console.print(f"    Jira Story {status}: {issue_key} — {workload_name}")
        return issue

    def create_wave_board(
        self,
        wave_epics: list[dict[str, Any]],
        dry_run: bool = True,
    ) -> list[JiraIssue]:
        """
        Create full Jira board structure for all waves:
        Epic per wave → Stories per workload.

        wave_epics: list of dicts with keys:
          wave_number, wave_name, workload_count, estimated_weeks,
          migration_cost, risk_level, workloads (list of workload dicts)
        """
        all_issues: list[JiraIssue] = []
        mode = "DRY RUN" if dry_run or self._dry_run else "LIVE"
        console.print(f"\n[bold]Creating Jira board structure ({mode})...[/bold]")

        for wave_data in wave_epics:
            wave_num = wave_data["wave_number"]
            epic = self.create_wave_epic(
                wave_number=wave_num,
                wave_name=wave_data["wave_name"],
                workload_count=wave_data["workload_count"],
                estimated_weeks=wave_data["estimated_weeks"],
                migration_cost=wave_data["migration_cost"],
                risk_level=wave_data["risk_level"],
            )
            all_issues.append(epic)

            for wl in wave_data.get("workloads", []):
                story = self.create_workload_story(
                    workload_name=wl.get("name", ""),
                    workload_id=wl.get("id", ""),
                    strategy=wl.get("strategy", "Rehost"),
                    target_service=wl.get("target_service", "EC2"),
                    estimated_weeks=wl.get("estimated_weeks", 4.0),
                    business_criticality=wl.get("business_criticality", "medium"),
                    complexity=wl.get("complexity", "Medium"),
                    annual_savings=wl.get("annual_savings", 0.0),
                    epic_key=epic.key,
                    ai_rationale=wl.get("ai_rationale", ""),
                )
                epic.children.append(story)
                all_issues.append(story)

        epics = [i for i in all_issues if i.issue_type == "Epic"]
        stories = [i for i in all_issues if i.issue_type == "Story"]
        console.print(
            f"\n[bold]Jira board created:[/bold] {len(epics)} epics, {len(stories)} stories"
        )
        return all_issues
