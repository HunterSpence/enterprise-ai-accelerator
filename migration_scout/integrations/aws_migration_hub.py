"""
integrations/aws_migration_hub.py — AWS Migration Hub Integration
=================================================================

Registers workload assessments with AWS Migration Hub.

NOTE: AWS Migration Hub was closed to NEW customers on November 15, 2025.
Existing customers retain access. This module demonstrates the API structure
for portfolio/interview purposes and works fully in dry-run mode.

Environment variables:
  AWS_REGION          — e.g., "us-east-1"
  AWS_ACCESS_KEY_ID   — AWS credentials
  AWS_SECRET_ACCESS_KEY — AWS credentials
  MIG_HUB_HOME_REGION — AWS account home region for Migration Hub
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rich.console import Console

console = Console()


@dataclass
class MigrationHubApplication:
    """Represents a Migration Hub application grouping."""
    name: str
    description: str
    application_id: str
    servers: list[str] = field(default_factory=list)
    dry_run: bool = False

    def __str__(self) -> str:
        prefix = "[DRY RUN] " if self.dry_run else ""
        return f"{prefix}MigHub App: {self.name} ({len(self.servers)} servers)"


@dataclass
class MigrationTask:
    """Represents a single Migration Hub task (progress event)."""
    task_id: str
    migration_task_name: str
    progress_percent: int
    status: str
    status_detail: str
    dry_run: bool = False

    def __str__(self) -> str:
        prefix = "[DRY RUN] " if self.dry_run else ""
        return f"{prefix}{self.migration_task_name}: {self.status} ({self.progress_percent}%)"


class MigrationHubClient:
    """
    AWS Migration Hub API client.

    Capabilities:
    - Create application groupings per wave
    - Register server profiles for each workload
    - Track migration progress (0–100%) per workload
    - Associate discovered servers with applications
    - Import migration tasks from external tools (ServiceNow / Jira)

    NOTE: Migration Hub closed to new customers Nov 15, 2025.
    This client demonstrates the boto3 API structure for portfolios.
    Dry-run mode requires zero AWS credentials.

    References:
      https://docs.aws.amazon.com/migrationhub/latest/ug/API_Reference.html
      boto3: client('migrationhub-config') — home region
      boto3: client('mgh') — migration tracking
    """

    # Migration Hub task status values
    STATUS_NOT_STARTED = "NOT_STARTED"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_FAILED = "FAILED"
    STATUS_COMPLETED = "COMPLETED"

    def __init__(
        self,
        region: str | None = None,
        home_region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.home_region = home_region or os.environ.get("MIG_HUB_HOME_REGION", "us-east-1")
        self.access_key_id = access_key_id or os.environ.get("AWS_ACCESS_KEY_ID", "")
        self.secret_access_key = secret_access_key or os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        self._mgh_client: Any = None
        self._config_client: Any = None

    @property
    def _dry_run(self) -> bool:
        return not (self.access_key_id and self.secret_access_key)

    def _get_mgh_client(self) -> Any:
        """Lazy-init boto3 Migration Hub client."""
        if self._mgh_client is None:
            try:
                import boto3
                session = boto3.Session(
                    aws_access_key_id=self.access_key_id,
                    aws_secret_access_key=self.secret_access_key,
                    region_name=self.home_region,
                )
                self._mgh_client = session.client("mgh")
            except ImportError:
                console.print("[yellow]boto3 not installed — using dry-run mode[/yellow]")
        return self._mgh_client

    def _simulate_progress_update(self, task_name: str, progress: int) -> dict[str, Any]:
        fake_id = str(abs(hash(task_name)) % 1000000)
        return {
            "ProgressUpdateStreamName": "MigrationScout",
            "MigrationTaskName": task_name,
            "Task": {
                "Status": self.STATUS_IN_PROGRESS if progress < 100 else self.STATUS_COMPLETED,
                "StatusDetail": f"Automated by MigrationScout V2",
                "ProgressPercent": progress,
            },
            "UpdateDateTime": datetime.utcnow().isoformat() + "Z",
            "_simulated": True,
            "_task_id": fake_id,
        }

    def create_progress_update_stream(self, stream_name: str = "MigrationScout") -> bool:
        """
        Create a Migration Hub progress update stream.
        Each external migration tool gets its own stream.
        """
        if self._dry_run:
            console.print(f"  [dim](dry run)[/dim] Progress stream: {stream_name}")
            return True

        try:
            client = self._get_mgh_client()
            client.create_progress_update_stream(
                ProgressUpdateStreamName=stream_name,
                DryRun=False,
            )
            console.print(f"  [green]Created[/green] Migration Hub stream: {stream_name}")
            return True
        except Exception as e:
            console.print(f"  [yellow]Stream creation warning (may already exist): {e}[/yellow]")
            return False

    def import_migration_task(
        self,
        workload_name: str,
        workload_id: str,
        strategy: str,
        target_service: str,
        stream_name: str = "MigrationScout",
    ) -> MigrationTask:
        """
        Import a workload into Migration Hub as a migration task.
        Establishes tracking for this workload's migration journey.
        """
        task_name = f"migscout-{workload_id}"

        if self._dry_run:
            result = self._simulate_progress_update(task_name, 0)
        else:
            try:
                client = self._get_mgh_client()
                client.import_migration_task(
                    ProgressUpdateStream=stream_name,
                    MigrationTaskName=task_name,
                    DryRun=False,
                )
                result = self._simulate_progress_update(task_name, 0)
            except Exception as e:
                console.print(f"  [red]Migration Hub import error: {e}[/red]")
                result = self._simulate_progress_update(task_name, 0)

        task = MigrationTask(
            task_id=result["_task_id"],
            migration_task_name=task_name,
            progress_percent=0,
            status=self.STATUS_NOT_STARTED,
            status_detail=f"Imported by MigrationScout V2. Strategy: {strategy} → {target_service}",
            dry_run=self._dry_run,
        )

        status = "[dim](dry run)[/dim]" if self._dry_run else "[green]imported[/green]"
        console.print(f"  Migration Hub task {status}: {task_name} — {workload_name}")
        return task

    def notify_migration_task_state(
        self,
        task_name: str,
        progress_percent: int,
        status_detail: str = "",
        stream_name: str = "MigrationScout",
    ) -> MigrationTask:
        """
        Update migration task progress. Called at key migration milestones:
          0%   = Planning
          25%  = Pre-migration validation complete
          50%  = Migration in progress
          75%  = Cutover window open
          100% = Migration complete + validated
        """
        status = self.STATUS_COMPLETED if progress_percent >= 100 else self.STATUS_IN_PROGRESS
        if progress_percent == 0:
            status = self.STATUS_NOT_STARTED

        if self._dry_run:
            result = self._simulate_progress_update(task_name, progress_percent)
        else:
            try:
                client = self._get_mgh_client()
                client.notify_migration_task_state(
                    ProgressUpdateStream=stream_name,
                    MigrationTaskName=task_name,
                    Task={
                        "Status": status,
                        "StatusDetail": status_detail or f"Progress: {progress_percent}%",
                        "ProgressPercent": progress_percent,
                    },
                    UpdateDateTime=datetime.utcnow(),
                    NextUpdateSeconds=300,
                    DryRun=False,
                )
                result = self._simulate_progress_update(task_name, progress_percent)
            except Exception as e:
                console.print(f"  [red]Migration Hub state update error: {e}[/red]")
                result = self._simulate_progress_update(task_name, progress_percent)

        is_dry = self._dry_run
        task = MigrationTask(
            task_id=result["_task_id"],
            migration_task_name=task_name,
            progress_percent=progress_percent,
            status=status,
            status_detail=status_detail,
            dry_run=is_dry,
        )

        mode = "[dim](dry run)[/dim]" if is_dry else "[green]updated[/green]"
        console.print(f"  Migration Hub {mode}: {task_name} → {progress_percent}% ({status})")
        return task

    def associate_discovered_resource(
        self,
        task_name: str,
        server_id: str,
        description: str,
        stream_name: str = "MigrationScout",
    ) -> bool:
        """
        Associate an ADS (Application Discovery Service) server with a migration task.
        Links discovered on-prem servers to their migration tracking records.
        """
        if self._dry_run:
            console.print(f"  [dim](dry run)[/dim] Associated resource: {server_id} → {task_name}")
            return True

        try:
            client = self._get_mgh_client()
            client.associate_discovered_resource(
                ProgressUpdateStream=stream_name,
                MigrationTaskName=task_name,
                DiscoveredResource={
                    "ConfigurationId": server_id,
                    "Description": description,
                },
                DryRun=False,
            )
            console.print(f"  [green]Associated[/green] ADS resource: {server_id} → {task_name}")
            return True
        except Exception as e:
            console.print(f"  [red]Resource association error: {e}[/red]")
            return False

    def list_migration_tasks(
        self,
        stream_name: str = "MigrationScout",
        status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List all migration tasks in the stream.
        Optionally filter by status: NOT_STARTED, IN_PROGRESS, FAILED, COMPLETED.
        """
        if self._dry_run:
            console.print(f"  [dim](dry run)[/dim] list_migration_tasks — no real data in demo mode")
            return []

        try:
            client = self._get_mgh_client()
            kwargs: dict[str, Any] = {"ProgressUpdateStream": stream_name}
            if status_filter:
                kwargs["ResourceName"] = status_filter
            resp = client.list_migration_tasks(**kwargs)
            tasks = resp.get("MigrationTaskSummaryList", [])
            console.print(f"  [green]Found {len(tasks)} migration tasks[/green]")
            return tasks
        except Exception as e:
            console.print(f"  [red]list_migration_tasks error: {e}[/red]")
            return []

    def bulk_register_wave(
        self,
        wave_number: int,
        workloads: list[dict[str, Any]],
        stream_name: str = "MigrationScout",
    ) -> list[MigrationTask]:
        """
        Register all workloads in a wave with Migration Hub.

        workloads: list of dicts with keys:
          id, name, strategy, target_service
        """
        tasks: list[MigrationTask] = []
        console.print(
            f"\n[bold]Registering Wave {wave_number} with AWS Migration Hub "
            f"({len(workloads)} workloads)...[/bold]"
        )
        mode = "DRY RUN — demo mode" if self._dry_run else "LIVE — writing to Migration Hub"
        console.print(f"[dim]Mode: {mode}[/dim]")

        self.create_progress_update_stream(stream_name)

        for wl in workloads:
            task = self.import_migration_task(
                workload_name=wl.get("name", "Unknown"),
                workload_id=wl.get("id", ""),
                strategy=wl.get("strategy", "Rehost"),
                target_service=wl.get("target_service", "EC2"),
                stream_name=stream_name,
            )
            tasks.append(task)

        console.print(
            f"\n[bold]Registered {len(tasks)} workloads in Migration Hub "
            f"(Wave {wave_number})[/bold]"
        )
        return tasks
