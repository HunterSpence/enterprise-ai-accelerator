"""
AWS infrastructure discovery scanner.

Scans 13+ AWS services in parallel using asyncio, returns a typed
InfrastructureSnapshot with resource counts, configurations, and cost estimates.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Hardcoded monthly cost approximations per resource unit (USD).
# These are conservative list-price estimates for the most common instance
# families / service tiers. Real costs require the AWS Price List API.
# ---------------------------------------------------------------------------
EC2_HOURLY_PRICES: dict[str, float] = {
    "t2.micro": 0.0116,
    "t2.small": 0.023,
    "t2.medium": 0.0464,
    "t2.large": 0.0928,
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
    "m6i.large": 0.096,
    "m6i.xlarge": 0.192,
    "m6i.2xlarge": 0.384,
    "c5.large": 0.085,
    "c5.xlarge": 0.170,
    "c5.2xlarge": 0.340,
    "r5.large": 0.126,
    "r5.xlarge": 0.252,
    "r5.2xlarge": 0.504,
    "r5.4xlarge": 1.008,
}
HOURS_PER_MONTH = 730.0

RDS_HOURLY_PRICES: dict[str, float] = {
    "db.t3.micro": 0.017,
    "db.t3.small": 0.034,
    "db.t3.medium": 0.068,
    "db.t3.large": 0.136,
    "db.m5.large": 0.171,
    "db.m5.xlarge": 0.342,
    "db.m5.2xlarge": 0.684,
    "db.r5.large": 0.24,
    "db.r5.xlarge": 0.48,
    "db.r5.2xlarge": 0.96,
}

LAMBDA_COST_PER_MILLION_INVOCATIONS = 0.20
LAMBDA_COST_PER_GB_SECOND = 0.0000166667
S3_COST_PER_GB_MONTH = 0.023
EBS_COST_PER_GB_MONTH_GP2 = 0.10
EBS_COST_PER_GB_MONTH_GP3 = 0.08
ELASTICACHE_NODE_HOURLY: dict[str, float] = {
    "cache.t3.micro": 0.017,
    "cache.t3.small": 0.034,
    "cache.m5.large": 0.127,
    "cache.r5.large": 0.169,
}
NAT_GATEWAY_HOURLY = 0.045
NAT_GATEWAY_PER_GB = 0.045
ELASTIC_IP_IDLE_MONTHLY = 3.60


# ---------------------------------------------------------------------------
# Resource dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EC2Instance:
    instance_id: str
    instance_type: str
    state: str
    region: str
    az: str
    platform: str
    launch_time: datetime | None
    vpc_id: str | None
    subnet_id: str | None
    public_ip: str | None
    private_ip: str | None
    security_groups: list[str]
    tags: dict[str, str]
    estimated_monthly_cost: float


@dataclass
class RDSInstance:
    db_instance_id: str
    db_instance_class: str
    engine: str
    engine_version: str
    status: str
    region: str
    multi_az: bool
    allocated_storage_gb: int
    vpc_id: str | None
    publicly_accessible: bool
    encrypted: bool
    tags: dict[str, str]
    estimated_monthly_cost: float


@dataclass
class LambdaFunction:
    function_name: str
    runtime: str
    memory_mb: int
    timeout_seconds: int
    last_modified: str
    code_size_bytes: int
    region: str
    vpc_config: dict[str, Any]
    tags: dict[str, str]
    estimated_monthly_cost: float


@dataclass
class S3Bucket:
    name: str
    region: str
    creation_date: datetime | None
    versioning: str
    encryption: str | None
    public_access_blocked: bool
    tags: dict[str, str]
    size_gb: float
    object_count: int
    estimated_monthly_cost: float


@dataclass
class EBSVolume:
    volume_id: str
    volume_type: str
    size_gb: int
    state: str
    region: str
    az: str
    encrypted: bool
    attached_instance: str | None
    tags: dict[str, str]
    estimated_monthly_cost: float


@dataclass
class EKSCluster:
    cluster_name: str
    kubernetes_version: str
    status: str
    region: str
    endpoint: str | None
    node_groups: list[dict[str, Any]]
    tags: dict[str, str]
    estimated_monthly_cost: float


@dataclass
class ECSCluster:
    cluster_name: str
    cluster_arn: str
    status: str
    region: str
    running_tasks: int
    pending_tasks: int
    active_services: int
    tags: dict[str, str]
    estimated_monthly_cost: float


@dataclass
class VPC:
    vpc_id: str
    cidr_block: str
    region: str
    is_default: bool
    state: str
    tags: dict[str, str]
    subnets: list[dict[str, Any]]
    internet_gateways: list[str]
    nat_gateways: list[dict[str, Any]]
    estimated_monthly_cost: float


@dataclass
class IAMSummary:
    users: int
    roles: int
    groups: int
    policies_attached: int
    mfa_enabled_users: int
    users_without_mfa: list[str]
    access_keys_not_rotated: list[str]
    overprivileged_roles: list[str]


@dataclass
class CloudFrontDistribution:
    distribution_id: str
    domain_name: str
    status: str
    enabled: bool
    origins: list[str]
    price_class: str
    tags: dict[str, str]
    estimated_monthly_cost: float


@dataclass
class ElastiCacheCluster:
    cluster_id: str
    engine: str
    engine_version: str
    node_type: str
    num_nodes: int
    status: str
    region: str
    encrypted: bool
    tags: dict[str, str]
    estimated_monthly_cost: float


@dataclass
class DynamoDBTable:
    table_name: str
    status: str
    billing_mode: str
    region: str
    item_count: int
    size_bytes: int
    encrypted: bool
    point_in_time_recovery: bool
    tags: dict[str, str]
    estimated_monthly_cost: float


@dataclass
class SQSQueue:
    queue_url: str
    queue_name: str
    region: str
    visibility_timeout: int
    message_retention_seconds: int
    approximate_messages: int
    is_fifo: bool
    tags: dict[str, str]


@dataclass
class SNSTopic:
    topic_arn: str
    topic_name: str
    region: str
    subscriptions_confirmed: int
    tags: dict[str, str]


@dataclass
class ElasticIP:
    allocation_id: str
    public_ip: str
    region: str
    associated_instance: str | None
    is_idle: bool
    estimated_monthly_cost: float


@dataclass
class InfrastructureSnapshot:
    """Complete point-in-time snapshot of AWS infrastructure across services."""

    account_id: str
    regions: list[str]
    scanned_at: datetime
    ec2_instances: list[EC2Instance] = field(default_factory=list)
    rds_instances: list[RDSInstance] = field(default_factory=list)
    lambda_functions: list[LambdaFunction] = field(default_factory=list)
    s3_buckets: list[S3Bucket] = field(default_factory=list)
    ebs_volumes: list[EBSVolume] = field(default_factory=list)
    eks_clusters: list[EKSCluster] = field(default_factory=list)
    ecs_clusters: list[ECSCluster] = field(default_factory=list)
    vpcs: list[VPC] = field(default_factory=list)
    iam_summary: IAMSummary | None = None
    cloudfront_distributions: list[CloudFrontDistribution] = field(default_factory=list)
    elasticache_clusters: list[ElastiCacheCluster] = field(default_factory=list)
    dynamodb_tables: list[DynamoDBTable] = field(default_factory=list)
    sqs_queues: list[SQSQueue] = field(default_factory=list)
    sns_topics: list[SNSTopic] = field(default_factory=list)
    elastic_ips: list[ElasticIP] = field(default_factory=list)
    scan_errors: list[str] = field(default_factory=list)

    @property
    def total_estimated_monthly_cost(self) -> float:
        total = 0.0
        for inst in self.ec2_instances:
            total += inst.estimated_monthly_cost
        for rds in self.rds_instances:
            total += rds.estimated_monthly_cost
        for fn in self.lambda_functions:
            total += fn.estimated_monthly_cost
        for bucket in self.s3_buckets:
            total += bucket.estimated_monthly_cost
        for vol in self.ebs_volumes:
            total += vol.estimated_monthly_cost
        for cluster in self.eks_clusters:
            total += cluster.estimated_monthly_cost
        for cf in self.cloudfront_distributions:
            total += cf.estimated_monthly_cost
        for ec in self.elasticache_clusters:
            total += ec.estimated_monthly_cost
        for vpc in self.vpcs:
            total += vpc.estimated_monthly_cost
        for eip in self.elastic_ips:
            total += eip.estimated_monthly_cost
        return total

    @property
    def resource_counts(self) -> dict[str, int]:
        return {
            "ec2_instances": len(self.ec2_instances),
            "rds_instances": len(self.rds_instances),
            "lambda_functions": len(self.lambda_functions),
            "s3_buckets": len(self.s3_buckets),
            "ebs_volumes": len(self.ebs_volumes),
            "eks_clusters": len(self.eks_clusters),
            "ecs_clusters": len(self.ecs_clusters),
            "vpcs": len(self.vpcs),
            "cloudfront_distributions": len(self.cloudfront_distributions),
            "elasticache_clusters": len(self.elasticache_clusters),
            "dynamodb_tables": len(self.dynamodb_tables),
            "sqs_queues": len(self.sqs_queues),
            "sns_topics": len(self.sns_topics),
            "elastic_ips": len(self.elastic_ips),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize snapshot to a plain dict suitable for JSON or LLM context."""
        return {
            "account_id": self.account_id,
            "regions": self.regions,
            "scanned_at": self.scanned_at.isoformat(),
            "resource_counts": self.resource_counts,
            "total_estimated_monthly_cost": round(self.total_estimated_monthly_cost, 2),
            "scan_errors": self.scan_errors,
        }


