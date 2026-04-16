"""Tests for cloud_iq multi-cloud discovery and migration_scout cross-cloud modules."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from cloud_iq.adapters.base import Workload, DiscoveryAdapter
from cloud_iq.adapters.unified import UnifiedDiscovery


# ---------------------------------------------------------------------------
# Minimal concrete adapter for test isolation
# ---------------------------------------------------------------------------

class _StubAdapter(DiscoveryAdapter):
    def __init__(self, cloud, items=None):
        self._cloud = cloud
        self._items = items or []

    @property
    def cloud_name(self):
        return self._cloud

    @staticmethod
    def is_configured():
        return True

    async def discover_workloads(self):
        return self._items


def _w(cloud="aws", name="res-1"):
    return Workload(id=f"{cloud}-{name}", name=name, cloud=cloud, service_type="ec2", region="us-east-1")


class TestMultiCloudDiscovery:
    async def test_aws_adapter_can_return_workloads(self):
        w = _w("aws", "ec2-1")
        adapter = _StubAdapter("aws", [w])
        results = await adapter.discover_workloads()
        assert len(results) == 1

    async def test_azure_adapter_can_return_workloads(self):
        w = _w("azure", "vm-1")
        adapter = _StubAdapter("azure", [w])
        results = await adapter.discover_workloads()
        assert any(x.name == "vm-1" for x in results)

    async def test_gcp_adapter_can_return_workloads(self):
        w = _w("gcp", "gce-1")
        adapter = _StubAdapter("gcp", [w])
        results = await adapter.discover_workloads()
        assert results[0].cloud == "gcp"

    async def test_k8s_adapter_can_return_workloads(self):
        w = _w("k8s", "pod-1")
        adapter = _StubAdapter("k8s", [w])
        results = await adapter.discover_workloads()
        assert results[0].cloud == "k8s"

    async def test_unified_discovery_merges_all_clouds(self):
        adapters = [
            _StubAdapter("aws", [_w("aws")]),
            _StubAdapter("azure", [_w("azure")]),
            _StubAdapter("gcp", [_w("gcp")]),
        ]
        discovery = UnifiedDiscovery(adapters)
        results = await discovery.discover()
        clouds = {w.cloud for w in results}
        assert "aws" in clouds
        assert "azure" in clouds
        assert "gcp" in clouds

    async def test_unified_returns_empty_when_no_adapters(self):
        discovery = UnifiedDiscovery([])
        results = await discovery.discover()
        assert results == []

    def test_unified_adapter_count(self):
        discovery = UnifiedDiscovery([_StubAdapter("aws"), _StubAdapter("gcp")])
        assert discovery.adapter_count == 2

    def test_configured_clouds_list(self):
        discovery = UnifiedDiscovery([_StubAdapter("aws"), _StubAdapter("azure")])
        assert "aws" in discovery.configured_clouds

    async def test_failing_adapter_does_not_stop_others(self):
        class _Bad(_StubAdapter):
            async def discover_workloads(self):
                raise RuntimeError("AWS API down")

        bad = _Bad("aws")
        good = _StubAdapter("gcp", [_w("gcp")])
        discovery = UnifiedDiscovery([bad, good])
        results = await discovery.discover()
        assert any(w.cloud == "gcp" for w in results)

    async def test_summary_returns_dict(self):
        w1 = _w("aws"); w2 = _w("gcp")
        discovery = UnifiedDiscovery([_StubAdapter("aws", [w1]), _StubAdapter("gcp", [w2])])
        results = await discovery.discover()
        summary = discovery.summary(results)
        assert "total_workloads" in summary
        assert summary["total_workloads"] == 2

    def test_workload_tags_default_empty(self):
        w = _w()
        assert w.tags == {}

    def test_workload_monthly_cost_default(self):
        w = _w()
        assert w.monthly_cost_usd == 0.0

    def test_workload_metadata_default_empty(self):
        w = _w()
        assert w.metadata == {}


class TestWorkloadDataclass:
    def test_workload_all_clouds_accepted(self):
        for cloud in ("aws", "azure", "gcp", "k8s"):
            w = Workload(id="x", name="n", cloud=cloud, service_type="s", region="r")
            assert w.cloud == cloud

    def test_workload_storage_gb_default(self):
        w = _w()
        assert w.storage_gb == 0.0

    def test_workload_cpu_cores_default(self):
        w = _w()
        assert w.cpu_cores == 0
