"""
iac_security/drift_detector.py
================================

DriftDetector — compare declared IaC state to actual cloud state.

Matching strategy:
  1. Primary:   tag 'eaa:iac-id' on the live workload == resource.address
  2. Secondary: resource.name == workload.name AND resource_type maps to
                workload.service_type (via TYPE_MAP)
  3. Fallback:  no match → both sides flagged separately

Categories of drift:
  - missing_in_cloud:   resource declared in IaC but not found live
  - unmanaged_in_cloud: live workload with no IaC declaration
  - attribute_drift:    resource matched but specific attributes differ

Integrates with cloud_iq/adapters/ via duck typing (Protocol).
Does NOT import from cloud_iq — accepts any object with the Workload
protocol shape so this module is independently testable and the cloud
adapter track can plug in without a circular import.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol definitions (duck-typing, no hard import from cloud_iq)
# ---------------------------------------------------------------------------


@runtime_checkable
class IaCResource(Protocol):
    """Duck-type accepted from TerraformResource / PulumiResource."""

    kind: str
    resource_type: str
    name: str
    attributes: dict[str, Any]
    source_file: str
    source_line: int

    def get(self, key: str, default: Any = None) -> Any: ...

    @property
    def address(self) -> str: ...


@runtime_checkable
class CloudWorkload(Protocol):
    """
    Duck-type accepted from cloud_iq.adapters.base.Workload.
    The DriftDetector does not import Workload directly so it stays
    independently deployable and testable without cloud credentials.
    """

    id: str
    name: str
    service_type: str  # e.g. "EC2", "S3", "RDS"
    tags: dict[str, str]
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Service type mapping: Terraform resource_type -> cloud service_type
# ---------------------------------------------------------------------------

TYPE_MAP: dict[str, str] = {
    # Compute
    "aws_instance": "EC2",
    "aws_launch_template": "EC2",
    # Storage
    "aws_s3_bucket": "S3",
    "aws_ebs_volume": "EBS",
    # Database
    "aws_db_instance": "RDS",
    "aws_rds_cluster": "RDS",
    "aws_dynamodb_table": "DynamoDB",
    # Networking
    "aws_vpc": "VPC",
    "aws_security_group": "SecurityGroup",
    "aws_lb": "ELB",
    "aws_alb": "ELB",
    # Serverless
    "aws_lambda_function": "Lambda",
    # Containers
    "aws_ecs_service": "ECS",
    "aws_ecs_cluster": "ECS",
    # IAM
    "aws_iam_role": "IAM",
    "aws_iam_policy": "IAM",
    # KMS
    "aws_kms_key": "KMS",
    # CloudTrail
    "aws_cloudtrail": "CloudTrail",
    # Pulumi type token -> service type
    "aws:ec2/instance:Instance": "EC2",
    "aws:s3/bucket:Bucket": "S3",
    "aws:rds/instance:Instance": "RDS",
    "aws:lambda/function:Function": "Lambda",
    "aws:vpc/vpc:Vpc": "VPC",
}


# ---------------------------------------------------------------------------
# Drift result data model
# ---------------------------------------------------------------------------


@dataclass
class AttributeDelta:
    """A single attribute that differs between IaC declaration and live state."""

    attribute: str
    iac_value: Any
    cloud_value: Any


@dataclass
class DriftItem:
    """A single drift finding."""

    category: str  # "missing_in_cloud" | "unmanaged_in_cloud" | "attribute_drift"
    iac_address: str       # resource.address or ""
    cloud_id: str          # workload.id or ""
    cloud_name: str        # workload.name or ""
    service_type: str      # e.g. "EC2"
    attribute_deltas: list[AttributeDelta] = field(default_factory=list)
    match_method: str = ""  # "tag" | "name_type" | "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "iac_address": self.iac_address,
            "cloud_id": self.cloud_id,
            "cloud_name": self.cloud_name,
            "service_type": self.service_type,
            "match_method": self.match_method,
            "attribute_deltas": [
                {
                    "attribute": d.attribute,
                    "iac_value": d.iac_value,
                    "cloud_value": d.cloud_value,
                }
                for d in self.attribute_deltas
            ],
        }


@dataclass
class DriftReport:
    """Aggregated drift analysis between IaC and live cloud state."""

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    iac_resource_count: int = 0
    cloud_workload_count: int = 0
    items: list[DriftItem] = field(default_factory=list)

    @property
    def missing_in_cloud(self) -> list[DriftItem]:
        return [i for i in self.items if i.category == "missing_in_cloud"]

    @property
    def unmanaged_in_cloud(self) -> list[DriftItem]:
        return [i for i in self.items if i.category == "unmanaged_in_cloud"]

    @property
    def attribute_drift(self) -> list[DriftItem]:
        return [i for i in self.items if i.category == "attribute_drift"]

    @property
    def is_clean(self) -> bool:
        return len(self.items) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "iac_resource_count": self.iac_resource_count,
            "cloud_workload_count": self.cloud_workload_count,
            "summary": {
                "total_drift_items": len(self.items),
                "missing_in_cloud": len(self.missing_in_cloud),
                "unmanaged_in_cloud": len(self.unmanaged_in_cloud),
                "attribute_drift": len(self.attribute_drift),
                "is_clean": self.is_clean,
            },
            "items": [i.to_dict() for i in self.items],
        }


# ---------------------------------------------------------------------------
# Attribute comparison helpers
# ---------------------------------------------------------------------------

# IaC attributes we can realistically compare to live cloud metadata
# Maps: iac_attribute_key -> cloud metadata key (in workload.metadata)
COMPARABLE_ATTRIBUTES: dict[str, str] = {
    # EC2
    "instance_type": "InstanceType",
    "ami": "ImageId",
    "associate_public_ip_address": "PublicIpAddress",
    # S3
    "bucket": "Name",
    # RDS
    "engine": "Engine",
    "engine_version": "EngineVersion",
    "instance_class": "DBInstanceClass",
    "storage_encrypted": "StorageEncrypted",
    "multi_az": "MultiAZ",
    "publicly_accessible": "PubliclyAccessible",
    # Lambda
    "runtime": "Runtime",
    "memory_size": "MemorySize",
    "timeout": "Timeout",
}


def _compare_attributes(
    resource: IaCResource,
    workload: CloudWorkload,
) -> list[AttributeDelta]:
    """
    Compare known IaC attributes against workload.metadata values.
    Returns a list of deltas where the values differ meaningfully.
    """
    deltas: list[AttributeDelta] = []
    cloud_meta = getattr(workload, "metadata", {}) or {}

    for iac_key, cloud_key in COMPARABLE_ATTRIBUTES.items():
        iac_val = resource.get(iac_key)
        if iac_val is None:
            continue  # Not declared in IaC — skip
        cloud_val = cloud_meta.get(cloud_key)
        if cloud_val is None:
            continue  # Not available in cloud data — skip

        # Normalise booleans
        if isinstance(iac_val, bool) and isinstance(cloud_val, bool):
            if iac_val != cloud_val:
                deltas.append(AttributeDelta(iac_key, iac_val, cloud_val))
        elif isinstance(iac_val, str) and isinstance(cloud_val, str):
            if iac_val.lower() != cloud_val.lower():
                deltas.append(AttributeDelta(iac_key, iac_val, cloud_val))
        elif str(iac_val) != str(cloud_val):
            deltas.append(AttributeDelta(iac_key, iac_val, cloud_val))

    return deltas


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------


def _match_by_tag(
    resource: IaCResource, workloads: list[CloudWorkload]
) -> Optional[CloudWorkload]:
    """Match by eaa:iac-id tag on the live workload."""
    for wl in workloads:
        tags = getattr(wl, "tags", {}) or {}
        if tags.get("eaa:iac-id") == resource.address:
            return wl
    return None


def _match_by_name_type(
    resource: IaCResource, workloads: list[CloudWorkload]
) -> Optional[CloudWorkload]:
    """
    Match by name + service_type mapping.
    Requires TYPE_MAP to map resource_type to service_type.
    """
    expected_svc = TYPE_MAP.get(resource.resource_type, "")
    if not expected_svc:
        return None
    for wl in workloads:
        svc = getattr(wl, "service_type", "")
        name = getattr(wl, "name", "")
        if svc == expected_svc and name == resource.name:
            return wl
    return None


# ---------------------------------------------------------------------------
# Public detector
# ---------------------------------------------------------------------------


class DriftDetector:
    """
    Compare declared IaC resources to live cloud workloads.

    iac_state   : output of terraform_parser.parse_terraform() or
                  pulumi_parser.parse_pulumi()
    cloud_state : list of CloudWorkload objects from cloud_iq adapters
                  (accepted via duck typing — no direct import)

    Usage::

        from iac_security import DriftDetector
        report = DriftDetector(
            iac_state=terraform_resources,
            cloud_state=aws_workloads,
        ).detect()
        print(report.to_dict())
    """

    def __init__(
        self,
        iac_state: list[Any],
        cloud_state: list[Any],
        *,
        unmanaged_service_types: Optional[set[str]] = None,
    ) -> None:
        # Filter to resource-kind only (skip variables, outputs, modules)
        self.iac_resources: list[Any] = [
            r for r in iac_state if getattr(r, "kind", "") == "resource"
        ]
        self.cloud_workloads: list[Any] = cloud_state
        # Only flag unmanaged workloads for these service types (None = all)
        self.unmanaged_service_types: Optional[set[str]] = unmanaged_service_types

    def detect(self) -> DriftReport:
        """Run drift detection and return a DriftReport."""
        report = DriftReport(
            iac_resource_count=len(self.iac_resources),
            cloud_workload_count=len(self.cloud_workloads),
        )

        matched_workloads: set[str] = set()  # track workload IDs already matched

        for resource in self.iac_resources:
            # Try tag match first, then name+type
            wl = _match_by_tag(resource, self.cloud_workloads)
            match_method = "tag"
            if wl is None:
                wl = _match_by_name_type(resource, self.cloud_workloads)
                match_method = "name_type"

            if wl is None:
                # Resource declared in IaC but not found live
                report.items.append(
                    DriftItem(
                        category="missing_in_cloud",
                        iac_address=resource.address,
                        cloud_id="",
                        cloud_name="",
                        service_type=TYPE_MAP.get(resource.resource_type, resource.resource_type),
                        match_method="none",
                    )
                )
                continue

            wl_id = getattr(wl, "id", getattr(wl, "name", ""))
            matched_workloads.add(wl_id)

            # Compare attributes
            deltas = _compare_attributes(resource, wl)
            if deltas:
                report.items.append(
                    DriftItem(
                        category="attribute_drift",
                        iac_address=resource.address,
                        cloud_id=wl_id,
                        cloud_name=getattr(wl, "name", ""),
                        service_type=getattr(wl, "service_type", ""),
                        attribute_deltas=deltas,
                        match_method=match_method,
                    )
                )

        # Identify unmanaged cloud workloads
        for wl in self.cloud_workloads:
            wl_id = getattr(wl, "id", getattr(wl, "name", ""))
            if wl_id in matched_workloads:
                continue
            svc = getattr(wl, "service_type", "")
            if self.unmanaged_service_types and svc not in self.unmanaged_service_types:
                continue
            report.items.append(
                DriftItem(
                    category="unmanaged_in_cloud",
                    iac_address="",
                    cloud_id=wl_id,
                    cloud_name=getattr(wl, "name", ""),
                    service_type=svc,
                    match_method="none",
                )
            )

        logger.info(
            "DriftDetector: %d IaC resources, %d cloud workloads, "
            "%d missing, %d unmanaged, %d attribute drift",
            len(self.iac_resources),
            len(self.cloud_workloads),
            len(report.missing_in_cloud),
            len(report.unmanaged_in_cloud),
            len(report.attribute_drift),
        )
        return report
