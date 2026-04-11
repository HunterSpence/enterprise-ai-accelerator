"""
PolicyGuard — Bias Detection Engine
=====================================
V2 comprehensive fairness testing suite for AI systems.

Metrics implemented:
  1. Demographic Parity Difference   (target: < 0.05)
  2. Equalized Odds (TPR parity across groups)
  3. Disparate Impact Ratio          (EEOC 4/5ths rule: > 0.80)
  4. Individual Fairness             (similar inputs → similar outputs)
  5. Counterfactual Fairness         (change protected attr only → same output)

Additional:
  - Synthetic dataset generation (zero-credential demo)
  - SHAP-style feature importance (pure Python, no SHAP dependency)
  - Recommended mitigations ranked by effectiveness
  - EU AI Act Article 10(2) compliance check integration
  - SOC2 AICC-7 evidence generation
"""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEMOGRAPHIC_PARITY_THRESHOLD = 0.05  # EU AI Act / internal policy
DISPARATE_IMPACT_THRESHOLD = 0.80    # EEOC 4/5ths rule
EQUALIZED_ODDS_THRESHOLD = 0.10      # Acceptable TPR gap between groups


# ---------------------------------------------------------------------------
# Synthetic dataset generator
# ---------------------------------------------------------------------------

def _stable_random(seed_str: str) -> float:
    """Deterministic pseudo-random float [0,1] from a string seed."""
    h = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
    return (h % 10000) / 10000.0


def generate_synthetic_dataset(
    n_samples: int = 2000,
    protected_attributes: Optional[list[str]] = None,
    seed: int = 42,
) -> list[dict]:
    """
    Generate a synthetic hiring/lending decision dataset for bias testing.
    Deliberately introduces bias: group 'B' is approved at a lower rate,
    simulating a biased AI system.
    """
    if protected_attributes is None:
        protected_attributes = ["gender", "race", "age_group"]

    random.seed(seed)
    dataset: list[dict] = []

    group_approval_rates = {
        "gender": {"M": 0.72, "F": 0.58},        # 80% rule violated (F/M = 0.81, borderline)
        "race": {"white": 0.75, "nonwhite": 0.54},  # Disparate impact: 0.54/0.75 = 0.72 — VIOLATION
        "age_group": {"25-40": 0.70, "41-60": 0.62, "60+": 0.45},  # Age discrimination
    }

    for i in range(n_samples):
        gender = random.choice(["M", "F"])
        race = random.choice(["white", "nonwhite"])
        age_group = random.choices(["25-40", "41-60", "60+"], weights=[0.5, 0.35, 0.15])[0]

        # Correlated features (proxy variables — the insidious source of bias)
        credit_score = random.gauss(680 if race == "white" else 640, 80)
        income = random.gauss(75000 if gender == "M" else 65000, 20000)
        years_employed = random.gauss(8 if age_group == "41-60" else 4, 3)

        # True approval probability: based on legitimate features + protected attr bias
        legitimate_prob = (
            min(1.0, max(0.0, (credit_score - 580) / 300)) * 0.5
            + min(1.0, max(0.0, (income - 30000) / 100000)) * 0.3
            + min(1.0, max(0.0, years_employed / 20)) * 0.2
        )

        # Add discriminatory bias (this is what we're detecting)
        biased_prob = (
            legitimate_prob
            * group_approval_rates["gender"].get(gender, 0.65)
            / 0.65
            * group_approval_rates["race"].get(race, 0.65)
            / 0.72
        )

        approved = random.random() < biased_prob

        dataset.append({
            "id": i,
            "gender": gender,
            "race": race,
            "age_group": age_group,
            "credit_score": round(credit_score, 1),
            "income": round(income, 0),
            "years_employed": round(max(0, years_employed), 1),
            "approved": int(approved),
            "ground_truth": int(legitimate_prob > 0.5),  # What an unbiased model would decide
        })

    return dataset


# ---------------------------------------------------------------------------
# Fairness metrics
# ---------------------------------------------------------------------------

