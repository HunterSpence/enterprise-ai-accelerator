"""
assessor.py — ML-Enhanced 6R Workload Assessment Engine (V2)
=============================================================

V2 upgrades:
  - scikit-learn GradientBoostingClassifier trained on 500+ synthetic workloads
  - SHAP-style feature importance explanations per prediction
  - Claude Haiku enrichment for edge cases where ML confidence < threshold
  - Pydantic v2 models throughout
  - Full async-compatible design (sync ML + optional async AI)

6R Framework:
  Rehost     — Lift and shift to cloud VMs
  Replatform — Lift, tinker, shift (managed DB, containers)
  Repurchase — Move to SaaS
  Refactor   — Re-architect for cloud-native
  Retire     — Decommission
  Retain     — Keep on-premises
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import anthropic
import numpy as np
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


# ---------------------------------------------------------------------------
# Strategy enum (kept as plain Python enum for internal use — Pydantic model
# in models.py handles API serialization)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Dataclasses (internal, not exposed via API directly)
# ---------------------------------------------------------------------------

@dataclass
class WorkloadInventory:
    """A single workload entry from the inventory."""
    id: str
    name: str
    workload_type: str
    language: str = "unknown"
    framework: str = "unknown"
    os: str = "Linux"
    cpu_cores: int = 4
    ram_gb: int = 16
    storage_gb: int = 200
    monthly_on_prem_cost: float = 2500.0
    age_years: float = 5.0
    has_external_dependencies: bool = False
    dependency_count: int = 0
    has_custom_hardware: bool = False
    is_stateful: bool = True
    database_type: str | None = None
    business_criticality: str = "medium"
    team_cloud_familiarity: str = "medium"
    last_major_update_years: float = 2.0
    license_type: str = "open_source"
    license_cost_annual: float = 0.0
    containerized: bool = False
    team_size: int = 5
    notes: str = ""
    # Multi-cloud: "aws" | "azure" | "gcp" — controls target service recommendations
    cloud_provider: str = "aws"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    def to_ml_features(self) -> list[float]:
        """Convert workload to ML feature vector (10 features)."""
        db_type_map = {"oracle": 4, "mssql": 3, "mysql": 2, "postgresql": 2, "mongodb": 1, None: 0, "redis": 0}
        lang_complexity = {
            "COBOL": 5, "C": 4, "C++": 4, "Java": 3, "C#": 3,
            "Python": 2, "Go": 2, "Node.js": 2, "Ruby": 2,
            "unknown": 2,
        }
        crit_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}

        return [
            float(self.age_years),
            float(len(self.notes) / 20 + self.dependency_count * 0.5),  # complexity proxy
            float(self.dependency_count),
            float(db_type_map.get(self.database_type, 0)),
            float(lang_complexity.get(self.language, 2)),
            float(self.team_size),
            float(crit_map.get(self.business_criticality, 2)),
            float(self.license_cost_annual / 50000),  # normalized
            1.0 if self.containerized else 0.0,
            1.0 if self.is_stateful else 0.0,
        ]


@dataclass
class FeatureImportance:
    feature: str
    importance: float
    direction: str  # "increases" or "decreases"


@dataclass
class WorkloadAssessment:
    """Full 6R assessment result for a single workload."""
    workload: WorkloadInventory
    strategy: MigrationStrategy
    cloud_readiness_score: int
    complexity: ComplexityLevel
    risk_score: int
    migration_readiness_score: int
    estimated_migration_weeks: float
    estimated_migration_cost_usd: float
    monthly_cloud_cost_usd: float
    annual_savings_usd: float
    ai_rationale: str
    target_service: str
    quick_wins: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    confidence: float = 0.85
    ml_classified: bool = False
    ai_enriched: bool = False
    top_feature_importances: list[FeatureImportance] = field(default_factory=list)

    @property
    def three_year_savings(self) -> float:
        return self.annual_savings_usd * 3 - self.estimated_migration_cost_usd

    @property
    def roi_months(self) -> float:
        if self.annual_savings_usd <= 0:
            return float("inf")
        return self.estimated_migration_cost_usd / (self.annual_savings_usd / 12)


# ---------------------------------------------------------------------------
# Synthetic training data generation
# ---------------------------------------------------------------------------

_STRATEGY_LABELS = list(MigrationStrategy)
_LABEL_IDX = {s: i for i, s in enumerate(_STRATEGY_LABELS)}
_IDX_LABEL = {i: s for i, s in enumerate(_STRATEGY_LABELS)}

_FEATURE_NAMES = [
    "age_years",
    "complexity_score",
    "dependencies_count",
    "database_type_score",
    "language_complexity",
    "team_size",
    "business_criticality",
    "license_cost_normalized",
    "containerized",
    "stateful",
]


def _generate_synthetic_training_data(n_samples: int = 600) -> tuple[list[list[float]], list[int]]:
    """
    Generate synthetic labeled training data for the 6R classifier.

    Rules based on cloud migration industry best practices:
    - Old (>12yr) + low criticality + stale = Retire
    - Custom hardware / mainframe = Retain
    - CRM/ERP proxy (high license cost) = Repurchase
    - Modern + many deps + high team skill + containerized = Refactor
    - Database + standard RDBMS = Replatform
    - Everything else that's modern + medium complexity = Replatform
    - Default fallback = Rehost
    """
    rng = random.Random(42)
    np_rng = np.random.default_rng(42)

    X: list[list[float]] = []
    y: list[int] = []

    def noise(val: float, scale: float = 0.1) -> float:
        return val + rng.gauss(0, scale)

    for _ in range(n_samples):
        # Pick a target strategy first, then generate realistic features
        target = rng.choice(_STRATEGY_LABELS)

        if target == MigrationStrategy.RETIRE:
            age = noise(rng.uniform(12, 25), 1.5)
            complexity = noise(rng.uniform(0.5, 2.0), 0.3)
            deps = int(max(0, rng.gauss(2, 1)))
            db = 0.0
            lang = rng.uniform(1, 3)
            team = max(1, int(rng.gauss(3, 1)))
            crit = 1.0
            lic = noise(0.1, 0.05)
            cont = 0.0
            stat = rng.choice([0.0, 1.0])

        elif target == MigrationStrategy.RETAIN:
            age = noise(rng.uniform(8, 20), 2.0)
            complexity = noise(rng.uniform(3.0, 6.0), 0.5)
            deps = int(max(0, rng.gauss(8, 3)))
            db = rng.choice([3.0, 4.0])
            lang = rng.uniform(3, 5)
            team = max(1, int(rng.gauss(6, 2)))
            crit = rng.uniform(3, 4)
            lic = noise(rng.uniform(0.5, 1.5), 0.1)
            cont = 0.0
            stat = 1.0

        elif target == MigrationStrategy.REPURCHASE:
            age = noise(rng.uniform(4, 12), 1.0)
            complexity = noise(rng.uniform(1.0, 3.0), 0.3)
            deps = int(max(0, rng.gauss(3, 2)))
            db = 0.0
            lang = rng.uniform(2, 4)
            team = max(1, int(rng.gauss(5, 2)))
            crit = rng.uniform(2, 3)
            lic = noise(rng.uniform(0.8, 2.0), 0.2)  # High license cost
            cont = 0.0
            stat = rng.choice([0.0, 1.0])

        elif target == MigrationStrategy.REFACTOR:
            age = noise(rng.uniform(1, 8), 1.0)
            complexity = noise(rng.uniform(2.0, 5.0), 0.5)
            deps = int(max(0, rng.gauss(10, 4)))
            db = rng.choice([1.0, 2.0])
            lang = rng.uniform(2, 3)
            team = max(1, int(rng.gauss(10, 3)))
            crit = rng.uniform(2, 4)
            lic = noise(0.2, 0.05)
            cont = rng.choices([1.0, 0.0], weights=[0.6, 0.4])[0]
            stat = 0.0

        elif target == MigrationStrategy.REPLATFORM:
            age = noise(rng.uniform(3, 10), 1.0)
            complexity = noise(rng.uniform(1.5, 3.5), 0.3)
            deps = int(max(0, rng.gauss(5, 2)))
            db = rng.choice([2.0, 2.0, 3.0])  # weighted toward relational
            lang = rng.uniform(2, 3)
            team = max(1, int(rng.gauss(6, 2)))
            crit = rng.uniform(2, 3)
            lic = noise(0.2, 0.05)
            cont = rng.choices([1.0, 0.0], weights=[0.3, 0.7])[0]
            stat = rng.choices([1.0, 0.0], weights=[0.6, 0.4])[0]

        else:  # REHOST
            age = noise(rng.uniform(5, 15), 1.5)
            complexity = noise(rng.uniform(1.0, 3.0), 0.3)
            deps = int(max(0, rng.gauss(4, 2)))
            db = 0.0
            lang = rng.uniform(2, 4)
            team = max(1, int(rng.gauss(5, 2)))
            crit = rng.uniform(2, 3)
            lic = noise(0.15, 0.05)
            cont = rng.choices([1.0, 0.0], weights=[0.2, 0.8])[0]
            stat = rng.choices([1.0, 0.0], weights=[0.7, 0.3])[0]

        features = [age, complexity, float(deps), db, lang, float(team), crit, lic, cont, stat]
        X.append(features)
        y.append(_LABEL_IDX[target])

    return X, y


# ---------------------------------------------------------------------------
# ML Classifier
# ---------------------------------------------------------------------------

class SixRMLClassifier:
    """
    Gradient Boosting classifier for 6R strategy prediction.

    Trained on 600 synthetic workloads with realistic feature distributions.
    Provides confidence scores and SHAP-style feature importances per prediction.
    """

    FEATURE_LABELS = _FEATURE_NAMES

    def __init__(self) -> None:
        self._model: Any = None
        self._trained = False
        self._feature_importances: list[float] = []

    def train(self) -> None:
        """Train the classifier on synthetic data. Call once at startup."""
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline

            X_raw, y = _generate_synthetic_training_data(600)
            X = np.array(X_raw, dtype=np.float64)

            self._model = Pipeline([
                ("scaler", StandardScaler()),
                ("clf", GradientBoostingClassifier(
                    n_estimators=150,
                    max_depth=4,
                    learning_rate=0.08,
                    subsample=0.85,
                    random_state=42,
                    n_iter_no_change=15,
                    validation_fraction=0.15,
                )),
            ])
            self._model.fit(X, y)
            self._feature_importances = self._model.named_steps["clf"].feature_importances_.tolist()
            self._trained = True

        except ImportError:
            console.print("[yellow]scikit-learn not available — ML classifier disabled[/yellow]")
            self._trained = False

    @property
    def is_trained(self) -> bool:
        return self._trained

    def predict(
        self, workload: WorkloadInventory
    ) -> tuple[MigrationStrategy, float, list[FeatureImportance]]:
        """
        Predict 6R strategy for a workload.

        Returns (strategy, confidence, top_3_feature_importances).
        """
        if not self._trained or self._model is None:
            return MigrationStrategy.REHOST, 0.5, []

        features = np.array([workload.to_ml_features()], dtype=np.float64)
        proba = self._model.predict_proba(features)[0]
        pred_idx = int(np.argmax(proba))
        confidence = float(proba[pred_idx])
        strategy = _IDX_LABEL[pred_idx]

        # SHAP-style: use feature importance × feature magnitude for this sample
        scaled_features = self._model.named_steps["scaler"].transform(features)[0]
        shap_approx = [
            abs(float(scaled_features[i])) * self._feature_importances[i]
            for i in range(len(self._feature_importances))
        ]
        top_indices = sorted(range(len(shap_approx)), key=lambda i: shap_approx[i], reverse=True)[:3]

        top_importances = []
        for idx in top_indices:
            feat_val = features[0][idx]
            # Determine direction heuristically
            if self._feature_importances[idx] > 0.05:
                direction = "increases" if feat_val > 0.5 else "decreases"
            else:
                direction = "neutral"
            top_importances.append(
                FeatureImportance(
                    feature=self.FEATURE_LABELS[idx],
                    importance=round(self._feature_importances[idx], 4),
                    direction=direction,
                )
            )

        return strategy, confidence, top_importances


# Singleton ML classifier — trained once on module load
_ml_classifier = SixRMLClassifier()


def get_ml_classifier() -> SixRMLClassifier:
    """Get the shared ML classifier, training it if needed."""
    if not _ml_classifier.is_trained:
        _ml_classifier.train()
    return _ml_classifier


# ---------------------------------------------------------------------------
# Rule-based fallback (unchanged logic, used when ML confidence < threshold)
# ---------------------------------------------------------------------------

def _rule_based_classify(w: WorkloadInventory) -> tuple[MigrationStrategy, int, ComplexityLevel, int]:
    """Fast rule-based pre-classification. Returns (strategy, readiness, complexity, risk)."""
    if w.age_years > 15 and w.last_major_update_years > 5 and w.business_criticality == "low":
        return MigrationStrategy.RETIRE, 20, ComplexityLevel.LOW, 10

    if w.has_custom_hardware:
        return MigrationStrategy.RETAIN, 30, ComplexityLevel.HIGH, 70

    saas_candidates = {"crm", "erp", "itsm", "ticketing", "hr", "payroll", "email"}
    if any(kw in w.name.lower() or kw in w.workload_type.lower() for kw in saas_candidates):
        return MigrationStrategy.REPURCHASE, 75, ComplexityLevel.LOW, 25

    if (w.workload_type == "web_app" and w.dependency_count > 8
            and w.age_years < 8 and w.team_cloud_familiarity == "high"):
        return MigrationStrategy.REFACTOR, 65, ComplexityLevel.HIGH, 55

    if w.workload_type == "database" and w.database_type in ("mysql", "postgresql", "mssql"):
        return MigrationStrategy.REPLATFORM, 70, ComplexityLevel.MEDIUM, 40

    if w.workload_type in ("web_app", "microservice") and w.age_years < 10:
        return MigrationStrategy.REPLATFORM, 68, ComplexityLevel.MEDIUM, 35

    readiness = max(20, min(90, 80 - int(w.age_years * 2) - (w.dependency_count * 3)
                            - (20 if w.has_custom_hardware else 0)
                            + (10 if w.team_cloud_familiarity == "high" else 0)))

    complexity_map = {
        "low": ComplexityLevel.LOW, "medium": ComplexityLevel.MEDIUM,
        "high": ComplexityLevel.HIGH, "critical": ComplexityLevel.HIGH,
    }
    complexity = complexity_map.get(w.business_criticality, ComplexityLevel.MEDIUM)
    risk = min(90, w.dependency_count * 5 + int(w.age_years * 3) + (20 if w.has_custom_hardware else 0))

    return MigrationStrategy.REHOST, readiness, complexity, risk


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _estimate_target_service(strategy: MigrationStrategy, w: WorkloadInventory) -> str:
    """
    Recommend a target cloud service for the given strategy + workload.
    Supports AWS (default), Azure, and GCP.
    """
    if strategy == MigrationStrategy.RETIRE:
        return "Decommission"
    if strategy == MigrationStrategy.RETAIN:
        return "On-Premises"
    if strategy == MigrationStrategy.REPURCHASE:
        saas_map = {"crm": "Salesforce / HubSpot", "erp": "SAP S/4HANA Cloud",
                    "itsm": "ServiceNow SaaS", "email": "Microsoft 365 / Google Workspace"}
        for k, v in saas_map.items():
            if k in w.name.lower():
                return v
        return "SaaS Replacement"

    provider = getattr(w, "cloud_provider", "aws").lower()

    # ── AWS ────────────────────────────────────────────────────────────
    if provider == "aws":
        if w.workload_type == "database":
            db_map = {
                "mysql": "RDS Aurora MySQL", "postgresql": "RDS Aurora PostgreSQL",
                "mssql": "RDS SQL Server", "oracle": "RDS Oracle / Aurora PostgreSQL (migration)",
                "mongodb": "DocumentDB / MongoDB Atlas", "redis": "ElastiCache Redis",
                "cassandra": "Amazon Keyspaces",
            }
            return db_map.get(w.database_type or "", "RDS Managed DB")
        if strategy == MigrationStrategy.REFACTOR:
            if w.workload_type in ("web_app", "microservice"):
                return "ECS Fargate / EKS"
            return "Lambda / Step Functions"
        if strategy == MigrationStrategy.REPLATFORM:
            if w.workload_type in ("web_app", "microservice"):
                return "ECS Fargate"
            if w.workload_type == "batch_job":
                return "AWS Batch"
            return "Elastic Beanstalk"
        # Rehost — pick EC2 instance type by RAM
        size_map = [(64, "r5.2xlarge"), (32, "m5.xlarge"), (16, "m5.large"), (0, "t3.medium")]
        for threshold, instance in size_map:
            if w.ram_gb >= threshold:
                return f"EC2 {instance}"
        return "EC2 t3.medium"

    # ── Azure ──────────────────────────────────────────────────────────
    if provider == "azure":
        if w.workload_type == "database":
            db_map = {
                "mysql": "Azure Database for MySQL", "postgresql": "Azure Database for PostgreSQL",
                "mssql": "Azure SQL Database", "oracle": "Azure SQL Managed Instance",
                "mongodb": "Azure Cosmos DB (MongoDB API)", "redis": "Azure Cache for Redis",
                "cassandra": "Azure Cosmos DB (Cassandra API)",
            }
            return db_map.get(w.database_type or "", "Azure SQL Database")
        if strategy == MigrationStrategy.REFACTOR:
            if w.workload_type in ("web_app", "microservice"):
                return "Azure Container Apps / AKS"
            return "Azure Functions"
        if strategy == MigrationStrategy.REPLATFORM:
            if w.workload_type in ("web_app", "microservice"):
                return "Azure App Service / Container Apps"
            if w.workload_type == "batch_job":
                return "Azure Batch"
            return "Azure App Service"
        # Rehost — Azure VM sizing by RAM
        size_map = [(64, "Standard_E8s_v5"), (32, "Standard_D8s_v5"),
                    (16, "Standard_D4s_v5"), (0, "Standard_D2s_v5")]
        for threshold, vm_size in size_map:
            if w.ram_gb >= threshold:
                return f"Azure VM {vm_size}"
        return "Azure VM Standard_D2s_v5"

    # ── GCP ────────────────────────────────────────────────────────────
    if provider == "gcp":
        if w.workload_type == "database":
            db_map = {
                "mysql": "Cloud SQL (MySQL)", "postgresql": "Cloud SQL (PostgreSQL) / AlloyDB",
                "mssql": "Cloud SQL (SQL Server)", "oracle": "Bare Metal Solution / Cloud SQL",
                "mongodb": "Firestore / MongoDB Atlas on GCP", "redis": "Memorystore for Redis",
                "cassandra": "Bigtable",
            }
            return db_map.get(w.database_type or "", "Cloud SQL")
        if strategy == MigrationStrategy.REFACTOR:
            if w.workload_type in ("web_app", "microservice"):
                return "Cloud Run / GKE Autopilot"
            return "Cloud Functions (2nd gen)"
        if strategy == MigrationStrategy.REPLATFORM:
            if w.workload_type in ("web_app", "microservice"):
                return "Cloud Run"
            if w.workload_type == "batch_job":
                return "Cloud Batch"
            return "App Engine"
        # Rehost — Compute Engine sizing by RAM
        size_map = [(64, "n2-highmem-8"), (32, "n2-standard-8"),
                    (16, "n2-standard-4"), (0, "e2-standard-2")]
        for threshold, machine_type in size_map:
            if w.ram_gb >= threshold:
                return f"Compute Engine {machine_type}"
        return "Compute Engine e2-standard-2"

    # Unknown provider — log and return generic recommendation
    import logging
    logging.getLogger(__name__).warning(
        "Unknown cloud_provider '%s' for workload '%s'. "
        "Supported: aws, azure, gcp. Defaulting to generic recommendation.",
        provider, w.name,
    )
    return f"Cloud VM ({provider} — assessment coming soon)"


def _estimate_monthly_cloud_cost(strategy: MigrationStrategy, w: WorkloadInventory) -> float:
    if strategy in (MigrationStrategy.RETIRE, MigrationStrategy.RETAIN):
        return 0.0
    if strategy == MigrationStrategy.REPURCHASE:
        return w.monthly_on_prem_cost * 0.6

    cpu_cost = w.cpu_cores * 35
    ram_cost = w.ram_gb * 6
    storage_cost = w.storage_gb * 0.10
    base = cpu_cost + ram_cost + storage_cost

    if strategy == MigrationStrategy.REPLATFORM:
        base *= 1.3
    elif strategy == MigrationStrategy.REFACTOR:
        base *= 0.7

    return round(base * 0.70, 2)


def _estimate_migration_cost(complexity: ComplexityLevel, strategy: MigrationStrategy) -> float:
    base = {ComplexityLevel.LOW: 8_000, ComplexityLevel.MEDIUM: 25_000, ComplexityLevel.HIGH: 65_000}[complexity]
    multiplier = {
        MigrationStrategy.REHOST: 0.8, MigrationStrategy.REPLATFORM: 1.2,
        MigrationStrategy.REPURCHASE: 0.6, MigrationStrategy.REFACTOR: 2.5,
        MigrationStrategy.RETIRE: 0.2, MigrationStrategy.RETAIN: 0.1,
    }[strategy]
    return round(base * multiplier, 0)


def _estimate_migration_weeks(complexity: ComplexityLevel, strategy: MigrationStrategy) -> float:
    weeks = {ComplexityLevel.LOW: 2.0, ComplexityLevel.MEDIUM: 6.0, ComplexityLevel.HIGH: 16.0}[complexity]
    multiplier = {
        MigrationStrategy.REHOST: 0.7, MigrationStrategy.REPLATFORM: 1.0,
        MigrationStrategy.REPURCHASE: 0.8, MigrationStrategy.REFACTOR: 2.0,
        MigrationStrategy.RETIRE: 0.3, MigrationStrategy.RETAIN: 0.1,
    }[strategy]
    return round(weeks * multiplier, 1)


def _compute_migration_readiness(w: WorkloadInventory, dep_graph_metrics: dict[str, Any] | None = None) -> int:
    """
    0-100 migration readiness score.
    High score = easier to migrate now.
    """
    score = 100

    # Penalize age
    score -= min(25, int(w.age_years * 1.5))

    # Penalize dependency complexity
    score -= min(20, w.dependency_count * 2)

    # Penalize stateful apps
    if w.is_stateful:
        score -= 10

    # Penalize custom hardware
    if w.has_custom_hardware:
        score -= 25

    # Reward containerized apps
    if w.containerized:
        score += 15

    # Reward cloud-familiar teams
    familiarity_bonus = {"low": 0, "medium": 5, "high": 12}
    score += familiarity_bonus.get(w.team_cloud_familiarity, 5)

    # Penalize old Oracle/commercial licenses
    if w.database_type == "oracle" or w.license_cost_annual > 100000:
        score -= 15

    # Use betweenness centrality from graph if available
    if dep_graph_metrics:
        centrality = dep_graph_metrics.get("betweenness_centrality", 0.0)
        score -= min(15, int(centrality * 50))

    return max(0, min(100, score))


# ---------------------------------------------------------------------------
# Main Assessor class
# ---------------------------------------------------------------------------

class WorkloadAssessor:
    """
    V2 ML-Enhanced 6R workload assessor.

    Pipeline:
    1. ML gradient boosting classifier → strategy + confidence
    2. If confidence < threshold → Claude Haiku override
    3. Rule-based fallback if both unavailable
    """

    def __init__(
        self,
        use_ml: bool = True,
        use_ai: bool = True,
        confidence_threshold: float = 0.65,
    ) -> None:
        self.use_ml = use_ml
        self.use_ai = use_ai
        self.confidence_threshold = confidence_threshold
        self._client: anthropic.Anthropic | None = None
        self._ml: SixRMLClassifier | None = None

        if self.use_ml:
            self._ml = get_ml_classifier()

        if self.use_ai:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                self._client = anthropic.Anthropic(api_key=api_key)
            else:
                console.print("[yellow]ANTHROPIC_API_KEY not set — AI enrichment disabled[/yellow]")
                self.use_ai = False

    def _ai_enrich(
        self, w: WorkloadInventory, ml_strategy: MigrationStrategy, ml_confidence: float
    ) -> tuple[str, list[str], list[str], float, MigrationStrategy]:
        """
        Call Claude Haiku to enrich low-confidence ML classifications.
        Returns (rationale, quick_wins, risks, confidence, final_strategy).
        """
        if not self._client:
            return (
                f"ML classification ({ml_confidence:.0%} confidence): {ml_strategy.value}",
                ["Validate with application owner", "Review current license costs"],
                ["Assess all dependencies before cutover"],
                ml_confidence,
                ml_strategy,
            )

        prompt = f"""You are an expert cloud migration architect. Classify this workload and provide guidance.

