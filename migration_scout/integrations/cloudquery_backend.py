"""
integrations/cloudquery_backend.py — CloudQuery Asset Discovery Backend
========================================================================

CloudQuery (https://github.com/cloudquery/cloudquery, 6.3K+ stars) is the
leading open-source cloud asset inventory tool. It syncs live infrastructure
data from AWS, Azure, GCP, and 200+ other sources into a queryable SQL store.

This integration replaces the deprecated AWS Migration Hub backend.
Migration Hub was closed to new customers on November 7, 2025.

Capabilities:
  - Auto-detect installed CloudQuery CLI (cq)
  - Execute `cloudquery sync` to pull live asset inventory
  - Parse CloudQuery output into MigrationScout WorkloadInventory objects
  - Fall back gracefully to manual inventory input when CLI is unavailable

Supported cloud providers:
  AWS   — EC2, RDS, Lambda, ECS, EKS, S3, and 100+ resource types
  Azure — VMs, AKS, SQL, App Service, Cosmos DB, and 80+ resource types
  GCP   — Compute Engine, GKE, Cloud SQL, Cloud Run, and 70+ resource types

Usage:
  from migration_scout.integrations.cloudquery_backend import CloudQueryBackend

  backend = CloudQueryBackend(provider="aws", region="us-east-1")
  result = backend.discover()
  if result.available:
      workloads = result.workloads
  else:
      # Fall through to manual input path
      workloads = load_manual_inventory()

Environment variables:
  CQ_CLOUD_PROVIDER   — "aws" | "azure" | "gcp" (default: auto-detect)
  CQ_CONFIG_PATH      — path to cloudquery config file (default: ./cq-config.yaml)
  AWS_REGION          — AWS region for discovery
  AZURE_SUBSCRIPTION  — Azure subscription ID for discovery
  GCP_PROJECT         — GCP project ID for discovery
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# CloudQuery config templates (minimal — enough for basic inventory sync)
# ---------------------------------------------------------------------------

_CQ_CONFIG_AWS = """\
kind: source
spec:
  name: aws
  path: cloudquery/aws
  registry: cloudquery
  version: "v26.0.0"
  tables:
    - aws_ec2_instances
    - aws_rds_instances
    - aws_lambda_functions
    - aws_ecs_services
    - aws_eks_clusters
    - aws_elasticbeanstalk_environments
  destinations:
    - sqlite
---
kind: destination
spec:
  name: sqlite
  path: cloudquery/sqlite
  registry: cloudquery
  version: "v3.0.0"
  spec:
    connection_string: "cq_inventory.db"
"""

_CQ_CONFIG_AZURE = """\
kind: source
spec:
  name: azure
  path: cloudquery/azure
  registry: cloudquery
  version: "v14.0.0"
  tables:
    - azure_compute_virtual_machines
    - azure_sql_servers
    - azure_app_service_web_apps
    - azure_container_service_managed_clusters
    - azure_cosmosdb_accounts
    - azure_keyvault_vaults
  destinations:
    - sqlite
---
kind: destination
spec:
  name: sqlite
  path: cloudquery/sqlite
  registry: cloudquery
  version: "v3.0.0"
  spec:
    connection_string: "cq_inventory.db"
"""

_CQ_CONFIG_GCP = """\
kind: source
spec:
  name: gcp
  path: cloudquery/gcp
  registry: cloudquery
  version: "v14.0.0"
  tables:
    - gcp_compute_instances
    - gcp_sql_instances
    - gcp_run_services
    - gcp_container_clusters
    - gcp_functions_functions
    - gcp_storage_buckets
  destinations:
    - sqlite
---
kind: destination
spec:
  name: sqlite
  path: cloudquery/sqlite
  registry: cloudquery
  version: "v3.0.0"
  spec:
    connection_string: "cq_inventory.db"
