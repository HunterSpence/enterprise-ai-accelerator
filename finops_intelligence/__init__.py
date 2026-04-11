"""
FinOps Intelligence V2 — Open-source cloud cost optimization.

Replaces CloudZero / IBM Cloudability ($60-90K/year, or 2-3% of cloud spend)
with a free, local alternative built on DuckDB, FastAPI, and ensemble ML.

Headline: $89,400/month ($1.07M/year) savings identified on a $340K/month bill.
"""

# V1 modules (preserved)
from .cost_tracker import CostTracker, SpendData, ServiceSpend, DailySpend
from .anomaly_detector import AnomalyDetector as AnomalyDetectorV1, Anomaly, AnomalySeverity
from .forecaster import Forecaster, ForecastResult, BurnRateResult
from .optimizer import Optimizer, OptimizationPlan, OptimizationOpportunity, OpportunityType
from .nl_interface import NLInterface, ConversationSession
from .dashboard import Dashboard
from .reporter import Reporter, ReportConfig, ReportData, generate_cfo_report

# V2 modules
from .analytics_engine import AnalyticsEngine, AnalyticsConfig, ServiceBreakdown
from .anomaly_detector_v2 import EnsembleAnomalyDetector, DetectorConfig, AnomalyV2, SuppressionRule
from .unit_economics import (
    UnitEconomicsEngine,
    UnitEconomicsConfig,
    UnitEconomicsResult,
    MetricSnapshot,
    EfficiencyTrend,
)
from .commitment_optimizer import (
    CommitmentOptimizer,
    CommitmentOptimizerConfig,
    CommitmentAnalysisReport,
    SavingsPlanRecommendation,
)
from .maturity_assessment import (
    MaturityAssessment,
    MaturityAssessmentConfig,
    MaturityReport,
    MaturityStage,
)

__version__ = "2.0.0"

__all__ = [
    # V1
    "CostTracker",
    "SpendData",
    "ServiceSpend",
    "DailySpend",
    "AnomalyDetectorV1",
    "Anomaly",
    "AnomalySeverity",
    "Forecaster",
    "ForecastResult",
    "BurnRateResult",
    "Optimizer",
    "OptimizationPlan",
    "OptimizationOpportunity",
    "OpportunityType",
    "NLInterface",
    "ConversationSession",
    "Dashboard",
    # V2 — reporter
    "Reporter",
    "ReportConfig",
    "ReportData",
    "generate_cfo_report",
    # V2 — analytics engine
    "AnalyticsEngine",
    "AnalyticsConfig",
    "ServiceBreakdown",
    # V2 — ensemble anomaly detector
    "EnsembleAnomalyDetector",
    "DetectorConfig",
    "AnomalyV2",
    "SuppressionRule",
    # V2 — unit economics
    "UnitEconomicsEngine",
    "UnitEconomicsConfig",
    "UnitEconomicsResult",
    "MetricSnapshot",
    "EfficiencyTrend",
    # V2 — commitment optimizer
    "CommitmentOptimizer",
    "CommitmentOptimizerConfig",
    "CommitmentAnalysisReport",
    "SavingsPlanRecommendation",
    # V2 — maturity assessment
    "MaturityAssessment",
    "MaturityAssessmentConfig",
    "MaturityReport",
    "MaturityStage",
]
