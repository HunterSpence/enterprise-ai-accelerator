"""
cloud_iq/adapters — Multi-cloud workload discovery adapter layer.

Public surface area:

    from cloud_iq.adapters import (
        DiscoveryAdapter,   # ABC — implement to add a new cloud
        Workload,           # Unified dataclass for every resource
        AWSAdapter,         # boto3: EC2, RDS, Lambda, S3, Cost Explorer
        AzureAdapter,       # Azure Resource Graph + Cost Management
        GCPAdapter,         # Cloud Asset Inventory + Cloud Billing
        KubernetesAdapter,  # Deployments, StatefulSets, DaemonSets
        UnifiedDiscovery,   # Fan-out aggregator
    )

Quickstart (auto-detect from env):

    import asyncio
    from cloud_iq.adapters import UnifiedDiscovery

    async def main():
        discovery = UnifiedDiscovery.auto()
        workloads = await discovery.discover()
        print(discovery.summary(workloads))

    asyncio.run(main())

Wire into assessor.py:

    from cloud_iq.adapters import UnifiedDiscovery
    discovery = UnifiedDiscovery.auto()
    workloads = await discovery.discover()   # list[Workload]
    # Pass workloads to CloudIQAssessor or NLQueryEngine as context
"""

from cloud_iq.adapters.base import DiscoveryAdapter, Workload
from cloud_iq.adapters.aws import AWSAdapter
from cloud_iq.adapters.azure import AzureAdapter
from cloud_iq.adapters.gcp import GCPAdapter
from cloud_iq.adapters.kubernetes import KubernetesAdapter
from cloud_iq.adapters.unified import UnifiedDiscovery

__all__ = [
    "DiscoveryAdapter",
    "Workload",
    "AWSAdapter",
    "AzureAdapter",
    "GCPAdapter",
    "KubernetesAdapter",
    "UnifiedDiscovery",
]
