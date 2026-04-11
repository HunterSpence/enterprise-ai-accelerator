"""
Abstract base class for CloudIQ cloud provider adapters.

Every provider implements this async interface so the multi-cloud aggregator
can treat AWS, Azure, and GCP uniformly. Adding a new cloud provider means
implementing this class — no changes elsewhere required.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ProviderCapabilities:
    """Declares which optional features a provider supports."""

    cost_export: bool = False
    rightsizing_api: bool = False
    kubernetes: bool = False
    serverless: bool = False
    object_storage: bool = False
    managed_databases: bool = False
    terraform_import: bool = False


@dataclass
class CloudResource:
    """Minimal common representation for any cloud resource."""

    resource_id: str
    resource_type: str
    provider: str
    region: str
    monthly_cost_usd: float
    tags: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderCostSummary:
    """High-level cost summary returned by get_cost_summary()."""

    provider: str
    account_id: str
    display_name: str
    currency: str
    monthly_cost_usd: float
    daily_costs_30d: list[tuple[datetime, float]]
    top_services: list[dict[str, Any]]
    resource_count: int
    waste_usd: float


class AbstractCloudProvider(ABC):
    """
    Async interface every cloud provider adapter must implement.

    The async design lets the multi-cloud aggregator fan out provider
    queries in parallel using asyncio.gather() rather than serialising them.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name (e.g. 'AWS', 'Azure', 'GCP')."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Declare which optional features this provider supports."""
        ...

    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Verify credentials are valid and return True on success.

        Should be called before any data-fetching methods. Raises
        PermissionError if credentials are present but insufficient.
        """
        ...

    @abstractmethod
    async def get_cost_summary(
        self, days: int = 90
    ) -> ProviderCostSummary:
        """
        Return a high-level cost breakdown for the past N days.

        Always returns a populated object even if billing data is unavailable
        (returns zeros with a warning in metadata).
        """
        ...

    @abstractmethod
    async def list_resources(
        self, regions: list[str] | None = None
    ) -> list[CloudResource]:
        """
        Enumerate all billable resources across the specified regions.

        If regions is None, discovers all available regions automatically.
        """
        ...

    @abstractmethod
    async def get_rightsizing_recommendations(self) -> list[dict[str, Any]]:
        """
        Return native rightsizing recommendations from the provider's API.

        AWS: Cost Explorer Rightsizing API
        Azure: Azure Advisor
        GCP: Recommender API
        """
        ...

    async def health_check(self) -> dict[str, Any]:
        """
        Lightweight connectivity check.

        Returns {"healthy": bool, "latency_ms": float, "detail": str|None}.
        """
        import time
        t0 = time.monotonic()
        try:
            ok = await self.authenticate()
            return {
                "healthy": ok,
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "detail": None,
            }
        except Exception as exc:
            return {
                "healthy": False,
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "detail": str(exc)[:200],
            }
