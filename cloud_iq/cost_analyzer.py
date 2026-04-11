"""
AWS cost intelligence and waste detection engine.

Pulls 90-day Cost Explorer data, identifies top cost drivers, detects
waste across EC2/RDS/EBS/NAT/EIP, and generates right-sizing recommendations
backed by CloudWatch utilization metrics.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from cloud_iq.scanner import (
    EBSVolume,
    EC2Instance,
    ElasticIP,
    InfrastructureSnapshot,
    RDSInstance,
    VPC,
)

logger = logging.getLogger(__name__)

INSTANCE_DOWNSIZE_MAP: dict[str, str] = {
    "t3.2xlarge": "t3.xlarge",
    "t3.xlarge": "t3.large",
    "t3.large": "t3.medium",
    "t3.medium": "t3.small",
    "m5.8xlarge": "m5.4xlarge",
    "m5.4xlarge": "m5.2xlarge",
    "m5.2xlarge": "m5.xlarge",
    "m5.xlarge": "m5.large",
    "c5.2xlarge": "c5.xlarge",
    "c5.xlarge": "c5.large",
    "r5.4xlarge": "r5.2xlarge",
    "r5.2xlarge": "r5.xlarge",
    "r5.xlarge": "r5.large",
    "db.m5.2xlarge": "db.m5.xlarge",
    "db.m5.xlarge": "db.m5.large",
    "db.r5.2xlarge": "db.r5.xlarge",
    "db.r5.xlarge": "db.r5.large",
    "db.t3.large": "db.t3.medium",
    "db.t3.medium": "db.t3.small",
}

INSTANCE_HOURLY_PRICES: dict[str, float] = {
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t3.2xlarge": 0.3328,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "m5.4xlarge": 0.768,
    "m5.8xlarge": 1.536,
    "c5.large": 0.085,
    "c5.xlarge": 0.170,
    "c5.2xlarge": 0.340,
    "r5.large": 0.126,
    "r5.xlarge": 0.252,
    "r5.2xlarge": 0.504,
    "r5.4xlarge": 1.008,
}
HOURS_PER_MONTH = 730.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class WasteItem:
    category: str
    resource_id: str
    resource_type: str
    region: str
    estimated_monthly_waste: float
    description: str
    recommendation: str
    severity: str  # "critical" | "high" | "medium" | "low"
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class RightsizingRecommendation:
    instance_id: str
    instance_type: str
    region: str
    current_monthly_cost: float
    recommended_instance_type: str
    recommended_monthly_cost: float
    monthly_savings: float
    annual_savings: float
    avg_cpu_utilization: float
    max_cpu_utilization: float
    confidence: str  # "HIGH" | "MEDIUM" | "LOW"
    tags: dict[str, str]


@dataclass
class CostDriverEntry:
    service: str
    monthly_cost: float
    percentage_of_total: float
    month_over_month_change: float


@dataclass
class ShadowITItem:
    resource_id: str
    resource_type: str
    region: str
    estimated_monthly_cost: float
    description: str


@dataclass
class CostReport:
    """Complete cost intelligence report for an AWS account."""

    account_id: str
    report_date: date
    analysis_period_days: int
    monthly_avg_cost: float
    top_cost_drivers: list[CostDriverEntry]
    waste_items: list[WasteItem]
    rightsizing_recommendations: list[RightsizingRecommendation]
    shadow_it_items: list[ShadowITItem]
    total_identified_waste: float
    total_rightsizing_savings: float
    scan_errors: list[str] = field(default_factory=list)

    @property
    def total_monthly_savings_opportunity(self) -> float:
        return round(self.total_identified_waste + self.total_rightsizing_savings, 2)

    @property
    def annual_savings_opportunity(self) -> float:
        return round(self.total_monthly_savings_opportunity * 12, 2)


# ---------------------------------------------------------------------------
# Analyzer implementation
# ---------------------------------------------------------------------------


class CostAnalyzer:
    """
    Analyzes AWS costs and identifies waste using Cost Explorer and CloudWatch.

    Combines billing data with real utilization metrics to produce actionable
    recommendations with dollar amounts attached to every finding.
    """

    def __init__(
        self,
        region: str = "us-east-1",
        profile_name: str | None = None,
        terraform_state_path: str | None = None,
    ) -> None:
        session_kwargs: dict[str, Any] = {}
        if profile_name:
            session_kwargs["profile_name"] = profile_name
        self._session = boto3.Session(region_name=region, **session_kwargs)
        self._terraform_state_path = terraform_state_path

    def _client(self, service: str, region: str | None = None) -> Any:
        kwargs = {}
        if region:
            kwargs["region_name"] = region
        return self._session.client(service, **kwargs)

    # ------------------------------------------------------------------
    # Cost Explorer
    # ------------------------------------------------------------------

    def _get_cost_by_service(
        self, days: int = 90
    ) -> tuple[list[CostDriverEntry], float]:
        ce = self._client("ce")
        end = date.today()
        start = end - timedelta(days=days)

        try:
            response = ce.get_cost_and_usage(
                TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )
        except ClientError as exc:
            logger.warning("Cost Explorer not available: %s", exc)
            return [], 0.0

        service_totals: dict[str, float] = {}
        for result in response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                service = group["Keys"][0]
                amount = float(
                    group["Metrics"]["UnblendedCost"]["Amount"]
                )
                service_totals[service] = service_totals.get(service, 0.0) + amount

        total = sum(service_totals.values())
        if total == 0:
            return [], 0.0

        drivers = sorted(service_totals.items(), key=lambda x: x[1], reverse=True)[:10]
        entries: list[CostDriverEntry] = []
        for service, cost in drivers:
            entries.append(
                CostDriverEntry(
                    service=service,
                    monthly_cost=round(cost / (days / 30), 2),
                    percentage_of_total=round((cost / total) * 100, 1),
                    month_over_month_change=0.0,
                )
            )
        monthly_avg = round(total / (days / 30), 2)
        return entries, monthly_avg

    # ------------------------------------------------------------------
    # CloudWatch utilization metrics
    # ------------------------------------------------------------------

    def _get_ec2_avg_cpu(
        self,
        instance_id: str,
        region: str,
        days: int = 14,
    ) -> tuple[float, float]:
        """Returns (avg_cpu_pct, max_cpu_pct) over the past N days."""
        cw = self._client("cloudwatch", region)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        try:
            response = cw.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=start,
                EndTime=end,
                Period=3600,
                Statistics=["Average", "Maximum"],
            )
            points = response.get("Datapoints", [])
            if not points:
                return 0.0, 0.0
            avg = sum(p["Average"] for p in points) / len(points)
            maximum = max(p["Maximum"] for p in points)
            return round(avg, 1), round(maximum, 1)
        except ClientError:
            return 0.0, 0.0

    def _get_rds_avg_cpu(
        self, db_instance_id: str, region: str, days: int = 14
    ) -> tuple[float, float]:
        cw = self._client("cloudwatch", region)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        try:
            response = cw.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName="CPUUtilization",
                Dimensions=[
                    {"Name": "DBInstanceIdentifier", "Value": db_instance_id}
                ],
                StartTime=start,
                EndTime=end,
                Period=3600,
                Statistics=["Average", "Maximum"],
            )
            points = response.get("Datapoints", [])
            if not points:
                return 0.0, 0.0
            avg = sum(p["Average"] for p in points) / len(points)
            maximum = max(p["Maximum"] for p in points)
            return round(avg, 1), round(maximum, 1)
        except ClientError:
            return 0.0, 0.0

    # ------------------------------------------------------------------
    # Waste detection
    # ------------------------------------------------------------------

    def _detect_idle_ec2(
        self, instances: list[EC2Instance]
    ) -> list[WasteItem]:
        waste: list[WasteItem] = []
        for inst in instances:
            if inst.state != "running":
                continue
            avg_cpu, max_cpu = self._get_ec2_avg_cpu(inst.instance_id, inst.region)
            if max_cpu < 5.0 and avg_cpu < 2.0:
                waste.append(
                    WasteItem(
                        category="Idle EC2 Instance",
                        resource_id=inst.instance_id,
                        resource_type="EC2 Instance",
                        region=inst.region,
                        estimated_monthly_waste=inst.estimated_monthly_cost,
                        description=(
                            f"{inst.instance_id} ({inst.instance_type}) has had "
                            f"avg CPU {avg_cpu}% / max CPU {max_cpu}% over 14 days. "
                            f"No meaningful workload detected."
                        ),
                        recommendation=(
                            "Stop or terminate this instance. If it serves a "
                            "periodic workload, consider AWS Scheduler or Lambda "
                            "instead of a persistent EC2 instance."
                        ),
                        severity="critical",
                        tags=inst.tags,
                    )
                )
        return waste

    def _detect_unattached_ebs(
        self, volumes: list[EBSVolume]
    ) -> list[WasteItem]:
        waste: list[WasteItem] = []
        for vol in volumes:
            if vol.state == "available" and vol.attached_instance is None:
                waste.append(
                    WasteItem(
                        category="Unattached EBS Volume",
                        resource_id=vol.volume_id,
                        resource_type="EBS Volume",
                        region=vol.region,
                        estimated_monthly_waste=vol.estimated_monthly_cost,
                        description=(
                            f"{vol.volume_id} ({vol.size_gb} GB {vol.volume_type}) "
                            f"is not attached to any instance."
                        ),
                        recommendation=(
                            "Create a snapshot for backup if needed, then delete "
                            "this volume. Unattached EBS volumes accrue full "
                            "storage costs with zero utilization."
                        ),
                        severity="high",
                        tags=vol.tags,
                    )
                )
        return waste

    def _detect_idle_elastic_ips(
        self, eips: list[ElasticIP]
    ) -> list[WasteItem]:
        waste: list[WasteItem] = []
        for eip in eips:
            if eip.is_idle:
                waste.append(
                    WasteItem(
                        category="Idle Elastic IP",
                        resource_id=eip.allocation_id,
                        resource_type="Elastic IP",
                        region=eip.region,
                        estimated_monthly_waste=eip.estimated_monthly_cost,
                        description=(
                            f"Elastic IP {eip.public_ip} ({eip.allocation_id}) "
                            f"is not associated with any running instance."
                        ),
                        recommendation=(
                            "Release this Elastic IP immediately. AWS charges "
                            "$3.60/month for unassociated Elastic IPs."
                        ),
                        severity="medium",
                    )
                )
        return waste

    def _detect_nat_gateway_overuse(
        self, vpcs: list[VPC]
    ) -> list[WasteItem]:
        waste: list[WasteItem] = []
        for vpc in vpcs:
            nat_count = len(vpc.nat_gateways)
            if nat_count > 3:
                monthly_cost = nat_count * 0.045 * HOURS_PER_MONTH
                waste.append(
                    WasteItem(
                        category="NAT Gateway Overuse",
                        resource_id=vpc.vpc_id,
                        resource_type="VPC",
                        region=vpc.region,
                        estimated_monthly_waste=round(monthly_cost, 2),
                        description=(
                            f"VPC {vpc.vpc_id} has {nat_count} NAT Gateways "
                            f"(${monthly_cost:.0f}/mo base cost, plus data "
                            f"processing charges at $0.045/GB)."
                        ),
                        recommendation=(
                            "Consolidate traffic through fewer NAT Gateways "
                            "where cross-AZ latency is acceptable. Consider "
                            "VPC endpoints for AWS service traffic (S3, DynamoDB) "
                            "to eliminate NAT Gateway data charges entirely."
                        ),
                        severity="high",
                        tags=vpc.tags,
                    )
                )
        return waste

    def _detect_overprovisioned_rds(
        self, rds_instances: list[RDSInstance]
    ) -> list[WasteItem]:
        waste: list[WasteItem] = []
        for inst in rds_instances:
            if inst.status != "available":
                continue
            avg_cpu, max_cpu = self._get_rds_avg_cpu(
                inst.db_instance_id, inst.region
            )
            if max_cpu < 20.0 and avg_cpu < 10.0:
                smaller = INSTANCE_DOWNSIZE_MAP.get(inst.db_instance_class)
                if smaller:
                    savings = inst.estimated_monthly_cost * 0.45
                    waste.append(
                        WasteItem(
                            category="Over-Provisioned RDS",
                            resource_id=inst.db_instance_id,
                            resource_type="RDS Instance",
                            region=inst.region,
                            estimated_monthly_waste=round(savings, 2),
                            description=(
                                f"{inst.db_instance_id} ({inst.db_instance_class}, "
                                f"{inst.engine} {inst.engine_version}) shows "
                                f"avg CPU {avg_cpu}% / max CPU {max_cpu}% over "
                                f"14 days. Significantly over-provisioned."
                            ),
                            recommendation=(
                                f"Downsize to {smaller}. This reduces instance "
                                f"cost by ~50% with ample headroom for current load. "
                                f"Schedule a maintenance window to apply during "
                                f"low-traffic hours."
                            ),
                            severity="high",
                            tags=inst.tags,
                        )
                    )
        return waste

    def _detect_old_snapshots(self, region: str) -> list[WasteItem]:
        waste: list[WasteItem] = []
        try:
            ec2 = self._session.client("ec2", region_name=region)
            sts = self._session.client("sts")
            account_id = sts.get_caller_identity()["Account"]
            paginator = ec2.get_paginator("describe_snapshots")
            cutoff = datetime.now(timezone.utc) - timedelta(days=180)
            old_count = 0
            old_size_gb = 0
            for page in paginator.paginate(OwnerIds=[account_id]):
                for snap in page["Snapshots"]:
                    start_time = snap.get("StartTime")
                    if start_time and start_time < cutoff:
                        old_count += 1
                        old_size_gb += snap.get("VolumeSize", 0)
            if old_count > 0:
                monthly_cost = old_size_gb * 0.05
                waste.append(
                    WasteItem(
                        category="Old EBS Snapshots",
                        resource_id=f"{region}/snapshots",
                        resource_type="EBS Snapshots",
                        region=region,
                        estimated_monthly_waste=round(monthly_cost, 2),
                        description=(
                            f"{old_count} snapshots older than 180 days in {region} "
                            f"consuming {old_size_gb} GB of snapshot storage "
                            f"(${monthly_cost:.0f}/mo at $0.05/GB)."
                        ),
                        recommendation=(
                            "Implement a snapshot lifecycle policy using AWS Data "
                            "Lifecycle Manager. Retain 7 daily + 4 weekly + "
                            "12 monthly snapshots; delete everything older."
                        ),
                        severity="medium",
                    )
                )
        except ClientError:
            pass
        return waste

    # ------------------------------------------------------------------
    # Rightsizing
    # ------------------------------------------------------------------

    def _compute_rightsizing(
        self, instances: list[EC2Instance]
    ) -> list[RightsizingRecommendation]:
        recs: list[RightsizingRecommendation] = []
        for inst in instances:
            if inst.state != "running":
                continue
            avg_cpu, max_cpu = self._get_ec2_avg_cpu(inst.instance_id, inst.region)
            if max_cpu > 60.0:
                continue
            smaller = INSTANCE_DOWNSIZE_MAP.get(inst.instance_type)
            if not smaller:
                continue
            current_cost = inst.estimated_monthly_cost
            new_hourly = INSTANCE_HOURLY_PRICES.get(
                smaller,
                INSTANCE_HOURLY_PRICES.get(inst.instance_type, 0.10) * 0.5,
            )
            new_cost = round(new_hourly * HOURS_PER_MONTH, 2)
            savings = round(current_cost - new_cost, 2)
            if savings <= 0:
                continue
            if max_cpu < 20:
                confidence = "HIGH"
            elif max_cpu < 40:
                confidence = "MEDIUM"
            else:
                confidence = "LOW"
            recs.append(
                RightsizingRecommendation(
                    instance_id=inst.instance_id,
                    instance_type=inst.instance_type,
                    region=inst.region,
                    current_monthly_cost=current_cost,
                    recommended_instance_type=smaller,
                    recommended_monthly_cost=new_cost,
                    monthly_savings=savings,
                    annual_savings=round(savings * 12, 2),
                    avg_cpu_utilization=avg_cpu,
                    max_cpu_utilization=max_cpu,
                    confidence=confidence,
                    tags=inst.tags,
                )
            )
        return sorted(recs, key=lambda r: r.monthly_savings, reverse=True)

    # ------------------------------------------------------------------
    # Shadow IT detection
    # ------------------------------------------------------------------

    def _detect_shadow_it(
        self, snapshot: InfrastructureSnapshot
    ) -> list[ShadowITItem]:
        if not self._terraform_state_path:
            return []
        try:
            with open(self._terraform_state_path) as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read Terraform state: %s", exc)
            return []

        managed_ids: set[str] = set()
        for resource in state.get("resources", []):
            for instance in resource.get("instances", []):
                attrs = instance.get("attributes", {})
                for key in ("id", "instance_id", "db_instance_id"):
                    if key in attrs:
                        managed_ids.add(attrs[key])

        items: list[ShadowITItem] = []
        for inst in snapshot.ec2_instances:
            if inst.instance_id not in managed_ids:
                items.append(
                    ShadowITItem(
                        resource_id=inst.instance_id,
                        resource_type="EC2 Instance",
                        region=inst.region,
                        estimated_monthly_cost=inst.estimated_monthly_cost,
                        description=(
                            f"EC2 instance {inst.instance_id} "
                            f"({inst.instance_type}) exists in AWS but is "
                            f"not tracked in Terraform state."
                        ),
                    )
                )
        for rds in snapshot.rds_instances:
            if rds.db_instance_id not in managed_ids:
                items.append(
                    ShadowITItem(
                        resource_id=rds.db_instance_id,
                        resource_type="RDS Instance",
                        region=rds.region,
                        estimated_monthly_cost=rds.estimated_monthly_cost,
                        description=(
                            f"RDS instance {rds.db_instance_id} "
                            f"({rds.db_instance_class}) not tracked in "
                            f"Terraform state."
                        ),
                    )
                )
        return items

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def analyze(self, snapshot: InfrastructureSnapshot) -> CostReport:
        """
        Run the full cost analysis against the infrastructure snapshot.

        Combines Cost Explorer data, CloudWatch metrics, and static analysis
        to produce a CostReport with every finding dollar-quantified.
        """
        errors: list[str] = []

        top_drivers, monthly_avg = self._get_cost_by_service(days=90)

        waste: list[WasteItem] = []
        for region in snapshot.regions:
            region_ec2 = [i for i in snapshot.ec2_instances if i.region == region]
            region_ebs = [v for v in snapshot.ebs_volumes if v.region == region]
            region_rds = [r for r in snapshot.rds_instances if r.region == region]
            region_vpcs = [v for v in snapshot.vpcs if v.region == region]
            region_eips = [e for e in snapshot.elastic_ips if e.region == region]

            waste.extend(self._detect_idle_ec2(region_ec2))
            waste.extend(self._detect_unattached_ebs(region_ebs))
            waste.extend(self._detect_idle_elastic_ips(region_eips))
            waste.extend(self._detect_nat_gateway_overuse(region_vpcs))
            waste.extend(self._detect_overprovisioned_rds(region_rds))
            waste.extend(self._detect_old_snapshots(region))

        waste.sort(key=lambda w: w.estimated_monthly_waste, reverse=True)

        rightsizing = self._compute_rightsizing(snapshot.ec2_instances)

        shadow_it = self._detect_shadow_it(snapshot)

        total_waste = round(
            sum(w.estimated_monthly_waste for w in waste), 2
        )
        total_rightsizing = round(
            sum(r.monthly_savings for r in rightsizing), 2
        )

        return CostReport(
            account_id=snapshot.account_id,
            report_date=date.today(),
            analysis_period_days=90,
            monthly_avg_cost=monthly_avg,
            top_cost_drivers=top_drivers,
            waste_items=waste,
            rightsizing_recommendations=rightsizing,
            shadow_it_items=shadow_it,
            total_identified_waste=total_waste,
            total_rightsizing_savings=total_rightsizing,
            scan_errors=errors,
        )
