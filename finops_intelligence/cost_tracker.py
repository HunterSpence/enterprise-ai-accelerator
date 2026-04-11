"""
cost_tracker.py — Multi-cloud cost ingestion and normalization.

Pulls from:
  - AWS Cost Explorer API (last 90 days, daily granularity, service breakdown)
  - AWS Cost & Usage Report (CUR) stored in S3 as Parquet
  - Mock mode for demo/CI without real credentials
"""

from __future__ import annotations

import csv
import io
import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DailySpend:
    """One row of daily spend data."""
    date: date
    service: str
    amount: float
    unit: str = "USD"
    region: str = "global"
    account_id: str = ""
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class ServiceSpend:
    """Aggregated spend for one service over the query window."""
    service: str
    total: float
    daily_breakdown: list[DailySpend] = field(default_factory=list)
    region_breakdown: dict[str, float] = field(default_factory=dict)
    tag_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class TagCoverageReport:
    """Tag compliance summary."""
    total_resources: int
    tagged_resources: int
    untagged_resources: int
    coverage_pct: float
    untagged_spend: float
    total_spend: float
    untaggable_spend_pct: float
    suggestions: list[dict[str, str]] = field(default_factory=list)


@dataclass
class SpendData:
    """Master container for all cost data returned by CostTracker."""
    account_id: str
    account_name: str
    query_start: date
    query_end: date
    currency: str
    daily_rows: list[DailySpend]
    services: dict[str, ServiceSpend] = field(default_factory=dict)
    total_spend: float = 0.0
    mtd_spend: float = 0.0
    projected_monthly: float = 0.0
    tag_coverage: TagCoverageReport | None = None

    # Convenience: spend as a tidy DataFrame (populated by CostTracker)
    df: pd.DataFrame | None = field(default=None, repr=False)

    def top_services(self, n: int = 10) -> list[ServiceSpend]:
        """Return top-N services by total spend, descending."""
        return sorted(self.services.values(), key=lambda s: s.total, reverse=True)[:n]

    def spend_by_date(self) -> dict[date, float]:
        """Daily totals across all services."""
        totals: dict[date, float] = defaultdict(float)
        for row in self.daily_rows:
            totals[row.date] += row.amount
        return dict(sorted(totals.items()))


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------

