"""
MigrationScout V2 — ML-Enhanced Cloud Migration Planning
=========================================================

Automates the $50K-$200K cloud migration assessment that consulting firms
do manually. One engineer replaces a 5-person consulting team in 6 weeks.

V2 additions:
    models            — Pydantic v2 API models (AssessmentRequest/Response, etc.)
    api               — FastAPI async REST API + WebSocket progress streaming
    report_generator  — HTML business case with SVG charts + Claude Sonnet exec summary
    integrations/     — ServiceNow, Jira, Confluence, AWS Migration Hub

V2 upgrades:
    assessor          — GradientBoosting ML classifier (600-sample training) + SHAP importance
    dependency_mapper — SCC, betweenness centrality, blast radius simulation, D3 + Mermaid export
    wave_planner      — 10,000-iteration Monte Carlo, P10-P90 CIs, HTML Gantt, 3 approaches
    tco_calculator    — 3 scenarios, IRR, NPV, openpyxl Excel export
    runbook_generator — Claude Sonnet 4.6, Pyramid Principle framing
    demo              — 75 workloads, Oracle $420K elimination, SAP RISE, SCC loop scene
"""

from .assessor import (
    MigrationStrategy,
    WorkloadAssessment,
    WorkloadAssessor,
    WorkloadInventory,
)
from .dependency_mapper import (
    DependencyEdge,
    DependencyGraph,
    DependencyMapper,
    WorkloadNode,
)
try:
    from .models import (
        AssessmentRequest,
        AssessmentResponse,
        DependencyGraphResponse,
        HealthResponse,
        RunbookRequest,
        RunbookResponse,
        TCOResponse,
        WavePlanRequest,
        WavePlanResponse,
        WhatIfRequest,
        WhatIfResponse,
        WorkloadInventoryModel,
    )
except ImportError:
    # pydantic v2 not installed — API models unavailable
    AssessmentRequest = None
    AssessmentResponse = None
    DependencyGraphResponse = None
    HealthResponse = None
    RunbookRequest = None
    RunbookResponse = None
    TCOResponse = None
    WavePlanRequest = None
    WavePlanResponse = None
    WhatIfRequest = None
    WhatIfResponse = None
    WorkloadInventoryModel = None
from .report_generator import ReportConfig, ReportGenerator
from .runbook_generator import (
    MigrationRunbook,
    RunbookGenerator,
    RunbookResult,
    RunbookStep,
    WaveRunbook,
)
from .tco_calculator import (
    CloudCosts,
    OnPremCosts,
    TCOAnalysis,
    TCOCalculator,
)
from .wave_planner import (
    MigrationApproach,
    MigrationWave,
    MonteCarloResult,
    WaveConfidenceInterval,
    WavePlan,
    WavePlanner,
)

__version__ = "2.0.0"
__author__ = "Hunter Spence"
__description__ = (
    "ML-enhanced cloud migration planning — "
    "GradientBoosting 6R classifier, 10k Monte Carlo, 3-scenario TCO, "
    "FastAPI REST + WebSocket, Claude Sonnet runbooks"
)

__all__ = [
    # Assessor
    "WorkloadAssessment",
    "WorkloadInventory",
    "MigrationStrategy",
    "WorkloadAssessor",
    # Dependency Mapper
    "DependencyGraph",
    "WorkloadNode",
    "DependencyEdge",
    "DependencyMapper",
    # Wave Planner
    "MigrationWave",
    "WavePlan",
    "MonteCarloResult",
    "WaveConfidenceInterval",
    "MigrationApproach",
    "WavePlanner",
    # TCO Calculator
    "OnPremCosts",
    "CloudCosts",
    "TCOAnalysis",
    "TCOCalculator",
    # Runbook Generator
    "RunbookStep",
    "MigrationRunbook",
    "WaveRunbook",
    "RunbookResult",
    "RunbookGenerator",
    # Report Generator
    "ReportConfig",
    "ReportGenerator",
    # Pydantic v2 API Models
    "WorkloadInventoryModel",
    "AssessmentRequest",
    "AssessmentResponse",
    "WavePlanRequest",
    "WavePlanResponse",
    "TCOResponse",
    "DependencyGraphResponse",
    "RunbookRequest",
    "RunbookResponse",
    "WhatIfRequest",
    "WhatIfResponse",
    "HealthResponse",
]
