"""
cloud_iq/adapters/unified.py
============================

UnifiedDiscovery — fans out to all configured adapters in parallel and returns
a single flat list of Workload objects.

Usage (manual adapter construction):

    from cloud_iq.adapters import AWSAdapter, KubernetesAdapter, UnifiedDiscovery

    discovery = UnifiedDiscovery([AWSAdapter(), KubernetesAdapter()])
    workloads = await discovery.discover()

Usage (auto-detect from env vars):

    discovery = UnifiedDiscovery.auto()
    workloads = await discovery.discover()

The auto() factory inspects env vars via each adapter's is_configured() static
method and only instantiates adapters whose credentials are present. This means
a customer with only AWS configured gets exactly one adapter — no Azure/GCP
errors, no empty-catch noise.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from cloud_iq.adapters.base import DiscoveryAdapter, Workload

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class UnifiedDiscovery:
    """
    Aggregates workload discovery across multiple cloud adapters.

    All adapter discover_workloads() calls run concurrently via asyncio.gather
    with return_exceptions=True so a single adapter failure never blocks the
    others. Exceptions are logged at WARNING level and the adapter contributes
    an empty slice to the merged result.
    """

    def __init__(self, adapters: list[DiscoveryAdapter]) -> None:
        self._adapters = adapters

    # ------------------------------------------------------------------
    # Auto-detect factory
    # ------------------------------------------------------------------

    @classmethod
    def auto(cls) -> "UnifiedDiscovery":
        """
        Construct a UnifiedDiscovery from whichever adapters are configured.

        Checks each adapter's is_configured() (env-var-only, no network) and
        instantiates only those that have credentials available. Returns an
        instance with zero adapters if nothing is configured — calling
        discover() on it will return [] gracefully.

        Adapter detection order: AWS → Azure → GCP → Kubernetes.
        """
        from cloud_iq.adapters.aws import AWSAdapter
        from cloud_iq.adapters.azure import AzureAdapter
        from cloud_iq.adapters.gcp import GCPAdapter
        from cloud_iq.adapters.kubernetes import KubernetesAdapter

        adapters: list[DiscoveryAdapter] = []

        if AWSAdapter.is_configured():
            adapters.append(AWSAdapter())
            logger.info("unified_discovery_auto adapter=AWS status=configured")
        else:
            logger.debug("unified_discovery_auto adapter=AWS status=not_configured")

        if AzureAdapter.is_configured():
            adapters.append(AzureAdapter())
            logger.info("unified_discovery_auto adapter=Azure status=configured")
        else:
            logger.debug("unified_discovery_auto adapter=Azure status=not_configured")

        if GCPAdapter.is_configured():
            adapters.append(GCPAdapter())
            logger.info("unified_discovery_auto adapter=GCP status=configured")
        else:
            logger.debug("unified_discovery_auto adapter=GCP status=not_configured")

        if KubernetesAdapter.is_configured():
            adapters.append(KubernetesAdapter())
            logger.info("unified_discovery_auto adapter=Kubernetes status=configured")
        else:
            logger.debug("unified_discovery_auto adapter=Kubernetes status=not_configured")

        if not adapters:
            logger.warning(
                "unified_discovery_no_adapters — set AWS_ACCESS_KEY_ID, "
                "AZURE_SUBSCRIPTION_ID, GOOGLE_CLOUD_PROJECT, or KUBECONFIG"
            )

        return cls(adapters)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def discover(self) -> list[Workload]:
        """
        Run all adapters in parallel and merge results.

        Returns a flat list of Workload objects sorted by cloud then service_type.
        Adapter failures are caught and logged — never propagated.
        """
        if not self._adapters:
            return []

        results = await asyncio.gather(
            *[adapter.discover_workloads() for adapter in self._adapters],
            return_exceptions=True,
        )

        all_workloads: list[Workload] = []
        for adapter, result in zip(self._adapters, results):
            if isinstance(result, Exception):
                logger.warning(
                    "unified_discovery_adapter_error adapter=%s error=%s",
                    adapter.cloud_name,
                    result,
                )
            else:
                logger.info(
                    "unified_discovery_adapter_ok adapter=%s count=%d",
                    adapter.cloud_name,
                    len(result),
                )
                all_workloads.extend(result)

        # Stable sort: cloud name, then service_type, then resource name
        all_workloads.sort(key=lambda w: (w.cloud, w.service_type, w.name))
        return all_workloads

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def adapter_count(self) -> int:
        return len(self._adapters)

    @property
    def configured_clouds(self) -> list[str]:
        return [a.cloud_name for a in self._adapters]

    def summary(self, workloads: list[Workload]) -> dict[str, Any]:
        """Return a quick stats dict from a discover() result."""
        from collections import defaultdict
        by_cloud: dict[str, int] = defaultdict(int)
        total_cost = 0.0
        for w in workloads:
            by_cloud[w.cloud] += 1
            total_cost += w.monthly_cost_usd
        return {
            "total_workloads": len(workloads),
            "by_cloud": dict(by_cloud),
            "total_monthly_cost_usd": round(total_cost, 2),
            "configured_clouds": self.configured_clouds,
        }


# ---------------------------------------------------------------------------
# Allow 'from typing import Any' without adding it to the main import block
# ---------------------------------------------------------------------------
from typing import Any  # noqa: E402 — intentional late import for summary()
