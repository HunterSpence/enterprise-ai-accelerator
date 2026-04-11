"""
models.py — Pydantic v2 Shared Data Models for MigrationScout V2
================================================================

All shared Pydantic models used across the API, assessor, and other modules.
Enables full OpenAPI documentation and type-safe serialization.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MigrationStrategy(str, Enum):
    REHOST = "Rehost"
    REPLATFORM = "Replatform"
    REPURCHASE = "Repurchase"
    REFACTOR = "Refactor"
    RETIRE = "Retire"
    RETAIN = "Retain"

    @property
    def color(self) -> str:
        return {
            MigrationStrategy.REHOST: "green",
            MigrationStrategy.REPLATFORM: "cyan",
            MigrationStrategy.REPURCHASE: "magenta",
            MigrationStrategy.REFACTOR: "yellow",
            MigrationStrategy.RETIRE: "red",
            MigrationStrategy.RETAIN: "blue",
        }[self]

    @property
    def label(self) -> str:
        return {
            MigrationStrategy.REHOST: "lift",
            MigrationStrategy.REPLATFORM: "tune",
            MigrationStrategy.REPURCHASE: "swap",
            MigrationStrategy.REFACTOR: "arch",
            MigrationStrategy.RETIRE: "EOL",
            MigrationStrategy.RETAIN: "keep",
        }[self]


class ComplexityLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class BusinessCriticality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DatabaseType(str, Enum):
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    MSSQL = "mssql"
    ORACLE = "oracle"
    MONGODB = "mongodb"
    REDIS = "redis"
    CASSANDRA = "cassandra"
    DYNAMODB = "dynamodb"
    NONE = "none"


class WorkloadInventoryModel(BaseModel):
    """Pydantic v2 model for workload inventory input."""

    id: str = Field(..., description="Unique workload identifier", examples=["ec-web-01"])
    name: str = Field(..., description="Human-readable workload name")
    workload_type: str = Field(
        ...,
        description="Type: web_app, database, batch_job, middleware, legacy, microservice",
        examples=["web_app"],
    )
    language: str = Field(default="unknown", description="Primary programming language")
    framework: str = Field(default="unknown", description="Primary framework")
    os: str = Field(default="Linux", description="Operating system")
    cpu_cores: int = Field(default=4, ge=1, le=1024, description="vCPU count")
    ram_gb: int = Field(default=16, ge=1, le=16384, description="RAM in gigabytes")
    storage_gb: int = Field(default=200, ge=1, description="Storage in gigabytes")
    monthly_on_prem_cost: float = Field(
        default=2500.0, ge=0, description="Current monthly on-prem cost USD"
    )
    age_years: float = Field(default=5.0, ge=0, description="Application age in years")
    has_external_dependencies: bool = Field(default=False)
    dependency_count: int = Field(default=0, ge=0, description="Number of direct dependencies")
    has_custom_hardware: bool = Field(default=False)
    is_stateful: bool = Field(default=True, description="Whether the workload manages state")
    database_type: DatabaseType | None = Field(default=None)
    business_criticality: BusinessCriticality = Field(default=BusinessCriticality.MEDIUM)
    team_cloud_familiarity: str = Field(
        default="medium",
        description="Team cloud skill level: low, medium, high",
    )
    last_major_update_years: float = Field(default=2.0, ge=0)
    license_type: str = Field(
        default="open_source",
        description="License type: open_source, commercial, custom",
    )
    license_cost_annual: float = Field(default=0.0, ge=0, description="Annual license cost USD")
    containerized: bool = Field(default=False, description="Already containerized?")
    team_size: int = Field(default=5, ge=1, description="App team size (FTEs)")
    notes: str = Field(default="")

    class Config:
        use_enum_values = True


class AssessmentRequest(BaseModel):
    """Request body for POST /assessments."""

    inventory: list[WorkloadInventoryModel] = Field(
        ..., description="Workload inventory to assess"
    )
    use_ml_classifier: bool = Field(default=True, description="Use ML gradient boosting classifier")
    use_ai_enrichment: bool = Field(
        default=True, description="Use Claude Haiku for low-confidence workloads"
    )
    confidence_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Confidence below this triggers AI enrichment",
    )
    project_name: str = Field(default="Migration Assessment", description="Project name for reports")


class AssessmentStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class FeatureImportance(BaseModel):
    feature: str
    importance: float
    direction: str = Field(description="'increases' or 'decreases' the predicted strategy")


class WorkloadAssessmentResult(BaseModel):
    """Result for a single workload assessment."""

    workload_id: str
    workload_name: str
    strategy: str
    cloud_readiness_score: int = Field(ge=0, le=100)
    complexity: str
    risk_score: int = Field(ge=0, le=100)
    migration_readiness_score: int = Field(
        ge=0, le=100, description="0-100 readiness based on dependency + complexity"
    )
    estimated_migration_weeks: float
    estimated_migration_cost_usd: float
    monthly_cloud_cost_usd: float
    annual_savings_usd: float
    three_year_net_benefit: float
    target_service: str
    quick_wins: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    ai_rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    ml_classified: bool = Field(default=False)
    ai_enriched: bool = Field(default=False)
    top_feature_importances: list[FeatureImportance] = Field(default_factory=list)


class AssessmentSummary(BaseModel):
    """Summary statistics for a full assessment run."""

    total_workloads: int
    strategy_distribution: dict[str, int]
    total_annual_savings_usd: float
    total_migration_cost_usd: float
    three_year_net_benefit: float
    payback_months: float
    average_cloud_readiness: float
    high_risk_count: int
    ml_classified_count: int
    ai_enriched_count: int


class AssessmentResponse(BaseModel):
    """Response for GET /assessments/{id}."""

    job_id: str
    status: AssessmentStatusEnum
    project_name: str
    created_at: datetime
    completed_at: datetime | None = None
    progress_pct: float = Field(default=0.0, ge=0, le=100)
    results: list[WorkloadAssessmentResult] = Field(default_factory=list)
    summary: AssessmentSummary | None = None
    error: str | None = None


class WavePlanRequest(BaseModel):
    """Request for POST /assessments/{id}/waves."""

    strategy: str = Field(
        default="balanced",
        description="Migration strategy: aggressive, balanced, conservative",
    )
    max_workloads_per_wave: int = Field(default=15, ge=3, le=50)
    max_waves: int = Field(default=6, ge=2, le=12)
    monte_carlo_iterations: int = Field(default=10000, ge=1000, le=50000)


class WaveConfidenceInterval(BaseModel):
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float


class WaveResult(BaseModel):
    """Result for a single migration wave."""

    wave_number: int
    name: str
    workload_ids: list[str]
    workload_names: list[str]
    strategies: list[str]
    estimated_duration_weeks: float
    confidence_interval: WaveConfidenceInterval
    total_migration_cost_usd: float
    total_monthly_savings_usd: float
    risk_level: str
    risk_score: float
    is_critical_path: bool
    notes: str = ""


class MonteCarloSummary(BaseModel):
    iterations: int
    p10_weeks: float
    p25_weeks: float
    p50_weeks: float
    p75_weeks: float
    p90_weeks: float
    min_weeks: float
    max_weeks: float
    mean_weeks: float
    std_weeks: float
    convergence_achieved: bool
    p50_cost: float
    p80_cost: float
    p95_cost: float


class WavePlanResponse(BaseModel):
    """Response for POST /assessments/{id}/waves."""

    assessment_id: str
    migration_strategy: str
    waves: list[WaveResult]
    monte_carlo: MonteCarloSummary
    total_workloads: int
    total_migration_cost_usd: float
    total_annual_savings_usd: float
    critical_path_weeks: float
    generated_at: datetime


class TCOScenario(BaseModel):
    name: str
    strategy: str
    year1_cost: float
    year2_cost: float
    year3_cost: float
    total_3yr: float
    npv_3yr: float
    break_even_months: float
    irr_percent: float
    recommendation: str


class TCOResponse(BaseModel):
    """Response for GET /assessments/{id}/tco."""

    assessment_id: str
    on_prem_monthly_total: float
    cloud_monthly_total: float
    monthly_savings: float
    annual_savings: float
    migration_cost: float
    break_even_months: float
    npv_3yr: float
    npv_5yr: float
    irr_percent: float
    three_year_net_benefit: float
    five_year_net_benefit: float
    scenarios: list[TCOScenario]
    cost_breakdown: dict[str, Any]
    generated_at: datetime


class DependencyNodeJSON(BaseModel):
    id: str
    name: str
    workload_type: str
    business_criticality: str
    strategy: str
    betweenness_centrality: float
    in_degree: int
    out_degree: int
    is_critical_path: bool
    migration_readiness_score: int
    scc_id: str | None = None
    blast_radius: list[str] = Field(default_factory=list)


class DependencyEdgeJSON(BaseModel):
    source: str
    target: str
    dependency_type: str
    strength: str
    traffic_mbps: float
    calls_per_hour: int


class DependencyGraphResponse(BaseModel):
    nodes: list[DependencyNodeJSON]
    edges: list[DependencyEdgeJSON]
    scc_count: int
    circular_dependency_groups: list[list[str]]
    critical_path: list[str]
    hub_services: list[str] = Field(description="Top 5 services by betweenness centrality")
    mermaid_diagram: str
    d3_json: dict[str, Any]


class WhatIfRequest(BaseModel):
    """Request for POST /what-if."""

    assessment_id: str
    prioritize_workload_ids: list[str] = Field(
        ..., description="Move these workloads to Wave 1"
    )
    exclude_workload_ids: list[str] = Field(default_factory=list)
    scenario_name: str = Field(default="What-If Scenario")


class WhatIfResponse(BaseModel):
    scenario_name: str
    original_plan_weeks_p50: float
    new_plan_weeks_p50: float
    delta_weeks: float
    original_wave1_count: int
    new_wave1_count: int
    dependency_violations: list[str] = Field(
        description="Workloads that cannot be moved (unmet dependencies)"
    )
    risk_delta: float
    cost_delta: float
    recommendation: str
    new_wave_plan: WavePlanResponse


class RunbookRequest(BaseModel):
    workload_id: str
    use_ai: bool = Field(default=True)


class RunbookResponse(BaseModel):
    workload_id: str
    workload_name: str
    strategy: str
    target_service: str
    estimated_total_hours: float
    ai_generated: bool
    markdown_content: str
    generated_at: datetime


class HealthResponse(BaseModel):
    status: str
    version: str
    ml_model_loaded: bool
    ai_available: bool
