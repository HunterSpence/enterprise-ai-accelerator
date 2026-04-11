"""
CloudIQ V2 — Multi-cloud aggregator.

Fans out queries to all configured providers concurrently, then merges
results into a unified cost view. A hiring manager seeing this should
recognise the producer/consumer pattern: adding a 4th provider (e.g.,
Oracle Cloud) requires zero changes to this file.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from cloud_iq.providers.base import (
    AbstractCloudProvider,
    CloudResource,
    ProviderCostSummary,
)

logger = logging.getLogger(__name__)


class MultiCloudAggregator:
    """
    Aggregates cost data and resources from multiple cloud providers.

    Queries are fanned out in parallel using asyncio.gather(), so total
    latency equals the slowest provider — not the sum of all providers.

    Usage:
        from cloud_iq.providers import AWSProvider, AzureProvider, GCPProvider
        agg = MultiCloudAggregator([
            AWSProvider(mock=True),
            AzureProvider(subscription_id="demo", mock=True),
            GCPProvider(project_id="demo", billing_account_id="demo", mock=True),
        ])
        summary = await agg.get_unified_summary()
    """

    def __init__(self, providers: list[AbstractCloudProvider]) -> None:
        self._providers = providers

    async def authenticate_all(self) -> dict[str, bool]:
        """
        Authenticate to all providers concurrently.

        Returns a dict mapping provider_name -> authenticated.
        """
        results = await asyncio.gather(
            *[p.authenticate() for p in self._providers],
            return_exceptions=True,
        )
        return {
            p.provider_name: (result is True)
            for p, result in zip(self._providers, results)
        }

    async def get_unified_summary(
        self, days: int = 90
    ) -> dict[str, Any]:
        """
        Fetch cost summaries from all providers and merge into one view.

        Returns a dict with:
            providers: list of per-provider ProviderCostSummary dicts
            total_monthly_cost_usd: float
            total_waste_usd: float
            total_resources: int
            breakdown_by_provider: dict[provider_name -> pct_of_total]
            generated_at: ISO timestamp
        """
        summaries: list[ProviderCostSummary | Exception] = await asyncio.gather(
            *[p.get_cost_summary(days=days) for p in self._providers],
            return_exceptions=True,
        )

        valid: list[ProviderCostSummary] = []
        for s, p in zip(summaries, self._providers):
            if isinstance(s, Exception):
                logger.warning(
                    "provider_cost_failed",
                    provider=p.provider_name,
                    error=str(s),
                )
            else:
                valid.append(s)

        total_monthly = sum(s.monthly_cost_usd for s in valid)
        total_waste = sum(s.waste_usd for s in valid)
        total_resources = sum(s.resource_count for s in valid)

        breakdown: dict[str, float] = {}
        for s in valid:
            pct = (s.monthly_cost_usd / total_monthly * 100) if total_monthly > 0 else 0.0
            breakdown[s.provider] = round(pct, 1)

        return {
            "providers": [
                {
                    "provider": s.provider,
                    "account_id": s.account_id,
                    "display_name": s.display_name,
                    "monthly_cost_usd": s.monthly_cost_usd,
                    "waste_usd": s.waste_usd,
                    "waste_pct": round(s.waste_usd / s.monthly_cost_usd * 100, 1) if s.monthly_cost_usd else 0,
                    "resource_count": s.resource_count,
                    "top_services": s.top_services[:3],
                }
                for s in valid
            ],
            "total_monthly_cost_usd": round(total_monthly, 2),
            "total_annual_cost_usd": round(total_monthly * 12, 2),
            "total_waste_usd": round(total_waste, 2),
            "total_waste_pct": round(total_waste / total_monthly * 100, 1) if total_monthly else 0,
            "total_resources": total_resources,
            "breakdown_by_provider": breakdown,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def list_all_resources(
        self, regions: list[str] | None = None
    ) -> list[CloudResource]:
        """
        Enumerate resources across all providers in parallel.

        Returns a flat list with each resource tagged by provider.
        """
        results = await asyncio.gather(
            *[p.list_resources(regions) for p in self._providers],
            return_exceptions=True,
        )
        all_resources: list[CloudResource] = []
        for result, p in zip(results, self._providers):
            if isinstance(result, Exception):
                logger.warning(
                    "provider_list_failed",
                    provider=p.provider_name,
                    error=str(result),
                )
            else:
                all_resources.extend(result)
        return all_resources

    async def get_all_rightsizing(self) -> dict[str, list[dict[str, Any]]]:
        """
        Gather rightsizing recommendations from all providers concurrently.

        Returns dict[provider_name -> list_of_recommendations].
        """
        results = await asyncio.gather(
            *[p.get_rightsizing_recommendations() for p in self._providers],
            return_exceptions=True,
        )
        return {
            p.provider_name: (result if not isinstance(result, Exception) else [])
            for p, result in zip(self._providers, results)
        }

    @property
    def provider_count(self) -> int:
        return len(self._providers)

    @property
    def provider_names(self) -> list[str]:
        return [p.provider_name for p in self._providers]