# ---------------------------------------------------------------------------
# Scanner implementation
# ---------------------------------------------------------------------------


def _tags_to_dict(tag_list: list[dict[str, str]] | None) -> dict[str, str]:
    if not tag_list:
        return {}
    return {t["Key"]: t["Value"] for t in tag_list}


def _ec2_monthly_cost(instance_type: str, state: str) -> float:
    if state != "running":
        return 0.0
    hourly = EC2_HOURLY_PRICES.get(instance_type, 0.10)
    return round(hourly * HOURS_PER_MONTH, 2)


def _rds_monthly_cost(instance_class: str, multi_az: bool, storage_gb: int) -> float:
    hourly = RDS_HOURLY_PRICES.get(instance_class, 0.20)
    compute = hourly * HOURS_PER_MONTH
    if multi_az:
        compute *= 2
    storage = storage_gb * 0.115
    return round(compute + storage, 2)


class InfrastructureScanner:
    """
    Discovers AWS infrastructure across multiple regions and services.

    Uses asyncio.gather to run service scans in parallel, dramatically
    reducing scan time for large accounts.
    """

    SUPPORTED_SERVICES = [
        "EC2 Instances",
        "RDS Instances",
        "Lambda Functions",
        "S3 Buckets",
        "EBS Volumes",
        "EKS Clusters",
        "ECS Clusters",
        "VPCs",
        "IAM",
        "CloudFront",
        "ElastiCache",
        "DynamoDB",
        "SQS",
        "SNS",
        "Elastic IPs",
    ]

    def __init__(
        self,
        regions: list[str] | None = None,
        profile_name: str | None = None,
    ) -> None:
        self._regions = regions or ["us-east-1"]
        self._profile = profile_name
        self._session_kwargs: dict[str, Any] = {}
        if profile_name:
            self._session_kwargs["profile_name"] = profile_name

    def _boto_session(self, region: str) -> boto3.Session:
        return boto3.Session(region_name=region, **self._session_kwargs)

    def _client(self, service: str, region: str) -> Any:
        return self._boto_session(region).client(service)

    # ------------------------------------------------------------------
    # Per-service scan methods (synchronous, called via run_in_executor)
    # ------------------------------------------------------------------

    def _scan_ec2(self, region: str) -> list[EC2Instance]:
        ec2 = self._client("ec2", region)
        instances: list[EC2Instance] = []
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate():
            for reservation in page["Reservations"]:
                for raw in reservation["Instances"]:
                    instance_type = raw.get("InstanceType", "unknown")
                    state = raw.get("State", {}).get("Name", "unknown")
                    instances.append(
                        EC2Instance(
                            instance_id=raw["InstanceId"],
                            instance_type=instance_type,
                            state=state,
                            region=region,
                            az=raw.get("Placement", {}).get("AvailabilityZone", ""),
                            platform=raw.get("Platform", "linux"),
                            launch_time=raw.get("LaunchTime"),
                            vpc_id=raw.get("VpcId"),
                            subnet_id=raw.get("SubnetId"),
                            public_ip=raw.get("PublicIpAddress"),
                            private_ip=raw.get("PrivateIpAddress"),
                            security_groups=[
                                sg["GroupId"]
                                for sg in raw.get("SecurityGroups", [])
                            ],
                            tags=_tags_to_dict(raw.get("Tags")),
                            estimated_monthly_cost=_ec2_monthly_cost(
                                instance_type, state
                            ),
                        )
                    )
        return instances

    def _scan_rds(self, region: str) -> list[RDSInstance]:
        rds = self._client("rds", region)
        instances: list[RDSInstance] = []
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for raw in page["DBInstances"]:
                instance_class = raw.get("DBInstanceClass", "db.t3.micro")
                multi_az = raw.get("MultiAZ", False)
                storage = raw.get("AllocatedStorage", 20)
                instances.append(
                    RDSInstance(
                        db_instance_id=raw["DBInstanceIdentifier"],
                        db_instance_class=instance_class,
                        engine=raw.get("Engine", ""),
                        engine_version=raw.get("EngineVersion", ""),
                        status=raw.get("DBInstanceStatus", ""),
                        region=region,
                        multi_az=multi_az,
                        allocated_storage_gb=storage,
                        vpc_id=raw.get("DBSubnetGroup", {}).get("VpcId"),
                        publicly_accessible=raw.get("PubliclyAccessible", False),
                        encrypted=raw.get("StorageEncrypted", False),
                        tags=_tags_to_dict(raw.get("TagList")),
                        estimated_monthly_cost=_rds_monthly_cost(
                            instance_class, multi_az, storage
                        ),
                    )
                )
        return instances

    def _scan_lambda(self, region: str) -> list[LambdaFunction]:
        lam = self._client("lambda", region)
        functions: list[LambdaFunction] = []
        paginator = lam.get_paginator("list_functions")
        for page in paginator.paginate():
            for raw in page["Functions"]:
                memory = raw.get("MemorySize", 128)
                functions.append(
                    LambdaFunction(
                        function_name=raw["FunctionName"],
                        runtime=raw.get("Runtime", "unknown"),
                        memory_mb=memory,
                        timeout_seconds=raw.get("Timeout", 3),
                        last_modified=raw.get("LastModified", ""),
                        code_size_bytes=raw.get("CodeSize", 0),
                        region=region,
                        vpc_config=raw.get("VpcConfig", {}),
                        tags=raw.get("Tags", {}),
                        estimated_monthly_cost=round(
                            LAMBDA_COST_PER_MILLION_INVOCATIONS * 0.1
                            + LAMBDA_COST_PER_GB_SECOND
                            * (memory / 1024)
                            * 100_000,
                            4,
                        ),
                    )
                )
        return functions

    def _scan_s3(self) -> list[S3Bucket]:
        s3 = self._client("s3", "us-east-1")
        s3_control = self._boto_session("us-east-1").client(
            "s3control",
            endpoint_url="https://s3.amazonaws.com",
        )
        buckets: list[S3Bucket] = []
        response = s3.list_buckets()
        for raw in response.get("Buckets", []):
            name = raw["Name"]
            creation_date = raw.get("CreationDate")

            region = "us-east-1"
            try:
                loc = s3.get_bucket_location(Bucket=name)
                region = loc.get("LocationConstraint") or "us-east-1"
            except ClientError:
                pass

            versioning = "Disabled"
            try:
                v = s3.get_bucket_versioning(Bucket=name)
                versioning = v.get("Status", "Disabled") or "Disabled"
            except ClientError:
                pass

            encryption = None
            try:
                enc = s3.get_bucket_encryption(Bucket=name)
                rules = enc.get("ServerSideEncryptionConfiguration", {}).get(
                    "Rules", []
                )
                if rules:
                    encryption = rules[0].get(
                        "ApplyServerSideEncryptionByDefault", {}
                    ).get("SSEAlgorithm")
            except ClientError:
                pass

            public_access_blocked = True
            try:
                pab = s3.get_public_access_block(Bucket=name)
                cfg = pab.get("PublicAccessBlockConfiguration", {})
                public_access_blocked = all(cfg.values())
            except ClientError:
                pass

            tags: dict[str, str] = {}
            try:
                t = s3.get_bucket_tagging(Bucket=name)
                tags = _tags_to_dict(t.get("TagSet"))
            except ClientError:
                pass

            buckets.append(
                S3Bucket(
                    name=name,
                    region=region,
                    creation_date=creation_date,
                    versioning=versioning,
                    encryption=encryption,
                    public_access_blocked=public_access_blocked,
                    tags=tags,
                    size_gb=0.0,
                    object_count=0,
                    estimated_monthly_cost=0.0,
                )
            )
        return buckets

    def _scan_ebs(self, region: str) -> list[EBSVolume]:
        ec2 = self._client("ec2", region)
        volumes: list[EBSVolume] = []
        paginator = ec2.get_paginator("describe_volumes")
        for page in paginator.paginate():
            for raw in page["Volumes"]:
                vol_type = raw.get("VolumeType", "gp2")
                size_gb = raw.get("Size", 0)
                state = raw.get("State", "")
                attachments = raw.get("Attachments", [])
                attached_instance = (
                    attachments[0]["InstanceId"] if attachments else None
                )
                if vol_type == "gp3":
                    cost_per_gb = EBS_COST_PER_GB_MONTH_GP3
                else:
                    cost_per_gb = EBS_COST_PER_GB_MONTH_GP2
                volumes.append(
                    EBSVolume(
                        volume_id=raw["VolumeId"],
                        volume_type=vol_type,
                        size_gb=size_gb,
                        state=state,
                        region=region,
                        az=raw.get("AvailabilityZone", ""),
                        encrypted=raw.get("Encrypted", False),
                        attached_instance=attached_instance,
                        tags=_tags_to_dict(raw.get("Tags")),
                        estimated_monthly_cost=round(size_gb * cost_per_gb, 2),
                    )
                )
        return volumes

    def _scan_elastic_ips(self, region: str) -> list[ElasticIP]:
        ec2 = self._client("ec2", region)
        eips: list[ElasticIP] = []
        response = ec2.describe_addresses()
        for raw in response.get("Addresses", []):
            associated = raw.get("InstanceId")
            is_idle = associated is None
            eips.append(
                ElasticIP(
                    allocation_id=raw.get("AllocationId", ""),
                    public_ip=raw.get("PublicIp", ""),
                    region=region,
                    associated_instance=associated,
                    is_idle=is_idle,
                    estimated_monthly_cost=ELASTIC_IP_IDLE_MONTHLY if is_idle else 0.0,
                )
            )
        return eips

    def _scan_eks(self, region: str) -> list[EKSCluster]:
        eks = self._client("eks", region)
        clusters: list[EKSCluster] = []
        paginator = eks.get_paginator("list_clusters")
        for page in paginator.paginate():
            for name in page["clusters"]:
                try:
                    detail = eks.describe_cluster(name=name)["cluster"]
                    node_groups: list[dict[str, Any]] = []
                    try:
                        ng_pag = eks.get_paginator("list_nodegroups")
                        for ng_page in ng_pag.paginate(clusterName=name):
                            for ng_name in ng_page["nodegroups"]:
                                ng = eks.describe_nodegroup(
                                    clusterName=name, nodegroupName=ng_name
                                )["nodegroup"]
                                node_groups.append(
                                    {
                                        "name": ng_name,
                                        "instance_types": ng.get(
                                            "instanceTypes", []
                                        ),
                                        "desired_size": ng.get(
                                            "scalingConfig", {}
                                        ).get("desiredSize", 0),
                                    }
                                )
                    except ClientError:
                        pass

                    node_cost = sum(
                        _ec2_monthly_cost(
                            ng.get("instance_types", ["m5.large"])[0],
                            "running",
                        )
                        * ng.get("desired_size", 1)
                        for ng in node_groups
                    )
                    clusters.append(
                        EKSCluster(
                            cluster_name=name,
                            kubernetes_version=detail.get("version", ""),
                            status=detail.get("status", ""),
                            region=region,
                            endpoint=detail.get("endpoint"),
                            node_groups=node_groups,
                            tags=detail.get("tags", {}),
                            estimated_monthly_cost=round(
                                72.0 + node_cost, 2
                            ),  # $72/mo control plane
                        )
                    )
                except ClientError:
                    pass
        return clusters

    def _scan_ecs(self, region: str) -> list[ECSCluster]:
        ecs = self._client("ecs", region)
        clusters: list[ECSCluster] = []
        paginator = ecs.get_paginator("list_clusters")
        arns: list[str] = []
        for page in paginator.paginate():
            arns.extend(page["clusterArns"])
        if not arns:
            return clusters
        for i in range(0, len(arns), 100):
            batch = arns[i : i + 100]
            detail = ecs.describe_clusters(clusters=batch, include=["TAGS"])
            for raw in detail["clusters"]:
                clusters.append(
                    ECSCluster(
                        cluster_name=raw["clusterName"],
                        cluster_arn=raw["clusterArn"],
                        status=raw.get("status", ""),
                        region=region,
                        running_tasks=raw.get("runningTasksCount", 0),
                        pending_tasks=raw.get("pendingTasksCount", 0),
                        active_services=raw.get("activeServicesCount", 0),
                        tags=_tags_to_dict(raw.get("tags")),
                        estimated_monthly_cost=0.0,
                    )
                )
        return clusters

    def _scan_vpc(self, region: str) -> list[VPC]:
        ec2 = self._client("ec2", region)
        vpcs: list[VPC] = []
        response = ec2.describe_vpcs()
        for raw in response["Vpcs"]:
            vpc_id = raw["VpcId"]

            subnets: list[dict[str, Any]] = []
            try:
                sub_resp = ec2.describe_subnets(
                    Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
                )
                subnets = [
                    {
                        "subnet_id": s["SubnetId"],
                        "cidr": s["CidrBlock"],
                        "az": s["AvailabilityZone"],
                        "public": s.get("MapPublicIpOnLaunch", False),
                    }
                    for s in sub_resp["Subnets"]
                ]
            except ClientError:
                pass

            igws: list[str] = []
            try:
                igw_resp = ec2.describe_internet_gateways(
                    Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
                )
                igws = [g["InternetGatewayId"] for g in igw_resp["InternetGateways"]]
            except ClientError:
                pass

            nat_gws: list[dict[str, Any]] = []
            monthly_nat_cost = 0.0
            try:
                nat_resp = ec2.describe_nat_gateways(
                    Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
                )
                for gw in nat_resp["NatGateways"]:
                    if gw.get("State") == "available":
                        nat_gws.append(
                            {
                                "id": gw["NatGatewayId"],
                                "subnet_id": gw.get("SubnetId"),
                                "state": gw["State"],
                            }
                        )
                        monthly_nat_cost += NAT_GATEWAY_HOURLY * HOURS_PER_MONTH
            except ClientError:
                pass

            vpcs.append(
                VPC(
                    vpc_id=vpc_id,
                    cidr_block=raw.get("CidrBlock", ""),
                    region=region,
                    is_default=raw.get("IsDefault", False),
                    state=raw.get("State", ""),
                    tags=_tags_to_dict(raw.get("Tags")),
                    subnets=subnets,
                    internet_gateways=igws,
                    nat_gateways=nat_gws,
                    estimated_monthly_cost=round(monthly_nat_cost, 2),
                )
            )
        return vpcs

    def _scan_iam(self) -> IAMSummary:
        iam = self._client("iam", "us-east-1")
        summary = iam.get_account_summary()["SummaryMap"]

        users_without_mfa: list[str] = []
        access_keys_not_rotated: list[str] = []
        try:
            paginator = iam.get_paginator("generate_credential_report")
            iam.generate_credential_report()
            import time

            time.sleep(2)
            report = iam.get_credential_report()
            import csv
            import io

            reader = csv.DictReader(io.StringIO(report["Content"].decode("utf-8")))
            from datetime import timedelta

            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            for row in reader:
                if row.get("user") == "<root_account>":
                    continue
                if row.get("mfa_active", "false") == "false":
                    users_without_mfa.append(row["user"])
                for key_num in ("1", "2"):
                    last_rotated = row.get(f"access_key_{key_num}_last_rotated", "N/A")
                    if last_rotated not in ("N/A", "no_information"):
                        try:
                            rotated_dt = datetime.fromisoformat(
                                last_rotated.replace("Z", "+00:00")
                            )
                            if rotated_dt < cutoff:
                                access_keys_not_rotated.append(
                                    f"{row['user']} (key {key_num})"
                                )
                        except ValueError:
                            pass
        except ClientError:
            pass

        overprivileged: list[str] = []
        try:
            role_pag = iam.get_paginator("list_roles")
            for page in role_pag.paginate():
                for role in page["Roles"]:
                    attached = iam.list_attached_role_policies(
                        RoleName=role["RoleName"]
                    )
                    for policy in attached["AttachedPolicies"]:
                        if policy["PolicyName"] in (
                            "AdministratorAccess",
                            "PowerUserAccess",
                        ):
                            overprivileged.append(role["RoleName"])
                            break
        except ClientError:
            pass

        return IAMSummary(
            users=summary.get("Users", 0),
            roles=summary.get("Roles", 0),
            groups=summary.get("Groups", 0),
            policies_attached=summary.get("AttachedPoliciesPerUserQuota", 0),
            mfa_enabled_users=summary.get("AccountMFAEnabled", 0),
            users_without_mfa=users_without_mfa,
            access_keys_not_rotated=access_keys_not_rotated,
            overprivileged_roles=overprivileged,
        )

    def _scan_cloudfront(self) -> list[CloudFrontDistribution]:
        cf = self._client("cloudfront", "us-east-1")
        distributions: list[CloudFrontDistribution] = []
        paginator = cf.get_paginator("list_distributions")
        for page in paginator.paginate():
            dist_list = page.get("DistributionList", {}).get("Items", [])
            for raw in dist_list:
                origins = [
                    o["DomainName"]
                    for o in raw.get("Origins", {}).get("Items", [])
                ]
                distributions.append(
                    CloudFrontDistribution(
                        distribution_id=raw["Id"],
                        domain_name=raw.get("DomainName", ""),
                        status=raw.get("Status", ""),
                        enabled=raw.get("Enabled", False),
                        origins=origins,
                        price_class=raw.get("PriceClass", ""),
                        tags={},
                        estimated_monthly_cost=50.0,
                    )
                )
        return distributions

    def _scan_elasticache(self, region: str) -> list[ElastiCacheCluster]:
        ec = self._client("elasticache", region)
        clusters: list[ElastiCacheCluster] = []
        paginator = ec.get_paginator("describe_cache_clusters")
        for page in paginator.paginate():
            for raw in page["CacheClusters"]:
                node_type = raw.get("CacheNodeType", "cache.t3.micro")
                num_nodes = raw.get("NumCacheNodes", 1)
                hourly = ELASTICACHE_NODE_HOURLY.get(node_type, 0.05)
                clusters.append(
                    ElastiCacheCluster(
                        cluster_id=raw["CacheClusterId"],
                        engine=raw.get("Engine", ""),
                        engine_version=raw.get("EngineVersion", ""),
                        node_type=node_type,
                        num_nodes=num_nodes,
                        status=raw.get("CacheClusterStatus", ""),
                        region=region,
                        encrypted=raw.get("AtRestEncryptionEnabled", False),
                        tags={},
                        estimated_monthly_cost=round(
                            hourly * HOURS_PER_MONTH * num_nodes, 2
                        ),
                    )
                )
        return clusters

    def _scan_dynamodb(self, region: str) -> list[DynamoDBTable]:
        ddb = self._client("dynamodb", region)
        tables: list[DynamoDBTable] = []
        paginator = ddb.get_paginator("list_tables")
        for page in paginator.paginate():
            for name in page["TableNames"]:
                try:
                    detail = ddb.describe_table(TableName=name)["Table"]
                    pitr = False
                    try:
                        pitr_resp = ddb.describe_continuous_backups(TableName=name)
                        pitr = (
                            pitr_resp.get("ContinuousBackupsDescription", {})
                            .get("PointInTimeRecoveryDescription", {})
                            .get("PointInTimeRecoveryStatus", "DISABLED")
                            == "ENABLED"
                        )
                    except ClientError:
                        pass

                    tags: dict[str, str] = {}
                    try:
                        t = ddb.list_tags_of_resource(
                            ResourceArn=detail["TableArn"]
                        )
                        tags = _tags_to_dict(t.get("Tags"))
                    except ClientError:
                        pass

                    billing_mode = detail.get("BillingModeSummary", {}).get(
                        "BillingMode", "PROVISIONED"
                    )
                    item_count = detail.get("ItemCount", 0)
                    size_bytes = detail.get("TableSizeBytes", 0)
                    monthly_cost = round(
                        (size_bytes / (1024**3)) * 0.25
                        + (item_count / 1_000_000) * 0.25,
                        2,
                    )
                    tables.append(
                        DynamoDBTable(
                            table_name=name,
                            status=detail.get("TableStatus", ""),
                            billing_mode=billing_mode,
                            region=region,
                            item_count=item_count,
                            size_bytes=size_bytes,
                            encrypted=detail.get("SSEDescription", {}).get(
                                "Status"
                            )
                            == "ENABLED",
                            point_in_time_recovery=pitr,
                            tags=tags,
                            estimated_monthly_cost=monthly_cost,
                        )
                    )
                except ClientError:
                    pass
        return tables

    def _scan_sqs(self, region: str) -> list[SQSQueue]:
        sqs = self._client("sqs", region)
        queues: list[SQSQueue] = []
        paginator = sqs.get_paginator("list_queues")
        for page in paginator.paginate():
            for url in page.get("QueueUrls", []):
                try:
                    attrs = sqs.get_queue_attributes(
                        QueueUrl=url,
                        AttributeNames=[
                            "VisibilityTimeout",
                            "MessageRetentionPeriod",
                            "ApproximateNumberOfMessages",
                        ],
                    )["Attributes"]
                    name = url.split("/")[-1]
                    tags: dict[str, str] = {}
                    try:
                        tags = sqs.list_queue_tags(QueueUrl=url).get("Tags", {})
                    except ClientError:
                        pass
                    queues.append(
                        SQSQueue(
                            queue_url=url,
                            queue_name=name,
                            region=region,
                            visibility_timeout=int(
                                attrs.get("VisibilityTimeout", 30)
                            ),
                            message_retention_seconds=int(
                                attrs.get("MessageRetentionPeriod", 345600)
                            ),
                            approximate_messages=int(
                                attrs.get("ApproximateNumberOfMessages", 0)
                            ),
                            is_fifo=name.endswith(".fifo"),
                            tags=tags,
                        )
                    )
                except ClientError:
                    pass
        return queues

    def _scan_sns(self, region: str) -> list[SNSTopic]:
        sns = self._client("sns", region)
        topics: list[SNSTopic] = []
        paginator = sns.get_paginator("list_topics")
        for page in paginator.paginate():
            for t in page["Topics"]:
                arn = t["TopicArn"]
                name = arn.split(":")[-1]
                confirmed = 0
                try:
                    attrs = sns.get_topic_attributes(TopicArn=arn)["Attributes"]
                    confirmed = int(
                        attrs.get("SubscriptionsConfirmed", 0)
                    )
                except ClientError:
                    pass
                tags: dict[str, str] = {}
                try:
                    tags = _tags_to_dict(
                        sns.list_tags_for_resource(ResourceArn=arn).get("Tags")
                    )
                except ClientError:
                    pass
                topics.append(
                    SNSTopic(
                        topic_arn=arn,
                        topic_name=name,
                        region=region,
                        subscriptions_confirmed=confirmed,
                        tags=tags,
                    )
                )
        return topics

    # ------------------------------------------------------------------
    # Async orchestration
    # ------------------------------------------------------------------

    async def _run_in_executor(self, func, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)

    async def _scan_region(
        self,
        region: str,
        progress: Progress,
        task_id,
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}
        errors: list[str] = []

        async def safe(name: str, coro):
            try:
                results[name] = await coro
            except (ClientError, Exception) as exc:
                errors.append(f"{region}/{name}: {exc}")
                results[name] = []
            finally:
                progress.advance(task_id)

        await asyncio.gather(
            safe("ec2", self._run_in_executor(self._scan_ec2, region)),
            safe("rds", self._run_in_executor(self._scan_rds, region)),
            safe("lambda", self._run_in_executor(self._scan_lambda, region)),
            safe("ebs", self._run_in_executor(self._scan_ebs, region)),
            safe("elastic_ips", self._run_in_executor(self._scan_elastic_ips, region)),
            safe("eks", self._run_in_executor(self._scan_eks, region)),
            safe("ecs", self._run_in_executor(self._scan_ecs, region)),
            safe("vpc", self._run_in_executor(self._scan_vpc, region)),
            safe("elasticache", self._run_in_executor(self._scan_elasticache, region)),
            safe("dynamodb", self._run_in_executor(self._scan_dynamodb, region)),
            safe("sqs", self._run_in_executor(self._scan_sqs, region)),
            safe("sns", self._run_in_executor(self._scan_sns, region)),
        )
        results["errors"] = errors
        return results

    async def scan_async(self) -> InfrastructureSnapshot:
        """Execute a full infrastructure scan across all configured regions."""
        account_id = "unknown"
        try:
            sts = self._client("sts", "us-east-1")
            account_id = sts.get_caller_identity()["Account"]
        except (ClientError, NoCredentialsError):
            pass

        services_per_region = 12
        total_tasks = len(self._regions) * services_per_region + 3  # +IAM, S3, CF

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Scanning {len(self._regions)} region(s)...", total=total_tasks
            )

            snapshot = InfrastructureSnapshot(
                account_id=account_id,
                regions=self._regions,
                scanned_at=datetime.now(timezone.utc),
            )

            # Global services (single region)
            async def scan_global():
                errors: list[str] = []
                try:
                    snapshot.s3_buckets = await self._run_in_executor(self._scan_s3)
                except Exception as exc:
                    errors.append(f"s3: {exc}")
                progress.advance(task)

                try:
                    snapshot.iam_summary = await self._run_in_executor(self._scan_iam)
                except Exception as exc:
                    errors.append(f"iam: {exc}")
                progress.advance(task)

                try:
                    snapshot.cloudfront_distributions = await self._run_in_executor(
                        self._scan_cloudfront
                    )
                except Exception as exc:
                    errors.append(f"cloudfront: {exc}")
                progress.advance(task)

                snapshot.scan_errors.extend(errors)

            region_tasks = [
                self._scan_region(region, progress, task)
                for region in self._regions
            ]
            results = await asyncio.gather(scan_global(), *region_tasks)

            for region_result in results[1:]:
                if not isinstance(region_result, dict):
                    continue
                snapshot.ec2_instances.extend(region_result.get("ec2", []))
                snapshot.rds_instances.extend(region_result.get("rds", []))
                snapshot.lambda_functions.extend(region_result.get("lambda", []))
                snapshot.ebs_volumes.extend(region_result.get("ebs", []))
                snapshot.elastic_ips.extend(region_result.get("elastic_ips", []))
                snapshot.eks_clusters.extend(region_result.get("eks", []))
                snapshot.ecs_clusters.extend(region_result.get("ecs", []))
                snapshot.vpcs.extend(region_result.get("vpc", []))
                snapshot.elasticache_clusters.extend(
                    region_result.get("elasticache", [])
                )
                snapshot.dynamodb_tables.extend(region_result.get("dynamodb", []))
                snapshot.sqs_queues.extend(region_result.get("sqs", []))
                snapshot.sns_topics.extend(region_result.get("sns", []))
                snapshot.scan_errors.extend(region_result.get("errors", []))

        return snapshot

    def scan(self) -> InfrastructureSnapshot:
        """Synchronous wrapper for scan_async."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.scan_async())
                    return future.result()
            return loop.run_until_complete(self.scan_async())
        except RuntimeError:
            return asyncio.run(self.scan_async())
