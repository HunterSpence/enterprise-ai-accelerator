"""
Cross-Cloud Migration Planner
==============================
Maps any source cloud to any target cloud across all 12 directional pairs:

  AWS  →  Azure | GCP | OCI
  Azure →  AWS  | GCP | OCI
  GCP  →  AWS  | Azure | OCI
  OCI  →  AWS  | Azure | GCP

Provides:
  - Resource type mapping (EC2 → Azure VM, S3 → GCS, etc.)
  - Network egress cost estimates per GB (source → internet → target)
  - Migration strategy recommendation (lift-and-shift vs re-platform)
  - Step-by-step migration runbook skeleton
  - AI-powered complexity assessment (optional — requires ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from cloud_config import CloudProvider

# ---------------------------------------------------------------------------
# Resource type mapping tables
# ---------------------------------------------------------------------------

# Format: source_type → {target_provider → target_service_name}
_RESOURCE_MAP: dict[str, dict[CloudProvider, str]] = {
    # Compute
    "EC2 Instance": {
        CloudProvider.AZURE: "Azure Virtual Machine",
        CloudProvider.GCP: "Compute Engine VM",
        CloudProvider.OCI: "OCI Compute Instance",
    },
    "Azure Virtual Machine": {
        CloudProvider.AWS: "EC2 Instance",
        CloudProvider.GCP: "Compute Engine VM",
        CloudProvider.OCI: "OCI Compute Instance",
    },
    "Compute Engine VM": {
        CloudProvider.AWS: "EC2 Instance",
        CloudProvider.AZURE: "Azure Virtual Machine",
        CloudProvider.OCI: "OCI Compute Instance",
    },
    "OCI Compute Instance": {
        CloudProvider.AWS: "EC2 Instance",
        CloudProvider.AZURE: "Azure Virtual Machine",
        CloudProvider.GCP: "Compute Engine VM",
    },
    # Object Storage
    "S3 Bucket": {
        CloudProvider.AZURE: "Azure Blob Storage",
        CloudProvider.GCP: "Google Cloud Storage",
        CloudProvider.OCI: "OCI Object Storage",
    },
    "Azure Blob Storage": {
        CloudProvider.AWS: "S3 Bucket",
        CloudProvider.GCP: "Google Cloud Storage",
        CloudProvider.OCI: "OCI Object Storage",
    },
    "Google Cloud Storage": {
        CloudProvider.AWS: "S3 Bucket",
        CloudProvider.AZURE: "Azure Blob Storage",
        CloudProvider.OCI: "OCI Object Storage",
    },
    "OCI Object Storage": {
        CloudProvider.AWS: "S3 Bucket",
        CloudProvider.AZURE: "Azure Blob Storage",
        CloudProvider.GCP: "Google Cloud Storage",
    },
    # Managed Kubernetes
    "Amazon EKS": {
        CloudProvider.AZURE: "Azure Kubernetes Service (AKS)",
        CloudProvider.GCP: "Google Kubernetes Engine (GKE)",
        CloudProvider.OCI: "Oracle Kubernetes Engine (OKE)",
    },
    "Azure Kubernetes Service (AKS)": {
        CloudProvider.AWS: "Amazon EKS",
        CloudProvider.GCP: "Google Kubernetes Engine (GKE)",
        CloudProvider.OCI: "Oracle Kubernetes Engine (OKE)",
    },
    "Google Kubernetes Engine (GKE)": {
        CloudProvider.AWS: "Amazon EKS",
        CloudProvider.AZURE: "Azure Kubernetes Service (AKS)",
        CloudProvider.OCI: "Oracle Kubernetes Engine (OKE)",
    },
    "Oracle Kubernetes Engine (OKE)": {
        CloudProvider.AWS: "Amazon EKS",
        CloudProvider.AZURE: "Azure Kubernetes Service (AKS)",
        CloudProvider.GCP: "Google Kubernetes Engine (GKE)",
    },
    # Managed Databases (relational)
    "Amazon RDS": {
        CloudProvider.AZURE: "Azure Database / Azure SQL",
        CloudProvider.GCP: "Cloud SQL",
        CloudProvider.OCI: "OCI Database Service / Autonomous DB",
    },
    "Azure Database / Azure SQL": {
        CloudProvider.AWS: "Amazon RDS",
        CloudProvider.GCP: "Cloud SQL",
        CloudProvider.OCI: "OCI Database Service / Autonomous DB",
    },
    "Cloud SQL": {
        CloudProvider.AWS: "Amazon RDS",
        CloudProvider.AZURE: "Azure Database / Azure SQL",
        CloudProvider.OCI: "OCI Database Service / Autonomous DB",
    },
    "OCI Database Service / Autonomous DB": {
        CloudProvider.AWS: "Amazon RDS",
        CloudProvider.AZURE: "Azure Database / Azure SQL",
        CloudProvider.GCP: "Cloud SQL",
    },
    # Serverless / Functions
    "AWS Lambda": {
        CloudProvider.AZURE: "Azure Functions",
        CloudProvider.GCP: "Cloud Functions / Cloud Run",
        CloudProvider.OCI: "OCI Functions",
    },
    "Azure Functions": {
        CloudProvider.AWS: "AWS Lambda",
        CloudProvider.GCP: "Cloud Functions / Cloud Run",
        CloudProvider.OCI: "OCI Functions",
    },
    "Cloud Functions / Cloud Run": {
        CloudProvider.AWS: "AWS Lambda",
        CloudProvider.AZURE: "Azure Functions",
        CloudProvider.OCI: "OCI Functions",
    },
    "OCI Functions": {
        CloudProvider.AWS: "AWS Lambda",
        CloudProvider.AZURE: "Azure Functions",
        CloudProvider.GCP: "Cloud Functions / Cloud Run",
    },
    # CDN / Load Balancer
    "Amazon CloudFront": {
        CloudProvider.AZURE: "Azure Front Door / CDN",
        CloudProvider.GCP: "Cloud CDN",
        CloudProvider.OCI: "OCI Load Balancer / CDN",
    },
    # Networking
    "AWS VPC": {
        CloudProvider.AZURE: "Azure Virtual Network (VNet)",
        CloudProvider.GCP: "Google VPC",
        CloudProvider.OCI: "OCI Virtual Cloud Network (VCN)",
    },
    # Identity
    "AWS IAM": {
        CloudProvider.AZURE: "Azure Active Directory / Entra ID",
        CloudProvider.GCP: "Google Cloud IAM",
        CloudProvider.OCI: "OCI IAM",
    },
    # Monitoring
    "Amazon CloudWatch": {
        CloudProvider.AZURE: "Azure Monitor",
        CloudProvider.GCP: "Cloud Monitoring (formerly Stackdriver)",
        CloudProvider.OCI: "OCI Monitoring",
    },
}

# Network egress cost (USD per GB, approximate public list prices 2025)
# Source provider → target provider → cost_per_gb
_EGRESS_COSTS: dict[CloudProvider, dict[CloudProvider, float]] = {
    CloudProvider.AWS: {
        CloudProvider.AZURE: 0.09,
        CloudProvider.GCP: 0.09,
        CloudProvider.OCI: 0.09,
    },
    CloudProvider.AZURE: {
        CloudProvider.AWS: 0.087,
        CloudProvider.GCP: 0.087,
        CloudProvider.OCI: 0.087,
    },
    CloudProvider.GCP: {
        CloudProvider.AWS: 0.12,
        CloudProvider.AZURE: 0.12,
        CloudProvider.OCI: 0.12,
    },
    CloudProvider.OCI: {
        CloudProvider.AWS: 0.0085,  # OCI has extremely cheap egress
        CloudProvider.AZURE: 0.0085,
        CloudProvider.GCP: 0.0085,
    },
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ResourceMapping:
    source_type: str
    target_type: str
    source_provider: CloudProvider
    target_provider: CloudProvider
    migration_notes: str = ""


@dataclass
class EgressCostEstimate:
    source_provider: CloudProvider
    target_provider: CloudProvider
    data_size_tb: float
    cost_per_gb: float
    total_cost_usd: float
    notes: str = ""


@dataclass
class CrossCloudMigrationPlan:
    source_cloud: CloudProvider
    target_cloud: CloudProvider
    resource_mappings: list[ResourceMapping] = field(default_factory=list)
    egress_estimate: EgressCostEstimate | None = None
    strategy: str = ""
    complexity: str = ""   # LOW / MEDIUM / HIGH / VERY_HIGH
    estimated_duration_weeks: int = 0
    runbook_steps: list[str] = field(default_factory=list)
    ai_assessment: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class CrossCloudMigrationPlanner:
    """
    Plans a migration between any two of the four supported cloud providers.

    Usage
    -----
        planner = CrossCloudMigrationPlanner(source="aws", target="oci")
        plan = planner.build_plan(
            resource_types=["EC2 Instance", "S3 Bucket", "Amazon RDS"],
            data_size_tb=42.0,
        )
    """

    def __init__(
        self,
        source: str | CloudProvider,
        target: str | CloudProvider,
    ) -> None:
        self.source = CloudProvider.from_str(source) if isinstance(source, str) else source
        self.target = CloudProvider.from_str(target) if isinstance(target, str) else target

        if self.source == self.target:
            raise ValueError(
                f"Source and target cloud must differ. Got: {self.source.value}"
            )

    def map_resources(
        self, resource_types: list[str]
    ) -> list[ResourceMapping]:
        """Return equivalence mappings for each resource type."""
        mappings: list[ResourceMapping] = []
        for src_type in resource_types:
            target_type = (
                _RESOURCE_MAP.get(src_type, {}).get(self.target)
                or f"{src_type} (no direct equivalent — manual mapping required)"
            )
            notes = self._migration_notes(src_type, self.source, self.target)
            mappings.append(ResourceMapping(
                source_type=src_type,
                target_type=target_type,
                source_provider=self.source,
                target_provider=self.target,
                migration_notes=notes,
            ))
        return mappings

    def estimate_egress_cost(
        self, data_size_tb: float
    ) -> EgressCostEstimate:
        """Estimate one-time network egress cost for the migration."""
        cost_per_gb = (
            _EGRESS_COSTS.get(self.source, {}).get(self.target, 0.09)
        )
        total = cost_per_gb * data_size_tb * 1024  # TB → GB

        # OCI has a free egress tier (10 TB/month)
        notes = ""
        if self.source == CloudProvider.OCI:
            free_tb = min(data_size_tb, 10.0)
            total = max(0, (data_size_tb - free_tb) * 1024 * cost_per_gb)
            notes = f"OCI free egress: 10 TB/month applied. Charged: {data_size_tb - free_tb:.1f} TB."
        elif self.target == CloudProvider.OCI:
            notes = "Ingress to OCI is free. Only source-side egress charged."

        return EgressCostEstimate(
            source_provider=self.source,
            target_provider=self.target,
            data_size_tb=data_size_tb,
            cost_per_gb=cost_per_gb,
            total_cost_usd=round(total, 2),
            notes=notes,
        )

    def build_plan(
        self,
        resource_types: list[str] | None = None,
        data_size_tb: float = 0.0,
        workload_count: int = 1,
    ) -> CrossCloudMigrationPlan:
        """Build the full migration plan."""
        resource_types = resource_types or []
        mappings = self.map_resources(resource_types)
        egress = self.estimate_egress_cost(data_size_tb) if data_size_tb > 0 else None
        complexity = self._assess_complexity(resource_types, workload_count, data_size_tb)
        duration = self._estimate_duration(complexity, workload_count)
        runbook = self._generate_runbook(resource_types)
        warnings = self._build_warnings(resource_types)

        return CrossCloudMigrationPlan(
            source_cloud=self.source,
            target_cloud=self.target,
            resource_mappings=mappings,
            egress_estimate=egress,
            strategy=self._strategy_label(resource_types),
            complexity=complexity,
            estimated_duration_weeks=duration,
            runbook_steps=runbook,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _migration_notes(  # noqa: PLR0912
        self,
        src_type: str,
        source: CloudProvider,
        target: CloudProvider,
    ) -> str:
        pair = (source, target)
        # Database-specific notes
        if "RDS" in src_type or "Database" in src_type or "SQL" in src_type:
            if target == CloudProvider.OCI:
                return (
                    "Use Oracle Data Pump or GoldenGate for zero-downtime replication. "
                    "Autonomous DB supports direct schema import."
                )
            if target == CloudProvider.AZURE:
                return "Azure Database Migration Service (DMS) supports online migration."
            if target == CloudProvider.GCP:
                return "Database Migration Service (DMS) supports PostgreSQL/MySQL online migration."
            return "Use provider-native DMS for minimal downtime."
        # Object storage
        if "S3" in src_type or "Storage" in src_type or "Bucket" in src_type:
            if target == CloudProvider.OCI:
                return "rclone or OCI CLI multipart upload. OCI S3 Compatibility API eases migration."
            return "rclone, AWS DataSync, or provider-native transfer tools."
        # Serverless
        if "Lambda" in src_type or "Function" in src_type:
            return "Runtime portability varies. Container-packaged functions migrate cleanest."
        # Kubernetes
        if "EKS" in src_type or "AKS" in src_type or "GKE" in src_type or "OKE" in src_type:
            return (
                "Export manifests with Velero. "
                "Review node selectors, storage classes, and cloud-specific annotations."
            )
        return "Evaluate provider-native migration tooling before resorting to manual export/import."

    def _assess_complexity(
        self,
        resource_types: list[str],
        workload_count: int,
        data_size_tb: float,
    ) -> str:
        score = 0
        score += min(workload_count // 10, 4)
        score += min(int(data_size_tb // 50), 4)
        score += len([r for r in resource_types if "Database" in r or "RDS" in r or "SQL" in r]) * 2
        score += len([r for r in resource_types if "Lambda" in r or "Function" in r])
        if score <= 2:
            return "LOW"
        elif score <= 5:
            return "MEDIUM"
        elif score <= 9:
            return "HIGH"
        return "VERY_HIGH"

    def _estimate_duration(self, complexity: str, workload_count: int) -> int:
        base = {"LOW": 4, "MEDIUM": 8, "HIGH": 16, "VERY_HIGH": 26}[complexity]
        return base + workload_count // 20

    def _strategy_label(self, resource_types: list[str]) -> str:
        db_heavy = any("Database" in r or "RDS" in r for r in resource_types)
        fn_heavy = any("Lambda" in r or "Function" in r for r in resource_types)
        if db_heavy and fn_heavy:
            return "Re-platform: Managed services on target cloud recommended"
        if db_heavy:
            return "Hybrid: Lift-and-shift compute, re-platform databases"
        if fn_heavy:
            return "Re-platform: Containerise functions for portability"
        return "Lift-and-shift: IaaS resources map directly between providers"

    def _generate_runbook(self, resource_types: list[str]) -> list[str]:
        src_name = self.source.display_name()
        tgt_name = self.target.display_name()
        steps = [
            f"1. Discovery: Export full {src_name} inventory with CloudIQ scanner",
            f"2. Assessment: Run MigrationScout 6R classification on all workloads",
            f"3. Target setup: Provision landing zone in {tgt_name} (VPC/VNet/VCN + IAM)",
            f"4. Auth config: Set TARGET_CLOUD={self.target.value} and provider credentials in .env",
            "5. Network: Establish dedicated connectivity (VPN or ExpressRoute/Interconnect/FastConnect)",
            "6. Identity federation: Map {src_name} IAM roles/principals to {tgt_name} equivalents",
        ]
        if any("Database" in r or "RDS" in r or "SQL" in r for r in resource_types):
            steps.append("7. Data: Set up CDC replication with provider DMS for zero-downtime DB migration")
        if any("S3" in r or "Blob" in r or "Storage" in r for r in resource_types):
            steps.append("8. Storage: Transfer objects with rclone (parallelised, checksum-verified)")
        if any("EKS" in r or "AKS" in r or "GKE" in r or "OKE" in r for r in resource_types):
            steps.append("9. Kubernetes: Export workloads with Velero; redeploy to target cluster")
        steps += [
            f"{len(steps) + 1}. Cutover: DNS flip + traffic shifting (canary → 100%)",
            f"{len(steps) + 2}. Validation: Run smoke tests and CloudIQ scan on {tgt_name}",
            f"{len(steps) + 3}. Decommission: Terminate {src_name} resources after 30-day observation window",
        ]
        return steps

    def _build_warnings(self, resource_types: list[str]) -> list[str]:
        warnings: list[str] = []
        if self.source == CloudProvider.AWS and self.target == CloudProvider.OCI:
            warnings.append(
                "AWS proprietary services (DynamoDB, Kinesis, SageMaker) have no direct OCI equivalent. "
                "Evaluate re-platforming to OCI NoSQL / Streaming / Data Science."
            )
        if self.source == CloudProvider.AZURE and self.target == CloudProvider.OCI:
            warnings.append(
                "Azure AD (Entra ID) federates with OCI IAM via SAML 2.0. "
                "Configure identity federation before migrating workloads."
            )
        if self.source == CloudProvider.OCI and self.target in (CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP):
            warnings.append(
                "OCI-native services (Exadata, Autonomous DB) have no direct equivalent. "
                "Plan re-platforming for any Autonomous Database workloads."
            )
        if any("Lambda" in r or "Function" in r for r in resource_types):
            warnings.append(
                "Serverless functions depend on provider-specific triggers/bindings. "
                "Container packaging (OCI image) is the most portable migration path."
            )
        return warnings
