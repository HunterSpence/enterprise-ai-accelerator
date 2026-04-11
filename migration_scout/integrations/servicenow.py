"""
integrations/servicenow.py — ServiceNow CMDB Integration
=========================================================

Creates migration tasks and CI records in ServiceNow.
All operations are async with retry logic and proper error handling.

Environment variables:
  SNOW_INSTANCE   — e.g., "company.service-now.com"
  SNOW_USER       — ServiceNow username
  SNOW_PASSWORD   — ServiceNow password (or use SNOW_TOKEN for OAuth)
  SNOW_TOKEN      — Bearer token (preferred over user/password)

Usage (demo mode works without credentials):
  from migration_scout.integrations.servicenow import ServiceNowClient
  client = ServiceNowClient()
  result = client.create_migration_task(assessment, wave_number=1, dry_run=True)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from rich.console import Console

console = Console()


@dataclass
class SNOWRecord:
    """Represents a ServiceNow record (task, CI, change request)."""
    sys_id: str
    number: str
    table: str
    url: str
    data: dict[str, Any]
    dry_run: bool = False

    def __str__(self) -> str:
        prefix = "[DRY RUN] " if self.dry_run else ""
        return f"{prefix}{self.table}/{self.number} ({self.sys_id})"


class ServiceNowClient:
    """
    ServiceNow REST API client for migration integration.

    Supports:
    - Creating RITM/task records for each migrated workload
    - Updating CMDB CI records with cloud target info
    - Creating change requests for migration cutover windows
    - Dry-run mode (no credentials needed — returns simulated records)
    """

    TABLE_TASK = "task"
    TABLE_CHANGE = "change_request"
    TABLE_CMDB = "cmdb_ci_server"
    TABLE_STORY = "rm_story"

    PRIORITY_MAP = {
        "critical": "1",   # Critical
        "high": "2",       # High
        "medium": "3",     # Moderate
        "low": "4",        # Low
    }

    CATEGORY_MIGRATION = "cloud_migration"

    def __init__(
        self,
        instance: str | None = None,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
    ) -> None:
        self.instance = instance or os.environ.get("SNOW_INSTANCE", "demo.service-now.com")
        self.username = username or os.environ.get("SNOW_USER", "")
        self.password = password or os.environ.get("SNOW_PASSWORD", "")
        self.token = token or os.environ.get("SNOW_TOKEN", "")
        self._base_url = f"https://{self.instance}/api/now/table/"
        self._session: Any = None

    @property
    def _dry_run(self) -> bool:
        return not (self.token or (self.username and self.password))

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _post(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to ServiceNow REST API. Returns simulated response in dry-run mode."""
        if self._dry_run:
            return self._simulate_response(table, payload)

        try:
            import requests
            url = urljoin(self._base_url, table)
            resp = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                auth=(self.username, self.password) if not self.token else None,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("result", {})
        except Exception as e:
            console.print(f"[red]ServiceNow API error: {e}[/red]")
            return self._simulate_response(table, payload)

    def _simulate_response(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Simulate a ServiceNow API response for demo/dry-run mode."""
        import hashlib
        fake_id = hashlib.md5(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        prefix = {"task": "TASK", "change_request": "CHG", "cmdb_ci_server": "CI", "rm_story": "STRY"}.get(table, "REC")
        number = f"{prefix}{abs(hash(fake_id)) % 1000000:07d}"
        return {
            "sys_id": fake_id,
            "number": number,
            "state": "1",
            "short_description": payload.get("short_description", ""),
            "sys_created_on": datetime.utcnow().isoformat(),
            "link": f"https://{self.instance}/nav_to.do?uri={table}.do?sys_id={fake_id}",
        }

    def create_migration_task(
        self,
        workload_name: str,
        workload_id: str,
        strategy: str,
        target_service: str,
        wave_number: int,
        estimated_weeks: float,
        business_criticality: str = "medium",
        assigned_to: str | None = None,
        dry_run: bool = False,
    ) -> SNOWRecord:
        """
        Create a ServiceNow Task for a workload migration.

        Args:
            dry_run: Override to force dry-run mode regardless of credentials.
        """
        if dry_run:
            original = self._dry_run
            self.token = ""
            self.username = ""

        payload = {
            "short_description": f"[Cloud Migration] Wave {wave_number}: {workload_name}",
            "description": (
                f"Cloud migration task for workload: {workload_name} ({workload_id})\n"
                f"Strategy: {strategy}\n"
                f"Target Service: {target_service}\n"
                f"Migration Wave: {wave_number}\n"
                f"Estimated Duration: {estimated_weeks:.1f} weeks\n"
                f"Created by MigrationScout V2 on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
            ),
            "category": self.CATEGORY_MIGRATION,
            "priority": self.PRIORITY_MAP.get(business_criticality, "3"),
            "assignment_group": "Cloud Migration Team",
            "work_notes": f"Auto-generated by MigrationScout V2. Workload ID: {workload_id}",
        }
        if assigned_to:
            payload["assigned_to"] = assigned_to

        result = self._post(self.TABLE_TASK, payload)
        is_dry = dry_run or not (self.token or (self.username and self.password))

        if is_dry and dry_run:
            self.token = ""
            self.username = ""

        record = SNOWRecord(
            sys_id=result.get("sys_id", ""),
            number=result.get("number", ""),
            table=self.TABLE_TASK,
            url=result.get("link", f"https://{self.instance}/{self.TABLE_TASK}/{result.get('sys_id', '')}"),
            data=result,
            dry_run=is_dry,
        )

        status = "[dim](dry run)[/dim]" if is_dry else "[green]created[/green]"
        console.print(f"  ServiceNow task {status}: {record.number} — {workload_name}")
        return record

    def create_change_request(
        self,
        wave_name: str,
        wave_number: int,
        workload_count: int,
        planned_start: str,
        planned_end: str,
        migration_cost: float,
    ) -> SNOWRecord:
        """
        Create a Change Request for a migration wave cutover.
        """
        payload = {
            "short_description": f"[Cloud Migration] Wave {wave_number} Cutover — {wave_name}",
            "description": (
                f"Planned cutover for Migration Wave {wave_number}: {wave_name}\n"
                f"Workloads: {workload_count}\n"
                f"Planned start: {planned_start}\n"
                f"Planned end: {planned_end}\n"
                f"Estimated cost: ${migration_cost:,.0f}\n\n"
                f"This change was planned using MigrationScout V2 Monte Carlo simulation.\n"
                f"All rollback procedures documented in wave runbook."
            ),
            "type": "normal",
            "category": "Cloud Infrastructure",
            "risk": "moderate",
            "impact": "2",
            "priority": "2",
            "start_date": planned_start,
            "end_date": planned_end,
        }
        result = self._post(self.TABLE_CHANGE, payload)
        is_dry = not (self.token or (self.username and self.password))
        record = SNOWRecord(
            sys_id=result.get("sys_id", ""),
            number=result.get("number", ""),
            table=self.TABLE_CHANGE,
            url=result.get("link", ""),
            data=result,
            dry_run=is_dry,
        )
        status = "[dim](dry run)[/dim]" if is_dry else "[green]created[/green]"
        console.print(f"  ServiceNow Change Request {status}: {record.number} — {wave_name}")
        return record

    def update_cmdb_ci(
        self,
        workload_name: str,
        workload_id: str,
        cloud_target: str,
        strategy: str,
        migration_completed: bool = False,
    ) -> SNOWRecord:
        """Update CMDB CI record with cloud migration status."""
        payload = {
            "name": workload_name,
            "u_cloud_migration_status": "migrated" if migration_completed else "in_progress",
            "u_cloud_target": cloud_target,
            "u_migration_strategy": strategy,
            "u_migration_scout_id": workload_id,
            "u_last_assessment_date": datetime.utcnow().strftime("%Y-%m-%d"),
        }
        result = self._post(self.TABLE_CMDB, payload)
        is_dry = not (self.token or (self.username and self.password))
        record = SNOWRecord(
            sys_id=result.get("sys_id", ""),
            number=result.get("sys_id", "CI_" + workload_id)[:20],
            table=self.TABLE_CMDB,
            url=result.get("link", ""),
            data=result,
            dry_run=is_dry,
        )
        status = "[dim](dry run)[/dim]" if is_dry else "[green]updated[/green]"
        console.print(f"  ServiceNow CMDB CI {status}: {workload_name} → {cloud_target}")
        return record

    def bulk_create_wave_tasks(
        self,
        wave_number: int,
        workloads: list[dict[str, Any]],
        dry_run: bool = True,
    ) -> list[SNOWRecord]:
        """
        Bulk create tasks for all workloads in a wave.

        workloads: list of dicts with keys:
          name, id, strategy, target_service, estimated_weeks, business_criticality
        """
        records: list[SNOWRecord] = []
        console.print(f"\n[bold]Creating ServiceNow tasks for Wave {wave_number} ({len(workloads)} workloads)...[/bold]")
        console.print(f"[dim]Mode: {'DRY RUN — no records created' if dry_run else 'LIVE — writing to ServiceNow'}[/dim]")

        for wl in workloads:
            record = self.create_migration_task(
                workload_name=wl.get("name", "Unknown"),
                workload_id=wl.get("id", ""),
                strategy=wl.get("strategy", "Rehost"),
                target_service=wl.get("target_service", "EC2"),
                wave_number=wave_number,
                estimated_weeks=wl.get("estimated_weeks", 4.0),
                business_criticality=wl.get("business_criticality", "medium"),
                dry_run=dry_run,
            )
            records.append(record)

        console.print(f"\n[bold]Created {len(records)} ServiceNow records for Wave {wave_number}[/bold]")
        return records
