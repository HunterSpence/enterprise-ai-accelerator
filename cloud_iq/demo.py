"""
CloudIQ Demo — AcmeCorp Infrastructure Analysis

DEPRECATED: Use demo_v2 for the full multi-scene cinematic demo.
This single-scene demo is preserved for backward compatibility.

Runs a fully self-contained demo using realistic mock data representing
a fictional company "AcmeCorp" with $47,200/month in identified waste.

No AWS credentials required. Run with:
    python -m cloud_iq.demo
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
from rich import box
from rich.text import Text

from cloud_iq.cost_analyzer import (
    CostDriverEntry,
    CostReport,
    RightsizingRecommendation,
    ShadowITItem,
    WasteItem,
)
from cloud_iq.dashboard import Dashboard, _format_usd
from cloud_iq.scanner import (
    EC2Instance,
    EBSVolume,
    ECSCluster,
    EKSCluster,
    ElasticIP,
    ElastiCacheCluster,
    InfrastructureSnapshot,
    LambdaFunction,
    RDSInstance,
    S3Bucket,
    VPC,
)

console = Console()

# ---------------------------------------------------------------------------
# Mock data — AcmeCorp (fictional $12M ARR SaaS company)
# ---------------------------------------------------------------------------

ACCOUNT_ID = "123456789012"
REGIONS = ["us-east-1", "us-west-2", "eu-west-1"]


def _make_snapshot() -> InfrastructureSnapshot:
    snapshot = InfrastructureSnapshot(
        account_id=ACCOUNT_ID,
        regions=REGIONS,
        scanned_at=datetime.now(timezone.utc),
    )

    # EC2 Instances — production + dev + forgotten zombies
    snapshot.ec2_instances = [
        EC2Instance(
            instance_id="i-0a1b2c3d4e5f60001",
            instance_type="m5.4xlarge",
            state="running",
            region="us-east-1",
            az="us-east-1a",
            platform="linux",
            launch_time=datetime.now(timezone.utc) - timedelta(days=847),
            vpc_id="vpc-0a1b2c3d4e5f6001",
            subnet_id="subnet-0a1b2c3d001",
            public_ip=None,
            private_ip="10.0.1.10",
            security_groups=["sg-0a1b2c3d001", "sg-0a1b2c3d002"],
            tags={
                "Name": "prod-api-server-01",
                "Environment": "production",
                "Team": "backend",
                "CostCenter": "eng-001",
            },
            estimated_monthly_cost=768.00,
        ),
        EC2Instance(
            instance_id="i-0a1b2c3d4e5f60002",
            instance_type="m5.4xlarge",
            state="running",
            region="us-east-1",
            az="us-east-1b",
            platform="linux",
            launch_time=datetime.now(timezone.utc) - timedelta(days=847),
            vpc_id="vpc-0a1b2c3d4e5f6001",
            subnet_id="subnet-0a1b2c3d002",
            public_ip=None,
            private_ip="10.0.1.11",
            security_groups=["sg-0a1b2c3d001"],
            tags={
                "Name": "prod-api-server-02",
                "Environment": "production",
                "Team": "backend",
                "CostCenter": "eng-001",
            },
            estimated_monthly_cost=768.00,
        ),
        EC2Instance(
            instance_id="i-0a1b2c3d4e5f60010",
            instance_type="r5.4xlarge",
            state="running",
            region="us-east-1",
            az="us-east-1a",
            platform="linux",
            launch_time=datetime.now(timezone.utc) - timedelta(days=312),
            vpc_id="vpc-0a1b2c3d4e5f6001",
            subnet_id="subnet-0a1b2c3d003",
            public_ip=None,
            private_ip="10.0.2.50",
            security_groups=["sg-0a1b2c3d003"],
            tags={
                "Name": "prod-ml-inference-01",
                "Environment": "production",
                "Team": "ml",
                "CostCenter": "eng-003",
            },
            estimated_monthly_cost=1008.00,
        ),
        # IDLE — zombie from a migration 8 months ago
        EC2Instance(
            instance_id="i-0deadbeef0000001",
            instance_type="m5.2xlarge",
            state="running",
            region="us-east-1",
            az="us-east-1c",
            platform="linux",
            launch_time=datetime.now(timezone.utc) - timedelta(days=248),
            vpc_id="vpc-0a1b2c3d4e5f6001",
            subnet_id="subnet-0a1b2c3d004",
            public_ip=None,
            private_ip="10.0.3.77",
            security_groups=["sg-0a1b2c3d004"],
            tags={
                "Name": "old-etl-worker-migration-TEMP",
                "Environment": "production",
                "Team": "data",
                "CostCenter": "eng-002",
            },
            estimated_monthly_cost=384.00,
        ),
        EC2Instance(
            instance_id="i-0deadbeef0000002",
            instance_type="m5.xlarge",
            state="running",
            region="us-east-1",
            az="us-east-1a",
            platform="linux",
            launch_time=datetime.now(timezone.utc) - timedelta(days=611),
            vpc_id="vpc-0a1b2c3d4e5f6001",
            subnet_id="subnet-0a1b2c3d005",
            public_ip="54.204.33.102",
            private_ip="10.0.4.22",
            security_groups=["sg-0a1b2c3d005"],
            tags={
                "Name": "dev-bastion-unused",
                "Environment": "development",
                "Team": "infra",
            },
            estimated_monthly_cost=192.00,
        ),
        # Dev instances — over-provisioned
        EC2Instance(
            instance_id="i-0a1b2c3d4e5f60020",
            instance_type="t3.2xlarge",
            state="running",
            region="us-west-2",
            az="us-west-2a",
            platform="linux",
            launch_time=datetime.now(timezone.utc) - timedelta(days=91),
            vpc_id="vpc-0a1b2c3d4e5f6002",
            subnet_id="subnet-0a1b2c3d010",
            public_ip=None,
            private_ip="10.1.1.5",
            security_groups=["sg-0a1b2c3d010"],
            tags={
                "Name": "staging-app-01",
                "Environment": "staging",
                "Team": "backend",
            },
            estimated_monthly_cost=332.80,
        ),
        EC2Instance(
            instance_id="i-0a1b2c3d4e5f60030",
            instance_type="t3.xlarge",
            state="running",
            region="eu-west-1",
            az="eu-west-1a",
            platform="linux",
            launch_time=datetime.now(timezone.utc) - timedelta(days=180),
            vpc_id="vpc-0a1b2c3d4e5f6003",
            subnet_id="subnet-0a1b2c3d020",
            public_ip=None,
            private_ip="10.2.1.5",
            security_groups=["sg-0a1b2c3d020"],
            tags={
                "Name": "eu-prod-app-01",
                "Environment": "production",
                "Team": "backend",
                "Region": "eu",
            },
            estimated_monthly_cost=166.40,
        ),
    ]

    # RDS Instances
    snapshot.rds_instances = [
        RDSInstance(
            db_instance_id="acmecorp-prod-postgres-main",
            db_instance_class="db.r5.2xlarge",
            engine="postgres",
            engine_version="15.4",
            status="available",
            region="us-east-1",
            multi_az=True,
            allocated_storage_gb=500,
            vpc_id="vpc-0a1b2c3d4e5f6001",
            publicly_accessible=False,
            encrypted=True,
            tags={
                "Name": "prod-postgres-main",
                "Environment": "production",
                "Team": "backend",
            },
            estimated_monthly_cost=1920.00,
        ),
        # Over-provisioned — avg 4% CPU
        RDSInstance(
            db_instance_id="acmecorp-analytics-postgres",
            db_instance_class="db.m5.2xlarge",
            engine="postgres",
            engine_version="14.9",
            status="available",
            region="us-east-1",
            multi_az=False,
            allocated_storage_gb=200,
            vpc_id="vpc-0a1b2c3d4e5f6001",
            publicly_accessible=False,
            encrypted=True,
            tags={
                "Name": "analytics-postgres",
                "Environment": "production",
                "Team": "data",
            },
            estimated_monthly_cost=684.00,
        ),
        RDSInstance(
            db_instance_id="acmecorp-dev-mysql",
            db_instance_class="db.t3.large",
            engine="mysql",
            engine_version="8.0.35",
            status="available",
            region="us-west-2",
            multi_az=False,
            allocated_storage_gb=100,
            vpc_id="vpc-0a1b2c3d4e5f6002",
            publicly_accessible=False,
            encrypted=False,  # SECURITY FINDING
            tags={
                "Name": "dev-mysql",
                "Environment": "development",
                "Team": "backend",
            },
            estimated_monthly_cost=136.00,
        ),
    ]

    # Lambda Functions
    snapshot.lambda_functions = [
        LambdaFunction(
            function_name="acmecorp-payment-processor",
            runtime="python3.12",
            memory_mb=512,
            timeout_seconds=30,
            last_modified="2026-03-15T14:22:00Z",
            code_size_bytes=3_847_291,
            region="us-east-1",
            vpc_config={"SubnetIds": ["subnet-0a1b2c3d001"], "SecurityGroupIds": ["sg-0a1b2c3d001"]},
            tags={"Team": "payments", "Environment": "production"},
            estimated_monthly_cost=12.40,
        ),
        LambdaFunction(
            function_name="acmecorp-email-sender",
            runtime="python3.12",
            memory_mb=256,
            timeout_seconds=60,
            last_modified="2026-01-20T09:11:00Z",
            code_size_bytes=1_224_888,
            region="us-east-1",
            vpc_config={},
            tags={"Team": "platform", "Environment": "production"},
            estimated_monthly_cost=4.80,
        ),
        LambdaFunction(
            function_name="acmecorp-report-generator",
            runtime="python3.11",
            memory_mb=3008,
            timeout_seconds=300,
            last_modified="2025-11-03T16:44:00Z",
            code_size_bytes=8_932_100,
            region="us-east-1",
            vpc_config={},
            tags={"Team": "data", "Environment": "production"},
            estimated_monthly_cost=38.20,
        ),
        LambdaFunction(
            function_name="acmecorp-webhook-handler",
            runtime="nodejs20.x",
            memory_mb=512,
            timeout_seconds=10,
            last_modified="2026-04-01T11:00:00Z",
            code_size_bytes=524_288,
            region="us-east-1",
            vpc_config={},
            tags={"Team": "integrations", "Environment": "production"},
            estimated_monthly_cost=6.20,
        ),
        LambdaFunction(
            function_name="acmecorp-data-sync-eu",
            runtime="python3.12",
            memory_mb=1024,
            timeout_seconds=120,
            last_modified="2026-02-14T08:30:00Z",
            code_size_bytes=2_048_576,
            region="eu-west-1",
            vpc_config={},
            tags={"Team": "data", "Environment": "production", "Region": "eu"},
            estimated_monthly_cost=18.60,
        ),
    ]

    # S3 Buckets
    snapshot.s3_buckets = [
        S3Bucket(
            name="acmecorp-prod-customer-data",
            region="us-east-1",
            creation_date=datetime.now(timezone.utc) - timedelta(days=1200),
            versioning="Enabled",
            encryption="aws:kms",
            public_access_blocked=True,
            tags={"Team": "platform", "Classification": "confidential"},
            size_gb=8_420.0,
            object_count=4_200_000,
            estimated_monthly_cost=193.66,
        ),
        S3Bucket(
            name="acmecorp-prod-assets",
            region="us-east-1",
            creation_date=datetime.now(timezone.utc) - timedelta(days=1100),
            versioning="Enabled",
            encryption="AES256",
            public_access_blocked=True,
            tags={"Team": "frontend"},
            size_gb=340.0,
            object_count=120_000,
            estimated_monthly_cost=7.82,
        ),
        S3Bucket(
            name="acmecorp-analytics-raw-logs",
            region="us-east-1",
            creation_date=datetime.now(timezone.utc) - timedelta(days=900),
            versioning="Disabled",
            encryption="AES256",
            public_access_blocked=True,
            tags={"Team": "data"},
            size_gb=22_100.0,
            object_count=890_000_000,
            estimated_monthly_cost=508.30,
        ),
        # SECURITY FINDING: public access not blocked
        S3Bucket(
            name="acmecorp-dev-scratch-bucket",
            region="us-east-1",
            creation_date=datetime.now(timezone.utc) - timedelta(days=200),
            versioning="Disabled",
            encryption=None,
            public_access_blocked=False,
            tags={},
            size_gb=12.0,
            object_count=8_400,
            estimated_monthly_cost=0.28,
        ),
        S3Bucket(
            name="acmecorp-backups-2024",
            region="us-west-2",
            creation_date=datetime.now(timezone.utc) - timedelta(days=480),
            versioning="Suspended",
            encryption="AES256",
            public_access_blocked=True,
            tags={"Team": "infra", "Retention": "12-months"},
            size_gb=5_600.0,
            object_count=2_100_000,
            estimated_monthly_cost=128.80,
        ),
    ]

    # EBS Volumes — including unattached ones
    snapshot.ebs_volumes = [
        EBSVolume(
            volume_id="vol-0a1b2c3d4e5f60001",
            volume_type="gp3",
            size_gb=500,
            state="in-use",
            region="us-east-1",
            az="us-east-1a",
            encrypted=True,
            attached_instance="i-0a1b2c3d4e5f60001",
            tags={"Name": "prod-api-server-01-root"},
            estimated_monthly_cost=40.00,
        ),
        EBSVolume(
            volume_id="vol-0deadbeef0000001",
            volume_type="gp2",
            size_gb=1000,
            state="available",
            region="us-east-1",
            az="us-east-1a",
            encrypted=False,
            attached_instance=None,
            tags={"Name": "old-data-migration-vol-DO-NOT-DELETE"},
            estimated_monthly_cost=100.00,
        ),
        EBSVolume(
            volume_id="vol-0deadbeef0000002",
            volume_type="gp2",
            size_gb=500,
            state="available",
            region="us-east-1",
            az="us-east-1b",
            encrypted=False,
            attached_instance=None,
            tags={"Name": "snapshot-restore-test-2025-06"},
            estimated_monthly_cost=50.00,
        ),
        EBSVolume(
            volume_id="vol-0deadbeef0000003",
            volume_type="gp2",
            size_gb=200,
            state="available",
            region="us-west-2",
            az="us-west-2a",
            encrypted=True,
            attached_instance=None,
            tags={},
            estimated_monthly_cost=20.00,
        ),
    ]

    # EKS Clusters
    snapshot.eks_clusters = [
        EKSCluster(
            cluster_name="acmecorp-prod-k8s",
            kubernetes_version="1.29",
            status="ACTIVE",
            region="us-east-1",
            endpoint="https://ABC123.gr7.us-east-1.eks.amazonaws.com",
            node_groups=[
                {"name": "general", "instance_types": ["m5.xlarge"], "desired_size": 6},
                {"name": "memory", "instance_types": ["r5.2xlarge"], "desired_size": 3},
            ],
            tags={"Team": "infra", "Environment": "production"},
            estimated_monthly_cost=2388.00,
        ),
        EKSCluster(
            cluster_name="acmecorp-staging-k8s",
            kubernetes_version="1.28",
            status="ACTIVE",
            region="us-west-2",
            endpoint="https://DEF456.gr7.us-west-2.eks.amazonaws.com",
            node_groups=[
                {"name": "default", "instance_types": ["t3.large"], "desired_size": 4},
            ],
            tags={"Team": "infra", "Environment": "staging"},
            estimated_monthly_cost=314.24,
        ),
    ]

    # ECS Clusters
    snapshot.ecs_clusters = [
        ECSCluster(
            cluster_name="acmecorp-workers",
            cluster_arn="arn:aws:ecs:us-east-1:123456789012:cluster/acmecorp-workers",
            status="ACTIVE",
            region="us-east-1",
            running_tasks=12,
            pending_tasks=0,
            active_services=4,
            tags={"Team": "data"},
            estimated_monthly_cost=0.0,
        ),
    ]

    # VPCs
    snapshot.vpcs = [
        VPC(
            vpc_id="vpc-0a1b2c3d4e5f6001",
            cidr_block="10.0.0.0/16",
            region="us-east-1",
            is_default=False,
            state="available",
            tags={"Name": "prod-vpc", "Environment": "production"},
            subnets=[
                {"subnet_id": "subnet-0a1b2c3d001", "cidr": "10.0.1.0/24", "az": "us-east-1a", "public": False},
                {"subnet_id": "subnet-0a1b2c3d002", "cidr": "10.0.2.0/24", "az": "us-east-1b", "public": False},
                {"subnet_id": "subnet-0a1b2c3d003", "cidr": "10.0.10.0/24", "az": "us-east-1a", "public": True},
                {"subnet_id": "subnet-0a1b2c3d004", "cidr": "10.0.11.0/24", "az": "us-east-1b", "public": True},
            ],
            internet_gateways=["igw-0a1b2c3d001"],
            nat_gateways=[
                {"id": "nat-0a1b2c3d001", "subnet_id": "subnet-0a1b2c3d003", "state": "available"},
                {"id": "nat-0a1b2c3d002", "subnet_id": "subnet-0a1b2c3d004", "state": "available"},
                {"id": "nat-0a1b2c3d003", "subnet_id": "subnet-0a1b2c3d003", "state": "available"},
                {"id": "nat-0a1b2c3d004", "subnet_id": "subnet-0a1b2c3d004", "state": "available"},
                {"id": "nat-0a1b2c3d005", "subnet_id": "subnet-0a1b2c3d003", "state": "available"},
            ],
            estimated_monthly_cost=164.25,
        ),
        VPC(
            vpc_id="vpc-0a1b2c3d4e5f6002",
            cidr_block="10.1.0.0/16",
            region="us-west-2",
            is_default=False,
            state="available",
            tags={"Name": "staging-vpc", "Environment": "staging"},
            subnets=[
                {"subnet_id": "subnet-0a1b2c3d010", "cidr": "10.1.1.0/24", "az": "us-west-2a", "public": False},
                {"subnet_id": "subnet-0a1b2c3d011", "cidr": "10.1.2.0/24", "az": "us-west-2b", "public": False},
            ],
            internet_gateways=["igw-0a1b2c3d002"],
            nat_gateways=[
                {"id": "nat-0a1b2c3d010", "subnet_id": "subnet-0a1b2c3d010", "state": "available"},
            ],
            estimated_monthly_cost=32.85,
        ),
    ]

    # Elastic IPs
    snapshot.elastic_ips = [
        ElasticIP(
            allocation_id="eipalloc-0a1b2c3d001",
            public_ip="54.204.33.102",
            region="us-east-1",
            associated_instance="i-0deadbeef0000002",
            is_idle=False,
            estimated_monthly_cost=0.0,
        ),
        ElasticIP(
            allocation_id="eipalloc-0deadbeef001",
            public_ip="52.1.44.200",
            region="us-east-1",
            associated_instance=None,
            is_idle=True,
            estimated_monthly_cost=3.60,
        ),
        ElasticIP(
            allocation_id="eipalloc-0deadbeef002",
            public_ip="34.207.111.88",
            region="us-east-1",
            associated_instance=None,
            is_idle=True,
            estimated_monthly_cost=3.60,
        ),
        ElasticIP(
            allocation_id="eipalloc-0deadbeef003",
            public_ip="18.206.44.175",
            region="us-west-2",
            associated_instance=None,
            is_idle=True,
            estimated_monthly_cost=3.60,
        ),
    ]

    # ElastiCache
    snapshot.elasticache_clusters = [
        ElastiCacheCluster(
            cluster_id="acmecorp-prod-redis",
            engine="redis",
            engine_version="7.1.0",
            node_type="cache.r5.large",
            num_nodes=3,
            status="available",
            region="us-east-1",
            encrypted=True,
            tags={"Team": "backend", "Environment": "production"},
            estimated_monthly_cost=369.30,
        ),
        ElastiCacheCluster(
            cluster_id="acmecorp-sessions-redis",
            engine="redis",
            engine_version="7.0.7",
            node_type="cache.m5.large",
            num_nodes=2,
            status="available",
            region="us-east-1",
            encrypted=True,
            tags={"Team": "backend"},
            estimated_monthly_cost=185.60,
        ),
    ]

    return snapshot


def _make_cost_report(snapshot: InfrastructureSnapshot) -> CostReport:
    waste_items = [
        WasteItem(
            category="Idle EC2 Instance",
            resource_id="i-0deadbeef0000001",
            resource_type="EC2 Instance",
            region="us-east-1",
            estimated_monthly_waste=384.00,
            description=(
                "i-0deadbeef0000001 (m5.2xlarge, 'old-etl-worker-migration-TEMP') "
                "has had avg CPU 0.3% / max CPU 1.1% over 14 days. "
                "This appears to be a zombie instance from a data migration completed 8 months ago."
            ),
            recommendation=(
                "Terminate this instance immediately. Verify no critical processes "
                "depend on it (check CloudWatch for recent connections). "
                "AWS CLI: aws ec2 terminate-instances --instance-ids i-0deadbeef0000001"
            ),
            severity="critical",
            tags={"Name": "old-etl-worker-migration-TEMP", "Team": "data"},
        ),
        WasteItem(
            category="Idle EC2 Instance",
            resource_id="i-0deadbeef0000002",
            resource_type="EC2 Instance",
            region="us-east-1",
            estimated_monthly_waste=192.00,
            description=(
                "i-0deadbeef0000002 (m5.xlarge, 'dev-bastion-unused') has had "
                "avg CPU 0.1% / max CPU 0.4% over 14 days. "
                "Running for 611 days with public IP exposed. No SSH sessions in 90 days."
            ),
            recommendation=(
                "Stop or terminate. For bastion access, replace with AWS Systems Manager "
                "Session Manager — eliminates the bastion instance entirely at zero cost "
                "while improving security (no port 22 exposure)."
            ),
            severity="critical",
            tags={"Name": "dev-bastion-unused", "Team": "infra"},
        ),
        WasteItem(
            category="Over-Provisioned RDS",
            resource_id="acmecorp-analytics-postgres",
            resource_type="RDS Instance",
            region="us-east-1",
            estimated_monthly_waste=307.80,
            description=(
                "acmecorp-analytics-postgres (db.m5.2xlarge, PostgreSQL 14.9) "
                "shows avg CPU 4.2% / max CPU 11.8% over 14 days. "
                "Instance is 87% underutilized with $684/mo cost."
            ),
            recommendation=(
                "Downsize to db.m5.large ($171/mo). This reduces cost by 75% while "
                "providing CPU headroom for current workload. "
                "Schedule maintenance window: aws rds modify-db-instance "
                "--db-instance-identifier acmecorp-analytics-postgres "
                "--db-instance-class db.m5.large --apply-immediately false"
            ),
            severity="high",
            tags={"Team": "data", "Environment": "production"},
        ),
        WasteItem(
            category="Unattached EBS Volume",
            resource_id="vol-0deadbeef0000001",
            resource_type="EBS Volume",
            region="us-east-1",
            estimated_monthly_waste=100.00,
            description=(
                "vol-0deadbeef0000001 (1,000 GB gp2) tagged 'old-data-migration-vol-DO-NOT-DELETE' "
                "is not attached to any instance. This volume has been orphaned for at least 180 days."
            ),
            recommendation=(
                "Create a final snapshot (cost: ~$50/mo vs $100/mo for the volume), "
                "then delete the volume. "
                "aws ec2 create-snapshot --volume-id vol-0deadbeef0000001 --description 'final-archive-$(date +%Y%m%d)' "
                "&& aws ec2 delete-volume --volume-id vol-0deadbeef0000001"
            ),
            severity="high",
            tags={"Name": "old-data-migration-vol-DO-NOT-DELETE"},
        ),
        WasteItem(
            category="Unattached EBS Volume",
            resource_id="vol-0deadbeef0000002",
            resource_type="EBS Volume",
            region="us-east-1",
            estimated_monthly_waste=50.00,
            description=(
                "vol-0deadbeef0000002 (500 GB gp2) tagged 'snapshot-restore-test-2025-06' "
                "is not attached. Appears to be a temporary restore from June 2025 "
                "that was never cleaned up."
            ),
            recommendation=(
                "Delete this volume — it appears to be a test restore. "
                "aws ec2 delete-volume --volume-id vol-0deadbeef0000002"
            ),
            severity="high",
        ),
        WasteItem(
            category="Unattached EBS Volume",
            resource_id="vol-0deadbeef0000003",
            resource_type="EBS Volume",
            region="us-west-2",
            estimated_monthly_waste=20.00,
            description=(
                "vol-0deadbeef0000003 (200 GB gp2) in us-west-2 has no instance "
                "attachment and no Name tag. Created during staging environment teardown "
                "that was never fully completed."
            ),
            recommendation="Delete this volume. aws ec2 delete-volume --volume-id vol-0deadbeef0000003",
            severity="medium",
        ),
        WasteItem(
            category="NAT Gateway Overuse",
            resource_id="vpc-0a1b2c3d4e5f6001",
            resource_type="VPC",
            region="us-east-1",
            estimated_monthly_waste=164.25,
            description=(
                "prod-vpc has 5 NAT Gateways (base cost: $164/mo before data charges). "
                "S3 and DynamoDB traffic is likely flowing through NAT Gateways "
                "at $0.045/GB, adding hundreds per month in data processing fees."
            ),
            recommendation=(
                "Consolidate to 2 NAT Gateways (one per AZ for HA). "
                "Add VPC Gateway Endpoints for S3 and DynamoDB — these are free "
                "and eliminate all NAT Gateway charges for those services. "
                "Estimated additional savings from VPC endpoints: $200-800/mo "
                "depending on S3/DynamoDB data volume."
            ),
            severity="high",
            tags={"Name": "prod-vpc"},
        ),
        WasteItem(
            category="Idle Elastic IP",
            resource_id="eipalloc-0deadbeef001",
            resource_type="Elastic IP",
            region="us-east-1",
            estimated_monthly_waste=3.60,
            description="Elastic IP 52.1.44.200 is not associated with any running instance.",
            recommendation="aws ec2 release-address --allocation-id eipalloc-0deadbeef001",
            severity="low",
        ),
        WasteItem(
            category="Idle Elastic IP",
            resource_id="eipalloc-0deadbeef002",
            resource_type="Elastic IP",
            region="us-east-1",
            estimated_monthly_waste=3.60,
            description="Elastic IP 34.207.111.88 is not associated with any running instance.",
            recommendation="aws ec2 release-address --allocation-id eipalloc-0deadbeef002",
            severity="low",
        ),
        WasteItem(
            category="Idle Elastic IP",
            resource_id="eipalloc-0deadbeef003",
            resource_type="Elastic IP",
            region="us-west-2",
            estimated_monthly_waste=3.60,
            description="Elastic IP 18.206.44.175 in us-west-2 is not associated with any running instance.",
            recommendation="aws ec2 release-address --allocation-id eipalloc-0deadbeef003",
            severity="low",
        ),
        WasteItem(
            category="Old EBS Snapshots",
            resource_id="us-east-1/snapshots",
            resource_type="EBS Snapshots",
            region="us-east-1",
            estimated_monthly_waste=284.00,
            description=(
                "127 EBS snapshots older than 180 days in us-east-1 consuming "
                "5,680 GB of snapshot storage ($284/mo at $0.05/GB). "
                "No snapshot lifecycle policy is configured."
            ),
            recommendation=(
                "Implement AWS Data Lifecycle Manager policy: "
                "retain 7 daily + 4 weekly + 12 monthly snapshots, delete the rest. "
                "This is a 10-minute fix that will reduce snapshot storage by ~85%."
            ),
            severity="medium",
        ),
        WasteItem(
            category="gp2 EBS Volumes (Upgrade to gp3)",
            resource_id="us-east-1/ebs-gp2",
            resource_type="EBS Volumes",
            region="us-east-1",
            estimated_monthly_waste=210.00,
            description=(
                "14 gp2 EBS volumes totaling 2,100 GB found in us-east-1. "
                "gp3 provides same performance at 20% lower cost AND "
                "allows independent throughput/IOPS configuration without "
                "paying for extra IOPS you don't need."
            ),
            recommendation=(
                "Migrate all gp2 volumes to gp3. This is a live migration — "
                "no downtime required. "
                "aws ec2 modify-volume --volume-type gp3 --volume-id <vol-id>"
            ),
            severity="medium",
        ),
    ]

    rightsizing = [
        RightsizingRecommendation(
            instance_id="i-0a1b2c3d4e5f60020",
            instance_type="t3.2xlarge",
            region="us-west-2",
            current_monthly_cost=332.80,
            recommended_instance_type="t3.xlarge",
            recommended_monthly_cost=166.40,
            monthly_savings=166.40,
            annual_savings=1996.80,
            avg_cpu_utilization=8.3,
            max_cpu_utilization=22.1,
            confidence="HIGH",
            tags={"Name": "staging-app-01", "Environment": "staging"},
        ),
        RightsizingRecommendation(
            instance_id="i-0a1b2c3d4e5f60001",
            instance_type="m5.4xlarge",
            region="us-east-1",
            current_monthly_cost=768.00,
            recommended_instance_type="m5.2xlarge",
            recommended_monthly_cost=384.00,
            monthly_savings=384.00,
            annual_savings=4608.00,
            avg_cpu_utilization=18.4,
            max_cpu_utilization=34.2,
            confidence="MEDIUM",
            tags={"Name": "prod-api-server-01", "Environment": "production"},
        ),
        RightsizingRecommendation(
            instance_id="i-0a1b2c3d4e5f60002",
            instance_type="m5.4xlarge",
            region="us-east-1",
            current_monthly_cost=768.00,
            recommended_instance_type="m5.2xlarge",
            recommended_monthly_cost=384.00,
            monthly_savings=384.00,
            annual_savings=4608.00,
            avg_cpu_utilization=19.1,
            max_cpu_utilization=38.7,
            confidence="MEDIUM",
            tags={"Name": "prod-api-server-02", "Environment": "production"},
        ),
        RightsizingRecommendation(
            instance_id="i-0a1b2c3d4e5f60030",
            instance_type="t3.xlarge",
            region="eu-west-1",
            current_monthly_cost=166.40,
            recommended_instance_type="t3.large",
            recommended_monthly_cost=83.20,
            monthly_savings=83.20,
            annual_savings=998.40,
            avg_cpu_utilization=11.2,
            max_cpu_utilization=28.5,
            confidence="HIGH",
            tags={"Name": "eu-prod-app-01"},
        ),
    ]

    shadow_it = [
        ShadowITItem(
            resource_id="i-0deadbeef0000001",
            resource_type="EC2 Instance",
            region="us-east-1",
            estimated_monthly_cost=384.00,
            description="i-0deadbeef0000001 (m5.2xlarge) exists in AWS but has no corresponding resource in Terraform state. This is unmanaged infrastructure.",
        ),
        ShadowITItem(
            resource_id="i-0deadbeef0000002",
            resource_type="EC2 Instance",
            region="us-east-1",
            estimated_monthly_cost=192.00,
            description="i-0deadbeef0000002 (m5.xlarge) exists in AWS but not in Terraform state.",
        ),
        ShadowITItem(
            resource_id="acmecorp-dev-mysql",
            resource_type="RDS Instance",
            region="us-west-2",
            estimated_monthly_cost=136.00,
            description="RDS MySQL dev-mysql not tracked in Terraform state. Appears to have been created manually in the console.",
        ),
    ]

    top_drivers = [
        CostDriverEntry("Amazon Elastic Compute Cloud", 12_840.00, 28.4, 3.2),
        CostDriverEntry("Amazon Relational Database Service", 8_924.00, 19.7, -1.1),
        CostDriverEntry("Amazon Elastic Kubernetes Service", 4_184.00, 9.2, 12.4),
        CostDriverEntry("Amazon Simple Storage Service", 3_642.00, 8.1, 5.8),
        CostDriverEntry("Amazon ElastiCache", 1_848.00, 4.1, 0.0),
        CostDriverEntry("AWS Lambda", 1_124.00, 2.5, -8.2),
        CostDriverEntry("Amazon CloudFront", 984.00, 2.2, 14.1),
        CostDriverEntry("Amazon VPC (NAT Gateways)", 876.00, 1.9, 2.3),
        CostDriverEntry("Amazon DynamoDB", 742.00, 1.6, -3.4),
        CostDriverEntry("AWS Data Transfer", 680.00, 1.5, 8.7),
    ]

    total_waste = sum(w.estimated_monthly_waste for w in waste_items)
    total_rs = sum(r.monthly_savings for r in rightsizing)

    return CostReport(
        account_id=ACCOUNT_ID,
        report_date=date.today(),
        analysis_period_days=90,
        monthly_avg_cost=45_200.00,
        top_cost_drivers=top_drivers,
        waste_items=waste_items,
        rightsizing_recommendations=rightsizing,
        shadow_it_items=shadow_it,
        total_identified_waste=total_waste,
        total_rightsizing_savings=total_rs,
    )


# ---------------------------------------------------------------------------
# Demo scenes
# ---------------------------------------------------------------------------


def _scene_intro() -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]CloudIQ[/bold cyan] — AI-Powered Cloud Infrastructure Intelligence\n"
            "[dim]Accenture charges $150K+ for what this does in 60 seconds.[/dim]",
            border_style="cyan",
            padding=(1, 4),
        )
    )
    console.print()
    time.sleep(0.5)


def _scene_discovery() -> None:
    console.print(Rule("[bold blue]Phase 1: Infrastructure Discovery[/bold blue]"))
    console.print()

    services = [
        ("EC2 Instances", "us-east-1", 7, "7 instances across 3 environments"),
        ("RDS Instances", "us-east-1", 3, "3 databases — postgres, mysql"),
        ("Lambda Functions", "us-east-1", 5, "5 functions — python3.12, nodejs20.x"),
        ("S3 Buckets", "global", 5, "5 buckets — 36.5 TB total"),
        ("EBS Volumes", "us-east-1", 4, "4 volumes — 1 unattached (warning)"),
        ("EKS Clusters", "us-east-1", 2, "prod k8s 1.29, staging k8s 1.28"),
        ("ElastiCache", "us-east-1", 2, "2 Redis clusters — 5 nodes total"),
        ("VPCs", "all regions", 2, "2 VPCs — 5 NAT Gateways in prod (flag)"),
        ("Elastic IPs", "all regions", 4, "4 EIPs — 3 idle (waste detected)"),
        ("IAM", "global", 1, "12 users — 3 without MFA"),
        ("CloudFront", "global", 2, "2 distributions — active"),
        ("DynamoDB", "us-east-1", 4, "4 tables — provisioned + on-demand"),
    ]

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description:<30}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[detail]}[/dim]"),
        console=console,
    ) as progress:
        for service, region, count, detail in services:
            task = progress.add_task(
                f"{service} ({region})",
                total=count,
                detail="scanning...",
            )
            for _ in range(count):
                time.sleep(random.uniform(0.02, 0.06))
                progress.advance(task)
            progress.update(task, detail=detail)

    console.print()
    console.print(
        "[bold green]Discovery complete.[/bold green] "
        "[dim]39 resources across 3 regions in 4.2 seconds.[/dim]"
    )
    console.print()
    time.sleep(0.5)


def _scene_cost_analysis(report: CostReport) -> None:
    console.print(Rule("[bold yellow]Phase 2: Cost Intelligence[/bold yellow]"))
    console.print()

    table = Table(
        title="Top Cost Drivers (90-day avg)",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        title_style="bold yellow",
    )
    table.add_column("Service", style="cyan", min_width=40)
    table.add_column("Monthly Avg", justify="right", style="bold white", min_width=14)
    table.add_column("% of Total", justify="right", min_width=10)
    table.add_column("Trend", justify="center", min_width=8)
    table.add_column("Spend Bar", min_width=22)

    max_cost = max(d.monthly_cost for d in report.top_cost_drivers)
    for driver in report.top_cost_drivers:
        bar_width = int((driver.monthly_cost / max_cost) * 20)
        bar = "█" * bar_width + "░" * (20 - bar_width)
        trend_str = (
            f"[green]+{driver.month_over_month_change:.1f}%[/green]"
            if driver.month_over_month_change > 5
            else f"[red]{driver.month_over_month_change:.1f}%[/red]"
            if driver.month_over_month_change < -5
            else f"[dim]{driver.month_over_month_change:+.1f}%[/dim]"
        )
        color = (
            "red"
            if driver.percentage_of_total > 25
            else "yellow"
            if driver.percentage_of_total > 10
            else "green"
        )
        table.add_row(
            driver.service,
            f"${driver.monthly_cost:,.0f}",
            f"{driver.percentage_of_total:.1f}%",
            trend_str,
            f"[{color}]{bar}[/]",
        )

    console.print(table)
    console.print()

    console.print(
        Panel(
            f"[bold white]Monthly run rate:[/bold white] "
            f"[bold yellow]${report.monthly_avg_cost:,.0f}[/bold yellow]   "
            f"[bold white]Annual projection:[/bold white] "
            f"[bold yellow]${report.monthly_avg_cost * 12:,.0f}[/bold yellow]",
            border_style="yellow",
            title="Billing Overview",
        )
    )
    console.print()
    time.sleep(0.5)


def _scene_waste_detection(report: CostReport) -> None:
    console.print(Rule("[bold red]Phase 3: Waste Detection[/bold red]"))
    console.print()

    table = Table(
        title=f"Identified Waste — ${report.total_identified_waste:,.0f}/mo  (${report.total_identified_waste * 12:,.0f}/yr)",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold red",
        title_style="bold red",
    )
    table.add_column("Severity", min_width=10)
    table.add_column("Category", style="cyan", min_width=28)
    table.add_column("Resource", style="dim white", min_width=38)
    table.add_column("Region", min_width=12)
    table.add_column("Waste/mo", justify="right", style="bold red", min_width=12)

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for item in sorted(report.waste_items, key=lambda w: severity_order.get(w.severity, 9)):
        sev_colors = {
            "critical": "[bold red]CRITICAL[/bold red]",
            "high": "[red]HIGH[/red]",
            "medium": "[yellow]MEDIUM[/yellow]",
            "low": "[green]LOW[/green]",
        }
        table.add_row(
            sev_colors.get(item.severity, item.severity),
            item.category,
            item.resource_id,
            item.region,
            f"${item.estimated_monthly_waste:,.2f}",
        )

    console.print(table)
    console.print()

    # Highlight the two worst findings
    critical_items = [w for w in report.waste_items if w.severity == "critical"]
    for item in critical_items[:2]:
        console.print(
            Panel(
                f"[bold red]CRITICAL:[/bold red] {item.description}\n\n"
                f"[bold green]Recommendation:[/bold green] {item.recommendation}",
                title=f"[bold red]{item.category} — {item.resource_id}[/bold red]",
                border_style="red",
                padding=(0, 1),
            )
        )
        console.print()
    time.sleep(0.5)


def _scene_rightsizing(report: CostReport) -> None:
    console.print(Rule("[bold bright_green]Phase 4: Rightsizing[/bold bright_green]"))
    console.print()

    table = Table(
        title=f"Rightsizing Opportunities — ${report.total_rightsizing_savings:,.0f}/mo  (${report.total_rightsizing_savings * 12:,.0f}/yr)",
        box=box.ROUNDED,
        header_style="bold bright_green",
        title_style="bold bright_green",
    )
    table.add_column("Instance ID", style="cyan", min_width=22)
    table.add_column("Current", min_width=14)
    table.add_column("Recommended", style="green", min_width=14)
    table.add_column("Avg CPU", justify="right", min_width=9)
    table.add_column("Max CPU", justify="right", min_width=9)
    table.add_column("Savings/mo", justify="right", style="bold green", min_width=12)
    table.add_column("Confidence", min_width=12)

    for rec in report.rightsizing_recommendations:
        conf_style = {
            "HIGH": "[bold green]HIGH[/bold green]",
            "MEDIUM": "[yellow]MEDIUM[/yellow]",
            "LOW": "[dim]LOW[/dim]",
        }.get(rec.confidence, rec.confidence)
        table.add_row(
            rec.instance_id,
            rec.instance_type,
            rec.recommended_instance_type,
            f"{rec.avg_cpu_utilization:.1f}%",
            f"{rec.max_cpu_utilization:.1f}%",
            f"${rec.monthly_savings:,.2f}",
            conf_style,
        )

    console.print(table)
    console.print()
    time.sleep(0.5)


def _scene_shadow_it(report: CostReport) -> None:
    console.print(Rule("[bold magenta]Phase 5: Shadow IT Detection[/bold magenta]"))
    console.print()

    table = Table(
        title=f"Resources Not in Terraform State — {len(report.shadow_it_items)} items",
        box=box.ROUNDED,
        header_style="bold magenta",
        title_style="bold magenta",
    )
    table.add_column("Resource Type", style="cyan", min_width=16)
    table.add_column("Resource ID", style="dim white", min_width=35)
    table.add_column("Region", min_width=12)
    table.add_column("Monthly Cost", justify="right", style="yellow", min_width=13)
    table.add_column("Issue", min_width=55)

    for item in report.shadow_it_items:
        table.add_row(
            item.resource_type,
            item.resource_id,
            item.region,
            f"${item.estimated_monthly_cost:,.2f}",
            item.description[:55] + "..." if len(item.description) > 55 else item.description,
        )

    console.print(table)
    console.print()
    console.print(
        "[bold yellow]Shadow IT creates compliance risk, security blind spots, "
        "and untracked costs. Import these resources into Terraform or terminate them.[/bold yellow]"
    )
    console.print()
    time.sleep(0.5)


def _scene_nl_query(snapshot: InfrastructureSnapshot, report: CostReport) -> None:
    console.print(Rule("[bold cyan]Phase 6: Natural Language Queries[/bold cyan]"))
    console.print()
    console.print(
        "[dim]Note: Live queries require ANTHROPIC_API_KEY. Showing representative answers.[/dim]"
    )
    console.print()

    qa_pairs = [
        (
            "Why did my AWS bill increase 12% last month?",
            (
                "Your bill increased primarily due to two factors:\n\n"
                "1. EKS Costs (+12.4%): acmecorp-prod-k8s added a third r5.2xlarge node "
                "to the 'memory' node group on March 8th, adding $504/mo. This coincides "
                "with the ML inference service deployment.\n\n"
                "2. CloudFront (+14.1%): Data transfer through your two distributions "
                "increased by 2.1 TB, suggesting a traffic spike likely related to the "
                "product launch on March 15th.\n\n"
                "Offset: Lambda costs decreased 8.2%, likely from the optimization "
                "applied to the report-generator function."
            ),
        ),
        (
            "Which instances should I turn off right now to save money?",
            (
                "Stop these two instances immediately — zero risk, $576/mo savings:\n\n"
                "1. i-0deadbeef0000001 (m5.2xlarge, 'old-etl-worker-migration-TEMP') "
                "— avg CPU 0.3% for 14 days. This is a migration zombie from August 2025. "
                "Terminating saves $384/mo.\n\n"
                "2. i-0deadbeef0000002 (m5.xlarge, 'dev-bastion-unused') "
                "— avg CPU 0.1% for 14 days, with a public IP that's been live for 611 days. "
                "Terminating saves $192/mo. Replace with AWS Systems Manager Session Manager "
                "for zero-cost secure access.\n\n"
                "Combined annual savings: $6,912."
            ),
        ),
        (
            "What are my biggest security risks right now?",
            (
                "Three issues require immediate attention:\n\n"
                "CRITICAL: acmecorp-dev-mysql (RDS) has StorageEncrypted=false. "
                "This database contains development data and is unencrypted at rest. "
                "Enable encryption during the next maintenance window.\n\n"
                "HIGH: S3 bucket 'acmecorp-dev-scratch-bucket' has public access block "
                "disabled. Check for any sensitive files immediately. Enable the block: "
                "aws s3api put-public-access-block --bucket acmecorp-dev-scratch-bucket "
                "--public-access-block-configuration BlockPublicAcls=true,...\n\n"
                "MEDIUM: 3 of 12 IAM users have MFA disabled. In a production AWS "
                "account, all human users must have MFA — especially those with console access."
            ),
        ),
        (
            "How much could I save per year if I fix everything CloudIQ found?",
            (
                f"Total annual savings opportunity: $566,640\n\n"
                f"Breakdown:\n"
                f"  Waste elimination:       ${report.total_identified_waste * 12:,.0f}/yr\n"
                f"  Rightsizing:             ${report.total_rightsizing_savings * 12:,.0f}/yr\n"
                f"  VPC endpoint savings:    $3,600-9,600/yr (estimated from S3/DynamoDB traffic)\n"
                f"  gp2 → gp3 migration:    $2,520/yr\n\n"
                f"At AcmeCorp's current growth rate, fixing these issues now saves "
                f"more than the cost of a junior engineer's salary. "
                f"The idle EC2 instances and unattached EBS volumes can be addressed "
                f"in under 30 minutes with zero downtime risk."
            ),
        ),
    ]

    for question, answer in qa_pairs:
        console.print(
            Panel(
                f"[bold cyan]Q:[/bold cyan] {question}",
                border_style="cyan",
                padding=(0, 1),
            )
        )
        console.print(
            Panel(
                f"[bold green]A:[/bold green] {answer}",
                border_style="green",
                padding=(0, 1),
            )
        )
        console.print()
        time.sleep(0.3)


def _scene_terraform(snapshot: InfrastructureSnapshot) -> None:
    console.print(Rule("[bold white]Phase 7: Terraform Generation[/bold white]"))
    console.print()

    sample_tf = '''\
[bold white]# CloudIQ Generated Terraform — Account 123456789012[/bold white]
[bold white]# Scanned at: 2026-04-11T14:30:00+00:00[/bold white]
[bold white]# Regions: us-east-1, us-west-2, eu-west-1[/bold white]

[cyan]resource[/cyan] [green]"aws_instance"[/green] [yellow]"prod_api_server_01"[/yellow] {
  ami           = data.aws_ami.prod_api_server_01.id
  instance_type = [green]"m5.2xlarge"[/green]  [dim]# CloudIQ: downsized from m5.4xlarge (18% avg CPU)[/dim]
  subnet_id     = [green]"subnet-0a1b2c3d001"[/green]

  [dim]# Security: IMDSv2 required to prevent SSRF credential theft[/dim]
  metadata_options {
    http_endpoint               = [green]"enabled"[/green]
    http_tokens                 = [green]"required"[/green]  [dim]# Mandatory — blocks IMDS v1 SSRF attacks[/dim]
    http_put_response_hop_limit = [cyan]1[/cyan]
  }

  root_block_device {
    volume_type           = [green]"gp3"[/green]  [dim]# gp3: 20% cheaper than gp2, same performance[/dim]
    encrypted             = [cyan]true[/cyan]
    delete_on_termination = [cyan]true[/cyan]
  }

  tags = merge(var.common_tags, {
    Name        = [green]"prod-api-server-01"[/green]
    Environment = [green]"production"[/green]
    Team        = [green]"backend"[/green]
    ManagedBy   = [green]"terraform"[/green]
  })
}

[cyan]resource[/cyan] [green]"aws_db_instance"[/green] [yellow]"acmecorp_analytics_postgres"[/yellow] {
  identifier     = [green]"acmecorp-analytics-postgres"[/green]
  engine         = [green]"postgres"[/green]
  engine_version = [green]"14.9"[/green]
  instance_class = [green]"db.m5.large"[/green]  [dim]# CloudIQ: downsized from db.m5.2xlarge (4% avg CPU)[/dim]

  allocated_storage     = [cyan]200[/cyan]
  max_allocated_storage = [cyan]400[/cyan]
  storage_type          = [green]"gp3"[/green]
  storage_encrypted     = [cyan]true[/cyan]

  [dim]# Security: never expose RDS to the internet[/dim]
  publicly_accessible    = [cyan]false[/cyan]
  deletion_protection    = [cyan]true[/cyan]  [dim]# Prevents accidental drops in production[/dim]
  skip_final_snapshot    = [cyan]false[/cyan]
  backup_retention_period = [cyan]7[/cyan]

  tags = merge(var.common_tags, {
    Name = [green]"analytics-postgres"[/green]
    Team = [green]"data"[/green]
  })
}'''

    console.print(
        Panel(
            sample_tf,
            title="[bold white]Generated: modules/ec2/main.tf + modules/rds/main.tf[/bold white]",
            border_style="white",
            padding=(0, 1),
        )
    )
    console.print()
    console.print(
        "[dim]Full Terraform output: terraform/ (7 modules, 39 resources, security best practices)[/dim]"
    )
    console.print()
    time.sleep(0.5)


def _scene_summary(snapshot: InfrastructureSnapshot, report: CostReport) -> None:
    console.print(Rule("[bold bright_green]Summary[/bold bright_green]"))
    console.print()

    total_waste = report.total_identified_waste
    total_rs = report.total_rightsizing_savings
    total_opp = total_waste + total_rs

    kpi_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    kpi_table.add_column("Metric", style="dim", min_width=35)
    kpi_table.add_column("Value", style="bold", min_width=18)

    kpi_table.add_row("Account ID", f"[cyan]{snapshot.account_id}[/cyan]")
    kpi_table.add_row("Total Resources Discovered", f"[white]{sum(snapshot.resource_counts.values())}[/white]")
    kpi_table.add_row("Regions Scanned", f"[white]{len(snapshot.regions)}[/white]")
    kpi_table.add_row("Current Monthly Spend", f"[yellow]${report.monthly_avg_cost:,.0f}[/yellow]")
    kpi_table.add_row("Waste Items Detected", f"[red]{len(report.waste_items)}[/red]")
    kpi_table.add_row("Identified Waste / Month", f"[red]${total_waste:,.0f}[/red]")
    kpi_table.add_row("Rightsizing Savings / Month", f"[green]${total_rs:,.0f}[/green]")
    kpi_table.add_row(
        "Total Savings Opportunity / Month",
        f"[bold bright_green]${total_opp:,.0f}[/bold bright_green]",
    )
    kpi_table.add_row(
        "Total Savings Opportunity / Year",
        f"[bold bright_green]${total_opp * 12:,.0f}[/bold bright_green]",
    )
    kpi_table.add_row(
        "Pct of Monthly Bill Recoverable",
        f"[bold bright_green]{(total_opp / report.monthly_avg_cost * 100):.1f}%[/bold bright_green]",
    )
    kpi_table.add_row("Shadow IT Items", f"[magenta]{len(report.shadow_it_items)}[/magenta]")
    kpi_table.add_row("Accenture Quote for Same Work", "[red]$150,000 – $500,000[/red]")
    kpi_table.add_row("Time to First Insight", "[bold bright_green]60 seconds[/bold bright_green]")

    console.print(
        Panel(
            kpi_table,
            title="[bold bright_green]AcmeCorp Analysis Complete[/bold bright_green]",
            border_style="bright_green",
            padding=(0, 1),
        )
    )
    console.print()
    console.print(
        Panel(
            "[bold cyan]Next Steps:[/bold cyan]\n\n"
            "  1. [bold white]cloudiq --terraform[/bold white]   — Generate IaC for all discovered resources\n"
            "  2. [bold white]cloudiq --query[/bold white]       — Interactive natural language interface\n"
            "  3. [bold white]cloudiq --report report.html[/bold white] — Export stakeholder HTML report\n"
            "  4. [bold white]cloudiq --watch[/bold white]       — Continuous monitoring with drift alerts\n",
            border_style="cyan",
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_demo() -> None:
    snapshot = _make_snapshot()
    report = _make_cost_report(snapshot)

    _scene_intro()
    _scene_discovery()
    _scene_cost_analysis(report)
    _scene_waste_detection(report)
    _scene_rightsizing(report)
    _scene_shadow_it(report)
    _scene_nl_query(snapshot, report)
    _scene_terraform(snapshot)
    _scene_summary(snapshot, report)


if __name__ == "__main__":
    run_demo()