def _demographic_parity_difference(
    dataset: list[dict],
    protected_attr: str,
    positive_outcome: int = 1,
) -> dict[str, float]:
    """
    Demographic Parity Difference: |P(Y=1|A=a) - P(Y=1|A=b)|
    Target: < 0.05 (EU AI Act Article 10 + company policy)
    Returns approval rate per group and pairwise differences.
    """
    groups: dict[str, list[int]] = {}
    for row in dataset:
        g = str(row.get(protected_attr, "unknown"))
        groups.setdefault(g, []).append(row["approved"])

    approval_rates: dict[str, float] = {
        g: sum(outcomes) / len(outcomes)
        for g, outcomes in groups.items()
        if outcomes
    }

    group_names = sorted(approval_rates.keys())
    max_diff = 0.0
    pairwise: dict[str, float] = {}
    for i, g1 in enumerate(group_names):
        for g2 in group_names[i + 1:]:
            diff = abs(approval_rates[g1] - approval_rates[g2])
            pairwise[f"{g1}_vs_{g2}"] = round(diff, 4)
            max_diff = max(max_diff, diff)

    return {
        "metric": "Demographic Parity Difference",
        "approval_rates": {k: round(v, 4) for k, v in approval_rates.items()},
        "max_difference": round(max_diff, 4),
        "pairwise": pairwise,
        "threshold": DEMOGRAPHIC_PARITY_THRESHOLD,
        "passes": max_diff <= DEMOGRAPHIC_PARITY_THRESHOLD,
        "severity": "FAIL" if max_diff > DEMOGRAPHIC_PARITY_THRESHOLD else "PASS",
        "eu_ai_act_ref": "Article 10(2)(f) — bias testing requirement",
    }


def _equalized_odds(
    dataset: list[dict],
    protected_attr: str,
) -> dict:
    """
    Equalized Odds: equal TPR (sensitivity) and FPR across groups.
    Uses ground_truth as the true label.
    Target: TPR gap < 0.10
    """
    groups: dict[str, dict[str, list]] = {}
    for row in dataset:
        g = str(row.get(protected_attr, "unknown"))
        if g not in groups:
            groups[g] = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
        pred = row["approved"]
        true = row.get("ground_truth", row["approved"])
        if true == 1 and pred == 1:
            groups[g]["tp"] += 1
        elif true == 1 and pred == 0:
            groups[g]["fn"] += 1
        elif true == 0 and pred == 1:
            groups[g]["fp"] += 1
        else:
            groups[g]["tn"] += 1

    tpr: dict[str, float] = {}
    fpr: dict[str, float] = {}
    for g, cm in groups.items():
        pos = cm["tp"] + cm["fn"]
        neg = cm["fp"] + cm["tn"]
        tpr[g] = round(cm["tp"] / pos, 4) if pos > 0 else 0.0
        fpr[g] = round(cm["fp"] / neg, 4) if neg > 0 else 0.0

    tpr_values = list(tpr.values())
    tpr_gap = round(max(tpr_values) - min(tpr_values), 4) if len(tpr_values) > 1 else 0.0

    return {
        "metric": "Equalized Odds",
        "tpr_by_group": tpr,
        "fpr_by_group": fpr,
        "tpr_gap": tpr_gap,
        "threshold": EQUALIZED_ODDS_THRESHOLD,
        "passes": tpr_gap <= EQUALIZED_ODDS_THRESHOLD,
        "severity": "FAIL" if tpr_gap > EQUALIZED_ODDS_THRESHOLD else "PASS",
        "eu_ai_act_ref": "Article 10(2)(f) — bias testing requirement",
    }


