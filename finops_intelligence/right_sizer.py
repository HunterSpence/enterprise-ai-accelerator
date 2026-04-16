"""
finops_intelligence/right_sizer.py
====================================

RightSizer — EC2 instance right-sizing recommendation engine.

Pulls 14 days of CloudWatch metrics for each workload, classifies instances
as over-provisioned / under-provisioned / idle, and recommends a target
instance type from the bundled aws_instances.json catalog.

Accepts workloads via a duck-typed protocol — any object with the attributes:
    resource_id: str          (EC2 instance-id or ARN)
    instance_type: str        (e.g. "m5.xlarge")
    region: str               (e.g. "us-east-1")
    account_id: str

This keeps the module decoupled from the cloud_iq adapter classes.

No new dependencies — uses boto3, pandas, numpy (all in requirements.txt).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

import numpy as np
import pandas as pd

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Instance catalog path
# ---------------------------------------------------------------------------

_CATALOG_PATH = Path(__file__).parent / "data" / "aws_instances.json"

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_OVER_PROVISIONED_CPU_P95 = 40.0   # p95 CPU < 40%
_OVER_PROVISIONED_MEM_P95 = 50.0   # p95 Mem < 50% (if agent installed)
_UNDER_PROVISIONED_CPU_P95 = 85.0  # p95 CPU > 85%
_IDLE_CPU_P95 = 5.0                # p95 CPU < 5% for 7+ days
_IDLE_DAYS = 7
_LOOKBACK_DAYS = 14
_CW_PERIOD_SECONDS = 3600           # 1-hour CloudWatch granularity


# ---------------------------------------------------------------------------
# Protocol for workload duck-typing
# ---------------------------------------------------------------------------

@runtime_checkable
class Workload(Protocol):
    resource_id: str
    instance_type: str
    region: str
    account_id: str


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MetricsSnapshot:
    """Raw metric statistics for a single instance over the lookback window."""

    resource_id: str
    instance_type: str
    region: str
    cpu_avg: float = 0.0
    cpu_p95: float = 0.0
    mem_avg: Optional[float] = None   # None if CW agent not installed
    mem_p95: Optional[float] = None
    net_in_avg_mbps: float = 0.0
    net_out_avg_mbps: float = 0.0
    disk_read_iops_avg: float = 0.0
    disk_write_iops_avg: float = 0.0
    data_points: int = 0
    lookback_days: int = _LOOKBACK_DAYS
    idle_days: int = 0


@dataclass
class RightSizingRec:
    """Right-sizing recommendation for a single EC2 instance."""

    resource_id: str
    current_type: str
    recommended_type: str
    current_monthly_cost_usd: float
    recommended_monthly_cost_usd: float
    projected_monthly_savings: float
    savings_pct: float
    risk: str                  # 'low' | 'medium' | 'high'
    classification: str        # 'over_provisioned' | 'under_provisioned' | 'idle' | 'rightsized'
    region: str
    metrics_snapshot: MetricsSnapshot = field(repr=False)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "current_type": self.current_type,
            "recommended_type": self.recommended_type,
            "current_monthly_cost_usd": round(self.current_monthly_cost_usd, 2),
            "recommended_monthly_cost_usd": round(self.recommended_monthly_cost_usd, 2),
            "projected_monthly_savings": round(self.projected_monthly_savings, 2),
            "savings_pct": round(self.savings_pct, 1),
            "risk": self.risk,
            "classification": self.classification,
            "region": self.region,
            "rationale": self.rationale,
            "metrics": {
                "cpu_avg": round(self.metrics_snapshot.cpu_avg, 1),
                "cpu_p95": round(self.metrics_snapshot.cpu_p95, 1),
                "mem_p95": round(self.metrics_snapshot.mem_p95, 1) if self.metrics_snapshot.mem_p95 is not None else None,
                "idle_days": self.metrics_snapshot.idle_days,
                "data_points": self.metrics_snapshot.data_points,
            },
        }


# ---------------------------------------------------------------------------
# Instance catalog loader
# ---------------------------------------------------------------------------

class _InstanceCatalog:
    """In-process cache of the bundled aws_instances.json catalog."""

    _cache: Optional[dict[str, dict]] = None

    @classmethod
    def load(cls) -> dict[str, dict]:
        if cls._cache is None:
            with open(_CATALOG_PATH) as f:
                data = json.load(f)
            cls._cache = {inst["type"]: inst for inst in data["instances"]}
        return cls._cache

    @classmethod
    def get(cls, instance_type: str) -> Optional[dict]:
        return cls.load().get(instance_type)

    @classmethod
    def monthly_cost(cls, instance_type: str) -> float:
        """Return estimated monthly on-demand cost (730 hours) for us-east-1 Linux."""
        inst = cls.get(instance_type)
        if inst:
            return inst["od_linux_hourly_usd"] * 730
        return 0.0

    @classmethod
    def family_members(cls, family: str) -> list[dict]:
        """Return all instances in a given family, sorted by vCPU."""
        return sorted(
            [inst for inst in cls.load().values() if inst["family"] == family],
            key=lambda i: (i["vcpu"], i["ram_gb"]),
        )


# ---------------------------------------------------------------------------
# RightSizer
# ---------------------------------------------------------------------------

class RightSizer:
    """Fetches CloudWatch metrics and produces right-sizing recommendations.

    Usage::

        sizer = RightSizer(aws_profile="my-profile")
        recs = await sizer.recommend(workloads)
        for rec in recs:
            print(rec.to_dict())
    """

    def __init__(
        self,
        aws_profile: Optional[str] = None,
        aws_region: str = "us-east-1",
        lookback_days: int = _LOOKBACK_DAYS,
    ) -> None:
        if boto3 is None:
            raise RuntimeError("boto3 is required — pip install boto3>=1.34.0")
        self._aws_profile = aws_profile
        self._aws_region = aws_region
        self._lookback_days = lookback_days

    async def recommend(
        self,
        workloads: list[Any],
        metrics_source: Optional[Any] = None,
    ) -> list[RightSizingRec]:
        """Analyse workloads and return right-sizing recommendations.

        Args:
            workloads: List of objects with resource_id, instance_type, region,
                       account_id attributes (Workload protocol).
            metrics_source: Optional override for CloudWatch client (for testing).

        Returns:
            List of RightSizingRec, sorted by projected_monthly_savings desc.
        """
        recs: list[RightSizingRec] = []
        for wl in workloads:
            try:
                snapshot = self._fetch_metrics(wl, metrics_source)
                rec = self._classify_and_recommend(wl, snapshot)
                if rec is not None:
                    recs.append(rec)
            except Exception as exc:
                logger.warning("Skipping workload %s: %s", getattr(wl, "resource_id", "?"), exc)
        recs.sort(key=lambda r: r.projected_monthly_savings, reverse=True)
        logger.info("RightSizer: produced %d recommendations", len(recs))
        return recs

    # ------------------------------------------------------------------
    # CloudWatch metrics fetching
    # ------------------------------------------------------------------

    def _get_cw_client(self, region: str, metrics_source: Optional[Any]) -> Any:
        if metrics_source is not None:
            return metrics_source
        session = (
            boto3.Session(profile_name=self._aws_profile)
            if self._aws_profile
            else boto3.Session()
        )
        return session.client("cloudwatch", region_name=region)

    def _fetch_metrics(self, workload: Any, metrics_source: Optional[Any]) -> MetricsSnapshot:
        """Fetch 14d of hourly CW metrics for a single instance."""
        region = getattr(workload, "region", self._aws_region)
        resource_id = workload.resource_id
        instance_type = workload.instance_type
        cw = self._get_cw_client(region, metrics_source)

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self._lookback_days)

        def get_stat(metric: str, namespace: str, stat: str, dim_name: str, dim_val: str) -> list[float]:
            try:
                resp = cw.get_metric_statistics(
                    Namespace=namespace,
                    MetricName=metric,
                    Dimensions=[{"Name": dim_name, "Value": dim_val}],
                    StartTime=start,
                    EndTime=end,
                    Period=_CW_PERIOD_SECONDS,
                    Statistics=[stat],
                )
                return [p[stat] for p in resp.get("Datapoints", [])]
            except Exception as exc:
                logger.debug("CW fetch failed %s/%s: %s", namespace, metric, exc)
                return []

        cpu_vals = get_stat("CPUUtilization", "AWS/EC2", "Average", "InstanceId", resource_id)
        cpu_p95_vals = get_stat("CPUUtilization", "AWS/EC2", "p95", "InstanceId", resource_id)
        # If p95 not available as a stat, compute from average data
        if not cpu_p95_vals and cpu_vals:
            cpu_p95_vals = cpu_vals
        net_in = get_stat("NetworkIn", "AWS/EC2", "Average", "InstanceId", resource_id)
        net_out = get_stat("NetworkOut", "AWS/EC2", "Average", "InstanceId", resource_id)
        disk_read = get_stat("DiskReadOps", "AWS/EC2", "Average", "InstanceId", resource_id)
        disk_write = get_stat("DiskWriteOps", "AWS/EC2", "Average", "InstanceId", resource_id)
        # CW agent memory (optional)
        mem_vals = get_stat("mem_used_percent", "CWAgent", "Average", "InstanceId", resource_id)
        mem_p95_vals = get_stat("mem_used_percent", "CWAgent", "p95", "InstanceId", resource_id)
        if not mem_p95_vals and mem_vals:
            mem_p95_vals = mem_vals

        cpu_arr = np.array(cpu_vals or [0.0])
        cpu_p95_arr = np.array(cpu_p95_vals or [0.0])
        net_in_arr = np.array(net_in or [0.0]) / 1e6 / 8  # bytes/s -> Mbps
        net_out_arr = np.array(net_out or [0.0]) / 1e6 / 8

        # Idle detection: count days where all hourly CPU readings < IDLE threshold
        idle_days = 0
        if cpu_vals and len(cpu_vals) >= 24:
            # Chunk into 24-hour windows and check if all < threshold
            arr = np.array(cpu_vals)
            n_full_days = len(arr) // 24
            for d in range(n_full_days):
                day_slice = arr[d * 24 : (d + 1) * 24]
                if float(np.percentile(day_slice, 95)) < _IDLE_CPU_P95:
                    idle_days += 1

        return MetricsSnapshot(
            resource_id=resource_id,
            instance_type=instance_type,
            region=region,
            cpu_avg=float(np.mean(cpu_arr)),
            cpu_p95=float(np.percentile(cpu_p95_arr, 95)) if len(cpu_p95_arr) > 0 else 0.0,
            mem_avg=float(np.mean(mem_vals)) if mem_vals else None,
            mem_p95=float(np.percentile(mem_p95_vals, 95)) if mem_p95_vals else None,
            net_in_avg_mbps=float(np.mean(net_in_arr)),
            net_out_avg_mbps=float(np.mean(net_out_arr)),
            disk_read_iops_avg=float(np.mean(disk_read)) if disk_read else 0.0,
            disk_write_iops_avg=float(np.mean(disk_write)) if disk_write else 0.0,
            data_points=len(cpu_vals),
            lookback_days=self._lookback_days,
            idle_days=idle_days,
        )

    # ------------------------------------------------------------------
    # Classification + recommendation
    # ------------------------------------------------------------------

    def _classify_and_recommend(
        self, workload: Any, snapshot: MetricsSnapshot
    ) -> Optional[RightSizingRec]:
        current_type = workload.instance_type
        current_spec = _InstanceCatalog.get(current_type)
        if current_spec is None:
            logger.debug("Instance type %s not in catalog — skipping", current_type)
            return None

        current_monthly = _InstanceCatalog.monthly_cost(current_type)
        family = current_spec["family"]

        # --- Classification ---
        if snapshot.data_points < 24:
            return None  # Not enough data

        is_idle = snapshot.idle_days >= _IDLE_DAYS and snapshot.cpu_p95 < _IDLE_CPU_P95
        is_over = (
            snapshot.cpu_p95 < _OVER_PROVISIONED_CPU_P95
            and (snapshot.mem_p95 is None or snapshot.mem_p95 < _OVER_PROVISIONED_MEM_P95)
        )
        is_under = snapshot.cpu_p95 > _UNDER_PROVISIONED_CPU_P95

        if is_idle:
            classification = "idle"
            risk = "low"
            # Recommend one size down or t3.micro
            recommended = self._one_size_down(current_type, family)
        elif is_over:
            classification = "over_provisioned"
            risk = "low"
            recommended = self._one_size_down(current_type, family)
        elif is_under:
            classification = "under_provisioned"
            risk = "medium"
            recommended = self._one_size_up(current_type, family)
        else:
            classification = "rightsized"
            risk = "low"
            recommended = current_type

        if recommended == current_type:
            return None  # No change recommended

        recommended_monthly = _InstanceCatalog.monthly_cost(recommended)
        savings = current_monthly - recommended_monthly
        savings_pct = (savings / current_monthly * 100) if current_monthly > 0 else 0.0

        # Build rationale
        rationale_parts = [f"p95 CPU={snapshot.cpu_p95:.1f}%"]
        if snapshot.mem_p95 is not None:
            rationale_parts.append(f"p95 Mem={snapshot.mem_p95:.1f}%")
        if is_idle:
            rationale_parts.append(f"idle for {snapshot.idle_days} days")
        rationale = f"{classification.replace('_', ' ').title()}: {', '.join(rationale_parts)}"

        return RightSizingRec(
            resource_id=workload.resource_id,
            current_type=current_type,
            recommended_type=recommended,
            current_monthly_cost_usd=round(current_monthly, 2),
            recommended_monthly_cost_usd=round(recommended_monthly, 2),
            projected_monthly_savings=round(savings, 2),
            savings_pct=round(savings_pct, 1),
            risk=risk,
            classification=classification,
            region=workload.region,
            metrics_snapshot=snapshot,
            rationale=rationale,
        )

    def _family_members(self, family: str) -> list[dict]:
        return _InstanceCatalog.family_members(family)

    def _one_size_down(self, current_type: str, family: str) -> str:
        members = self._family_members(family)
        if not members:
            return current_type
        current_spec = _InstanceCatalog.get(current_type)
        if current_spec is None:
            return current_type
        current_vcpu = current_spec["vcpu"]
        # Find the next smaller type
        smaller = [m for m in members if m["vcpu"] < current_vcpu]
        if not smaller:
            return current_type
        # Pick the largest of the smaller options
        return smaller[-1]["type"]

    def _one_size_up(self, current_type: str, family: str) -> str:
        members = self._family_members(family)
        if not members:
            return current_type
        current_spec = _InstanceCatalog.get(current_type)
        if current_spec is None:
            return current_type
        current_vcpu = current_spec["vcpu"]
        larger = [m for m in members if m["vcpu"] > current_vcpu]
        if not larger:
            return current_type
        return larger[0]["type"]

    # ------------------------------------------------------------------
    # Reporting helper
    # ------------------------------------------------------------------

    @staticmethod
    def to_dataframe(recs: list[RightSizingRec]) -> pd.DataFrame:
        return pd.DataFrame([r.to_dict() for r in recs]) if recs else pd.DataFrame()