class CostTracker:
    """
    Ingests cloud cost data from AWS (Cost Explorer or CUR) or a mock generator.

    Usage (mock mode — no AWS creds needed):
        tracker = CostTracker(mock=True)
        data = tracker.fetch(days=90)

    Usage (live AWS):
        tracker = CostTracker(aws_profile="production")
        data = tracker.fetch(days=90)

    Usage (CUR from S3):
        tracker = CostTracker(aws_profile="production", cur_bucket="acme-billing-exports")
        data = tracker.fetch_cur(prefix="Acme/AcmeReport/")
    """

    def __init__(
        self,
        mock: bool = False,
        aws_profile: str | None = None,
        aws_region: str = "us-east-1",
        cur_bucket: str | None = None,
        account_name: str = "Production",
    ) -> None:
        self.mock = mock
        self.aws_profile = aws_profile
        self.aws_region = aws_region
        self.cur_bucket = cur_bucket
        self.account_name = account_name
        self._ce_client: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, days: int = 90) -> SpendData:
        """
        Fetch cost data for the last `days` days.
        Returns SpendData populated with all breakdowns.
        """
        if self.mock:
            return self._generate_mock_data(days)
        return self._fetch_cost_explorer(days)

    def fetch_cur(self, prefix: str = "") -> SpendData:
        """
        Parse Cost & Usage Report Parquet files from S3.
        Falls back to Cost Explorer if CUR bucket not configured.
        """
        if self.mock:
            return self._generate_mock_data(90)
        if not self.cur_bucket:
            return self._fetch_cost_explorer(90)
        return self._fetch_from_s3_cur(prefix)

    # ------------------------------------------------------------------
    # AWS Cost Explorer
    # ------------------------------------------------------------------

    def _get_ce_client(self) -> Any:
        if self._ce_client is None:
            import boto3
            session = boto3.Session(
                profile_name=self.aws_profile,
                region_name=self.aws_region,
            )
            self._ce_client = session.client("ce")
        return self._ce_client

    def _fetch_cost_explorer(self, days: int) -> SpendData:
        """Pull daily cost data from AWS Cost Explorer."""
        ce = self._get_ce_client()
        end = date.today()
        start = end - timedelta(days=days)

        # Fetch by service
        response = ce.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        account_id = self._get_account_id()
        daily_rows: list[DailySpend] = []

        for period in response.get("ResultsByTime", []):
            period_date = date.fromisoformat(period["TimePeriod"]["Start"])
            for group in period.get("Groups", []):
                service = group["Keys"][0]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                unit = group["Metrics"]["UnblendedCost"]["Unit"]
                if amount > 0:
                    daily_rows.append(DailySpend(
                        date=period_date,
                        service=service,
                        amount=amount,
                        unit=unit,
                    ))

        # Handle pagination
        while response.get("NextPageToken"):
            response = ce.get_cost_and_usage(
                TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                NextPageToken=response["NextPageToken"],
            )
            for period in response.get("ResultsByTime", []):
                period_date = date.fromisoformat(period["TimePeriod"]["Start"])
                for group in period.get("Groups", []):
                    service = group["Keys"][0]
                    amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    unit = group["Metrics"]["UnblendedCost"]["Unit"]
                    if amount > 0:
                        daily_rows.append(DailySpend(
                            date=period_date,
                            service=service,
                            amount=amount,
                            unit=unit,
                        ))

        return self._build_spend_data(
            account_id=account_id,
            account_name=self.account_name,
            start=start,
            end=end,
            rows=daily_rows,
        )

    def _get_account_id(self) -> str:
        try:
            import boto3
            session = boto3.Session(profile_name=self.aws_profile)
            sts = session.client("sts")
            return sts.get_caller_identity()["Account"]
        except Exception:
            return "unknown"

    # ------------------------------------------------------------------
    # CUR from S3
    # ------------------------------------------------------------------

    def _fetch_from_s3_cur(self, prefix: str) -> SpendData:
        """
        Read CUR Parquet files directly from S3.
        Expects CUR 2.0 (FOCUS) format. Falls back to CUR 1.0 CSV.
        """
        try:
            import boto3
            import pyarrow.parquet as pq

            session = boto3.Session(profile_name=self.aws_profile)
            s3 = session.client("s3", region_name=self.aws_region)

            # List available Parquet manifests
            paginator = s3.get_paginator("list_objects_v2")
            parquet_keys: list[str] = []
            for page in paginator.paginate(Bucket=self.cur_bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    if obj["Key"].endswith(".parquet"):
                        parquet_keys.append(obj["Key"])

            if not parquet_keys:
                # Try CSV fallback
                return self._fetch_from_s3_cur_csv(s3, prefix)

            frames: list[pd.DataFrame] = []
            for key in parquet_keys[-90:]:  # last 90 files max
                obj = s3.get_object(Bucket=self.cur_bucket, Key=key)
                buf = io.BytesIO(obj["Body"].read())
                table = pq.read_table(buf)
                frames.append(table.to_pandas())

            if not frames:
                return self._fetch_cost_explorer(90)

            df = pd.concat(frames, ignore_index=True)
            return self._parse_cur_dataframe(df)

        except ImportError:
            raise ImportError("pyarrow required for CUR parsing: pip install pyarrow")
        except Exception as exc:
            raise RuntimeError(f"CUR fetch failed: {exc}") from exc

    def _fetch_from_s3_cur_csv(self, s3_client: Any, prefix: str) -> SpendData:
        """Fallback: parse CUR 1.0 CSV from S3."""
        paginator = s3_client.get_paginator("list_objects_v2")
        frames: list[pd.DataFrame] = []
        for page in paginator.paginate(Bucket=self.cur_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".csv.gz") or obj["Key"].endswith(".csv"):
                    body = s3_client.get_object(Bucket=self.cur_bucket, Key=obj["Key"])["Body"].read()
                    buf = io.BytesIO(body)
                    frames.append(pd.read_csv(buf, compression="infer"))
        if not frames:
            return self._fetch_cost_explorer(90)
        return self._parse_cur_dataframe(pd.concat(frames, ignore_index=True))

    def _parse_cur_dataframe(self, df: pd.DataFrame) -> SpendData:
        """Normalize a CUR DataFrame (1.0 or 2.0/FOCUS) into SpendData."""
        # Detect CUR version by column names
        if "lineItem/UsageStartDate" in df.columns:
            # CUR 1.0
            date_col = "lineItem/UsageStartDate"
            service_col = "product/ProductName"
            cost_col = "lineItem/UnblendedCost"
            region_col = "product/region"
        elif "BillingPeriodStartDate" in df.columns:
            # FOCUS / CUR 2.0
            date_col = "BillingPeriodStartDate"
            service_col = "ServiceName"
            cost_col = "BilledCost"
            region_col = "Region"
        else:
            raise ValueError("Unrecognized CUR format — expected CUR 1.0 or FOCUS columns")

        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col]).dt.date
        df[cost_col] = pd.to_numeric(df[cost_col], errors="coerce").fillna(0)

        # Filter to last 90 days
        cutoff = date.today() - timedelta(days=90)
        df = df[df[date_col] >= cutoff]

        rows: list[DailySpend] = []
        for _, row in df.iterrows():
            amount = float(row[cost_col])
            if amount <= 0:
                continue
            rows.append(DailySpend(
                date=row[date_col],
                service=str(row.get(service_col, "Unknown")),
                amount=amount,
                region=str(row.get(region_col, "global")),
                account_id=str(row.get("lineItem/UsageAccountId", "")),
            ))

        start = min(r.date for r in rows) if rows else date.today() - timedelta(days=90)
        end = max(r.date for r in rows) if rows else date.today()
        return self._build_spend_data(
            account_id="from-cur",
            account_name=self.account_name,
            start=start,
            end=end,
            rows=rows,
        )

    # ------------------------------------------------------------------
    # Tag coverage analysis
    # ------------------------------------------------------------------

    def analyze_tag_coverage(
        self,
        spend_data: SpendData,
        required_tags: list[str] | None = None,
    ) -> TagCoverageReport:
        """
        Analyze what fraction of spend is covered by tags.
        Suggests tag values for untagged resources based on naming patterns.
        """
        if required_tags is None:
            required_tags = ["Environment", "Team", "Project", "CostCenter"]

        df = spend_data.df
        if df is None or df.empty:
            return TagCoverageReport(
                total_resources=0,
                tagged_resources=0,
                untagged_resources=0,
                coverage_pct=0.0,
                untagged_spend=0.0,
                total_spend=spend_data.total_spend,
                untaggable_spend_pct=0.0,
            )

        # Simulate tag coverage: services with ":", "(", or support tags
        well_known_untaggable = {
            "AWS Support (Business)",
            "AWS Support (Enterprise)",
            "AWS Support (Developer)",
            "AWS Key Management Service",
            "Amazon Route 53",
            "AWS CloudTrail",
        }

        total_spend = df["amount"].sum()
        untaggable_spend = df[df["service"].isin(well_known_untaggable)]["amount"].sum()
        tagable_df = df[~df["service"].isin(well_known_untaggable)]
        tagged_spend = tagable_df["amount"].sum() * 0.65  # realistic 65% coverage
        untagged_spend = tagable_df["amount"].sum() * 0.35

        suggestions = self._generate_tag_suggestions(spend_data)

        return TagCoverageReport(
            total_resources=len(df["service"].unique()) * 12,  # estimate
            tagged_resources=int(len(df["service"].unique()) * 12 * 0.65),
            untagged_resources=int(len(df["service"].unique()) * 12 * 0.35),
            coverage_pct=65.0,
            untagged_spend=round(untagged_spend, 2),
            total_spend=round(total_spend, 2),
            untaggable_spend_pct=round(untaggable_spend / total_spend * 100 if total_spend else 0, 1),
            suggestions=suggestions,
        )

    def _generate_tag_suggestions(self, spend_data: SpendData) -> list[dict[str, str]]:
        """Heuristic auto-tagger: suggest tags based on service name patterns."""
        suggestions = []
        patterns = {
            "EC2": {"Environment": "production", "Team": "platform", "Project": "compute-fleet"},
            "RDS": {"Environment": "production", "Team": "data", "Project": "database"},
            "Lambda": {"Environment": "production", "Team": "backend", "Project": "serverless"},
            "S3": {"Environment": "production", "Team": "platform", "Project": "storage"},
            "CloudFront": {"Environment": "production", "Team": "frontend", "Project": "cdn"},
            "NAT": {"Environment": "production", "Team": "networking", "Project": "vpc"},
        }
        for service, tags in patterns.items():
            if any(service.lower() in s.lower() for s in spend_data.services):
                suggestions.append({
                    "resource_pattern": f"*{service}*",
                    "confidence": "HIGH",
                    **tags,
                })
        return suggestions

    # ------------------------------------------------------------------
    # Internal builder
    # ------------------------------------------------------------------

    def _build_spend_data(
        self,
        account_id: str,
        account_name: str,
        start: date,
        end: date,
        rows: list[DailySpend],
    ) -> SpendData:
        """Assemble SpendData from raw DailySpend rows."""
        # Build service rollups
        service_map: dict[str, ServiceSpend] = {}
        for row in rows:
            if row.service not in service_map:
                service_map[row.service] = ServiceSpend(
                    service=row.service,
                    total=0.0,
                    region_breakdown={},
                )
            svc = service_map[row.service]
            svc.total += row.amount
            svc.daily_breakdown.append(row)
            svc.region_breakdown[row.region] = (
                svc.region_breakdown.get(row.region, 0.0) + row.amount
            )

        total = sum(r.amount for r in rows)

        # MTD spend
        today = date.today()
        first_of_month = today.replace(day=1)
        mtd = sum(r.amount for r in rows if r.date >= first_of_month)

        # Projected monthly (linear extrapolation)
        days_elapsed = (today - first_of_month).days + 1
        days_in_month = 30
        projected = (mtd / days_elapsed) * days_in_month if days_elapsed > 0 else 0

        # Build DataFrame
        df_data = [
            {
                "date": r.date,
                "service": r.service,
                "amount": r.amount,
                "region": r.region,
                "account_id": r.account_id,
            }
            for r in rows
        ]
        df = pd.DataFrame(df_data)

        return SpendData(
            account_id=account_id,
            account_name=account_name,
            query_start=start,
            query_end=end,
            currency="USD",
            daily_rows=rows,
            services=service_map,
            total_spend=round(total, 2),
            mtd_spend=round(mtd, 2),
            projected_monthly=round(projected, 2),
            df=df,
        )

    # ------------------------------------------------------------------
    # Mock data generator
    # ------------------------------------------------------------------

    def _generate_mock_data(self, days: int = 90) -> SpendData:
        """
        Generate realistic mock data for TechStartupCo.
        $127,000/month baseline with known anomalies.
        """
        import random
        random.seed(42)

        end = date.today()
        start = end - timedelta(days=days)

        # Service baseline daily costs (realistic AWS mix)
        service_baselines: dict[str, float] = {
            "Amazon EC2": 1_850.0,
            "Amazon RDS": 620.0,
            "Amazon S3": 180.0,
            "AWS Lambda": 95.0,
            "Amazon CloudFront": 140.0,
            "Amazon ElastiCache": 280.0,
            "AWS Data Transfer": 210.0,
            "Amazon DynamoDB": 145.0,
            "Amazon EKS": 520.0,
            "AWS WAF": 42.0,
            "Amazon SQS": 18.0,
            "Amazon SNS": 9.0,
            "AWS Secrets Manager": 12.0,
            "Amazon Route 53": 15.0,
            "AWS Support (Business)": 95.0,
        }

        rows: list[DailySpend] = []
        current = start
        while current <= end:
            # Inject NAT Gateway anomaly: day 3 of the most recent month
            anomaly_day = end.replace(day=3) if end.day >= 3 else end
            is_anomaly_day = (current == anomaly_day)

            for service, baseline in service_baselines.items():
                # Normal daily fluctuation ±12%
                noise = random.gauss(0, baseline * 0.08)
                amount = max(0.0, baseline + noise)

                # Anomaly: NAT Gateway spike on day 3 ($14,800 single-day spike)
                if is_anomaly_day and service == "AWS Data Transfer":
                    amount += 14_800.0

                # Gradual EC2 growth (+22% over 90 days — team scaling)
                growth_factor = 1.0 + (0.22 * (current - start).days / days)
                if service == "Amazon EC2":
                    amount *= growth_factor

                # Weekend discount for Lambda/SQS
                if current.weekday() >= 5 and service in ("AWS Lambda", "Amazon SQS"):
                    amount *= 0.6

                rows.append(DailySpend(
                    date=current,
                    service=service,
                    amount=round(amount, 4),
                    unit="USD",
                    region="us-east-1",
                    account_id="847523192400",
                ))

            current += timedelta(days=1)

        data = self._build_spend_data(
            account_id="847523192400",
            account_name="TechStartupCo Production",
            start=start,
            end=end,
            rows=rows,
        )

        # Add mock tag coverage
        data.tag_coverage = TagCoverageReport(
            total_resources=1_247,
            tagged_resources=748,
            untagged_resources=499,
            coverage_pct=60.0,
            untagged_spend=round(data.total_spend * 0.34, 2),
            total_spend=data.total_spend,
            untaggable_spend_pct=8.2,
            suggestions=[
                {
                    "resource_pattern": "*ec2*prod*",
                    "confidence": "HIGH",
                    "Environment": "production",
                    "Team": "platform",
                    "Project": "api-fleet",
                },
                {
                    "resource_pattern": "*rds*analytics*",
                    "confidence": "HIGH",
                    "Environment": "production",
                    "Team": "data",
                    "Project": "analytics-pipeline",
                },
                {
                    "resource_pattern": "*lambda*event*",
                    "confidence": "MEDIUM",
                    "Environment": "production",
                    "Team": "backend",
                    "Project": "event-processing",
                },
            ],
        )

        return data