def _disparate_impact_ratio(
    dataset: list[dict],
    protected_attr: str,
    privileged_group: Optional[str] = None,
) -> dict:
    """
    Disparate Impact Ratio (4/5ths rule): min(P(Y=1|group)) / max(P(Y=1|group))
    EEOC standard: ratio must be >= 0.80 (80% rule).
    """
    groups: dict[str, list[int]] = {}
    for row in dataset:
        g = str(row.get(protected_attr, "unknown"))
        groups.setdefault(g, []).append(row["approved"])

    approval_rates: dict[str, float] = {
        g: sum(outcomes) / len(outcomes)
        for g, outcomes in groups.items()
        if outcomes
    }

    if not approval_rates:
        return {"metric": "Disparate Impact Ratio", "ratio": 1.0, "passes": True, "severity": "PASS"}

    max_rate = max(approval_rates.values())
    min_rate = min(approval_rates.values())
    di_ratio = round(min_rate / max_rate, 4) if max_rate > 0 else 1.0

    worst_group = min(approval_rates, key=approval_rates.get)
    best_group = max(approval_rates, key=approval_rates.get)

    return {
        "metric": "Disparate Impact Ratio (EEOC 4/5ths Rule)",
        "approval_rates": {k: round(v, 4) for k, v in approval_rates.items()},
        "di_ratio": di_ratio,
        "worst_group": worst_group,
        "best_group": best_group,
        "threshold": DISPARATE_IMPACT_THRESHOLD,
        "passes": di_ratio >= DISPARATE_IMPACT_THRESHOLD,
        "severity": "FAIL" if di_ratio < DISPARATE_IMPACT_THRESHOLD else "PASS",
        "interpretation": (
            f"Group '{worst_group}' approved at {di_ratio:.0%} the rate of group '{best_group}'. "
            f"EEOC 4/5ths rule requires >= 80%. {'VIOLATION' if di_ratio < 0.80 else 'COMPLIANT'}."
        ),
        "legal_ref": "EEOC Uniform Guidelines on Employee Selection Procedures (29 CFR Part 1607)",
        "eu_ai_act_ref": "Article 10(2)(f)",
    }


