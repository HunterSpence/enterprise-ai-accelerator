"""
CloudIQ V2 — Shared mock data for AcmeCorp ($24M ARR SaaS).

Used by the API, demo, and tests. All numbers are calibrated to represent
a realistic mid-size company running a production EKS platform on AWS with
secondary workloads in Azure and GCP.

Monthly AWS spend: ~$154,200
Identified waste: $47,800 (31%)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from cloud_iq.cost_analyzer import (
    CostDriverEntry,
    CostReport,
    RightsizingRecommendation,
    WasteItem,
)
from cloud_iq.models import Severity, WasteRecommendation, CloudProvider
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

_NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Infrastructure snapshot
# ---------------------------------------------------------------------------

def _build_snapshot() -> InfrastructureSnapshot:
    snap = InfrastructureSnapshot(
        account_id="123456789012",
        regions=["us-east-1", "us-west-2", "eu-west-1"],
        scanned_at=_NOW,
    )

    snap.ec2_instances = [
        EC2Instance(
            instance_id="i-0a1b2c3d4e5f60001",
            instance_type="m5.4xlarge",
            state="running",
            region="us-east-1",
            az="us-east-1a",
            platform="linux",
            launch_time=_NOW - timedelta(days=847),
            vpc_id="vpc-0a1b2c3d4e5f6001",
            subnet_id="subnet-0a1b2c3d001",
            public_ip=None,
            private_ip="10.0.1.10",
            security_groups=["sg-0a1b2c3d001"],
            tags={"Name": "prod-api-server-01", "Environment": "production", "Team": "backend", "CostCenter": "eng-001"},
            estimated_monthly_cost=768.00,
        ),
        EC2Instance(
            instance_id="i-0a1b2c3d4e5f60002",
            instance_type="m5.4xlarge",
            state="running",
            region="us-east-1",
            az="us-east-1b",
            platform="linux",
            launch_time=_NOW - timedelta(days=847),
            vpc_id="vpc-0a1b2c3d4e5f6001",
            subnet_id="subnet-0a1b2c3d002",
            public_ip=None,
            private_ip="10.0.1.11",
            security_groups=["sg-0a1b2c3d001"],
            tags={"Name": "prod-api-server-02", "Environment": "production", "Team": "backend", "CostCenter": "eng-001"},
            estimated_monthly_cost=768.00,
        ),
        EC2Instance(
            instance_id="i-0a1b2c3d4e5f60003",
            instance_type="m5.4xlarge",
            state="running",
            region="us-east-1",
            az="us-east-1c",
            platform="linux",
            launch_time=_NOW - timedelta(days=612),
            vpc_id="vpc-0a1b2c3d4e5f6001",
            subnet_id="subnet-0a1b2c3d003",
            public_ip=None,
            private_ip="10.0.1.12",
            security_groups=["sg-0a1b2c3d001"],
            tags={"Name": "prod-worker-01", "Environment": "production", "Team": "data-eng", "CostCenter": "eng-002"},
            estimated_monthly_cost=768.00,
        ),
        # Idle dev/zombie instances
        EC2Instance(
            instance_id="i-0dead0000000dead1",
            instance_type="m5.2xlarge",
            state="running",
            region="us-east-1",
            az="us-east-1a",
            platform="linux",
            launch_time=_NOW - timedelta(days=312),
            vpc_id="vpc-0a1b2c3d4e5f6001",
            subnet_id="subnet-0a1b2c3d001",
            public_ip=None,
            private_ip="10.0.2.40",
            security_groups=["sg-0a1b2c3d005"],
            tags={"Name": "data-science-sandbox-FORGOTTEN", "Environment": "dev", "Team": "ml", "CostCenter": "eng-003"},
            estimated_monthly_cost=384.00,
        ),
        EC2Instance(
            instance_id="i-0dead0000000dead2",
            instance_type="r5.4xlarge",
            state="running",
            region="us-west-2",
            az="us-west-2a",
            platform="linux",
            launch_time=_NOW - timedelta(days=189),
            vpc_id="vpc-0b2c3d4e5f600001",
            subnet_id="subnet-0b2c3d001",
            public_ip="35.165.12.88",
            private_ip="10.1.1.5",
            security_groups=["sg-0b2c3d001"],
            tags={"Name": "analytics-spike-server-DO-NOT-TERMINATE-MAYBE", "Environment": "production", "Team": "analytics", "CostCenter": "eng-004"},
            estimated_monthly_cost=1_008.00,
        ),
        EC2Instance(
            instance_id="i-0dev0000000000001",
            instance_type="t3.2xlarge",
            state="running",
            region="eu-west-1",
            az="eu-west-1a",
            platform="linux",
            launch_time=_NOW - timedelta(days=94),
            vpc_id="vpc-0c3d4e5f60000001",
            subnet_id="subnet-0c3d001",
            public_ip=None,
            private_ip="10.2.1.30",
            security_groups=["sg-0c3d001"],
            tags={"Name": "eu-dev-build-agent-03", "Environment": "dev", "Team": "devops", "CostCenter": "eng-001"},
            estimated_monthly_cost=333.00,
        ),
    ]

    snap.rds_instances = [
        RDSInstance(
            db_instance_id="prod-postgres-primary",
            db_instance_class="db.r5.2xlarge",
            engine="postgres",
            engine_version="15.4",
            status="available",
            region="us-east-1",
            multi_az=True,
            storage_type="gp3",
            allocated_storage_gb=500,
            encrypted=True,
            tags={"Environment": "production", "Team": "backend", "CostCenter": "eng-001"},
            estimated_monthly_cost=1_401.60,
        ),
        RDSInstance(
            db_instance_id="prod-analytics-dwh",
            db_instance_class="db.r5.4xlarge",
            engine="postgres",
            engine_version="15.4",
            status="available",
            region="us-east-1",
            multi_az=True,
            storage_type="gp3",
            allocated_storage_gb=2000,
            encrypted=True,
            tags={"Environment": "production", "Team": "data-eng", "CostCenter": "eng-002"},
            estimated_monthly_cost=2_940.00,
        ),
        RDSInstance(
            db_instance_id="staging-postgres-01",
            db_instance_class="db.m5.2xlarge",
            engine="postgres",
            engine_version="14.8",
            status="available",
            region="us-east-1",
            multi_az=False,
            storage_type="gp2",
            allocated_storage_gb=200,
            encrypted=True,
            tags={"Environment": "staging", "Team": "engineering", "CostCenter": "eng-001"},
            estimated_monthly_cost=499.20,
        ),
    ]

    snap.ebs_volumes = [
        EBSVolume(
            volume_id="vol-0orphan000000001",
            volume_type="gp2",
            size_gb=500,
            state="available",
            region="us-east-1",
            az="us-east-1a",
            attached_instance=None,
            encrypted=True,
            tags={"Name": "data-migration-temp-DO-NOT-DELETE"},
            estimated_monthly_cost=50.00,
        ),
        EBSVolume(
            volume_id="vol-0orphan000000002",
            volume_type="gp2",
            size_gb=1000,
            state="available",
            region="us-west-2",
            az="us-west-2a",
            attached_instance=None,
            encrypted=False,
            tags={"Name": "old-prod-backup-vol"},
            estimated_monthly_cost=100.00,
        ),
        EBSVolume(
            volume_id="vol-0orphan000000003",
            volume_type="gp3",
            size_gb=200,
            state="available",
            region="eu-west-1",
            az="eu-west-1b",
            attached_instance=None,
            encrypted=True,
            tags={},
            estimated_monthly_cost=16.00,
        ),
    ]

    snap.elastic_ips = [
        ElasticIP(
            allocation_id="eipalloc-0a1b2c0001",
            public_ip="52.90.100.1",
            is_idle=True,
            region="us-east-1",
            tags={"Name": "legacy-bastion-eip"},
            estimated_monthly_cost=3.60,
        ),
        ElasticIP(
            allocation_id="eipalloc-0a1b2c0002",
            public_ip="52.90.100.2",
            is_idle=True,
            region="us-east-1",
            tags={},
            estimated_monthly_cost=3.60,
        ),
    ]

    snap.eks_clusters = [
        EKSCluster(
            cluster_name="prod-eks-01",
            kubernetes_version="1.29",
            status="ACTIVE",
            region="us-east-1",
            node_groups=[
                {"name": "app-ng", "instance_type": "m5.xlarge", "desired_size": 12, "min_size": 3, "max_size": 20},
                {"name": "data-pipeline-ng", "instance_type": "m5.4xlarge", "desired_size": 6, "min_size": 2, "max_size": 12},
                {"name": "spot-ng", "instance_type": "m5.large", "desired_size": 8, "min_size": 0, "max_size": 40},
            ],
            tags={"Environment": "production", "ManagedBy": "terraform"},
            estimated_monthly_cost=18_600.00,
        )
    ]

    snap.s3_buckets = [
        S3Bucket(
            name="acmecorp-prod-assets",
            region="us-east-1",
            versioning="Enabled",
            encryption="aws:kms",
            public_access_blocked=True,
            tags={"Environment": "production"},
            estimated_monthly_cost=840.00,
        ),
        S3Bucket(
            name="acmecorp-prod-backups",
            region="us-east-1",
            versioning="Enabled",
            encryption="aws:kms",
            public_access_blocked=True,
            tags={"Environment": "production"},
            estimated_monthly_cost=1_200.00,
        ),
        S3Bucket(
            name="acmecorp-data-lake",
            region="us-east-1",
            versioning="Suspended",
            encryption="AES256",
            public_access_blocked=True,
            tags={"Environment": "production", "Team": "data-eng"},
            estimated_monthly_cost=4_800.00,
        ),
    ]

    snap.vpcs = [
        VPC(
            vpc_id="vpc-0a1b2c3d4e5f6001",
            cidr_block="10.0.0.0/16",
            region="us-east-1",
            nat_gateways=["nat-001", "nat-002", "nat-003", "nat-004", "nat-005"],
            subnets=[
                {"cidr": "10.0.1.0/24", "az": "us-east-1a", "public": False},
                {"cidr": "10.0.2.0/24", "az": "us-east-1b", "public": False},
                {"cidr": "10.0.3.0/24", "az": "us-east-1c", "public": False},
                {"cidr": "10.0.101.0/24", "az": "us-east-1a", "public": True},
                {"cidr": "10.0.102.0/24", "az": "us-east-1b", "public": True},
            ],
            tags={"Name": "prod-vpc-us-east-1", "Environment": "production"},
        )
    ]

    snap.lambda_functions = [
        LambdaFunction(
            function_name="data-ingestion-webhook",
            runtime="python3.12",
            memory_mb=512,
            timeout_seconds=30,
            region="us-east-1",
            tags={"Team": "data-eng"},
            estimated_monthly_cost=24.00,
        ),
        LambdaFunction(
            function_name="email-notification-sender",
            runtime="python3.12",
            memory_mb=256,
            timeout_seconds=10,
            region="us-east-1",
            tags={"Team": "backend"},
            estimated_monthly_cost=8.00,
        ),
    ]

    snap.elasticache_clusters = [
        ElastiCacheCluster(
            cluster_id="prod-redis-session",
            engine="redis",
            engine_version="7.0.12",
            node_type="cache.m5.large",
            num_nodes=3,
            region="us-east-1",
            tags={"Environment": "production", "Team": "backend"},
            estimated_monthly_cost=278.00,
        )
    ]

    snap.ecs_clusters = [
        ECSCluster(
            cluster_name="prod-ecs-fargate",
            region="us-east-1",
            running_tasks=42,
            tags={"Environment": "production"},
            estimated_monthly_cost=3_200.00,
        )
    ]

    snap.total_estimated_monthly_cost = 154_200.0
    snap.resource_counts = {
        "ec2": len(snap.ec2_instances),
        "rds": len(snap.rds_instances),
        "ebs": len(snap.ebs_volumes),
        "eip": len(snap.elastic_ips),
        "eks": len(snap.eks_clusters),
        "s3": len(snap.s3_buckets),
        "vpc": len(snap.vpcs),
        "lambda": len(snap.lambda_functions),
        "elasticache": len(snap.elasticache_clusters),
        "ecs": len(snap.ecs_clusters),
    }

    return snap


def _build_cost_report(snap: InfrastructureSnapshot) -> CostReport:
    waste_items = [
        WasteItem(
            category="NAT Gateway Overuse",
            resource_id="vpc-0a1b2c3d4e5f6001",
            resource_type="VPC",
            region="us-east-1",
            estimated_monthly_waste=16_060.00,
            description=(
                "VPC vpc-0a1b2c3d4e5f6001 has 5 NAT Gateways ($1,642/mo base) "
                "plus $14,418/mo in data processing charges. Traffic analysis shows "
                "3 of 5 gateways carry <2% of total throughput. VPC endpoints for "
                "S3 and DynamoDB would eliminate $11,200/mo in NAT processing fees."
            ),
            recommendation=(
                "1. Create VPC endpoints for S3 and DynamoDB — eliminates ~$11,200/mo in NAT processing. "
                "2. Consolidate from 5 NAT gateways to 2 (one per primary AZ) — saves $1,093/mo. "
                "3. Enable NAT gateway CloudWatch metrics to validate traffic distribution before change."
            ),
            severity="critical",
            tags={"Name": "prod-vpc-us-east-1", "Environment": "production"},
        ),
        WasteItem(
            category="Idle EC2 Instance",
            resource_id="i-0dead0000000dead2",
            resource_type="EC2 Instance",
            region="us-west-2",
            estimated_monthly_waste=1_008.00,
            description=(
                "r5.4xlarge instance i-0dead0000000dead2 (analytics-spike-server) "
                "has averaged 1.2% CPU and 3.4% memory over 14 days. "
                "No inbound connections in 47 days. Running since 2024-09-04."
            ),
            recommendation=(
                "Stop and schedule for termination after 72hr confirmation window. "
                "If periodic analytics jobs run here, migrate to a scheduled ECS Fargate task "
                "or EMR serverless — pays per-second vs $1,008/mo always-on."
            ),
            severity="critical",
            tags={"Name": "analytics-spike-server-DO-NOT-TERMINATE-MAYBE", "Environment": "production"},
        ),
        WasteItem(
            category="Over-Provisioned RDS",
            resource_id="prod-analytics-dwh",
            resource_type="RDS Instance",
            region="us-east-1",
            estimated_monthly_waste=8_820.00,
            description=(
                "prod-analytics-dwh (db.r5.4xlarge, $2,940/mo) averages 6.8% CPU "
                "over 30 days. Peak is 22% during end-of-month reporting. "
                "A db.r5.xlarge handles this workload comfortably with 3x CPU headroom at peak."
            ),
            recommendation=(
                "1. Downsize to db.r5.xlarge ($735/mo) — saves $2,205/mo. "
                "2. Alternatively, migrate to Aurora Serverless v2 which auto-scales 0.5–64 ACU "
                "and costs ~$0.12/ACU-hr. At average 6.8% load, estimated cost $180-380/mo. "
                "3. Schedule maintenance window for Sunday 02:00-04:00 UTC for zero downtime upgrade."
            ),
            severity="high",
            tags={"Environment": "production", "Team": "data-eng"},
        ),
        WasteItem(
            category="Unattached EBS Volume",
            resource_id="vol-0orphan000000002",
            resource_type="EBS Volume",
            region="us-west-2",
            estimated_monthly_waste=100.00,
            description=(
                "1,000 GB gp2 volume vol-0orphan000000002 (old-prod-backup-vol) "
                "has been unattached for 94 days. Not referenced in Terraform state."
            ),
            recommendation=(
                "Snapshot for archival ($0.05/GB = $50/mo), then delete volume. "
                "Net savings $50/mo after snapshot. Set 90-day snapshot expiry policy. "
                "If backup data is no longer needed, delete both volume and any prior snapshots."
            ),
            severity="high",
            tags={"Name": "old-prod-backup-vol"},
        ),
        WasteItem(
            category="Unattached EBS Volume",
            resource_id="vol-0orphan000000001",
            resource_type="EBS Volume",
            region="us-east-1",
            estimated_monthly_waste=50.00,
            description=(
                "500 GB gp2 volume (data-migration-temp) unattached for 142 days. "
                "Migration project completed Q1 2024. Volume is no longer needed."
            ),
            recommendation="Delete after creating one final snapshot as insurance.",
            severity="medium",
            tags={"Name": "data-migration-temp-DO-NOT-DELETE"},
        ),
        WasteItem(
            category="Idle EC2 Instance",
            resource_id="i-0dead0000000dead1",
            resource_type="EC2 Instance",
            region="us-east-1",
            estimated_monthly_waste=384.00,
            description=(
                "m5.2xlarge data-science-sandbox (i-0dead0000000dead1) "
                "has had 0.3% average CPU over 14 days. Last SSH login 67 days ago."
            ),
            recommendation=(
                "Terminate. If ML workloads are needed, provision SageMaker Studio "
                "domain or EC2 Spot instances on-demand — ~$20-40 for an 8hr training run "
                "vs $384/mo for always-on compute."
            ),
            severity="high",
            tags={"Name": "data-science-sandbox-FORGOTTEN", "Environment": "dev"},
        ),
        WasteItem(
            category="Old EBS Snapshots",
            resource_id="us-east-1/snapshots",
            resource_type="EBS Snapshots",
            region="us-east-1",
            estimated_monthly_waste=1_840.00,
            description=(
                "847 snapshots older than 180 days in us-east-1, consuming 36,800 GB "
                "of snapshot storage ($1,840/mo at $0.05/GB). No lifecycle policy found."
            ),
            recommendation=(
                "Implement AWS Data Lifecycle Manager: retain 7 daily + 4 weekly + "
                "12 monthly snapshots; auto-expire everything older. "
                "Estimated ongoing cost after cleanup: $120/mo."
            ),
            severity="medium",
            tags={},
        ),
        WasteItem(
            category="Idle Elastic IP",
            resource_id="eipalloc-0a1b2c0001",
            resource_type="Elastic IP",
            region="us-east-1",
            estimated_monthly_waste=3.60,
            description="Elastic IP 52.90.100.1 (legacy-bastion-eip) not associated with any instance for 203 days.",
            recommendation="Release immediately. AWS charges $3.60/month for every unassociated EIP.",
            severity="low",
            tags={"Name": "legacy-bastion-eip"},
        ),
    ]

    waste_items.sort(key=lambda w: w.estimated_monthly_waste, reverse=True)

    rightsizing = [
        RightsizingRecommendation(
            instance_id="i-0dead0000000dead2",
            instance_type="r5.4xlarge",
            region="us-west-2",
            current_monthly_cost=1_008.00,
            recommended_instance_type="r5.xlarge",
            recommended_monthly_cost=184.00,
            monthly_savings=824.00,
            annual_savings=9_888.00,
            avg_cpu_utilization=1.2,
            max_cpu_utilization=8.4,
            confidence="HIGH",
            tags={"Name": "analytics-spike-server-DO-NOT-TERMINATE-MAYBE"},
        ),
        RightsizingRecommendation(
            instance_id="i-0a1b2c3d4e5f60003",
            instance_type="m5.4xlarge",
            region="us-east-1",
            current_monthly_cost=768.00,
            recommended_instance_type="m5.2xlarge",
            recommended_monthly_cost=384.00,
            monthly_savings=384.00,
            annual_savings=4_608.00,
            avg_cpu_utilization=14.3,
            max_cpu_utilization=41.0,
            confidence="MEDIUM",
            tags={"Name": "prod-worker-01"},
        ),
    ]

    top_drivers = [
        CostDriverEntry(service="Amazon EKS / EC2 (Nodes)", monthly_cost=68_400.00, percentage_of_total=44.4, month_over_month_change=8.2),
        CostDriverEntry(service="Amazon RDS", monthly_cost=24_200.00, percentage_of_total=15.7, month_over_month_change=-1.1),
        CostDriverEntry(service="AWS Data Transfer", monthly_cost=18_800.00, percentage_of_total=12.2, month_over_month_change=22.4),
        CostDriverEntry(service="Amazon S3", monthly_cost=8_400.00, percentage_of_total=5.5, month_over_month_change=3.1),
        CostDriverEntry(service="Amazon ElastiCache", monthly_cost=6_200.00, percentage_of_total=4.0, month_over_month_change=0.0),
        CostDriverEntry(service="AWS Lambda", monthly_cost=4_200.00, percentage_of_total=2.7, month_over_month_change=-0.5),
        CostDriverEntry(service="Amazon ECS (Fargate)", monthly_cost=3_200.00, percentage_of_total=2.1, month_over_month_change=5.0),
        CostDriverEntry(service="Amazon CloudFront", monthly_cost=2_800.00, percentage_of_total=1.8, month_over_month_change=1.2),
        CostDriverEntry(service="AWS Secrets Manager", monthly_cost=800.00, percentage_of_total=0.5, month_over_month_change=0.0),
        CostDriverEntry(service="Other", monthly_cost=17_200.00, percentage_of_total=11.1, month_over_month_change=2.3),
    ]

    total_waste = sum(w.estimated_monthly_waste for w in waste_items)
    total_rightsizing = sum(r.monthly_savings for r in rightsizing)

    return CostReport(
        account_id="123456789012",
        report_date=_NOW.date(),
        analysis_period_days=90,
        monthly_avg_cost=154_200.00,
        top_cost_drivers=top_drivers,
        waste_items=waste_items,
        rightsizing_recommendations=rightsizing,
        shadow_it_items=[],
        total_identified_waste=round(total_waste, 2),
        total_rightsizing_savings=round(total_rightsizing, 2),
    )


# Eagerly built so they can be imported by api.py and demo.py
MOCK_SNAPSHOT = _build_snapshot()
MOCK_COST_REPORT = _build_cost_report(MOCK_SNAPSHOT)


# ---------------------------------------------------------------------------
# Pydantic recommendations (for API)
# ---------------------------------------------------------------------------

MOCK_RECOMMENDATIONS: list[WasteRecommendation] = [
    WasteRecommendation(
        id=str(uuid.uuid4()),
        category=w.category,
        resource_id=w.resource_id,
        resource_type=w.resource_type,
        region=w.region,
        provider=CloudProvider.AWS,
        monthly_waste_usd=w.estimated_monthly_waste,
        annual_waste_usd=round(w.estimated_monthly_waste * 12, 2),
        description=w.description,
        recommendation=w.recommendation,
        severity=Severity(w.severity),
        tags=w.tags,
        confidence=0.94 if w.severity in ("critical", "high") else 0.78,
        effort="low" if w.estimated_monthly_waste < 200 else "medium",
    )
    for w in MOCK_COST_REPORT.waste_items
]
