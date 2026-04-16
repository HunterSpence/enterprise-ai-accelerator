"""
cloud_iq/adapters/azure.py
==========================

AzureAdapter — real Azure SDK discovery via Resource Graph + Cost Management.

Credential chain (standard Azure SDK order — no custom auth required):
  1. Service principal:    AZURE_CLIENT_ID + AZURE_CLIENT_SECRET + AZURE_TENANT_ID
  2. Managed identity:     AZURE_CLIENT_ID alone (user-assigned) or ambient (system-assigned)
  3. Azure CLI:            `az login` session token
  4. VS Code / DeviceCode: picked up automatically by DefaultAzureCredential

Required env vars:
  AZURE_SUBSCRIPTION_ID   — the subscription to scan (required; no default)
  AZURE_TENANT_ID         — required for service principal auth
  AZURE_CLIENT_ID         — required for service principal / user-assigned MI
  AZURE_CLIENT_SECRET     — required for service principal auth

All SDK calls run in asyncio.to_thread() — the azure-mgmt SDKs are synchronous.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from cloud_iq.adapters.base import DiscoveryAdapter, Workload

logger = logging.getLogger(__name__)

# Resource Graph query that pulls every resource in the subscription.
_ARG_QUERY = (
    "Resources "
    "| project id, name, type, location, tags, properties, resourceGroup, kind, sku"
)

# Cost Management granularity for last-30d actual costs
_COST_TIMEFRAME = "MonthToDate"


class AzureAdapter(DiscoveryAdapter):
    """
    Discovers Azure workloads using Resource Graph + Cost Management API.

    Resource Graph queries paginate automatically across the entire subscription,
    giving a complete inventory in minimal API calls (typically 1-2 pages for
    most subscriptions). Cost Management adds per-service-type cost actuals.
    """

    def __init__(self, subscription_id: str | None = None) -> None:
        self._subscription_id = (
            subscription_id or os.environ.get("AZURE_SUBSCRIPTION_ID", "")
        )

    # ------------------------------------------------------------------
    # DiscoveryAdapter interface
    # ------------------------------------------------------------------

    @property
    def cloud_name(self) -> str:
        return "azure"

    @staticmethod
    def is_configured() -> bool:
        """True when AZURE_SUBSCRIPTION_ID is present (auth falls to SDK chain)."""
        return bool(os.environ.get("AZURE_SUBSCRIPTION_ID"))

    async def discover_workloads(self) -> list[Workload]:
        if not self._subscription_id:
            logger.warning("azure_no_subscription_id")
            return []

        resources_task = asyncio.create_task(self._fetch_resources())
        cost_task = asyncio.create_task(self._fetch_costs())

        resources, cost_map = await asyncio.gather(
            resources_task, cost_task, return_exceptions=True
        )

        if isinstance(resources, Exception):
            logger.warning("azure_resource_graph_error error=%s", resources)
            resources = []
        if isinstance(cost_map, Exception):
            logger.warning("azure_cost_error error=%s", cost_map)
            cost_map = {}

        return self._map_resources(resources, cost_map)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Resource Graph
    # ------------------------------------------------------------------

    async def _fetch_resources(self) -> list[dict[str, Any]]:
        def _run() -> list[dict[str, Any]]:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.mgmt.resourcegraph import ResourceGraphClient
                from azure.mgmt.resourcegraph.models import QueryRequest

                credential = DefaultAzureCredential()
                client = ResourceGraphClient(credential)
                results: list[dict[str, Any]] = []
                skip_token: str | None = None

                while True:
                    req = QueryRequest(
                        subscriptions=[self._subscription_id],
                        query=_ARG_QUERY,
                        options={"resultFormat": "objectArray", "$skipToken": skip_token}
                        if skip_token
                        else {"resultFormat": "objectArray"},
                    )
                    resp = client.resources(req)
                    data = resp.data if hasattr(resp, "data") else []
                    if isinstance(data, list):
                        results.extend(data)
                    skip_token = getattr(resp, "skip_token", None)
                    if not skip_token:
                        break

                return results
            except ImportError as exc:
                logger.warning(
                    "azure_sdk_not_installed missing=%s — pip install azure-identity azure-mgmt-resourcegraph",
                    exc,
                )
                return []

        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # Cost Management
    # ------------------------------------------------------------------

    async def _fetch_costs(self) -> dict[str, float]:
        """Return {resource_type: total_usd} for the current month to date."""
        def _run() -> dict[str, float]:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.mgmt.costmanagement import CostManagementClient
                from azure.mgmt.costmanagement.models import (
                    QueryDefinition,
                    QueryTimePeriod,
                    QueryDataset,
                    QueryAggregation,
                    QueryGrouping,
                )

                credential = DefaultAzureCredential()
                client = CostManagementClient(credential)
                scope = f"/subscriptions/{self._subscription_id}"

                end = datetime.now(timezone.utc)
                start = end - timedelta(days=30)

                query = QueryDefinition(
                    type="ActualCost",
                    timeframe="Custom",
                    time_period=QueryTimePeriod(from_property=start, to=end),
                    dataset=QueryDataset(
                        granularity="None",
                        aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
                        grouping=[QueryGrouping(type="Dimension", name="ResourceType")],
                    ),
                )

                resp = client.query.usage(scope=scope, parameters=query)
                cost_map: dict[str, float] = {}
                if hasattr(resp, "rows") and resp.rows:
                    # rows: [[cost_amount, currency, resource_type], ...]
                    for row in resp.rows:
                        if len(row) >= 3:
                            try:
                                resource_type = str(row[2]).lower()
                                amount = float(row[0])
                                cost_map[resource_type] = cost_map.get(resource_type, 0.0) + amount
                            except (ValueError, TypeError):
                                pass
                return cost_map
            except ImportError as exc:
                logger.warning(
                    "azure_costmgmt_sdk_not_installed missing=%s — pip install azure-mgmt-costmanagement",
                    exc,
                )
                return {}
            except Exception as exc:
                logger.warning("azure_cost_fetch_error error=%s", exc)
                return {}

        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _map_resources(
        self, resources: list[dict[str, Any]], cost_map: dict[str, float]
    ) -> list[Workload]:
        now = datetime.now(timezone.utc)
        workloads: list[Workload] = []

        for r in resources:
            rtype = str(r.get("type", "")).lower()
            rtype_display = r.get("type", "Unknown")
            location = r.get("location", "unknown")
            rid = r.get("id", "")
            name = r.get("name", rid)
            tags: dict[str, str] = {}
            raw_tags = r.get("tags")
            if isinstance(raw_tags, dict):
                tags = {str(k): str(v) for k, v in raw_tags.items()}

            props: dict[str, Any] = r.get("properties") or {}
            service_type = _az_service_type(rtype)
            cpu, mem, storage = _az_resource_specs(rtype, props)

            cost = cost_map.get(rtype, 0.0)

            workloads.append(Workload(
                id=rid,
                name=name,
                cloud="azure",
                service_type=service_type,
                region=location,
                tags=tags,
                monthly_cost_usd=cost,
                cpu_cores=cpu,
                memory_gb=mem,
                storage_gb=storage,
                last_seen=now,
                metadata={
                    "resource_type": rtype_display,
                    "resource_group": r.get("resourceGroup"),
                    "kind": r.get("kind"),
                    "sku": r.get("sku"),
                    "provisioning_state": props.get("provisioningState"),
                },
            ))

        return workloads


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _az_service_type(resource_type: str) -> str:
    """Map Azure resource type to a friendly service category."""
    _map = {
        "microsoft.compute/virtualmachines": "VirtualMachine",
        "microsoft.sql/servers/databases": "SQLDatabase",
        "microsoft.dbformysql/servers": "MySQLDatabase",
        "microsoft.dbforpostgresql/servers": "PostgreSQLDatabase",
        "microsoft.web/sites": "AppService",
        "microsoft.containerservice/managedclusters": "AKS",
        "microsoft.storage/storageaccounts": "StorageAccount",
        "microsoft.keyvault/vaults": "KeyVault",
        "microsoft.network/virtualnetworks": "VirtualNetwork",
        "microsoft.network/loadbalancers": "LoadBalancer",
        "microsoft.cache/redis": "RedisCache",
        "microsoft.eventhub/namespaces": "EventHub",
        "microsoft.servicebus/namespaces": "ServiceBus",
        "microsoft.cognitiveservices/accounts": "CognitiveServices",
    }
    return _map.get(resource_type, "AzureResource")


def _az_resource_specs(
    resource_type: str, props: dict[str, Any]
) -> tuple[int, float, float]:
    """Return (cpu_cores, memory_gb, storage_gb) from properties; best-effort."""
    cpu, mem, storage = 0, 0.0, 0.0
    # VM hardware profile
    if "microsoft.compute/virtualmachines" in resource_type:
        hw = props.get("hardwareProfile", {})
        vm_size = hw.get("vmSize", "")
        # Rough lookup — Azure VM sizes encode specs differently
        cpu, mem = _az_vm_specs(vm_size)
    # SQL / managed DB storage
    elif "sql" in resource_type or "mysql" in resource_type or "postgresql" in resource_type:
        storage_mb = props.get("storageProfile", {}).get("storageMB", 0)
        storage = round(storage_mb / 1024, 2)
    # Storage account — approximate from quota
    elif "storage" in resource_type:
        storage = 0.0  # would require separate blob metrics call
    return cpu, float(mem), storage


# Minimal Azure VM size → (vcpu, ram_gb) table for common families
_AZ_VM_SPECS: dict[str, tuple[int, float]] = {
    "Standard_B1s": (1, 1), "Standard_B2s": (2, 4), "Standard_B4ms": (4, 16),
    "Standard_D2s_v3": (2, 8), "Standard_D4s_v3": (4, 16), "Standard_D8s_v3": (8, 32),
    "Standard_D16s_v3": (16, 64), "Standard_D32s_v3": (32, 128),
    "Standard_E2s_v3": (2, 16), "Standard_E4s_v3": (4, 32), "Standard_E8s_v3": (8, 64),
    "Standard_F2s_v2": (2, 4), "Standard_F4s_v2": (4, 8), "Standard_F8s_v2": (8, 16),
    "Standard_NC6": (6, 56), "Standard_NC12": (12, 112),
}


def _az_vm_specs(vm_size: str) -> tuple[int, float]:
    return _AZ_VM_SPECS.get(vm_size, (1, 1.0))
