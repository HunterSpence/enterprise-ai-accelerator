"""
cloud_iq/adapters/base.py
=========================

Shared ABC and Workload dataclass for the multi-cloud discovery adapter layer.

Every adapter (AWS, Azure, GCP, Kubernetes) implements DiscoveryAdapter so
UnifiedDiscovery can fan them out via asyncio.gather() without any
provider-specific logic in the aggregator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass
class Workload:
    """
    Normalised representation of a single cloud workload / resource.

    All adapters map their provider-specific objects to this common shape so
    downstream consumers (assessor.py, finops_intelligence, nl_query) never
    need to branch on cloud type for basic reporting.
    """

    id: str
    name: str
    cloud: Literal["aws", "azure", "gcp", "k8s"]
    service_type: str
    region: str
    tags: dict[str, str] = field(default_factory=dict)
    monthly_cost_usd: float = 0.0
    cpu_cores: int = 0
    memory_gb: float = 0.0
    storage_gb: float = 0.0
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


class DiscoveryAdapter(ABC):
    """
    Async interface every cloud adapter must implement.

    Design goals:
    - All I/O in discover_workloads(); no blocking calls on the event loop.
    - Graceful degradation: if credentials are absent or a service call fails,
      log a warning and return an empty list rather than raising.
    - is_configured() is a pure env-var check — no network calls — so
      UnifiedDiscovery.auto() can skip unconfigured adapters cheaply.
    """

    @property
    @abstractmethod
    def cloud_name(self) -> Literal["aws", "azure", "gcp", "k8s"]:
        """Short identifier matching Workload.cloud."""
        ...

    @staticmethod
    @abstractmethod
    def is_configured() -> bool:
        """
        Return True if the minimum required environment variables are set.

        Must not make any network calls — purely env-var inspection.
        Called by UnifiedDiscovery.auto() to decide which adapters to build.
        """
        ...

    @abstractmethod
    async def discover_workloads(self) -> list[Workload]:
        """
        Discover all workloads reachable with the current credentials.

        Must never raise — catch all exceptions internally, log at WARNING
        level, and return [] so the unified fan-out can continue with other
        adapters.
        """
        ...