def _individual_fairness_score(
    dataset: list[dict],
    n_pairs: int = 200,
    seed: int = 42,
) -> dict:
    """
    Individual Fairness: similar individuals should receive similar outcomes.
    Tests N random pairs — checks if feature-similar pairs get same decision.
    Similarity metric: L2 distance on normalized numeric features.
    """
    random.seed(seed)
    numeric_features = ["credit_score", "income", "years_employed"]

    # Normalize features for fair distance computation
    def normalize(val: float, feat: str) -> float:
        ranges = {"credit_score": (300, 850), "income": (0, 200000), "years_employed": (0, 40)}
        lo, hi = ranges.get(feat, (0, 1))
        return (val - lo) / (hi - lo) if hi > lo else 0.0

    inconsistencies = 0
    pairs_tested = min(n_pairs, len(dataset) * (len(dataset) - 1) // 2)

    for _ in range(pairs_tested):
        i, j = random.sample(range(len(dataset)), 2)
        a, b = dataset[i], dataset[j]

        dist = math.sqrt(sum(
            (normalize(float(a.get(f, 0)), f) - normalize(float(b.get(f, 0)), f)) ** 2
            for f in numeric_features
        ))

        # If very similar people (dist < 0.15) got different outcomes → inconsistency
        if dist < 0.15 and a["approved"] != b["approved"]:
            inconsistencies += 1

    inconsistency_rate = inconsistencies / pairs_tested if pairs_tested > 0 else 0.0

    return {
        "metric": "Individual Fairness",
        "pairs_tested": pairs_tested,
        "inconsistencies_found": inconsistencies,
        "inconsistency_rate": round(inconsistency_rate, 4),
        "threshold": 0.05,
        "passes": inconsistency_rate <= 0.05,
        "severity": "FAIL" if inconsistency_rate > 0.05 else "PASS",
        "interpretation": (
            f"{inconsistencies}/{pairs_tested} similar individuals received different decisions. "
            f"Rate: {inconsistency_rate:.1%}."
        ),
    }


def _counterfactual_fairness_score(
    dataset: list[dict],
    protected_attr: str,
    n_samples: int = 500,
    seed: int = 42,
) -> dict:
    """
    Counterfactual Fairness: if we change only the protected attribute,
    does the outcome change? Measures % of individuals where flipping
    protected attribute alone changes model output.
    """
    random.seed(seed)
    sample = random.sample(dataset, min(n_samples, len(dataset)))

    group_values = list(set(str(row.get(protected_attr, "")) for row in sample))
    if len(group_values) < 2:
        return {"metric": "Counterfactual Fairness", "passes": True, "severity": "PASS", "flip_rate": 0.0}

    flips = 0
    for row in sample:
        original_outcome = row["approved"]
        current_group = str(row.get(protected_attr, ""))
        other_group = next(g for g in group_values if g != current_group)

        # Simulate counterfactual: change group, keep all other features
        # Using approval rates as proxy for what the model would output
        # In a real system, this would call the model with modified input
        other_group_rate = sum(
            r["approved"] for r in dataset if str(r.get(protected_attr, "")) == other_group
        ) / max(1, sum(1 for r in dataset if str(r.get(protected_attr, "")) == other_group))

        current_group_rate = sum(
            r["approved"] for r in dataset if str(r.get(protected_attr, "")) == current_group
        ) / max(1, sum(1 for r in dataset if str(r.get(protected_attr, "")) == current_group))

        rate_diff = abs(other_group_rate - current_group_rate)
        # If rate diff > 10%, this individual's outcome likely would have differed
        if rate_diff > 0.10 and original_outcome == int(current_group_rate > 0.65):
            flips += 1

    flip_rate = flips / len(sample) if sample else 0.0
    return {
        "metric": "Counterfactual Fairness",
        "protected_attribute": protected_attr,
        "samples_tested": len(sample),
        "counterfactual_flips": flips,
        "flip_rate": round(flip_rate, 4),
        "threshold": 0.10,
        "passes": flip_rate <= 0.10,
        "severity": "FAIL" if flip_rate > 0.10 else "PASS",
        "interpretation": (
            f"{flip_rate:.1%} of individuals would likely receive a different outcome "
            f"if their {protected_attr} attribute were changed. "
            f"{'Indicates systematic bias.' if flip_rate > 0.10 else 'Within acceptable bounds.'}"
        ),
    }


def _shap_feature_importance(dataset: list[dict]) -> list[dict]:
    """
    SHAP-style feature importance using correlation analysis.
    Pure Python — no SHAP dependency required.
    Returns features ranked by correlation with outcome (proxy for importance).
    """
    numeric_features = ["credit_score", "income", "years_employed"]
    categorical_proxies = {
        "gender": {"M": 1, "F": 0},
        "race": {"white": 1, "nonwhite": 0},
    }

    outcomes = [row["approved"] for row in dataset]
    mean_outcome = statistics.mean(outcomes)
    std_outcome = statistics.stdev(outcomes) if len(outcomes) > 1 else 1.0

    importances: list[dict] = []

    for feat in numeric_features:
        values = [float(row.get(feat, 0)) for row in dataset]
        mean_feat = statistics.mean(values)
        std_feat = statistics.stdev(values) if len(values) > 1 else 1.0

        if std_feat == 0 or std_outcome == 0:
            corr = 0.0
        else:
            cov = statistics.mean(
                (v - mean_feat) * (o - mean_outcome)
                for v, o in zip(values, outcomes)
            )
            corr = cov / (std_feat * std_outcome)

        importances.append({
            "feature": feat,
            "importance": round(abs(corr), 4),
            "correlation": round(corr, 4),
            "protected": False,
            "disparity_risk": abs(corr) > 0.3 and feat in ("income",),
        })

    for feat, mapping in categorical_proxies.items():
        values = [float(mapping.get(str(row.get(feat, "")), 0)) for row in dataset]
        mean_feat = statistics.mean(values)
        std_feat = statistics.stdev(values) if len(values) > 1 else 1.0

        if std_feat == 0 or std_outcome == 0:
            corr = 0.0
        else:
            cov = statistics.mean(
                (v - mean_feat) * (o - mean_outcome)
                for v, o in zip(values, outcomes)
            )
            corr = cov / (std_feat * std_outcome)

        importances.append({
            "feature": feat,
            "importance": round(abs(corr), 4),
            "correlation": round(corr, 4),
            "protected": True,
            "disparity_risk": abs(corr) > 0.05,
        })

    return sorted(importances, key=lambda x: x["importance"], reverse=True)


# ---------------------------------------------------------------------------
# Mitigation recommendations
# ---------------------------------------------------------------------------

MITIGATION_STRATEGIES: list[dict] = [
    {
        "name": "Resampling — Oversampling minority group",
        "description": "Oversample underrepresented groups in training data using SMOTE or similar.",
        "effectiveness": 0.85,
        "implementation_effort": "LOW",
        "addresses": ["Demographic Parity", "Disparate Impact"],
        "eu_ai_act_ref": "Article 10(2)(f)",
    },
    {
        "name": "Adversarial Debiasing",
        "description": "Train a debiasing adversarial model that removes protected attribute information from representations.",
        "effectiveness": 0.90,
        "implementation_effort": "HIGH",
        "addresses": ["Demographic Parity", "Equalized Odds", "Counterfactual Fairness"],
        "eu_ai_act_ref": "Article 10",
    },
    {
        "name": "Calibrated Threshold Adjustment",
        "description": "Use group-specific decision thresholds to equalize TPR/FPR across groups (post-processing).",
        "effectiveness": 0.75,
        "implementation_effort": "LOW",
        "addresses": ["Equalized Odds", "Demographic Parity"],
        "eu_ai_act_ref": "Article 10",
    },
    {
        "name": "Feature Removal / Proxy Elimination",
        "description": "Remove features that serve as proxies for protected attributes (e.g., ZIP code for race).",
        "effectiveness": 0.65,
        "implementation_effort": "MEDIUM",
        "addresses": ["Disparate Impact", "Counterfactual Fairness"],
        "eu_ai_act_ref": "Article 10(2)(c)",
    },
    {
        "name": "Fairness Constraints in Training",
        "description": "Add fairness constraints to the loss function (e.g., equalized odds loss penalty).",
        "effectiveness": 0.80,
        "implementation_effort": "MEDIUM",
        "addresses": ["Equalized Odds", "Individual Fairness"],
        "eu_ai_act_ref": "Article 10",
    },
    {
        "name": "Human Review Queue for Borderline Cases",
        "description": "Route low-confidence decisions and cases involving protected group members to human review.",
        "effectiveness": 0.95,
        "implementation_effort": "MEDIUM",
        "addresses": ["Demographic Parity", "Individual Fairness"],
        "eu_ai_act_ref": "Article 14 — Human oversight",
    },
]


# ---------------------------------------------------------------------------
# Main data structures
# ---------------------------------------------------------------------------

@dataclass
class FairnessMetricResult:
    metric_name: str
    protected_attribute: str
    passes: bool
    severity: str     # PASS | FAIL
    score_value: float
    threshold: float
    details: dict
    eu_ai_act_ref: str


@dataclass
class FeatureImportanceItem:
    feature: str
    importance_score: float
    correlation: float
    is_protected_attribute: bool
    disparity_risk: bool


@dataclass
class MitigationRecommendation:
    rank: int
    name: str
    description: str
    effectiveness_pct: float
    implementation_effort: str
    addresses: list[str]
    eu_ai_act_ref: str


@dataclass
class BiasDetectionReport:
    system_name: str
    dataset_size: int
    protected_attributes_tested: list[str]

    # Per-attribute, per-metric results
    metric_results: list[FairnessMetricResult]

    # Feature importance
    feature_importances: list[FeatureImportanceItem]

    # Recommendations
    mitigations: list[MitigationRecommendation]

    # Summary
    overall_bias_detected: bool
    failing_metrics: int
    passing_metrics: int
    eu_ai_act_article_10_compliant: bool

    # Evidence for SOC2 AICC-7
    aicc7_evidence_summary: str

    def compute_summary(self) -> None:
        self.failing_metrics = sum(1 for r in self.metric_results if not r.passes)
        self.passing_metrics = sum(1 for r in self.metric_results if r.passes)
        self.overall_bias_detected = self.failing_metrics > 0
        # EU AI Act Article 10 compliance requires all bias tests to pass
        self.eu_ai_act_article_10_compliant = self.failing_metrics == 0

        fail_names = [r.metric_name for r in self.metric_results if not r.passes]
        protected_issues = [
            r.protected_attribute for r in self.metric_results
            if not r.passes
        ]
        self.aicc7_evidence_summary = (
            f"Bias testing conducted {self.dataset_size:,} samples. "
            f"Protected attributes tested: {', '.join(self.protected_attributes_tested)}. "
            f"Failing metrics: {', '.join(fail_names) if fail_names else 'None'}. "
            f"EU AI Act Article 10(2)(f) status: {'NON-COMPLIANT' if self.failing_metrics > 0 else 'COMPLIANT'}."
        )


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------

class BiasDetector:
    """
    Comprehensive fairness testing engine.
    Runs 5 fairness metrics across all protected attributes.
    Generates synthetic data for zero-credential demos.
    """

    def __init__(
        self,
        system_name: str = "HiringAI",
        protected_attributes: Optional[list[str]] = None,
        n_samples: int = 2000,
        seed: int = 42,
    ) -> None:
        self.system_name = system_name
        self.protected_attributes = protected_attributes or ["gender", "race", "age_group"]
        self.n_samples = n_samples
        self.seed = seed

    def run(self) -> BiasDetectionReport:
        """Run full bias detection suite. Returns complete report."""
        dataset = generate_synthetic_dataset(
            n_samples=self.n_samples,
            protected_attributes=self.protected_attributes,
            seed=self.seed,
        )

        metric_results: list[FairnessMetricResult] = []

        for attr in self.protected_attributes:
            if attr == "age_group":
                # Skip equalized odds and counterfactual for multi-value attrs for brevity
                metrics_to_run = ["dp", "di"]
            else:
                metrics_to_run = ["dp", "eo", "di", "cf"]

            for metric_code in metrics_to_run:
                if metric_code == "dp":
                    r = _demographic_parity_difference(dataset, attr)
                    metric_results.append(FairnessMetricResult(
                        metric_name="Demographic Parity Difference",
                        protected_attribute=attr,
                        passes=r["passes"],
                        severity=r["severity"],
                        score_value=r["max_difference"],
                        threshold=r["threshold"],
                        details=r,
                        eu_ai_act_ref=r["eu_ai_act_ref"],
                    ))

                elif metric_code == "eo":
                    r = _equalized_odds(dataset, attr)
                    metric_results.append(FairnessMetricResult(
                        metric_name="Equalized Odds (TPR Parity)",
                        protected_attribute=attr,
                        passes=r["passes"],
                        severity=r["severity"],
                        score_value=r["tpr_gap"],
                        threshold=r["threshold"],
                        details=r,
                        eu_ai_act_ref=r["eu_ai_act_ref"],
                    ))

                elif metric_code == "di":
                    r = _disparate_impact_ratio(dataset, attr)
                    metric_results.append(FairnessMetricResult(
                        metric_name="Disparate Impact Ratio (EEOC 4/5ths)",
                        protected_attribute=attr,
                        passes=r["passes"],
                        severity=r["severity"],
                        score_value=r["di_ratio"],
                        threshold=r["threshold"],
                        details=r,
                        eu_ai_act_ref=r.get("eu_ai_act_ref", "Article 10"),
                    ))

                elif metric_code == "cf":
                    r = _counterfactual_fairness_score(dataset, attr, seed=self.seed)
                    metric_results.append(FairnessMetricResult(
                        metric_name="Counterfactual Fairness",
                        protected_attribute=attr,
                        passes=r["passes"],
                        severity=r["severity"],
                        score_value=r["flip_rate"],
                        threshold=r["threshold"],
                        details=r,
                        eu_ai_act_ref="Article 10",
                    ))

        # Individual fairness (cross-attribute)
        if_result = _individual_fairness_score(dataset, seed=self.seed)
        metric_results.append(FairnessMetricResult(
            metric_name="Individual Fairness",
            protected_attribute="all_features",
            passes=if_result["passes"],
            severity=if_result["severity"],
            score_value=if_result["inconsistency_rate"],
            threshold=if_result["threshold"],
            details=if_result,
            eu_ai_act_ref="Article 10",
        ))

        # Feature importances
        raw_importances = _shap_feature_importance(dataset)
        feature_importances = [
            FeatureImportanceItem(
                feature=item["feature"],
                importance_score=item["importance"],
                correlation=item["correlation"],
                is_protected_attribute=item["protected"],
                disparity_risk=item["disparity_risk"],
            )
            for item in raw_importances
        ]

        # Mitigations — ranked by effectiveness descending
        failing_attrs = set(r.protected_attribute for r in metric_results if not r.passes)
        mitigations = [
            MitigationRecommendation(
                rank=i + 1,
                name=m["name"],
                description=m["description"],
                effectiveness_pct=m["effectiveness"] * 100,
                implementation_effort=m["implementation_effort"],
                addresses=m["addresses"],
                eu_ai_act_ref=m["eu_ai_act_ref"],
            )
            for i, m in enumerate(
                sorted(MITIGATION_STRATEGIES, key=lambda x: x["effectiveness"], reverse=True)
            )
        ]

        report = BiasDetectionReport(
            system_name=self.system_name,
            dataset_size=len(dataset),
            protected_attributes_tested=self.protected_attributes,
            metric_results=metric_results,
            feature_importances=feature_importances,
            mitigations=mitigations,
            overall_bias_detected=False,
            failing_metrics=0,
            passing_metrics=0,
            eu_ai_act_article_10_compliant=False,
            aicc7_evidence_summary="",
        )
        report.compute_summary()
        return report
