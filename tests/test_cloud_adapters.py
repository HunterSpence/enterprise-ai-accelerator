"""Tests for cloud_iq/adapters/base.py + unified.py — Workload, DiscoveryAdapter, UnifiedDiscovery."""

import asyncio
from datetime import datetime
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

import pytest
from cloud_iq.adapters.base import DiscoveryAdapter, Workload
from cloud_iq.adapters.unified import UnifiedDiscovery


class _FakeAdapter(DiscoveryAdapter):
    """Minimal concrete adapter for testing."""

    def __init__(self, cloud: str, workloads: list[Workload]):
        self._cloud = cloud
        self._workloads = workloads

    @property
    def cloud_name(self) -> Literal["aws", "azure", "gcp", "k8s"]:
        return self._cloud  # type: ignore[return-value]

    @staticmethod
    def is_configured() -> bool:
        return True

    async def discover_workloads(self) -> list[Workload]:
        return self._workloads


class _ErrorAdapter(_FakeAdapter):
    async def discover_workloads(self):
        raise RuntimeError("simulated adapter failure")


def _make_workload(cloud="aws", name="w1"):
    return Workload(
        id=f"{cloud}-{name}",
        name=name,
        cloud=cloud,  # type: ignore[arg-type]
        service_type="ec2",
        region="us-east-1",
    )


class TestWorkload:
    def test_workload_construction(self):
        w = _make_workload()
        assert w.cloud == "aws"
        assert w.service_type == "ec2"
        assert w.monthly_cost_usd == 0.0

    def test_workload_defaults(self):
        w = Workload(id="x", name="y", cloud="gcp", service_type="gce", region="us-central1")
        assert w.cpu_cores == 0
        assert w.memory_gb == 0.0
        assert isinstance(w.last_seen, datetime)

    def test_workload_tags(self):
        w = _make_workload()
        w.tags["env"] = "prod"
        assert w.tags["env"] == "prod"


class TestDiscoveryAdapterABC:
    def test_concrete_adapter_instantiates(self):
        adapter = _FakeAdapter("aws", [])
        assert adapter.cloud_name == "aws"
        assert adapter.is_configured() is True

    async def test_discover_workloads_returns_list(self):
        w = _make_workload()
        adapter = _FakeAdapter("aws", [w])
        workloads = await adapter.discover_workloads()
        assert len(workloads) == 1
        assert workloads[0].name == "w1"


class TestUnifiedDiscovery:
    async def test_empty_adapters_returns_empty(self):
        discovery = UnifiedDiscovery([])
        result = await discovery.discover()
        assert result == []

    async def test_single_adapter_returns_its_workloads(self):
        w = _make_workload()
        adapter = _FakeAdapter("aws", [w])
        discovery = UnifiedDiscovery([adapter])
        result = await discovery.discover()
        assert len(result) == 1

    async def test_multiple_adapters_merged(self):
        w1 = _make_workload("aws", "a")
        w2 = _make_workload("gcp", "b")
        aws_adapter = _FakeAdapter("aws", [w1])
        gcp_adapter = _FakeAdapter("gcp", [w2])
        discovery = UnifiedDiscovery([aws_adapter, gcp_adapter])
        result = await discovery.discover()
        assert len(result) == 2

    async def test_failing_adapter_does_not_block_others(self):
        w = _make_workload("gcp", "good")
        good_adapter = _FakeAdapter("gcp", [w])
        bad_adapter = _ErrorAdapter("aws", [])
        discovery = UnifiedDiscovery([bad_adapter, good_adapter])
        result = await discovery.discover()
        # Good adapter's workload should still appear
        assert any(x.cloud == "gcp" for x in result)

    def test_adapter_count_property(self):
        adapters = [_FakeAdapter("aws", []), _FakeAdapter("gcp", [])]
        discovery = UnifiedDiscovery(adapters)
        assert discovery.adapter_count == 2

    def test_configured_clouds_property(self):
        adapters = [_FakeAdapter("aws", []), _FakeAdapter("azure", [])]
        discovery = UnifiedDiscovery(adapters)
        clouds = discovery.configured_clouds
        assert "aws" in clouds
        assert "azure" in clouds

    async def test_result_is_sorted(self):
        w_aws = _make_workload("aws", "z")
        w_gcp = _make_workload("gcp", "a")
        discovery = UnifiedDiscovery([
            _FakeAdapter("gcp", [w_gcp]),
            _FakeAdapter("aws", [w_aws]),
        ])
        result = await discovery.discover()
        clouds = [w.cloud for w in result]
        assert clouds == sorted(clouds)
