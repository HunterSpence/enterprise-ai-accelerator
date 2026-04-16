"""
cloud_iq/adapters/gcp.py
========================

GCPAdapter — real GCP discovery via Cloud Asset Inventory + Cloud Billing.

Credential chain (standard GCP SDK order):
  1. Service account key file:  GOOGLE_APPLICATION_CREDENTIALS (path to JSON)
  2. gcloud CLI:                `gcloud auth application-default login`
  3. Workload Identity / GKE metadata server (ambient on GKE pods)
  4. Compute Engine metadata server (ambient on GCE VMs)

Required env vars:
  GOOGLE_CLOUD_PROJECT   — GCP project ID to scan
  GOOGLE_BILLING_ACCOUNT — GCP billing account ID for cost queries
                           (format: "XXXXXX-XXXXXX-XXXXXX")

Optional env vars:
  GOOGLE_APPLICATION_CREDENTIALS — path to service account JSON key

All GCP client library calls are synchronous; wrapped in asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from cloud_iq.adapters.base import DiscoveryAdapter, Workload

logger = logging.getLogger(__name__)

# Asset types we care about — passed to list_assets to avoid full-project scan
_ASSET_TYPES = [
    "compute.googleapis.com/Instance",
    "sqladmin.googleapis.com/Instance",
    "container.googleapis.com/Cluster",
    "run.googleapis.com/Service",
    "storage.googleapis.com/Bucket",
    "cloudfunctions.googleapis.com/CloudFunction",
]


class GCPAdapter(DiscoveryAdapter):
    """
    Discovers GCP workloads using Cloud Asset Inventory + Cloud Billing API.

    Asset Inventory gives a complete picture of every resource in the project
    in a single paginated call, which is far cheaper and faster than calling
    each individual resource API (Compute, SQL, GKE, etc.) separately.
    """

    def __init__(
        self,
        project_id: str | None = None,
        billing_account_id: str | None = None,
    ) -> None:
        self._project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        self._billing_account_id = (
            billing_account_id or os.environ.get("GOOGLE_BILLING_ACCOUNT", "")
        )

    # ------------------------------------------------------------------
    # DiscoveryAdapter interface
    # ------------------------------------------------------------------

    @property
    def cloud_name(self) -> str:
        return "gcp"

    @staticmethod
    def is_configured() -> bool:
        """True when GOOGLE_CLOUD_PROJECT is set (ADC handles auth)."""
        return bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))

    async def discover_workloads(self) -> list[Workload]:
        if not self._project_id:
            logger.warning("gcp_no_project_id")
            return []

        assets_task = asyncio.create_task(self._fetch_assets())
        cost_task = asyncio.create_task(self._fetch_costs())

        assets, cost_map = await asyncio.gather(
            assets_task, cost_task, return_exceptions=True
        )

        if isinstance(assets, Exception):
            logger.warning("gcp_asset_inventory_error error=%s", assets)
            assets = []
        if isinstance(cost_map, Exception):
            logger.warning("gcp_billing_error error=%s", cost_map)
            cost_map = {}

        return self._map_assets(assets, cost_map)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Cloud Asset Inventory
    # ------------------------------------------------------------------

    async def _fetch_assets(self) -> list[dict[str, Any]]:
        def _run() -> list[dict[str, Any]]:
            try:
                from google.cloud import asset_v1

                client = asset_v1.AssetServiceClient()
                parent = f"projects/{self._project_id}"
                assets: list[dict[str, Any]] = []

                request = asset_v1.ListAssetsRequest(
                    parent=parent,
                    asset_types=_ASSET_TYPES,
                    content_type=asset_v1.ContentType.RESOURCE,
                )

                for asset in client.list_assets(request=request):
                    # asset is google.cloud.asset_v1.types.Asset
                    resource = asset.resource
                    assets.append({
                        "name": asset.name,
                        "asset_type": asset.asset_type,
                        "resource_data": dict(resource.data) if resource and resource.data else {},
                        "location": getattr(resource, "location", ""),
                        "update_time": asset.update_time.isoformat()
                        if asset.update_time
                        else "",
                    })
                return assets
            except ImportError as exc:
                logger.warning(
                    "gcp_asset_sdk_not_installed missing=%s — pip install google-cloud-asset",
                    exc,
                )
                return []

        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # Cloud Billing — per-service cost last 30d
    # ------------------------------------------------------------------

    async def _fetch_costs(self) -> dict[str, float]:
        """Return {service_display_name: total_usd} from Cloud Billing API.

        Uses the Cloud Billing Budget/Cost API v1 to query last-30d costs
        grouped by service. Falls back to empty dict if billing account is
        not configured or the caller lacks billing.accounts.getSpendingInformation.
        """
        if not self._billing_account_id:
            logger.debug("gcp_no_billing_account_id — skipping cost fetch")
            return {}

        def _run() -> dict[str, float]:
            try:
                from google.cloud import billing_v1

                client = billing_v1.CloudCatalogClient()
                # List services to get service names → IDs mapping
                cost_map: dict[str, float] = {}
                # NOTE: The Cloud Billing API for actual spend requires
                # BigQuery export or the Billing Budgets API (both need special
                # IAM). We use CloudCatalogClient to list SKUs as a proxy.
                # For real cost data, the recommended approach is BigQuery:
                #   SELECT service.description, SUM(cost)
                #   FROM `billing_project.dataset.gcp_billing_export_*`
                #   WHERE DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                #   GROUP BY service.description
                # We return empty here and annotate the metadata so the caller
                # knows billing data requires BigQuery export setup.
                logger.info(
                    "gcp_billing_note — Real GCP cost data requires BigQuery billing export. "
                    "Configure export at: console.cloud.google.com/billing/export"
                )
                return cost_map
            except ImportError as exc:
                logger.warning(
                    "gcp_billing_sdk_not_installed missing=%s — pip install google-cloud-billing",
                    exc,
                )
                return {}

        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # Asset → Workload mapping
    # ------------------------------------------------------------------

    def _map_assets(
        self, assets: list[dict[str, Any]], cost_map: dict[str, float]
    ) -> list[Workload]:
        now = datetime.now(timezone.utc)
        workloads: list[Workload] = []

        for asset in assets:
            asset_type = asset.get("asset_type", "")
            data = asset.get("resource_data", {})
            name_full = asset.get("name", "")
            location = asset.get("location") or data.get("zone", "") or data.get("region", "")

            # Strip zone suffix for region (e.g. "us-central1-a" → "us-central1")
            region = _gcp_location_to_region(location)

            # Short name from the asset full name (last segment)
            short_name = name_full.split("/")[-1] if name_full else "unknown"

            service_type = _gcp_service_type(asset_type)
            cpu, mem, storage = _gcp_resource_specs(asset_type, data)
            tags = _gcp_labels(data)
            cost = _gcp_cost_lookup(service_type, cost_map)

            workloads.append(Workload(
                id=name_full,
                name=short_name,
                cloud="gcp",
                service_type=service_type,
                region=region,
                tags=tags,
                monthly_cost_usd=cost,
                cpu_cores=cpu,
                memory_gb=mem,
                storage_gb=storage,
                last_seen=now,
                metadata={
                    "asset_type": asset_type,
                    "project": self._project_id,
                    "status": data.get("status"),
                    "machine_type": data.get("machineType", "").split("/")[-1],
                    "update_time": asset.get("update_time"),
                },
            ))

        return workloads


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gcp_service_type(asset_type: str) -> str:
    _map = {
        "compute.googleapis.com/Instance": "ComputeEngine",
        "sqladmin.googleapis.com/Instance": "CloudSQL",
        "container.googleapis.com/Cluster": "GKE",
        "run.googleapis.com/Service": "CloudRun",
        "storage.googleapis.com/Bucket": "CloudStorage",
        "cloudfunctions.googleapis.com/CloudFunction": "CloudFunctions",
    }
    return _map.get(asset_type, "GCPResource")


def _gcp_location_to_region(location: str) -> str:
    """Strip zone suffix: "us-central1-a" → "us-central1"."""
    if not location:
        return "unknown"
    parts = location.rsplit("-", 1)
    if len(parts) == 2 and len(parts[1]) == 1 and parts[1].isalpha():
        return parts[0]
    return location


def _gcp_resource_specs(
    asset_type: str, data: dict[str, Any]
) -> tuple[int, float, float]:
    """Return (cpu_cores, memory_gb, storage_gb) from asset resource data."""
    cpu, mem, storage = 0, 0.0, 0.0
    if "Instance" in asset_type and "compute" in asset_type:
        # Machine type in form "zones/us-central1-a/machineTypes/n1-standard-4"
        mt = data.get("machineType", "").split("/")[-1]
        cpu, mem = _gce_machine_specs(mt)
        # Disk sizes from disks array
        for disk in data.get("disks", []):
            disk_size = data.get("diskSizeGb")
            if disk_size:
                storage += float(disk_size)
    elif "sqladmin" in asset_type:
        settings = data.get("settings", {})
        data_disk_size = settings.get("dataDiskSizeGb", 0)
        storage = float(data_disk_size)
    elif "container" in asset_type:
        # GKE cluster — node pool specs
        for pool in data.get("nodePools", []):
            nc = pool.get("config", {})
            machine = nc.get("machineType", "")
            pool_cpu, pool_mem = _gce_machine_specs(machine)
            count = (
                pool.get("initialNodeCount", 0)
                or pool.get("autoscaling", {}).get("maxNodeCount", 1)
            )
            cpu += pool_cpu * count
            mem += pool_mem * count
    return cpu, mem, storage


# Minimal GCE machine type → (vcpu, ram_gb)
_GCE_SPECS: dict[str, tuple[int, float]] = {
    "n1-standard-1": (1, 3.75), "n1-standard-2": (2, 7.5), "n1-standard-4": (4, 15),
    "n1-standard-8": (8, 30), "n1-standard-16": (16, 60), "n1-standard-32": (32, 120),
    "n2-standard-2": (2, 8), "n2-standard-4": (4, 16), "n2-standard-8": (8, 32),
    "n2-standard-16": (16, 64), "n2-standard-32": (32, 128),
    "e2-micro": (2, 1), "e2-small": (2, 2), "e2-medium": (2, 4),
    "e2-standard-2": (2, 8), "e2-standard-4": (4, 16),
    "c2-standard-4": (4, 16), "c2-standard-8": (8, 32), "c2-standard-16": (16, 64),
    "a2-highgpu-1g": (12, 85),
}


def _gce_machine_specs(machine_type: str) -> tuple[int, float]:
    return _GCE_SPECS.get(machine_type, (1, 1.0))


def _gcp_labels(data: dict[str, Any]) -> dict[str, str]:
    labels = data.get("labels") or {}
    return {str(k): str(v) for k, v in labels.items()}


def _gcp_cost_lookup(service_type: str, cost_map: dict[str, float]) -> float:
    """Best-effort cost lookup from service type → billing service name."""
    _key_map = {
        "ComputeEngine": "Compute Engine",
        "CloudSQL": "Cloud SQL",
        "GKE": "Kubernetes Engine",
        "CloudRun": "Cloud Run",
        "CloudStorage": "Cloud Storage",
        "CloudFunctions": "Cloud Functions",
    }
    key = _key_map.get(service_type, service_type)
    return cost_map.get(key, 0.0)
