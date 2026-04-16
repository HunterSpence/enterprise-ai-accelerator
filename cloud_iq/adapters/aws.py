"""
cloud_iq/adapters/aws.py
========================

AWSAdapter — real boto3 discovery for EC2, RDS, Lambda, S3, and Cost Explorer.

Credential chain (standard AWS SDK order — no custom auth required):
  1. AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (+ optional AWS_SESSION_TOKEN)
  2. AWS Profile:   AWS_PROFILE / AWS_DEFAULT_PROFILE
  3. ECS task role / EC2 instance metadata / SSO
  4. ~/.aws/credentials

Optional env vars:
  AWS_DEFAULT_REGION   — defaults to "us-east-1" if absent
  AWS_REGIONS          — comma-separated list to scan (overrides single region)
  AWS_PROFILE          — named profile (falls through to default chain)

All boto3 calls are wrapped in asyncio.to_thread() so the event loop stays free.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from cloud_iq.adapters.base import DiscoveryAdapter, Workload

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static EC2 instance type → approximate vCPU/RAM table (most common types).
# Avoids a Pricing API call per instance; add rows as needed.
# ---------------------------------------------------------------------------
_EC2_SPECS: dict[str, tuple[int, float]] = {
    # (vcpu, ram_gb)
    "t3.nano": (2, 0.5), "t3.micro": (2, 1), "t3.small": (2, 2),
    "t3.medium": (2, 4), "t3.large": (2, 8), "t3.xlarge": (4, 16),
    "t3.2xlarge": (8, 32),
    "t2.micro": (1, 1), "t2.small": (1, 2), "t2.medium": (2, 4),
    "t2.large": (2, 8), "t2.xlarge": (4, 16), "t2.2xlarge": (8, 32),
    "m5.large": (2, 8), "m5.xlarge": (4, 16), "m5.2xlarge": (8, 32),
    "m5.4xlarge": (16, 64), "m5.8xlarge": (32, 128), "m5.12xlarge": (48, 192),
    "m5.16xlarge": (64, 256), "m5.24xlarge": (96, 384),
    "m6i.large": (2, 8), "m6i.xlarge": (4, 16), "m6i.2xlarge": (8, 32),
    "m6i.4xlarge": (16, 64), "m6i.8xlarge": (32, 128),
    "c5.large": (2, 4), "c5.xlarge": (4, 8), "c5.2xlarge": (8, 16),
    "c5.4xlarge": (16, 32), "c5.9xlarge": (36, 72), "c5.18xlarge": (72, 144),
    "r5.large": (2, 16), "r5.xlarge": (4, 32), "r5.2xlarge": (8, 64),
    "r5.4xlarge": (16, 128), "r5.8xlarge": (32, 256),
    "p3.2xlarge": (8, 61), "p3.8xlarge": (32, 244),
    "g4dn.xlarge": (4, 16), "g4dn.2xlarge": (8, 32),
}


def _ec2_specs(instance_type: str) -> tuple[int, float]:
    """Return (vcpu, ram_gb) for an instance type; fall back to (1, 1)."""
    return _EC2_SPECS.get(instance_type, (1, 1.0))


class AWSAdapter(DiscoveryAdapter):
    """
    Discovers AWS workloads using real boto3 API calls.

    Pulls EC2 instances, RDS clusters, Lambda functions, S3 buckets (size via
    CloudWatch), and per-service costs from Cost Explorer over the last 30 days.
    Trusted Advisor summaries are attempted only when the Support API is
    available (Business / Enterprise support plans).
    """

    def __init__(
        self,
        region: str | None = None,
        regions: list[str] | None = None,
        profile_name: str | None = None,
    ) -> None:
        self._default_region = region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        env_regions = os.environ.get("AWS_REGIONS", "")
        self._regions: list[str] = (
            regions
            or ([r.strip() for r in env_regions.split(",") if r.strip()] or [self._default_region])
        )
        self._profile_name = profile_name or os.environ.get("AWS_PROFILE")

    # ------------------------------------------------------------------
    # DiscoveryAdapter interface
    # ------------------------------------------------------------------

    @property
    def cloud_name(self) -> str:
        return "aws"

    @staticmethod
    def is_configured() -> bool:
        """True if AWS key pair, profile, or in-cloud IAM env vars are set."""
        has_keys = bool(
            os.environ.get("AWS_ACCESS_KEY_ID")
            and os.environ.get("AWS_SECRET_ACCESS_KEY")
        )
        has_profile = bool(os.environ.get("AWS_PROFILE") or os.environ.get("AWS_DEFAULT_PROFILE"))
        # ECS tasks and EC2 instance roles expose these env vars
        has_ecs_role = bool(os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"))
        return has_keys or has_profile or has_ecs_role

    async def discover_workloads(self) -> list[Workload]:
        """Fan out all sub-discovery tasks in parallel and merge results."""
        try:
            session = await asyncio.to_thread(self._make_session)
        except Exception as exc:
            logger.warning("aws_session_failed error=%s", exc)
            return []

        tasks = [
            self._discover_ec2(session),
            self._discover_rds(session),
            self._discover_lambda(session),
            self._discover_s3(session),
        ]
        cost_map = await self._fetch_cost_by_service(session)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        workloads: list[Workload] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("aws_sub_discovery_error error=%s", r)
            else:
                workloads.extend(r)

        # Annotate with Cost Explorer actuals where service key matches
        self._apply_costs(workloads, cost_map)

        # Best-effort Trusted Advisor
        try:
            ta_workloads = await self._discover_trusted_advisor(session)
            workloads.extend(ta_workloads)
        except Exception as exc:
            logger.debug("trusted_advisor_unavailable reason=%s", exc)

        return workloads

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def _make_session(self) -> Any:
        import boto3
        kwargs: dict[str, Any] = {"region_name": self._default_region}
        if self._profile_name:
            kwargs["profile_name"] = self._profile_name
        return boto3.Session(**kwargs)

    # ------------------------------------------------------------------
    # EC2
    # ------------------------------------------------------------------

    async def _discover_ec2(self, session: Any) -> list[Workload]:
        def _run() -> list[Workload]:
            workloads: list[Workload] = []
            for region in self._regions:
                try:
                    ec2 = session.client("ec2", region_name=region)
                    paginator = ec2.get_paginator("describe_instances")
                    for page in paginator.paginate(
                        Filters=[{"Name": "instance-state-name", "Values": ["running", "stopped"]}]
                    ):
                        for reservation in page.get("Reservations", []):
                            for inst in reservation.get("Instances", []):
                                itype = inst.get("InstanceType", "unknown")
                                vcpu, ram = _ec2_specs(itype)
                                name = _tag_value(inst.get("Tags", []), "Name") or inst["InstanceId"]
                                workloads.append(Workload(
                                    id=inst["InstanceId"],
                                    name=name,
                                    cloud="aws",
                                    service_type="EC2",
                                    region=region,
                                    tags=_tags_to_dict(inst.get("Tags", [])),
                                    cpu_cores=vcpu,
                                    memory_gb=float(ram),
                                    last_seen=datetime.now(timezone.utc),
                                    metadata={
                                        "instance_type": itype,
                                        "state": inst.get("State", {}).get("Name"),
                                        "ami": inst.get("ImageId"),
                                        "vpc_id": inst.get("VpcId"),
                                        "az": inst.get("Placement", {}).get("AvailabilityZone"),
                                        "launch_time": str(inst.get("LaunchTime", "")),
                                    },
                                ))
                except Exception as exc:
                    logger.warning("aws_ec2_region_error region=%s error=%s", region, exc)
            return workloads

        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # RDS
    # ------------------------------------------------------------------

    async def _discover_rds(self, session: Any) -> list[Workload]:
        def _run() -> list[Workload]:
            workloads: list[Workload] = []
            for region in self._regions:
                try:
                    rds = session.client("rds", region_name=region)
                    paginator = rds.get_paginator("describe_db_instances")
                    for page in paginator.paginate():
                        for db in page.get("DBInstances", []):
                            storage_gb = float(db.get("AllocatedStorage", 0))
                            workloads.append(Workload(
                                id=db["DBInstanceIdentifier"],
                                name=db["DBInstanceIdentifier"],
                                cloud="aws",
                                service_type="RDS",
                                region=region,
                                tags=_tags_to_dict(db.get("TagList", [])),
                                storage_gb=storage_gb,
                                last_seen=datetime.now(timezone.utc),
                                metadata={
                                    "engine": db.get("Engine"),
                                    "engine_version": db.get("EngineVersion"),
                                    "instance_class": db.get("DBInstanceClass"),
                                    "status": db.get("DBInstanceStatus"),
                                    "multi_az": db.get("MultiAZ"),
                                    "publicly_accessible": db.get("PubliclyAccessible"),
                                },
                            ))
                except Exception as exc:
                    logger.warning("aws_rds_region_error region=%s error=%s", region, exc)
            return workloads

        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # Lambda
    # ------------------------------------------------------------------

    async def _discover_lambda(self, session: Any) -> list[Workload]:
        def _run() -> list[Workload]:
            workloads: list[Workload] = []
            for region in self._regions:
                try:
                    lmb = session.client("lambda", region_name=region)
                    paginator = lmb.get_paginator("list_functions")
                    for page in paginator.paginate():
                        for fn in page.get("Functions", []):
                            mem_mb = fn.get("MemorySize", 128)
                            workloads.append(Workload(
                                id=fn["FunctionArn"],
                                name=fn["FunctionName"],
                                cloud="aws",
                                service_type="Lambda",
                                region=region,
                                tags=fn.get("Tags") or {},
                                memory_gb=round(mem_mb / 1024, 3),
                                last_seen=datetime.now(timezone.utc),
                                metadata={
                                    "runtime": fn.get("Runtime"),
                                    "handler": fn.get("Handler"),
                                    "timeout_s": fn.get("Timeout"),
                                    "code_size_bytes": fn.get("CodeSize"),
                                    "last_modified": fn.get("LastModified"),
                                    "architecture": fn.get("Architectures", ["x86_64"])[0],
                                },
                            ))
                except Exception as exc:
                    logger.warning("aws_lambda_region_error region=%s error=%s", region, exc)
            return workloads

        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # S3 (buckets + CloudWatch size metrics)
    # ------------------------------------------------------------------

    async def _discover_s3(self, session: Any) -> list[Workload]:
        def _run() -> list[Workload]:
            workloads: list[Workload] = []
            try:
                s3 = session.client("s3", region_name=self._default_region)
                cw = session.client("cloudwatch", region_name=self._default_region)
                buckets = s3.list_buckets().get("Buckets", [])
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=2)
                for bucket in buckets:
                    name = bucket["Name"]
                    storage_gb = 0.0
                    try:
                        resp = cw.get_metric_statistics(
                            Namespace="AWS/S3",
                            MetricName="BucketSizeBytes",
                            Dimensions=[
                                {"Name": "BucketName", "Value": name},
                                {"Name": "StorageType", "Value": "StandardStorage"},
                            ],
                            StartTime=start,
                            EndTime=end,
                            Period=86400,
                            Statistics=["Average"],
                        )
                        points = resp.get("Datapoints", [])
                        if points:
                            storage_gb = round(
                                max(p["Average"] for p in points) / (1024 ** 3), 3
                            )
                    except Exception:
                        pass  # CloudWatch might not have data; storage_gb stays 0

                    # Fetch tags
                    tags: dict[str, str] = {}
                    try:
                        tag_resp = s3.get_bucket_tagging(Bucket=name)
                        tags = _tags_to_dict(tag_resp.get("TagSet", []))
                    except Exception:
                        pass

                    # Bucket region
                    bucket_region = self._default_region
                    try:
                        loc = s3.get_bucket_location(Bucket=name)
                        bucket_region = loc.get("LocationConstraint") or "us-east-1"
                    except Exception:
                        pass

                    workloads.append(Workload(
                        id=f"arn:aws:s3:::{name}",
                        name=name,
                        cloud="aws",
                        service_type="S3",
                        region=bucket_region,
                        tags=tags,
                        storage_gb=storage_gb,
                        last_seen=datetime.now(timezone.utc),
                        metadata={
                            "created": str(bucket.get("CreationDate", "")),
                        },
                    ))
            except Exception as exc:
                logger.warning("aws_s3_error error=%s", exc)
            return workloads

        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # Cost Explorer — last 30d cost per service
    # ------------------------------------------------------------------

    async def _fetch_cost_by_service(self, session: Any) -> dict[str, float]:
        """Return {service_name: monthly_usd} from Cost Explorer last 30d."""
        def _run() -> dict[str, float]:
            try:
                ce = session.client("ce", region_name="us-east-1")
                end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
                resp = ce.get_cost_and_usage(
                    TimePeriod={"Start": start, "End": end},
                    Granularity="MONTHLY",
                    Metrics=["UnblendedCost"],
                    GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                )
                result: dict[str, float] = {}
                for group_set in resp.get("ResultsByTime", []):
                    for group in group_set.get("Groups", []):
                        svc = group["Keys"][0]
                        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                        result[svc] = result.get(svc, 0.0) + amount
                return result
            except Exception as exc:
                logger.warning("aws_cost_explorer_error error=%s", exc)
                return {}

        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # Trusted Advisor (optional — Business/Enterprise only)
    # ------------------------------------------------------------------

    async def _discover_trusted_advisor(self, session: Any) -> list[Workload]:
        """Return Trusted Advisor check summaries as synthetic Workload rows.

        These represent finding categories (Cost Optimizing, Security, etc.)
        rather than infrastructure resources, but exposing them in the unified
        workload stream lets the assessor surface TA insights without extra
        plumbing.

        Silently returns [] if the account doesn't have Business/Enterprise
        support (the Support API raises SubscriptionRequiredException).
        """
        def _run() -> list[Workload]:
            try:
                support = session.client("support", region_name="us-east-1")
                checks = support.describe_trusted_advisor_checks(language="en")
                workloads: list[Workload] = []
                for check in checks.get("checks", []):
                    check_id = check["id"]
                    try:
                        result = support.describe_trusted_advisor_check_result(
                            checkId=check_id, language="en"
                        )
                        status = result.get("result", {}).get("status", "unknown")
                        workloads.append(Workload(
                            id=f"ta:{check_id}",
                            name=check["name"],
                            cloud="aws",
                            service_type="TrustedAdvisor",
                            region="global",
                            last_seen=datetime.now(timezone.utc),
                            metadata={
                                "category": check.get("category"),
                                "status": status,
                                "description": check.get("description", "")[:500],
                            },
                        ))
                    except Exception:
                        pass
                return workloads
            except Exception:
                return []

        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # Cost annotation
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_costs(workloads: list[Workload], cost_map: dict[str, float]) -> None:
        """Best-effort: map Cost Explorer service names onto Workload rows."""
        _svc_key_map = {
            "EC2": "Amazon Elastic Compute Cloud - Compute",
            "RDS": "Amazon Relational Database Service",
            "Lambda": "AWS Lambda",
            "S3": "Amazon Simple Storage Service",
        }
        for w in workloads:
            ce_key = _svc_key_map.get(w.service_type)
            if ce_key and w.monthly_cost_usd == 0.0:
                w.monthly_cost_usd = cost_map.get(ce_key, 0.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tags_to_dict(tag_list: list[dict[str, str]]) -> dict[str, str]:
    return {t["Key"]: t["Value"] for t in tag_list if "Key" in t and "Value" in t}


def _tag_value(tag_list: list[dict[str, str]], key: str) -> str | None:
    for t in tag_list:
        if t.get("Key") == key:
            return t.get("Value")
    return None
