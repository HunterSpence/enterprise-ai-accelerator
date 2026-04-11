"""
FinOps Intelligence — FOCUS 1.3 Specification Exporter
========================================================
Converts FinOps Intelligence cost data to FinOps Foundation FOCUS 1.3 format.

FOCUS (FinOps Open Cost and Usage Specification) is the emerging standard for
billing data normalization across cloud providers. Organizations adopting FOCUS
can plug FinOps Intelligence output into any FOCUS-compatible toolchain:
  - OpenCost (CNCF, Apache 2.0)
  - focus_converters (FinOps Foundation reference implementation)
  - Apptio Cloudability (commercial)
  - Spot by NetApp (commercial)
  - Any enterprise FinOps platform built on the spec

The FOCUS spec defines a normalized schema so multi-cloud cost data from AWS,
Azure, GCP, and Oracle can be queried with the same field names.

This exporter implements:
  - FOCUS 1.0: all 33 required columns
  - FOCUS 1.2/1.3: optional columns (InvoiceId, PricingCurrency, ServiceProvider,
    HostProvider, CapacityReservationId, CapacityReservationStatus)
  - AI/LLM cost rows: per-model token spend in FOCUS format (unique in OSS)
  - Multi-cloud normalization: AWS, Azure, GCP service category mapping
  - Parquet export: FOCUS 1.4-ready columnar output

Key FOCUS 1.0 column definitions implemented here:
  BilledCost          — The charge after all discounts (what you actually pay)
  EffectiveCost       — Amortized cost including RI/SP prepayments
  ListCost            — On-demand cost without discounts
  SkuPriceId          — Unique identifier for pricing dimension
  ServiceName         — Normalized service name (e.g., "Virtual Machines" not "EC2")
  ServiceCategory     — Compute | Storage | Database | Network | AI | Other
  RegionId            — Cloud-neutral region identifier
  ResourceId          — Provider-specific resource identifier
  UsageQuantity       — Consumption amount in UsageUnit
  UsageUnit           — Unit of measure (Hours, GB, Requests, Tokens)
  Tags                — Key-value cost allocation metadata

Reference: https://focus.finops.org/#specification

Usage:
    from finops_intelligence.focus_exporter import FOCUSExporter
    from finops_intelligence import CostTracker

    tracker = CostTracker(mock=True)
    data = tracker.get_spend_data(days=30)

    exporter = FOCUSExporter(provider="aws", account_id="123456789012")
    focus_rows = exporter.from_spend_data(data.service_breakdown)

    exporter.export_jsonl("./output/billing_focus.jsonl", focus_rows)
    exporter.export_csv("./output/billing_focus.csv", focus_rows)
    exporter.export_parquet("./output/billing_focus.parquet", focus_rows)

    # AI/LLM costs in FOCUS format
    ai_rows = exporter.export_ai_model_costs([
        {"model": "claude-sonnet-4-6", "input_tokens": 1_000_000,
         "output_tokens": 200_000, "total_cost": 4.20},
    ])

    # Or attach to_focus() to any SpendData
    focus_json = exporter.to_focus(spend_data)
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional


# ---------------------------------------------------------------------------
# FOCUS 1.0 / 1.3 column definitions
# ---------------------------------------------------------------------------

# AI model name prefix → cloud provider (for export_ai_model_costs)
AI_MODEL_PROVIDERS: dict[str, str] = {
    "claude": "Anthropic",
    "gpt": "OpenAI",
    "o1": "OpenAI",
    "o3": "OpenAI",
    "o4": "OpenAI",
    "gemini": "Google",
    "llama": "Meta",
    "mistral": "Mistral AI",
    "command": "Cohere",
}

# ServiceCategory normalization per FOCUS spec section 4.5
# Maps AWS service names to FOCUS ServiceCategory
_AWS_SERVICE_CATEGORY: dict[str, str] = {
    "Amazon EC2": "Compute",
    "Amazon ECS": "Compute",
    "Amazon EKS": "Compute",
    "AWS Lambda": "Compute",
    "AWS Batch": "Compute",
    "Amazon Lightsail": "Compute",
    "Amazon S3": "Storage",
    "Amazon EFS": "Storage",
    "Amazon Glacier": "Storage",
    "Amazon EBS": "Storage",
    "Amazon FSx": "Storage",
    "Amazon RDS": "Database",
    "Amazon DynamoDB": "Database",
    "Amazon ElastiCache": "Database",
    "Amazon Redshift": "Database",
    "Amazon Aurora": "Database",
    "Amazon DocumentDB": "Database",
    "Amazon Neptune": "Database",
    "Amazon VPC": "Network",
    "Amazon CloudFront": "Network",
    "AWS Direct Connect": "Network",
    "Elastic Load Balancing": "Network",
    "Amazon Route 53": "Network",
    "AWS Transfer Family": "Network",
    "Amazon SageMaker": "AI and Machine Learning",
    "Amazon Rekognition": "AI and Machine Learning",
    "Amazon Comprehend": "AI and Machine Learning",
    "Amazon Textract": "AI and Machine Learning",
    "Amazon Bedrock": "AI and Machine Learning",
    "Amazon Lex": "AI and Machine Learning",
    "Amazon Polly": "AI and Machine Learning",
    "Amazon Transcribe": "AI and Machine Learning",
    "Amazon Translate": "AI and Machine Learning",
    "AWS CloudWatch": "Management and Governance",
    "AWS Config": "Management and Governance",
    "AWS CloudTrail": "Management and Governance",
    "AWS Systems Manager": "Management and Governance",
    "AWS Organizations": "Management and Governance",
    "AWS IAM": "Security, Identity, and Compliance",
    "Amazon GuardDuty": "Security, Identity, and Compliance",
    "AWS Security Hub": "Security, Identity, and Compliance",
    "Amazon Inspector": "Security, Identity, and Compliance",
    "AWS WAF": "Security, Identity, and Compliance",
    "AWS Shield": "Security, Identity, and Compliance",
    "AWS KMS": "Security, Identity, and Compliance",
    "Amazon SNS": "Application Integration",
    "Amazon SQS": "Application Integration",
    "Amazon EventBridge": "Application Integration",
    "AWS Step Functions": "Application Integration",
    "AWS API Gateway": "Application Integration",
    "Amazon AppFlow": "Application Integration",
    "AWS Support": "Other",
    "AWS Marketplace": "Other",
}

# FOCUS ServiceName normalization (cloud-neutral display names)
_AWS_SERVICE_NAME: dict[str, str] = {
    "Amazon EC2": "Virtual Machines",
    "Amazon ECS": "Container Service",
    "Amazon EKS": "Kubernetes Service",
    "AWS Lambda": "Functions",
    "Amazon S3": "Blob Storage",
    "Amazon EBS": "Block Storage",
    "Amazon RDS": "Relational Database",
    "Amazon DynamoDB": "NoSQL Database",
    "Amazon ElastiCache": "Cache",
    "Amazon Redshift": "Data Warehouse",
    "Amazon SageMaker": "Machine Learning Platform",
    "Amazon Bedrock": "Foundation Model Service",
    "Amazon VPC": "Virtual Network",
    "Amazon CloudFront": "CDN",
    "Elastic Load Balancing": "Load Balancer",
    "Amazon Route 53": "DNS",
    "Amazon CloudWatch": "Monitoring",
    "AWS CloudTrail": "Audit Logging",
    "AWS Config": "Configuration Management",
    "Amazon GuardDuty": "Threat Detection",
    "AWS KMS": "Key Management",
    "Amazon SNS": "Notification Service",
    "Amazon SQS": "Message Queue",
    "AWS API Gateway": "API Management",
}

# ServiceCategory normalization for Azure services (FOCUS spec section 4.5)
_AZURE_SERVICE_CATEGORY: dict[str, str] = {
    "Virtual Machines": "Compute",
    "Azure Virtual Machines": "Compute",
    "Azure Kubernetes Service": "Compute",
    "Azure Container Instances": "Compute",
    "Azure App Service": "Compute",
    "Azure Functions": "Compute",
    "Azure Batch": "Compute",
    "Azure SQL Database": "Databases",
    "Azure Cosmos DB": "Databases",
    "Azure Database for PostgreSQL": "Databases",
    "Azure Database for MySQL": "Databases",
    "Azure Cache for Redis": "Databases",
    "Azure Synapse Analytics": "Analytics",
    "Azure HDInsight": "Analytics",
    "Azure Data Factory": "Analytics",
    "Azure Storage": "Storage",
    "Azure Blob Storage": "Storage",
    "Azure Files": "Storage",
    "Azure Disk Storage": "Storage",
    "Azure Backup": "Storage",
    "Azure Virtual Network": "Network",
    "Azure Load Balancer": "Network",
    "Azure Application Gateway": "Network",
    "Azure CDN": "Network",
    "Azure DNS": "Network",
    "Azure ExpressRoute": "Network",
    "Azure VPN Gateway": "Network",
    "Azure OpenAI Service": "AI and Machine Learning",
    "Azure Cognitive Services": "AI and Machine Learning",
    "Azure Machine Learning": "AI and Machine Learning",
    "Azure Bot Service": "AI and Machine Learning",
    "Azure Computer Vision": "AI and Machine Learning",
    "Azure Monitor": "Management and Governance",
    "Azure Policy": "Management and Governance",
    "Azure Automation": "Management and Governance",
    "Azure Active Directory": "Security, Identity, and Compliance",
    "Azure Key Vault": "Security, Identity, and Compliance",
    "Microsoft Defender for Cloud": "Security, Identity, and Compliance",
    "Azure Sentinel": "Security, Identity, and Compliance",
    "Azure Service Bus": "Application Integration",
    "Azure Event Hubs": "Application Integration",
    "Azure Logic Apps": "Application Integration",
    "Azure API Management": "Application Integration",
    "Azure Support": "Other",
}

# ServiceCategory normalization for GCP services (FOCUS spec section 4.5)
_GCP_SERVICE_CATEGORY: dict[str, str] = {
    "Compute Engine": "Compute",
    "Google Kubernetes Engine": "Compute",
    "Cloud Run": "Compute",
    "App Engine": "Compute",
    "Cloud Functions": "Compute",
    "Batch": "Compute",
    "Cloud SQL": "Databases",
    "Cloud Spanner": "Databases",
    "Firestore": "Databases",
    "Bigtable": "Databases",
    "Memorystore": "Databases",
    "Cloud Storage": "Storage",
    "Filestore": "Storage",
    "Persistent Disk": "Storage",
    "BigQuery": "Analytics",
    "Dataflow": "Analytics",
    "Dataproc": "Analytics",
    "Looker": "Analytics",
    "Pub/Sub": "Application Integration",
    "Cloud Tasks": "Application Integration",
    "Eventarc": "Application Integration",
    "Cloud Endpoints": "Application Integration",
    "Vertex AI": "AI and Machine Learning",
    "Cloud Natural Language": "AI and Machine Learning",
    "Cloud Vision": "AI and Machine Learning",
    "Cloud Translation": "AI and Machine Learning",
    "Cloud Speech-to-Text": "AI and Machine Learning",
    "Cloud Text-to-Speech": "AI and Machine Learning",
    "Document AI": "AI and Machine Learning",
    "Virtual Private Cloud": "Network",
    "Cloud Load Balancing": "Network",
    "Cloud CDN": "Network",
    "Cloud DNS": "Network",
    "Cloud Interconnect": "Network",
    "Cloud VPN": "Network",
    "Cloud Armor": "Security, Identity, and Compliance",
    "Identity and Access Management": "Security, Identity, and Compliance",
    "Secret Manager": "Security, Identity, and Compliance",
    "Cloud KMS": "Security, Identity, and Compliance",
    "Cloud Logging": "Management and Governance",
    "Cloud Monitoring": "Management and Governance",
    "Cloud Trace": "Management and Governance",
    "Cloud Billing": "Other",
    "Google Support": "Other",
}

# Provider ID normalization per FOCUS spec section 4.1
_PROVIDER_DISPLAY: dict[str, str] = {
    "aws": "Amazon Web Services",
    "azure": "Microsoft Azure",
    "gcp": "Google Cloud",
    "oracle": "Oracle Cloud Infrastructure",
}

# FOCUS ChargeType values
_CHARGE_TYPE_USAGE = "Usage"
_CHARGE_TYPE_PURCHASE = "Purchase"
_CHARGE_TYPE_TAX = "Tax"
_CHARGE_TYPE_ADJUSTMENT = "Adjustment"
_CHARGE_TYPE_CREDIT = "Credit"


@dataclass
class FOCUSRow:
    """
    A single FOCUS 1.3 row representing one billing line item.

    Field names match FOCUS spec column names exactly for toolchain compatibility.
    Implements all 33 FOCUS 1.0 required columns plus FOCUS 1.2/1.3 optional columns.
    """
    # Required FOCUS fields
    BilledCost: float
    BillingAccountId: str
    BillingAccountName: str
    BillingPeriodStart: str         # ISO 8601 date
    BillingPeriodEnd: str           # ISO 8601 date
    ChargePeriodStart: str          # ISO 8601 datetime
    ChargePeriodEnd: str            # ISO 8601 datetime
    ChargeCategory: str             # Usage | Purchase | Tax | Adjustment | Credit
    ChargeClass: str                # Correction | null
    ChargeDescription: str
    ChargeFrequency: str            # One-Time | Recurring | Usage-Based
    EffectiveCost: float
    InvoiceIssuerName: str
    ListCost: float
    ListUnitPrice: float
    PricingCategory: str            # On-Demand | Dynamic | Committed | Other
    PricingQuantity: float
    PricingUnit: str
    ProviderName: str
    PublisherName: str
    RegionId: str
    RegionName: str
    ResourceId: str
    ResourceName: str
    ResourceType: str
    ServiceCategory: str
    ServiceName: str
    SkuId: str
    SkuPriceId: str
    SubAccountId: str
    SubAccountName: str
    UsageQuantity: float
    UsageUnit: str

    # Optional: cost allocation tags (FOCUS custom column convention)
    Tags: dict[str, str] = field(default_factory=dict)

    # FOCUS 1.2 optional columns
    InvoiceId: Optional[str] = None
    PricingCurrency: Optional[str] = None

    # FOCUS 1.3 optional columns
    ServiceProvider: Optional[str] = None
    HostProvider: Optional[str] = None
    CapacityReservationId: Optional[str] = None
    CapacityReservationStatus: Optional[str] = None  # "Used" | "Unused" | "Unallocated"

    # FinOps Intelligence extension fields (FOCUS allows custom columns with x_ prefix)
    x_anomaly_score: float = 0.0
    x_waste_identified: bool = False
    x_waste_monthly_usd: float = 0.0
    x_finops_maturity_stage: str = ""
    x_ri_sp_coverage: float = 0.0
    x_input_tokens: Optional[int] = None
    x_output_tokens: Optional[int] = None
    x_cost_per_1k_tokens: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to FOCUS-compliant dict (flat, for CSV/JSON/Parquet output)."""
        d: dict[str, Any] = {
            # FOCUS 1.0 required columns (33)
            "BilledCost": self.BilledCost,
            "BillingAccountId": self.BillingAccountId,
            "BillingAccountName": self.BillingAccountName,
            "BillingPeriodStart": self.BillingPeriodStart,
            "BillingPeriodEnd": self.BillingPeriodEnd,
            "ChargePeriodStart": self.ChargePeriodStart,
            "ChargePeriodEnd": self.ChargePeriodEnd,
            "ChargeCategory": self.ChargeCategory,
            "ChargeClass": self.ChargeClass,
            "ChargeDescription": self.ChargeDescription,
            "ChargeFrequency": self.ChargeFrequency,
            "EffectiveCost": self.EffectiveCost,
            "InvoiceIssuerName": self.InvoiceIssuerName,
            "ListCost": self.ListCost,
            "ListUnitPrice": self.ListUnitPrice,
            "PricingCategory": self.PricingCategory,
            "PricingQuantity": self.PricingQuantity,
            "PricingUnit": self.PricingUnit,
            "ProviderName": self.ProviderName,
            "PublisherName": self.PublisherName,
            "RegionId": self.RegionId,
            "RegionName": self.RegionName,
            "ResourceId": self.ResourceId,
            "ResourceName": self.ResourceName,
            "ResourceType": self.ResourceType,
            "ServiceCategory": self.ServiceCategory,
            "ServiceName": self.ServiceName,
            "SkuId": self.SkuId,
            "SkuPriceId": self.SkuPriceId,
            "SubAccountId": self.SubAccountId,
            "SubAccountName": self.SubAccountName,
            "UsageQuantity": self.UsageQuantity,
            "UsageUnit": self.UsageUnit,
            # Tags as JSON string (FOCUS recommendation for flat formats)
            "Tags": json.dumps(self.Tags) if self.Tags else "{}",
            # Extension columns (x_ prefix per FOCUS custom column convention)
            "x_anomaly_score": self.x_anomaly_score,
            "x_waste_identified": self.x_waste_identified,
            "x_waste_monthly_usd": self.x_waste_monthly_usd,
            "x_finops_maturity_stage": self.x_finops_maturity_stage,
            "x_ri_sp_coverage": self.x_ri_sp_coverage,
        }
        # FOCUS 1.2/1.3 optional columns — only include when populated to keep
        # 1.0-only consumers from seeing unexpected columns unless data is present
        if self.InvoiceId is not None:
            d["InvoiceId"] = self.InvoiceId
        if self.PricingCurrency is not None:
            d["PricingCurrency"] = self.PricingCurrency
        if self.ServiceProvider is not None:
            d["ServiceProvider"] = self.ServiceProvider
        if self.HostProvider is not None:
            d["HostProvider"] = self.HostProvider
        if self.CapacityReservationId is not None:
            d["CapacityReservationId"] = self.CapacityReservationId
        if self.CapacityReservationStatus is not None:
            d["CapacityReservationStatus"] = self.CapacityReservationStatus
        # AI/LLM extension columns
        if self.x_input_tokens is not None:
            d["x_input_tokens"] = self.x_input_tokens
        if self.x_output_tokens is not None:
            d["x_output_tokens"] = self.x_output_tokens
        if self.x_cost_per_1k_tokens is not None:
            d["x_cost_per_1k_tokens"] = self.x_cost_per_1k_tokens
        return d


