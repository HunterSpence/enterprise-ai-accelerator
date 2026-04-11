"""
Shared Pydantic v2 models for CloudIQ V2.

All API request/response schemas, internal domain types, and event
messages are defined here to ensure a single source of truth.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ScanStatus(str, Enum):
    """Lifecycle states for an async infrastructure scan."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CloudProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


# ---------------------------------------------------------------------------
# Scan API
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    """POST /scan request body."""

    provider: CloudProvider = CloudProvider.AWS
    regions: list[str] = Field(default_factory=list)
    profile_name: str | None = None
    include_k8s: bool = False
    dry_run: bool = False

    @validator("regions")
    @classmethod
    def normalize_regions(cls, v: list[str]) -> list[str]:
        return [r.lower().strip() for r in v]


class ScanProgressEvent(BaseModel):
    """WebSocket message emitted during a running scan."""

    job_id: str
    stage: str
    message: str
    progress_pct: float = Field(ge=0.0, le=100.0)
    elapsed_seconds: float
    timestamp: datetime


class ScanResultSummary(BaseModel):
    """Lightweight summary embedded in GET /scan/{job_id} response."""

    total_resources: int
    monthly_cost_usd: float
    total_waste_usd: float
    total_savings_usd: float
    anomalies_detected: int
    critical_findings: int
    regions_scanned: list[str]


class ScanResponse(BaseModel):
    """GET /scan/{job_id} response."""

    job_id: str
    status: ScanStatus
    provider: CloudProvider
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    summary: ScanResultSummary | None = None
    result_url: str | None = None


# ---------------------------------------------------------------------------
# Recommendations API
# ---------------------------------------------------------------------------


class WasteRecommendation(BaseModel):
    """A single cost-waste finding surfaced via GET /recommendations."""

    id: str
    category: str
    resource_id: str
    resource_type: str
    region: str
    provider: CloudProvider = CloudProvider.AWS
    monthly_waste_usd: float
    annual_waste_usd: float
    description: str
    recommendation: str
    severity: Severity
    tags: dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)
    effort: str = "low"  # low | medium | high


class RecommendationsResponse(BaseModel):
    """Paginated recommendations list."""

    items: list[WasteRecommendation]
    total: int
    page: int
    page_size: int
    total_monthly_waste_usd: float
    total_annual_waste_usd: float


# ---------------------------------------------------------------------------
# NL Query API
# ---------------------------------------------------------------------------


class NLQueryRequest(BaseModel):
    """POST /query request body."""

    question: str = Field(...)
    session_id: str | None = None
    include_supporting_data: bool = True


class NLQueryResponse(BaseModel):
    """POST /query response."""

    question: str
    answer: str
    session_id: str
    supporting_data: list[dict[str, Any]] = Field(default_factory=list)
    model_used: str
    tokens_used: int
    timestamp: datetime


# ---------------------------------------------------------------------------
# Terraform API
# ---------------------------------------------------------------------------


class TerraformGenerateRequest(BaseModel):
    """POST /terraform/generate request body."""

    resource_ids: list[str] = Field(...)
    output_format: str = "modules"  # "modules" | "flat"
    include_security_hardening: bool = True
    include_cost_comments: bool = True
    remote_state_bucket: str | None = None
    remote_state_key: str = "cloudiq/terraform.tfstate"
    remote_state_region: str = "us-east-1"
    dynamodb_lock_table: str = "cloudiq-terraform-locks"


class TerraformFile(BaseModel):
    filename: str
    content: str
    size_bytes: int


class TerraformGenerateResponse(BaseModel):
    """POST /terraform/generate response."""

    job_id: str
    files: list[TerraformFile]
    total_resources: int
    estimated_monthly_cost_usd: float
    security_findings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class DependencyStatus(BaseModel):
    name: str
    healthy: bool
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded" | "unhealthy"
    version: str
    uptime_seconds: float
    dependencies: list[DependencyStatus]
    timestamp: datetime


# ---------------------------------------------------------------------------
# Anomaly / ML models
# ---------------------------------------------------------------------------


class AnomalyAlert(BaseModel):
    """An anomaly detected by the ML engine."""

    alert_id: str
    resource_id: str
    resource_type: str
    region: str
    provider: CloudProvider = CloudProvider.AWS
    anomaly_score: float = Field(ge=0.0, le=1.0)
    cost_impact_usd: float
    description: str
    detected_at: datetime
    severity: Severity
    dimensions: dict[str, float] = Field(default_factory=dict)


class CostForecast(BaseModel):
    """30/60/90-day cost forecast with confidence bands."""

    horizon_days: int
    p10_usd: float
    p50_usd: float
    p90_usd: float
    budget_exhaustion_date: datetime | None = None
    trend_direction: str  # "increasing" | "decreasing" | "stable"
    monthly_growth_rate_pct: float


class WhatIfScenario(BaseModel):
    """Cost savings projection if top recommendations implemented."""

    scenario_name: str
    recommendations_applied: list[str]
    current_monthly_cost_usd: float
    projected_monthly_cost_usd: float
    monthly_savings_usd: float
    annual_savings_usd: float
    payback_months: float | None = None


# ---------------------------------------------------------------------------
# Multi-cloud
# ---------------------------------------------------------------------------


class CloudAccountSummary(BaseModel):
    provider: CloudProvider
    account_id: str
    display_name: str
    monthly_cost_usd: float
    resource_count: int
    waste_usd: float
    currency: str = "USD"


class MultiCloudSummary(BaseModel):
    """Aggregated view across all cloud providers."""

    accounts: list[CloudAccountSummary]
    total_monthly_cost_usd: float
    total_waste_usd: float
    total_resources: int
    generated_at: datetime