"""

_CQ_CONFIGS: dict[str, str] = {
    "aws": _CQ_CONFIG_AWS,
    "azure": _CQ_CONFIG_AZURE,
    "gcp": _CQ_CONFIG_GCP,
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredWorkload:
    """
    A workload discovered via CloudQuery asset inventory.

    Fields map to MigrationScout WorkloadInventory for downstream assessment.
    """
    id: str
    name: str
    workload_type: str
    provider: str                 # "aws" | "azure" | "gcp"
    region: str
    resource_type: str            # e.g. "aws_ec2_instance", "azure_vm"
    raw: dict[str, Any] = field(default_factory=dict)

    # Enriched fields (best-effort from raw inventory data)
    language: str = "unknown"
    database_type: str | None = None
    cpu_cores: int = 4
    ram_gb: int = 16
    storage_gb: int = 100
    monthly_cost_estimate: float = 0.0
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class CloudQueryResult:
    """Result of a CloudQuery discovery run."""
    available: bool
    provider: str
    workloads: list[DiscoveredWorkload]
    raw_output: str = ""
    error: str = ""
    fallback_reason: str = ""

    @property
    def workload_count(self) -> int:
        return len(self.workloads)

    @property
    def is_live_data(self) -> bool:
        return self.available and not self.error


# ---------------------------------------------------------------------------
# Provider-specific parsers
# ---------------------------------------------------------------------------

def _parse_aws_instance(raw: dict[str, Any], idx: int) -> DiscoveredWorkload:
    instance_id = raw.get("instance_id") or raw.get("InstanceId") or f"aws-ec2-{idx}"
    name = (
        next((t["Value"] for t in raw.get("tags", []) if t.get("Key") == "Name"), None)
        or raw.get("name")
        or instance_id
    )
    instance_type = raw.get("instance_type") or raw.get("InstanceType") or "t3.medium"
    cpu_map = {"t3.micro": 2, "t3.small": 2, "t3.medium": 2, "t3.large": 2,
               "m5.large": 2, "m5.xlarge": 4, "m5.2xlarge": 8, "r5.large": 2,
               "r5.xlarge": 4, "r5.2xlarge": 8, "c5.large": 2, "c5.xlarge": 4}
    ram_map = {"t3.micro": 1, "t3.small": 2, "t3.medium": 4, "t3.large": 8,
               "m5.large": 8, "m5.xlarge": 16, "m5.2xlarge": 32, "r5.large": 16,
               "r5.xlarge": 32, "r5.2xlarge": 64, "c5.large": 4, "c5.xlarge": 8}
    return DiscoveredWorkload(
        id=instance_id,
        name=name,
        workload_type="compute_instance",
        provider="aws",
        region=raw.get("region", "us-east-1"),
        resource_type="aws_ec2_instance",
        raw=raw,
        cpu_cores=cpu_map.get(instance_type, 4),
        ram_gb=ram_map.get(instance_type, 16),
        tags={t["Key"]: t["Value"] for t in raw.get("tags", []) if "Key" in t},
    )


def _parse_aws_rds(raw: dict[str, Any], idx: int) -> DiscoveredWorkload:
    db_id = raw.get("db_instance_identifier") or raw.get("DBInstanceIdentifier") or f"aws-rds-{idx}"
    engine = (raw.get("engine") or raw.get("Engine") or "mysql").lower()
    return DiscoveredWorkload(
        id=db_id,
        name=db_id,
        workload_type="database",
        provider="aws",
        region=raw.get("region", "us-east-1"),
        resource_type="aws_rds_instance",
        raw=raw,
        database_type=engine,
        cpu_cores=int(raw.get("processor_features", {}).get("CoreCount", 4)),
        ram_gb=16,
    )


def _parse_azure_vm(raw: dict[str, Any], idx: int) -> DiscoveredWorkload:
    vm_id = raw.get("id") or f"azure-vm-{idx}"
    name = raw.get("name") or vm_id
    return DiscoveredWorkload(
        id=str(abs(hash(vm_id)) % 10_000_000),
        name=name,
        workload_type="compute_instance",
        provider="azure",
        region=raw.get("location", "eastus"),
        resource_type="azure_virtual_machine",
        raw=raw,
        tags=raw.get("tags") or {},
    )


def _parse_gcp_instance(raw: dict[str, Any], idx: int) -> DiscoveredWorkload:
    inst_id = raw.get("id") or raw.get("name") or f"gcp-vm-{idx}"
    name = raw.get("name") or inst_id
    machine_type = raw.get("machine_type", "n1-standard-2").split("/")[-1]
    cpu_map = {"n1-standard-2": 2, "n1-standard-4": 4, "n1-standard-8": 8,
               "n2-standard-2": 2, "n2-standard-4": 4, "e2-medium": 2}
    ram_map = {"n1-standard-2": 8, "n1-standard-4": 16, "n1-standard-8": 32,
               "n2-standard-2": 8, "n2-standard-4": 16, "e2-medium": 4}
    return DiscoveredWorkload(
        id=str(abs(hash(inst_id)) % 10_000_000),
        name=name,
        workload_type="compute_instance",
        provider="gcp",
        region=raw.get("zone", "us-central1-a").rsplit("-", 1)[0],
        resource_type="gcp_compute_instance",
        raw=raw,
        cpu_cores=cpu_map.get(machine_type, 4),
        ram_gb=ram_map.get(machine_type, 16),
        tags=raw.get("labels") or {},
    )


_PROVIDER_PARSERS: dict[str, dict[str, Any]] = {
    "aws": {
        "aws_ec2_instances": _parse_aws_instance,
        "aws_rds_instances": _parse_aws_rds,
    },
    "azure": {
        "azure_compute_virtual_machines": _parse_azure_vm,
    },
    "gcp": {
        "gcp_compute_instances": _parse_gcp_instance,
    },
}


# ---------------------------------------------------------------------------
# CloudQueryBackend
# ---------------------------------------------------------------------------

class CloudQueryBackend:
    """
    Live infrastructure discovery via CloudQuery CLI.

    Checks for the `cq` binary at init time. If available, runs
    `cloudquery sync` to pull asset inventory from the configured cloud
    provider. If unavailable or the sync fails, returns a CloudQueryResult
    with available=False so callers can fall back to manual inventory input.

    Supported providers: aws, azure, gcp

    Example:
        backend = CloudQueryBackend(provider="aws")
        result = backend.discover()

        if result.is_live_data:
            print(f"Discovered {result.workload_count} workloads from AWS")
            for wl in result.workloads:
                print(f"  {wl.id}  {wl.name}  ({wl.workload_type})")
        else:
            print(f"CloudQuery unavailable: {result.fallback_reason}")
            print("Using manual inventory input instead.")
    """

    CLI_BINARY = "cq"

    def __init__(
        self,
        provider: str | None = None,
        region: str | None = None,
        config_path: str | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.provider = (
            provider
            or os.environ.get("CQ_CLOUD_PROVIDER")
            or self._detect_provider()
        ).lower()
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.config_path = config_path or os.environ.get("CQ_CONFIG_PATH")
        self.timeout_seconds = timeout_seconds
        self._cli_path: str | None = shutil.which(self.CLI_BINARY)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def cli_available(self) -> bool:
        """True if the CloudQuery CLI binary is found on PATH."""
        return self._cli_path is not None

    def discover(self) -> CloudQueryResult:
        """
        Run live discovery via CloudQuery CLI.

        Returns a CloudQueryResult. If the CLI is not available or the sync
        fails, available=False and fallback_reason explains why so the caller
        can route to the manual input path.
        """
        if not self.cli_available:
            return CloudQueryResult(
                available=False,
                provider=self.provider,
                workloads=[],
                fallback_reason=(
                    "CloudQuery CLI (`cq`) not found on PATH. "
                    "Install from https://www.cloudquery.io/docs/quickstart "
                    "or use `brew install cloudquery/tap/cloudquery`. "
                    "Falling back to manual inventory input."
                ),
            )

        if self.provider not in _CQ_CONFIGS:
            return CloudQueryResult(
                available=False,
                provider=self.provider,
                workloads=[],
                fallback_reason=(
                    f"Unsupported provider '{self.provider}'. "
                    f"Supported: {', '.join(sorted(_CQ_CONFIGS))}. "
                    "Falling back to manual inventory input."
                ),
            )

        return self._run_sync()

    def check_cli_version(self) -> str | None:
        """Return the installed CloudQuery CLI version string, or None."""
        if not self.cli_available:
            return None
        try:
            result = subprocess.run(
                [self._cli_path, "version"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                if "cloudquery" in line.lower() or line.startswith("v"):
                    return line.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None

    # ------------------------------------------------------------------
    # Internal: sync execution
    # ------------------------------------------------------------------

    def _run_sync(self) -> CloudQueryResult:
        """Execute `cloudquery sync` and parse the output."""
        config_content = _CQ_CONFIGS[self.provider]

        with tempfile.TemporaryDirectory(prefix="migscout_cq_") as tmp_dir:
            config_file = os.path.join(tmp_dir, "cq-config.yaml")
            with open(config_file, "w") as f:
                f.write(config_content)

            try:
                proc = subprocess.run(
                    [self._cli_path, "sync", config_file, "--log-level", "warn"],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    cwd=tmp_dir,
                )
            except subprocess.TimeoutExpired:
                return CloudQueryResult(
                    available=False,
                    provider=self.provider,
                    workloads=[],
                    error=f"CloudQuery sync timed out after {self.timeout_seconds}s",
                    fallback_reason="Sync timeout — falling back to manual inventory input.",
                )
            except OSError as exc:
                return CloudQueryResult(
                    available=False,
                    provider=self.provider,
                    workloads=[],
                    error=str(exc),
                    fallback_reason="CLI execution error — falling back to manual inventory input.",
                )

            raw_output = proc.stdout + proc.stderr

            if proc.returncode != 0:
                return CloudQueryResult(
                    available=False,
                    provider=self.provider,
                    workloads=[],
                    raw_output=raw_output,
                    error=f"cloudquery sync exited with code {proc.returncode}",
                    fallback_reason=(
                        "Sync failed (check credentials / permissions). "
                        "Falling back to manual inventory input."
                    ),
                )

            workloads = self._parse_sync_output(raw_output, tmp_dir)

        return CloudQueryResult(
            available=True,
            provider=self.provider,
            workloads=workloads,
            raw_output=raw_output,
        )

    def _parse_sync_output(
        self, raw_output: str, work_dir: str
    ) -> list[DiscoveredWorkload]:
        """
        Parse CloudQuery sync output into DiscoveredWorkload objects.

        CloudQuery writes resources as JSONL or to a configured destination
        (SQLite, PostgreSQL, etc.). We attempt JSONL parsing of stdout first,
        then fall back to reading any .json/.jsonl files written to work_dir.
        """
        workloads: list[DiscoveredWorkload] = []
        parsers = _PROVIDER_PARSERS.get(self.provider, {})

        # Attempt inline JSONL parsing (cq --output json mode)
        for line in raw_output.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                record = json.loads(line)
                table = record.get("__table") or record.get("table", "")
                parser_fn = parsers.get(table)
                if parser_fn:
                    wl = parser_fn(record, len(workloads))
                    workloads.append(wl)
            except (json.JSONDecodeError, KeyError):
                continue

        # Fall back: scan for any .json/.jsonl files in work_dir
        if not workloads:
            for fname in os.listdir(work_dir):
                if not fname.endswith((".json", ".jsonl")):
                    continue
                fpath = os.path.join(work_dir, fname)
                table_name = fname.replace(".json", "").replace(".jsonl", "")
                parser_fn = parsers.get(table_name)
                if not parser_fn:
                    continue
                try:
                    with open(fpath) as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            record = json.loads(line)
                            wl = parser_fn(record, len(workloads))
                            workloads.append(wl)
                except (OSError, json.JSONDecodeError):
                    continue

        return workloads

    # ------------------------------------------------------------------
    # Provider auto-detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_provider() -> str:
        """
        Heuristic provider detection based on available environment variables.
        Returns "aws" | "azure" | "gcp" | "aws" (default fallback).
        """
        if os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE"):
            return "aws"
        if os.environ.get("AZURE_CLIENT_ID") or os.environ.get("AZURE_SUBSCRIPTION"):
            return "azure"
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("GCP_PROJECT"):
            return "gcp"
        return "aws"
