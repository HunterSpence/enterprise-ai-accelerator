"""
models.py — Pydantic v2 Shared Data Models for MigrationScout V2
================================================================

All shared Pydantic models used across the API, assessor, and other modules.
Enables full OpenAPI documentation and type-safe serialization.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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

    model_config = ConfigDict(use_enum_values=True)


class AssessmentRequest(BaseModel):
    """Request body for POST /assessments."""

    inventory: list[WorkloadInventoryModel] = Field(
        ..., description="Workload inventory to assess", min_length=1
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
    wave_planning_approach: str = Field(
        default="balanced", description="Migration approach: aggressive, balanced, conservative"
    )
    max_workloads_per_wave: int = Field(default=15, ge=1, le=100)


class AssessmentStatusEnum(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
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
    """Response for POST /assessments and GET /assessments/{id}.

    ponytail: mirrors what api.py actually builds (job_id/status/workload_count
    plus the completed-job summary fields it mutates in). The richer
    WorkloadAssessmentResult/AssessmentSummary schemas above are aspirational
    and unused — kept for future API expansion, not part of this contract.
    """

    job_id: str
    status: AssessmentStatusEnum
    workload_count: int
    message: str = ""
    waves_count: int | None = None
    total_p50_weeks: float | None = None
    annual_savings_usd: float | None = None
    break_even_months: float | None = None
    irr_percent: float | None = None
    top_workloads: list[dict[str, Any]] = Field(default_factory=list)


class WavePlanRequest(BaseModel):
    """Request for POST /assessments/{id}/waves."""

    approach: str = Field(
        default="balanced",
        description="Migration approach: aggressive, balanced, conservative",
    )
    max_workloads_per_wave: int = Field(default=15, ge=3, le=50)


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
    """Response for POST /assessments/{id}/waves.

    ponytail: waves is a loose dict shape (matches what api.py builds per
    wave: wave_number/name/workload_count/p10-p90/risk_level/costs/
    convergence_achieved) rather than the richer WaveResult model above,
    which nothing in api.py populates.
    """

    job_id: str
    approach: str
    waves: list[dict[str, Any]]
    total_p50_weeks: float
    gantt_html: str = ""


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
    """Response for GET /assessments/{id}/tco.

    ponytail: mirrors api.py's actual TCOCalculator.analyze_portfolio() ->
    TCOAnalysis field names (npv_3yr, not the aspirational npv_8pct/
    TCOScenario shape above, which nothing populates).
    """

    job_id: str
    annual_savings: float
    total_investment: float
    break_even_months: float
    irr_percent: float
    npv_8pct: float
    contingency_usd: float
    scenarios: list[dict[str, Any]]


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

    job_id: str
    workload_ids: list[str] = Field(
        ..., description="Workloads to move earlier/later", min_length=1
    )
    new_approach: str = Field(
        default="balanced", description="Migration approach: aggressive, balanced, conservative"
    )


class WhatIfResponse(BaseModel):
    """ponytail: mirrors api.py's actual what_if_analysis() return shape."""

    job_id: str
    workload_ids: list[str]
    base_p50_weeks: float
    new_p50_weeks: float
    p50_delta_weeks: float
    npv_delta_usd: float
    risk_delta: str
    impacted_workloads: dict[str, list[str]]
    recommendation: str


class RunbookRequest(BaseModel):
    job_id: str
    use_ai: bool = Field(default=True)


class RunbookResponse(BaseModel):
    """ponytail: mirrors api.py's generate_runbook() return shape (built from
    RunbookGenerator.generate_workload_runbook() -> RunbookResult)."""

    workload_id: str
    workload_name: str
    strategy: str
    runbook_markdown: str
    estimated_hours: float
    risk_level: str
    ai_generated: bool


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: int
    active_jobs: int