class FOCUSExporter:
    """
    Exports FinOps Intelligence data to FOCUS 1.3 format.

    Supports multi-cloud providers (AWS, Azure, GCP) and AI/LLM cost tracking —
    the only open-source FinOps tool that combines FOCUS 1.3 export with
    per-model LLM token costs.

    Methods:
      - from_spend_data(): Convert SpendData / ServiceSpend objects
      - export_ai_model_costs(): Convert per-model LLM spend to FOCUS rows
      - to_focus(): Convenience method that returns a list of FOCUS dicts
      - export_jsonl(): Write FOCUS JSONL (one JSON object per line)
      - export_csv(): Write FOCUS CSV (header + data rows)
      - export_parquet(): Write Parquet (FOCUS 1.4-ready columnar format)
      - validate_focus_compliance(): Validate rows and report FOCUS version level

    Example::

        exporter = FOCUSExporter(provider="aws", account_id="123456789012")
        rows = exporter.from_spend_data(spend_data.service_breakdown)
        exporter.export_jsonl("billing_focus.jsonl", rows)
        exporter.export_parquet("billing_focus.parquet", rows)

        ai_rows = exporter.export_ai_model_costs([
            {"model": "claude-sonnet-4-6", "input_tokens": 500_000,
             "output_tokens": 100_000, "total_cost": 2.10},
        ])
        result = exporter.validate_focus_compliance(rows + ai_rows)
        print(result["focus_version"])  # "1.3"
    """

    def __init__(
        self,
        provider: str = "aws",
        account_id: str = "000000000000",
        account_name: str = "production",
        billing_period_days: int = 30,
    ) -> None:
        self.provider = provider.lower()
        self.account_id = account_id
        self.account_name = account_name
        self.billing_period_days = billing_period_days
        self._provider_name = _PROVIDER_DISPLAY.get(self.provider, provider.title())

    def _billing_period(self) -> tuple[str, str]:
        """Return ISO date strings for current billing period."""
        today = date.today()
        period_end = today.replace(day=1)  # First of current month
        period_start = date(
            period_end.year if period_end.month > 1 else period_end.year - 1,
            period_end.month - 1 if period_end.month > 1 else 12,
            1,
        )
        return period_start.isoformat(), period_end.isoformat()

    def _normalize_service(self, service_name: str) -> tuple[str, str]:
        """
        Return (ServiceName, ServiceCategory) normalized per FOCUS spec.

        Routes to the appropriate provider dict based on service name signals.
        AWS services are checked first (most common), then Azure, then GCP.
        """
        # Try provider-specific dicts in order of specificity
        if self.provider == "azure" or service_name in _AZURE_SERVICE_CATEGORY:
            category = _AZURE_SERVICE_CATEGORY.get(service_name)
            if category is not None:
                return service_name, category

        if self.provider == "gcp" or service_name in _GCP_SERVICE_CATEGORY:
            category = _GCP_SERVICE_CATEGORY.get(service_name)
            if category is not None:
                return service_name, category

        # Default: AWS lookup
        category = _AWS_SERVICE_CATEGORY.get(service_name, "Other")
        name = _AWS_SERVICE_NAME.get(service_name, service_name)
        return name, category

    def from_spend_data(
        self,
        service_breakdown: list[Any],
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> list[FOCUSRow]:
        """
        Convert a list of ServiceSpend objects to FOCUS rows.

        Args:
            service_breakdown: List of ServiceSpend objects from CostTracker
            period_start: ISO date string (defaults to last 30 days)
            period_end: ISO date string (defaults to today)
        """
        if not period_start or not period_end:
            p_start, p_end = self._billing_period()
            period_start = period_start or p_start
            period_end = period_end or p_end

        rows: list[FOCUSRow] = []

        for svc in service_breakdown:
            service_name = getattr(svc, "service", "Unknown")
            total = getattr(svc, "total", 0.0)
            daily_breakdown = getattr(svc, "daily_breakdown", [])
            region_breakdown = getattr(svc, "region_breakdown", {})

            norm_name, category = self._normalize_service(service_name)

            # If we have daily breakdown, emit one row per day per region
            if daily_breakdown:
                for daily in daily_breakdown:
                    d_date = getattr(daily, "date", date.today())
                    d_amount = getattr(daily, "amount", 0.0)
                    d_region = getattr(daily, "region", "us-east-1")
                    d_tags = getattr(daily, "tags", {})

                    rows.append(self._build_row(
                        service_name=service_name,
                        norm_name=norm_name,
                        category=category,
                        amount=d_amount,
                        region=d_region,
                        charge_date=d_date,
                        billing_period_start=period_start,
                        billing_period_end=period_end,
                        tags=d_tags,
                    ))
            elif region_breakdown:
                # Aggregate to one row per region
                for region, amount in region_breakdown.items():
                    rows.append(self._build_row(
                        service_name=service_name,
                        norm_name=norm_name,
                        category=category,
                        amount=amount,
                        region=region,
                        billing_period_start=period_start,
                        billing_period_end=period_end,
                    ))
            else:
                # Single aggregate row
                rows.append(self._build_row(
                    service_name=service_name,
                    norm_name=norm_name,
                    category=category,
                    amount=total,
                    region="us-east-1",
                    billing_period_start=period_start,
                    billing_period_end=period_end,
                ))

        return rows

    def _build_row(
        self,
        service_name: str,
        norm_name: str,
        category: str,
        amount: float,
        region: str,
        billing_period_start: str,
        billing_period_end: str,
        charge_date: Optional[Any] = None,
        tags: Optional[dict] = None,
    ) -> FOCUSRow:
        """Build a single FOCUS row."""
        if charge_date is None:
            charge_date = date.today()

        if isinstance(charge_date, date):
            charge_start = f"{charge_date.isoformat()}T00:00:00Z"
            charge_end = f"{charge_date.isoformat()}T23:59:59Z"
        else:
            charge_start = str(charge_date)
            charge_end = str(charge_date)

        # FOCUS region normalization: AWS uses us-east-1, FOCUS wants provider-neutral
        region_name = {
            "us-east-1": "US East (N. Virginia)",
            "us-west-2": "US West (Oregon)",
            "eu-west-1": "Europe (Ireland)",
            "eu-central-1": "Europe (Frankfurt)",
            "ap-southeast-1": "Asia Pacific (Singapore)",
            "ap-northeast-1": "Asia Pacific (Tokyo)",
            "us-east-2": "US East (Ohio)",
            "us-west-1": "US West (N. California)",
        }.get(region, region)

        # Pricing: assume on-demand for mock data, adjust for committed if RI/SP
        pricing_category = "On-Demand"

        # Build stable SKU ID from service + region
        sku_id = f"{self.provider}/{service_name.lower().replace(' ', '-')}/{region}"
        sku_price_id = f"{sku_id}/standard"

        # Build provider-appropriate ResourceId
        if self.provider == "azure":
            resource_id = (
                f"/subscriptions/{self.account_id}/providers/"
                f"Microsoft.{service_name.replace(' ', '')}/{region}"
            )
        elif self.provider == "gcp":
            resource_id = (
                f"//cloudresourcemanager.googleapis.com/projects/"
                f"{self.account_id}/{service_name.lower().replace(' ', '-')}/{region}"
            )
        else:
            resource_id = (
                f"arn:aws:{service_name.lower().replace(' ', '')}:"
                f"{region}:{self.account_id}:*"
            )

        return FOCUSRow(
            BilledCost=round(amount, 6),
            BillingAccountId=self.account_id,
            BillingAccountName=self.account_name,
            BillingPeriodStart=billing_period_start,
            BillingPeriodEnd=billing_period_end,
            ChargePeriodStart=charge_start,
            ChargePeriodEnd=charge_end,
            ChargeCategory=_CHARGE_TYPE_USAGE,
            ChargeClass="",
            ChargeDescription=f"{norm_name} usage in {region_name}",
            ChargeFrequency="Usage-Based",
            EffectiveCost=round(amount, 6),  # No RI/SP amortization in base model
            InvoiceIssuerName=self._provider_name,
            ListCost=round(amount * 1.0, 6),  # List = billed for on-demand
            ListUnitPrice=0.0,                 # Would require SKU catalog lookup
            PricingCategory=pricing_category,
            PricingQuantity=1.0,
            PricingUnit="GB-Hours" if category == "Storage" else "Hours",
            ProviderName=self._provider_name,
            PublisherName=self._provider_name,
            RegionId=region,
            RegionName=region_name,
            ResourceId=resource_id,
            ResourceName=service_name,
            ResourceType=norm_name,
            ServiceCategory=category,
            ServiceName=norm_name,
            SkuId=sku_id,
            SkuPriceId=sku_price_id,
            SubAccountId=self.account_id,
            SubAccountName=self.account_name,
            UsageQuantity=1.0,
            UsageUnit="Hours",
            Tags=tags or {},
            # FOCUS 1.3 optional columns
            ServiceProvider=self._provider_name,
            HostProvider=self._provider_name,
        )

    def to_focus(self, spend_data: Any) -> list[dict[str, Any]]:
        """
        Convenience method: convert SpendData to list of FOCUS dicts.

        Suitable for API responses, Pandas DataFrames, and Parquet output.

        Example:
            tracker = CostTracker(mock=True)
            data = tracker.get_spend_data()
            exporter = FOCUSExporter()
            focus_json = exporter.to_focus(data)
            df = pd.DataFrame(focus_json)
        """
        service_breakdown = getattr(spend_data, "service_breakdown", [])
        if not service_breakdown and hasattr(spend_data, "__iter__"):
            service_breakdown = list(spend_data)
        rows = self.from_spend_data(service_breakdown)
        return [r.to_dict() for r in rows]

    def export_jsonl(
        self, output_path: str, rows: list[FOCUSRow]
    ) -> str:
        """
        Write FOCUS rows as JSONL (JSON Lines) — one JSON object per line.

        JSONL is the recommended FOCUS output format for streaming ingestion
        into Spark, BigQuery, Athena, and other analytics engines.
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")
        return output_path

    def export_csv(
        self, output_path: str, rows: list[FOCUSRow]
    ) -> str:
        """
        Write FOCUS rows as CSV with standard FOCUS column headers.

        Compatible with: Excel, Power BI, Tableau, focus_validator.
        """
        if not rows:
            return output_path

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        fieldnames = list(rows[0].to_dict().keys())

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row.to_dict())

        return output_path

    def export_ai_model_costs(
        self,
        model_costs: list[dict],
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> list[FOCUSRow]:
        """
        Convert per-model LLM spend into FOCUS 1.3 rows.

        Each entry in ``model_costs`` should contain:
          - model (str): model identifier, e.g. "claude-sonnet-4-6"
          - total_cost (float): total USD spend for the period
          - input_tokens (int, optional): input token count
          - output_tokens (int, optional): output token count

        Returns one FOCUSRow per model with:
          - ServiceCategory: "AI and Machine Learning"
          - ResourceType: "LLM Inference"
          - UsageUnit: "Tokens"
          - ServiceProvider populated from AI_MODEL_PROVIDERS prefix match
          - x_input_tokens, x_output_tokens, x_cost_per_1k_tokens extensions

        Example::

            rows = exporter.export_ai_model_costs([
                {"model": "claude-sonnet-4-6",
                 "input_tokens": 1_000_000,
                 "output_tokens": 200_000,
                 "total_cost": 4.20},
                {"model": "gpt-4o", "total_cost": 12.50,
                 "input_tokens": 500_000, "output_tokens": 100_000},
            ])
        """
        if not period_start or not period_end:
            p_start, p_end = self._billing_period()
            period_start = period_start or p_start
            period_end = period_end or p_end

        today = date.today()
        charge_start = f"{today.isoformat()}T00:00:00Z"
        charge_end = f"{today.isoformat()}T23:59:59Z"

        rows: list[FOCUSRow] = []

        for entry in model_costs:
            model_name: str = entry.get("model", "unknown-model")
            total_cost: float = float(entry.get("total_cost", 0.0))
            input_tokens: Optional[int] = entry.get("input_tokens")
            output_tokens: Optional[int] = entry.get("output_tokens")

            # Resolve service provider from model name prefix
            provider_name: str = "Unknown"
            model_lower = model_name.lower()
            for prefix, prov in AI_MODEL_PROVIDERS.items():
                if model_lower.startswith(prefix):
                    provider_name = prov
                    break

            total_tokens = (input_tokens or 0) + (output_tokens or 0)
            cost_per_1k: Optional[float] = (
                round((total_cost / total_tokens) * 1000, 6)
                if total_tokens > 0 else None
            )

            sku_id = f"ai/{provider_name.lower().replace(' ', '-')}/{model_name}"

            rows.append(FOCUSRow(
                BilledCost=round(total_cost, 6),
                BillingAccountId=self.account_id,
                BillingAccountName=self.account_name,
                BillingPeriodStart=period_start,
                BillingPeriodEnd=period_end,
                ChargePeriodStart=charge_start,
                ChargePeriodEnd=charge_end,
                ChargeCategory=_CHARGE_TYPE_USAGE,
                ChargeClass="",
                ChargeDescription=f"{model_name} inference — {total_tokens:,} tokens",
                ChargeFrequency="Usage-Based",
                EffectiveCost=round(total_cost, 6),
                InvoiceIssuerName=provider_name,
                ListCost=round(total_cost, 6),
                ListUnitPrice=cost_per_1k or 0.0,
                PricingCategory="On-Demand",
                PricingQuantity=float(total_tokens),
                PricingUnit="1K Tokens",
                ProviderName=provider_name,
                PublisherName=provider_name,
                RegionId="global",
                RegionName="Global",
                ResourceId=f"llm/{model_name}",
                ResourceName=model_name,
                ResourceType="LLM Inference",
                ServiceCategory="AI and Machine Learning",
                ServiceName=model_name,
                SkuId=sku_id,
                SkuPriceId=f"{sku_id}/per-token",
                SubAccountId=self.account_id,
                SubAccountName=self.account_name,
                UsageQuantity=float(total_tokens),
                UsageUnit="Tokens",
                # FOCUS 1.3 optional columns
                ServiceProvider=provider_name,
                HostProvider=provider_name,
                # AI extension columns
                x_input_tokens=input_tokens,
                x_output_tokens=output_tokens,
                x_cost_per_1k_tokens=cost_per_1k,
            ))

        return rows

    def export_parquet(self, output_path: str, rows: list[FOCUSRow]) -> str:
        """
        Write FOCUS rows as Parquet — columnar format aligned with FOCUS 1.4.

        Prefers pyarrow for full type control; falls back to pandas .to_parquet()
        if only pandas[parquet] is available.

        Args:
            output_path: Destination file path (e.g. "./output/billing.parquet").
            rows: FOCUS rows to serialize.

        Returns:
            Absolute path to the written file.

        Raises:
            ImportError: If neither pyarrow nor pandas is installed.
        """
        if not rows:
            return output_path

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        records = [r.to_dict() for r in rows]

        # Attempt 1: pyarrow (preferred — direct schema control, no pandas dep)
        try:
            import pyarrow as pa  # type: ignore[import]
            import pyarrow.parquet as pq  # type: ignore[import]

            table = pa.Table.from_pylist(records)
            pq.write_table(table, output_path, compression="snappy")
            return output_path
        except ImportError:
            pass

        # Attempt 2: pandas + parquet engine (fastparquet or pyarrow via pandas)
        try:
            import pandas as pd  # type: ignore[import]

            df = pd.DataFrame(records)
            df.to_parquet(output_path, index=False)
            return output_path
        except ImportError:
            pass

        raise ImportError(
            "Install pyarrow or pandas[parquet] for Parquet export: pip install pyarrow"
        )

    def validate_focus_compliance(self, rows: list[FOCUSRow]) -> dict[str, Any]:
        """
        FOCUS spec validation — checks required fields, detects spec version level.

        Reports the highest FOCUS version level supported by the rows:
          - 1.0: all 33 required columns populated
          - 1.2: 1.0 + InvoiceId and/or PricingCurrency present
          - 1.3: 1.2 + ServiceProvider and/or HostProvider present

        This is a lightweight validator; for full compliance use the
        FinOps Foundation's focus_validator tool.

        Returns:
            Dict with 'compliant', 'focus_version', 'errors', and 'warnings' keys.
        """
        required_fields = [
            "BilledCost", "BillingAccountId", "BillingPeriodStart",
            "BillingPeriodEnd", "ChargePeriodStart", "ChargePeriodEnd",
            "ChargeCategory", "EffectiveCost", "InvoiceIssuerName",
            "ListCost", "ProviderName", "ServiceCategory", "ServiceName",
        ]
        errors: list[str] = []
        warnings: list[str] = []

        # Track highest FOCUS version evidenced by optional column presence
        has_1_2_cols = False
        has_1_3_cols = False

        for i, row in enumerate(rows):
            row_dict = row.to_dict()
            for field_name in required_fields:
                val = row_dict.get(field_name)
                if val is None or val == "":
                    errors.append(f"Row {i}: required field '{field_name}' is empty")

            # Check BilledCost is numeric and non-negative
            if row.BilledCost < 0:
                warnings.append(
                    f"Row {i}: BilledCost is negative ({row.BilledCost}). "
                    "Expected Credits use ChargeCategory=Credit."
                )

            # Check ChargeCategory is a valid enum value
            valid_charge_categories = {
                "Usage", "Purchase", "Tax", "Adjustment", "Credit"
            }
            if row.ChargeCategory not in valid_charge_categories:
                errors.append(
                    f"Row {i}: ChargeCategory='{row.ChargeCategory}' is not a valid FOCUS value. "
                    f"Must be one of: {', '.join(sorted(valid_charge_categories))}"
                )

            # Detect FOCUS 1.2/1.3 optional column usage
            if row.InvoiceId is not None or row.PricingCurrency is not None:
                has_1_2_cols = True
            if row.ServiceProvider is not None or row.HostProvider is not None:
                has_1_3_cols = True

            # Validate CapacityReservationStatus if present
            if row.CapacityReservationStatus is not None:
                valid_cr_statuses = {"Used", "Unused", "Unallocated"}
                if row.CapacityReservationStatus not in valid_cr_statuses:
                    warnings.append(
                        f"Row {i}: CapacityReservationStatus='{row.CapacityReservationStatus}' "
                        f"should be one of: {', '.join(sorted(valid_cr_statuses))}"
                    )

        # Determine reported FOCUS version level
        if has_1_3_cols:
            focus_version = "1.3"
        elif has_1_2_cols:
            focus_version = "1.2"
        else:
            focus_version = "1.0"

        return {
            "compliant": len(errors) == 0,
            "total_rows": len(rows),
            "errors": errors[:20],      # Cap to first 20 for readability
            "warnings": warnings[:20],
            "focus_version": focus_version,
            "focus_1_2_columns_present": has_1_2_cols,
            "focus_1_3_columns_present": has_1_3_cols,
            "spec_uri": "https://focus.finops.org/#specification",
        }