WORKLOAD: {w.name}
Type: {w.workload_type}
Stack: {w.language}/{w.framework} on {w.os}
Size: {w.cpu_cores} vCPU, {w.ram_gb}GB RAM, {w.storage_gb}GB storage
Age: {w.age_years} years (last major update: {w.last_major_update_years}yr ago)
Dependencies: {w.dependency_count} direct
Business criticality: {w.business_criticality}
Team cloud familiarity: {w.team_cloud_familiarity}
Current monthly cost: ${w.monthly_on_prem_cost:,.0f}
Annual license cost: ${w.license_cost_annual:,.0f}
Containerized: {w.containerized}
Stateful: {w.is_stateful}
Database type: {w.database_type or 'none'}
ML preliminary strategy ({ml_confidence:.0%} confidence): {ml_strategy.value}
Notes: {w.notes if w.notes else 'None'}

Respond in JSON only:
{{
  "strategy": "Rehost|Replatform|Repurchase|Refactor|Retire|Retain",
  "rationale": "2-3 sentences explaining the strategy, citing specific workload attributes",
  "quick_wins": ["specific win 1", "specific win 2", "specific win 3"],
  "risks": ["specific risk 1", "specific risk 2"],
  "confidence": 0.0-1.0
}}"""

        try:
            response = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)

            strategy_str = data.get("strategy", ml_strategy.value)
            try:
                final_strategy = MigrationStrategy(strategy_str)
            except ValueError:
                final_strategy = ml_strategy

            return (
                data.get("rationale", f"{final_strategy.value} strategy confirmed."),
                data.get("quick_wins", []),
                data.get("risks", []),
                float(data.get("confidence", 0.85)),
                final_strategy,
            )
        except Exception as exc:
            return (
                f"{ml_strategy.value} strategy recommended. (AI enrichment failed: {exc})",
                ["Validate with application team"],
                ["Review dependencies thoroughly before migration"],
                ml_confidence,
                ml_strategy,
            )

    def assess_workload(
        self,
        w: WorkloadInventory,
        dep_graph_metrics: dict[str, Any] | None = None,
    ) -> WorkloadAssessment:
        """Assess a single workload. Returns full 6R assessment."""
        ml_strategy: MigrationStrategy | None = None
        ml_confidence: float = 0.0
        ml_feature_importances: list[FeatureImportance] = []
        ml_classified = False
        ai_enriched = False

        # Step 1: ML classification
        if self.use_ml and self._ml and self._ml.is_trained:
            ml_strategy, ml_confidence, ml_feature_importances = self._ml.predict(w)
            ml_classified = True

        # Step 2: Rule-based if ML unavailable
        if ml_strategy is None:
            rule_strategy, _, _, _ = _rule_based_classify(w)
            ml_strategy = rule_strategy
            ml_confidence = 0.60

        # Step 3: AI enrichment for low-confidence cases
        if self.use_ai and ml_confidence < self.confidence_threshold:
            rationale, quick_wins, risks, confidence, final_strategy = self._ai_enrich(
                w, ml_strategy, ml_confidence
            )
            ai_enriched = True
        elif ml_classified:
            # Use rule-based quick wins but ML strategy
            final_strategy = ml_strategy
            confidence = ml_confidence
            rationale = (
                f"ML Gradient Boosting ({confidence:.0%} confidence): {final_strategy.value} "
                f"recommended based on {w.age_years:.0f}-year-old {w.workload_type} with "
                f"{w.dependency_count} dependencies."
            )
            quick_wins = [
                "Validate ML classification with application owner before execution",
                "Run dependency discovery tool to confirm dependency count",
                "Benchmark current performance for post-migration comparison",
            ]
            risks = [
                f"{'Stateful application — requires careful data migration planning' if w.is_stateful else 'Verify all external API endpoints function correctly in cloud'}",
                "Team may need cloud training before migration execution",
            ]
        else:
            final_strategy = ml_strategy
            confidence = 0.70
            rationale = f"{final_strategy.value} recommended based on workload profile."
            quick_wins = ["Validate with application owner", "Review license costs"]
            risks = ["Assess dependencies", "Check compliance requirements"]

        # Derive readiness, complexity, risk from rules (these don't change with ML strategy)
        _, readiness, complexity, risk = _rule_based_classify(w)

        target_service = _estimate_target_service(final_strategy, w)
        monthly_cloud_cost = _estimate_monthly_cloud_cost(final_strategy, w)
        migration_cost = _estimate_migration_cost(complexity, final_strategy)
        migration_weeks = _estimate_migration_weeks(complexity, final_strategy)
        annual_savings = (w.monthly_on_prem_cost - monthly_cloud_cost) * 12
        mig_readiness = _compute_migration_readiness(w, dep_graph_metrics)

        return WorkloadAssessment(
            workload=w,
            strategy=final_strategy,
            cloud_readiness_score=readiness,
            complexity=complexity,
            risk_score=risk,
            migration_readiness_score=mig_readiness,
            estimated_migration_weeks=migration_weeks,
            estimated_migration_cost_usd=migration_cost,
            monthly_cloud_cost_usd=monthly_cloud_cost,
            annual_savings_usd=annual_savings,
            ai_rationale=rationale,
            target_service=target_service,
            quick_wins=quick_wins,
            risks=risks,
            confidence=confidence,
            ml_classified=ml_classified,
            ai_enriched=ai_enriched,
            top_feature_importances=ml_feature_importances,
        )

    def assess_inventory(
        self,
        inventory: list[WorkloadInventory],
        show_progress: bool = True,
    ) -> list[WorkloadAssessment]:
        """Assess an entire workload inventory."""
        assessments: list[WorkloadAssessment] = []

        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"Assessing {len(inventory)} workloads (ML + AI)...",
                    total=len(inventory),
                )
                for w in inventory:
                    assessments.append(self.assess_workload(w))
                    progress.advance(task)
                    if self.use_ai:
                        time.sleep(0.03)
        else:
            assessments = [self.assess_workload(w) for w in inventory]

        return assessments

    def print_summary_table(self, assessments: list[WorkloadAssessment]) -> None:
        """Print a rich summary table of all assessments."""
        table = Table(
            title="6R ML-Enhanced Workload Assessment Results",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold white on dark_blue",
        )

        table.add_column("Workload", style="white", min_width=22)
        table.add_column("Strategy", justify="center", min_width=12)
        table.add_column("Readiness", justify="center")
        table.add_column("Migration Ready", justify="center")
        table.add_column("Risk", justify="center")
        table.add_column("Confidence", justify="center")
        table.add_column("Source", justify="center")
        table.add_column("Target Service", style="dim", min_width=20)
        table.add_column("Annual Savings", justify="right")

        strategy_counts: dict[MigrationStrategy, int] = {}

        for a in assessments:
            strategy_counts[a.strategy] = strategy_counts.get(a.strategy, 0) + 1

            readiness_color = "green" if a.cloud_readiness_score >= 70 else (
                "yellow" if a.cloud_readiness_score >= 40 else "red"
            )
            mig_color = "green" if a.migration_readiness_score >= 70 else (
                "yellow" if a.migration_readiness_score >= 40 else "red"
            )
            risk_color = "red" if a.risk_score >= 70 else (
                "yellow" if a.risk_score >= 40 else "green"
            )
            conf_color = "green" if a.confidence >= 0.75 else (
                "yellow" if a.confidence >= 0.55 else "red"
            )
            source = (
                "[cyan]ML+AI[/cyan]" if a.ml_classified and a.ai_enriched
                else "[green]ML[/green]" if a.ml_classified
                else "[dim]rules[/dim]"
            )
            savings_str = (
                f"[green]+${a.annual_savings_usd:,.0f}[/green]"
                if a.annual_savings_usd > 0
                else f"[dim]${abs(a.annual_savings_usd):,.0f}[/dim]"
            )

            table.add_row(
                a.workload.name,
                f"[{a.strategy.color}]{a.strategy.value}[/{a.strategy.color}]",
                f"[{readiness_color}]{a.cloud_readiness_score}%[/{readiness_color}]",
                f"[{mig_color}]{a.migration_readiness_score}[/{mig_color}]",
                f"[{risk_color}]{a.risk_score}[/{risk_color}]",
                f"[{conf_color}]{a.confidence:.0%}[/{conf_color}]",
                source,
                a.target_service,
                savings_str,
            )

        console.print(table)

        dist_lines = []
        total = len(assessments)
        for strategy in MigrationStrategy:
            count = strategy_counts.get(strategy, 0)
            pct = count / total * 100 if total > 0 else 0
            bar = "#" * int(pct / 5)
            dist_lines.append(
                f"  [{strategy.color}]{strategy.value:<12}[/{strategy.color}] "
                f"[{strategy.color}]{bar:<20}[/{strategy.color}] "
                f"{count:2d} workloads ({pct:.0f}%)"
            )

        console.print(Panel("\n".join(dist_lines), title="[bold]Strategy Distribution[/bold]", border_style="dark_blue"))

        ml_count = sum(1 for a in assessments if a.ml_classified)
        ai_count = sum(1 for a in assessments if a.ai_enriched)
        total_annual = sum(a.annual_savings_usd for a in assessments)
        total_migration = sum(a.estimated_migration_cost_usd for a in assessments)
        total_3yr = sum(a.three_year_savings for a in assessments)

        console.print(
            Panel(
                f"  Annual savings identified:     [bold green]${total_annual:>12,.0f}[/bold green]\n"
                f"  Total migration investment:   [bold yellow]${total_migration:>12,.0f}[/bold yellow]\n"
                f"  3-year net benefit:           [bold cyan]${total_3yr:>12,.0f}[/bold cyan]\n"
                f"  Workloads assessed:           [bold white]{total:>12}[/bold white]\n"
                f"  ML classified:                [bold cyan]{ml_count:>12}[/bold cyan]\n"
                f"  AI enriched (low confidence): [bold magenta]{ai_count:>12}[/bold magenta]",
                title="[bold]Financial Summary[/bold]",
                border_style="green",
            )
        )
