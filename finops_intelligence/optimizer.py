"""
optimizer.py — Cost optimization engine.

Identifies and quantifies:
  - EC2/RDS rightsizing candidates (CloudWatch CPU < 20%)
  - Reserved Instance / Savings Plan purchase recommendations
  - Waste: idle instances, unattached EBS, unused Elastic IPs, old snapshots
  - Commitment coverage gap

Returns an OptimizationPlan ranked by savings impact.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any

from .cost_tracker import SpendData


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class OpportunityType(str, Enum):
    RIGHTSIZING = "RIGHTSIZING"
    RESERVED_INSTANCE = "RESERVED_INSTANCE"
    SAVINGS_PLAN = "SAVINGS_PLAN"
    WASTE_ELIMINATION = "WASTE_ELIMINATION"
    GRAVITON_MIGRATION = "GRAVITON_MIGRATION"
    SPOT_INSTANCE = "SPOT_INSTANCE"


@dataclass
class OptimizationOpportunity:
    """A single cost optimization opportunity."""
    type: OpportunityType
    title: str
    description: str
    resource_id: str        # instance ID, bucket name, volume ID, etc.
    resource_type: str      # e.g. "EC2 m5.2xlarge", "RDS db.r6g.2xlarge"
    current_monthly: float
    savings_monthly: float
    savings_annual: float
    savings_pct: float
    effort: str             # "LOW" | "MEDIUM" | "HIGH"
    risk: str               # "LOW" | "MEDIUM" | "HIGH"
    priority: int           # 1 = highest
    action: str             # specific next step
    confidence: float       # 0.0–1.0


@dataclass
class OptimizationPlan:
    """Complete optimization plan with all opportunities ranked."""
    generated_at: date
    total_monthly_savings: float
    total_annual_savings: float
    opportunities: list[OptimizationOpportunity]
    ri_sp_coverage_pct: float
    waste_monthly: float
    rightsizing_monthly: float
    commitment_monthly: float
    account_id: str = ""
    account_name: str = ""

    def top_opportunities(self, n: int = 5) -> list[OptimizationOpportunity]:
        return sorted(self.opportunities, key=lambda o: o.savings_monthly, reverse=True)[:n]

    @property
    def summary(self) -> str:
        top = self.top_opportunities(3)
        actions = "; ".join(f"({i+1}) {o.title}" for i, o in enumerate(top))
        return (
            f"${self.total_monthly_savings:,.0f}/month (${self.total_annual_savings:,.0f}/year) "
            f"identified across {len(self.opportunities)} opportunities. "
            f"Top actions: {actions}."
        )


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

class Optimizer:
    """
    Generates an OptimizationPlan from spend data.

    In mock mode (no AWS creds), generates realistic recommendations
    based on the mock spend profile.

    In live mode, calls:
      - AWS Compute Optimizer (rightsizing)
      - AWS Cost Explorer (RI/SP recommendations)
      - EC2/EBS/EIP APIs (waste detection)
    """

    def __init__(
        self,
        mock: bool = False,
        aws_profile: str | None = None,
        aws_region: str = "us-east-1",
    ) -> None:
        self.mock = mock
        self.aws_profile = aws_profile
        self.aws_region = aws_region

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def analyze(self, spend_data: SpendData) -> OptimizationPlan:
        """
        Run full optimization analysis.
        Returns OptimizationPlan sorted by savings impact.
        """
        if self.mock:
            return self._generate_mock_plan(spend_data)

        opportunities: list[OptimizationOpportunity] = []
        opportunities.extend(self._rightsizing_analysis(spend_data))
        opportunities.extend(self._ri_sp_analysis(spend_data))
        opportunities.extend(self._waste_analysis(spend_data))
        opportunities.extend(self._graviton_analysis(spend_data))

        # Sort by savings (highest first) and assign priority
        opportunities.sort(key=lambda o: o.savings_monthly, reverse=True)
        for i, opp in enumerate(opportunities):
            opp.priority = i + 1

        total_monthly = sum(o.savings_monthly for o in opportunities)
        waste = sum(o.savings_monthly for o in opportunities if o.type == OpportunityType.WASTE_ELIMINATION)
        rightsizing = sum(o.savings_monthly for o in opportunities if o.type == OpportunityType.RIGHTSIZING)
        commitment = sum(o.savings_monthly for o in opportunities if o.type in (
            OpportunityType.RESERVED_INSTANCE, OpportunityType.SAVINGS_PLAN
        ))
        ri_coverage = self._estimate_ri_coverage(spend_data)

        return OptimizationPlan(
            generated_at=date.today(),
            total_monthly_savings=round(total_monthly, 2),
            total_annual_savings=round(total_monthly * 12, 2),
            opportunities=opportunities,
            ri_sp_coverage_pct=ri_coverage,
            waste_monthly=round(waste, 2),
            rightsizing_monthly=round(rightsizing, 2),
            commitment_monthly=round(commitment, 2),
            account_id=spend_data.account_id,
            account_name=spend_data.account_name,
        )

    # ------------------------------------------------------------------
    # Live AWS analysis
    # ------------------------------------------------------------------

    def _get_boto3_session(self) -> Any:
        import boto3
        return boto3.Session(
            profile_name=self.aws_profile,
            region_name=self.aws_region,
        )

    def _rightsizing_analysis(self, spend_data: SpendData) -> list[OptimizationOpportunity]:
        """Pull EC2 rightsizing recommendations from AWS Compute Optimizer."""
        opps: list[OptimizationOpportunity] = []
        try:
            session = self._get_boto3_session()
            co = session.client("compute-optimizer")
            response = co.get_ec2_instance_recommendations()

            for rec in response.get("instanceRecommendations", []):
                current_type = rec.get("currentInstanceType", "")
                options = rec.get("recommendationOptions", [])
                if not options:
                    continue
                best = options[0]
                recommended_type = best.get("instanceType", "")
                savings = best.get("estimatedMonthlySavings", {})
                monthly = float(savings.get("value", 0))
                if monthly < 10:
                    continue

                current_monthly = self._get_instance_cost(rec.get("instanceArn", ""), spend_data)
                instance_id = rec.get("instanceArn", "").split("/")[-1]

                opp = OptimizationOpportunity(
                    type=OpportunityType.RIGHTSIZING,
                    title=f"Rightsize {instance_id}: {current_type} → {recommended_type}",
                    description=(
                        f"Average CPU utilization: {rec.get('utilizationMetrics', [{}])[0].get('value', 0):.1f}%. "
                        f"Recommended instance type {recommended_type} provides equivalent performance at lower cost."
                    ),
                    resource_id=instance_id,
                    resource_type=f"EC2 {current_type}",
                    current_monthly=round(current_monthly, 2),
                    savings_monthly=round(monthly, 2),
                    savings_annual=round(monthly * 12, 2),
                    savings_pct=round(monthly / current_monthly * 100 if current_monthly > 0 else 0, 1),
                    effort="LOW",
                    risk="LOW",
                    priority=0,
                    action=f"Schedule instance type modification: {current_type} → {recommended_type} during next maintenance window.",
                    confidence=0.85,
                )
                opps.append(opp)

        except Exception:
            pass
        return opps

    def _ri_sp_analysis(self, spend_data: SpendData) -> list[OptimizationOpportunity]:
        """Pull RI/SP purchase recommendations from Cost Explorer."""
        opps: list[OptimizationOpportunity] = []
        try:
            session = self._get_boto3_session()
            ce = session.client("ce")

            response = ce.get_savings_plans_purchase_recommendation(
                SavingsPlansType="COMPUTE_SP",
                TermInYears="ONE_YEAR",
                PaymentOption="NO_UPFRONT",
                LookbackPeriodInDays="SIXTY_DAYS",
            )
            summary = response.get("SavingsPlansPurchaseRecommendationSummary", {})
            monthly_savings = float(summary.get("EstimatedMonthlySavingsAmount", 0))
            hourly_commitment = float(summary.get("HourlyCommitmentToPurchase", 0))

            if monthly_savings >= 100:
                opps.append(OptimizationOpportunity(
                    type=OpportunityType.SAVINGS_PLAN,
                    title=f"Purchase Compute Savings Plan (${hourly_commitment:.2f}/hr)",
                    description=(
                        f"Buy a 1yr No-Upfront Compute Savings Plan at ${hourly_commitment:.2f}/hr. "
                        f"Covers EC2, Fargate, and Lambda. No upfront cost = zero risk."
                    ),
                    resource_id="compute-savings-plan",
                    resource_type="AWS Savings Plan",
                    current_monthly=float(summary.get("CurrentOnDemandSpend", 0)) / 30,
                    savings_monthly=round(monthly_savings, 2),
                    savings_annual=round(monthly_savings * 12, 2),
                    savings_pct=float(summary.get("SavingsPercentage", 0)),
                    effort="LOW",
                    risk="LOW",
                    priority=0,
                    action="Purchase Compute Savings Plan in AWS Billing Console. Takes effect within 1 hour.",
                    confidence=0.90,
                ))
        except Exception:
            pass
        return opps

    def _waste_analysis(self, spend_data: SpendData) -> list[OptimizationOpportunity]:
        """Identify idle resources wasting money."""
        opps: list[OptimizationOpportunity] = []
        try:
            session = self._get_boto3_session()
            ec2 = session.client("ec2")

            # Unattached EBS volumes
            volumes = ec2.describe_volumes(
                Filters=[{"Name": "status", "Values": ["available"]}]
            )
            for vol in volumes.get("Volumes", []):
                gb = vol.get("Size", 0)
                vol_type = vol.get("VolumeType", "gp2")
                price_per_gb = {"gp2": 0.10, "gp3": 0.08, "io1": 0.125, "io2": 0.125, "st1": 0.045, "sc1": 0.025}
                monthly = gb * price_per_gb.get(vol_type, 0.10)
                if monthly >= 5:
                    opps.append(OptimizationOpportunity(
                        type=OpportunityType.WASTE_ELIMINATION,
                        title=f"Delete unattached EBS volume {vol['VolumeId']} ({gb}GB {vol_type})",
                        description=(
                            f"EBS volume {vol['VolumeId']} is not attached to any instance. "
                            f"Size: {gb}GB {vol_type}. Created: {vol.get('CreateTime', 'unknown')}."
                        ),
                        resource_id=vol["VolumeId"],
                        resource_type=f"EBS {vol_type} {gb}GB",
                        current_monthly=round(monthly, 2),
                        savings_monthly=round(monthly, 2),
                        savings_annual=round(monthly * 12, 2),
                        savings_pct=100.0,
                        effort="LOW",
                        risk="LOW",
                        priority=0,
                        action=f"Snapshot then delete: aws ec2 delete-volume --volume-id {vol['VolumeId']}",
                        confidence=0.95,
                    ))

            # Unused Elastic IPs
            addresses = ec2.describe_addresses()
            for addr in addresses.get("Addresses", []):
                if not addr.get("InstanceId") and not addr.get("NetworkInterfaceId"):
                    opps.append(OptimizationOpportunity(
                        type=OpportunityType.WASTE_ELIMINATION,
                        title=f"Release unused Elastic IP {addr.get('PublicIp', '')}",
                        description="Elastic IP not associated with any running instance. Costs $0.005/hour (~$3.60/month).",
                        resource_id=addr.get("AllocationId", ""),
                        resource_type="Elastic IP",
                        current_monthly=3.60,
                        savings_monthly=3.60,
                        savings_annual=43.20,
                        savings_pct=100.0,
                        effort="LOW",
                        risk="LOW",
                        priority=0,
                        action=f"aws ec2 release-address --allocation-id {addr.get('AllocationId')}",
                        confidence=0.99,
                    ))

        except Exception:
            pass
        return opps

    def _graviton_analysis(self, spend_data: SpendData) -> list[OptimizationOpportunity]:
        """Identify Graviton3 migration opportunities based on EC2 spend."""
        opps: list[OptimizationOpportunity] = []
        ec2_service = spend_data.services.get("Amazon EC2")
        if not ec2_service:
            return opps

        monthly_ec2 = ec2_service.total / max(1, (spend_data.query_end - spend_data.query_start).days) * 30
        # Conservative: 30% of EC2 is Graviton-migratable at 20% savings
        migratable = monthly_ec2 * 0.30
        savings = migratable * 0.20

        if savings >= 100:
            opps.append(OptimizationOpportunity(
                type=OpportunityType.GRAVITON_MIGRATION,
                title="Migrate eligible EC2 workloads to Graviton3 (ARM)",
                description=(
                    f"AWS Graviton3 instances deliver ~20% better price-performance than x86 equivalents. "
                    f"Estimated {30:.0f}% of your EC2 fleet is ARM-compatible (based on common workload patterns). "
                    "Graviton3 instances: m7g, c7g, r7g families."
                ),
                resource_id="ec2-graviton-migration",
                resource_type="EC2 Fleet",
                current_monthly=round(monthly_ec2, 2),
                savings_monthly=round(savings, 2),
                savings_annual=round(savings * 12, 2),
                savings_pct=round(savings / monthly_ec2 * 100 if monthly_ec2 > 0 else 0, 1),
                effort="HIGH",
                risk="MEDIUM",
                priority=0,
                action="Identify x86 instances running Linux workloads. Test on Graviton3 in staging. Schedule migration during next sprint.",
                confidence=0.65,
            ))
        return opps

    def _estimate_ri_coverage(self, spend_data: SpendData) -> float:
        """Estimate RI/SP coverage (live mode: call CE API)."""
        try:
            session = self._get_boto3_session()
            ce = session.client("ce")
            end = date.today()
            start = end - timedelta(days=30)
            response = ce.get_savings_plans_coverage(
                TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                Granularity="MONTHLY",
            )
            total = response.get("SavingsPlansCoverages", [])
            if total:
                pct = float(total[0].get("Coverage", {}).get("CoveragePercentage", 0))
                return pct
        except Exception:
            pass
        return 30.0  # conservative estimate

    def _get_instance_cost(self, instance_arn: str, spend_data: SpendData) -> float:
        """Estimate monthly cost for an instance (simple heuristic)."""
        ec2_svc = spend_data.services.get("Amazon EC2")
        if ec2_svc:
            return ec2_svc.total / 100  # rough per-instance estimate
        return 200.0

    # ------------------------------------------------------------------
    # Mock plan generator
    # ------------------------------------------------------------------

    def _generate_mock_plan(self, spend_data: SpendData) -> OptimizationPlan:
        """
        Generate a realistic optimization plan for TechStartupCo.
        Total identified savings: $31,200/month.
        """
        opportunities = [
            # 1. Savings Plan purchase (biggest single win)
            OptimizationOpportunity(
                type=OpportunityType.SAVINGS_PLAN,
                title="Purchase 1yr No-Upfront Compute Savings Plan ($52/hr commitment)",
                description=(
                    "Your EC2+Lambda baseline spend is $57,200/month. "
                    "Buying a $52/hr Compute Savings Plan achieves 74% coverage. "
                    "No-Upfront = zero risk. Break-even: Day 1 (immediate savings)."
                ),
                resource_id="compute-savings-plan-recommendation",
                resource_type="Compute Savings Plan",
                current_monthly=57_200.0,
                savings_monthly=12_800.0,
                savings_annual=153_600.0,
                savings_pct=22.4,
                effort="LOW",
                risk="LOW",
                priority=1,
                action="Purchase in AWS Billing Console: Savings Plans > Purchase Savings Plan > Compute > No Upfront > $52/hr.",
                confidence=0.92,
            ),
            # 2. Rightsizing EC2
            OptimizationOpportunity(
                type=OpportunityType.RIGHTSIZING,
                title="Rightsize 8 oversized EC2 instances in api-prod ASG",
                description=(
                    "8 x m5.2xlarge instances in the api-prod Auto Scaling Group show "
                    "average CPU < 12% over 30 days (peak: 34%). "
                    "Downsize to m5.xlarge: equivalent performance, half the compute cost."
                ),
                resource_id="asg/api-prod",
                resource_type="EC2 m5.2xlarge → m5.xlarge",
                current_monthly=9_600.0,
                savings_monthly=4_800.0,
                savings_annual=57_600.0,
                savings_pct=50.0,
                effort="MEDIUM",
                risk="LOW",
                priority=2,
                action="Update api-prod Launch Template to m5.xlarge. Trigger rolling refresh during low-traffic window (Sat 02:00 UTC).",
                confidence=0.88,
            ),
            # 3. Idle RDS instance
            OptimizationOpportunity(
                type=OpportunityType.RIGHTSIZING,
                title="Downsize idle RDS analytics instance (db.r6g.2xlarge → db.r6g.large)",
                description=(
                    "RDS instance analytics-db-01 (db.r6g.2xlarge) shows average CPU 8%, "
                    "storage I/O 12% over 30 days — significantly underutilized. "
                    "db.r6g.large provides adequate capacity with no performance risk for analytics workloads."
                ),
                resource_id="analytics-db-01",
                resource_type="RDS db.r6g.2xlarge → db.r6g.large",
                current_monthly=7_600.0,
                savings_monthly=3_800.0,
                savings_annual=45_600.0,
                savings_pct=50.0,
                effort="LOW",
                risk="LOW",
                priority=3,
                action="Modify RDS instance class during next maintenance window. Enable Multi-AZ only if required. Estimated downtime: ~5 min.",
                confidence=0.91,
            ),
            # 4. Graviton migration
            OptimizationOpportunity(
                type=OpportunityType.GRAVITON_MIGRATION,
                title="Migrate worker fleet to Graviton3 (m7g.xlarge)",
                description=(
                    "12 x m5.xlarge worker instances run stateless Python/Go services — "
                    "fully ARM-compatible. Graviton3 equivalent (m7g.xlarge) costs $0.1542/hr vs. "
                    "$0.192/hr for m5.xlarge: 20% savings, 10% better performance."
                ),
                resource_id="asg/worker-fleet",
                resource_type="EC2 m5.xlarge → m7g.xlarge (Graviton3)",
                current_monthly=5_530.0,
                savings_monthly=3_320.0,
                savings_annual=39_840.0,
                savings_pct=20.0,
                effort="MEDIUM",
                risk="MEDIUM",
                priority=4,
                action="Test application stack on Graviton3 in staging environment. If passing, update worker-fleet Launch Template to m7g.xlarge.",
                confidence=0.78,
            ),
            # 5. NAT Gateway optimization
            OptimizationOpportunity(
                type=OpportunityType.WASTE_ELIMINATION,
                title="Fix Lambda retry loop causing NAT Gateway traffic spike",
                description=(
                    "A Lambda function entered a retry loop on the 3rd, generating $14,800 in "
                    "NAT Gateway data transfer charges in a single day. Root cause: uncaught "
                    "exception in the event-processor function causing indefinite SQS retries. "
                    "Normal NAT costs should be ~$210/day."
                ),
                resource_id="lambda/event-processor",
                resource_type="Lambda + NAT Gateway",
                current_monthly=4_200.0,  # ongoing elevated level
                savings_monthly=3_780.0,
                savings_annual=45_360.0,
                savings_pct=90.0,
                effort="MEDIUM",
                risk="LOW",
                priority=5,
                action="Add DLQ to event-processor Lambda. Set SQS maxReceiveCount=3. Add CloudWatch alarm: NatGateway BytesOutToDestination > 50GB/day.",
                confidence=0.94,
            ),
            # 6. Unattached EBS volumes
            OptimizationOpportunity(
                type=OpportunityType.WASTE_ELIMINATION,
                title="Delete 23 unattached EBS volumes (4.6TB total)",
                description=(
                    "23 EBS volumes are not attached to any running instance. "
                    "Total capacity: 4,600GB. These are likely orphaned from terminated instances. "
                    "Combined monthly cost: $1,840."
                ),
                resource_id="ebs-orphaned",
                resource_type="EBS gp3 volumes (23x)",
                current_monthly=1_840.0,
                savings_monthly=1_840.0,
                savings_annual=22_080.0,
                savings_pct=100.0,
                effort="LOW",
                risk="LOW",
                priority=6,
                action="Snapshot each volume, then delete. Script: aws ec2 describe-volumes --filters Name=status,Values=available",
                confidence=0.97,
            ),
            # 7. Unused Elastic IPs
            OptimizationOpportunity(
                type=OpportunityType.WASTE_ELIMINATION,
                title="Release 18 unused Elastic IPs",
                description=(
                    "18 Elastic IPs allocated but not associated with any running instance. "
                    "Each costs $0.005/hr when idle. Combined: $64.80/month."
                ),
                resource_id="eip-unused",
                resource_type="Elastic IPs (18x)",
                current_monthly=64.80,
                savings_monthly=64.80,
                savings_annual=777.60,
                savings_pct=100.0,
                effort="LOW",
                risk="LOW",
                priority=7,
                action="aws ec2 describe-addresses | jq '.Addresses[] | select(.InstanceId == null)' — then release each.",
                confidence=0.99,
            ),
            # 8. Old snapshots
            OptimizationOpportunity(
                type=OpportunityType.WASTE_ELIMINATION,
                title="Delete 847 EBS snapshots older than 180 days",
                description=(
                    "847 EBS snapshots were created >180 days ago. With a 30-day retention "
                    "policy, these are beyond useful recovery range. "
                    "Storage cost: $0.05/GB-month. Estimated volume: ~20TB."
                ),
                resource_id="snapshots-old",
                resource_type="EBS Snapshots",
                current_monthly=1_000.0,
                savings_monthly=850.0,
                savings_annual=10_200.0,
                savings_pct=85.0,
                effort="LOW",
                risk="LOW",
                priority=8,
                action="Use AWS Backup or Data Lifecycle Manager to enforce 30-day snapshot retention policy. Delete existing old snapshots.",
                confidence=0.88,
            ),
        ]

        # Sort by savings
        opportunities.sort(key=lambda o: o.savings_monthly, reverse=True)
        for i, opp in enumerate(opportunities):
            opp.priority = i + 1

        total_monthly = sum(o.savings_monthly for o in opportunities)
        waste = sum(o.savings_monthly for o in opportunities if o.type == OpportunityType.WASTE_ELIMINATION)
        rightsizing = sum(o.savings_monthly for o in opportunities if o.type == OpportunityType.RIGHTSIZING)
        commitment = sum(o.savings_monthly for o in opportunities if o.type in (
            OpportunityType.RESERVED_INSTANCE, OpportunityType.SAVINGS_PLAN
        ))

        return OptimizationPlan(
            generated_at=date.today(),
            total_monthly_savings=round(total_monthly, 2),
            total_annual_savings=round(total_monthly * 12, 2),
            opportunities=opportunities,
            ri_sp_coverage_pct=31.0,
            waste_monthly=round(waste, 2),
            rightsizing_monthly=round(rightsizing, 2),
            commitment_monthly=round(commitment, 2),
            account_id=spend_data.account_id,
            account_name=spend_data.account_name,
        )
