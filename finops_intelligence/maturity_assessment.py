"""
maturity_assessment.py — FinOps Foundation Maturity Assessment for FinOps Intelligence V2.

Scores organizations against the 6 FinOps Foundation capability domains
(Crawl / Walk / Run) with personalized roadmap and peer benchmarking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class MaturityLevel(str, Enum):
    CRAWL = "CRAWL"
    WALK = "WALK"
    RUN = "RUN"


@dataclass
class AssessmentQuestion:
    """Single assessment question."""
    id: str
    domain: str
    text: str
    crawl_indicator: str    # what CRAWL looks like
    walk_indicator: str     # what WALK looks like
    run_indicator: str      # what RUN looks like
    weight: float = 1.0     # relative importance in domain score


@dataclass
class QuestionResponse:
    """Response to an assessment question."""
    question_id: str
    score: int              # 1=Crawl, 2=Walk, 3=Run
    evidence: str = ""      # optional supporting evidence


@dataclass
class DomainScore:
    """Score for a single FinOps Foundation domain."""
    domain: str
    display_name: str
    level: MaturityLevel
    score: float            # 0.0–1.0
    max_score: float
    question_scores: dict[str, int]  # question_id -> score
    strengths: list[str]
    gaps: list[str]
    priority_actions: list[str]      # ranked next steps to reach next level
    peer_benchmark_pct: float        # what % of peer companies are at this level or below


@dataclass
class MaturityReport:
    """Complete maturity assessment report."""
    generated_at: date
    account_name: str
    overall_level: MaturityLevel
    overall_score: float    # 0.0–1.0
    domain_scores: list[DomainScore]
    peer_company_profile: str   # e.g. "50-200 engineers, Series B SaaS"
    roadmap: list[dict[str, Any]]  # ordered list of recommended actions
    quick_wins: list[str]          # things achievable in < 2 weeks
    headline_finding: str


# ---------------------------------------------------------------------------
# Assessment questions (30+ across 6 domains)
# ---------------------------------------------------------------------------

DOMAINS = [
    "Understand Cloud Usage & Cost",
    "Performance Tracking & Benchmarking",
    "Real-Time Decision Making",
    "Cloud Rate Optimization",
    "Cloud Usage Optimization",
    "Organizational Alignment",
]

QUESTIONS: list[AssessmentQuestion] = [
    # Domain 1: Understand Cloud Usage & Cost
    AssessmentQuestion(
        id="d1_q1", domain="Understand Cloud Usage & Cost",
        text="How is cloud spend tracked and reported?",
        crawl_indicator="Monthly invoice review only",
        walk_indicator="Daily cost reports with service breakdown",
        run_indicator="Real-time cost streaming with anomaly detection",
        weight=1.5,
    ),
    AssessmentQuestion(
        id="d1_q2", domain="Understand Cloud Usage & Cost",
        text="What is your resource tagging coverage?",
        crawl_indicator="<40% of resources tagged",
        walk_indicator="60-80% coverage, enforced on new resources",
        run_indicator=">90% coverage, automated enforcement, drift detection",
        weight=1.2,
    ),
    AssessmentQuestion(
        id="d1_q3", domain="Understand Cloud Usage & Cost",
        text="How are costs allocated to teams/products?",
        crawl_indicator="No allocation — single cost center",
        walk_indicator="Manual showback reports monthly",
        run_indicator="Automated chargeback with product P&L",
        weight=1.3,
    ),
    AssessmentQuestion(
        id="d1_q4", domain="Understand Cloud Usage & Cost",
        text="Are unit economics tracked?",
        crawl_indicator="Total spend only",
        walk_indicator="Cost-per-user or cost-per-transaction tracked",
        run_indicator="Multiple unit metrics with trend analysis and benchmarking",
        weight=1.4,
    ),
    AssessmentQuestion(
        id="d1_q5", domain="Understand Cloud Usage & Cost",
        text="Is CUR (Cost & Usage Report) enabled and ingested?",
        crawl_indicator="Using AWS Console only",
        walk_indicator="CUR enabled, manual analysis",
        run_indicator="CUR streaming to analytics (Athena/DuckDB), automated pipelines",
        weight=1.0,
    ),

    # Domain 2: Performance Tracking & Benchmarking
    AssessmentQuestion(
        id="d2_q1", domain="Performance Tracking & Benchmarking",
        text="How are KPIs defined for cloud efficiency?",
        crawl_indicator="No formal KPIs",
        walk_indicator="1-2 KPIs tracked (e.g. monthly spend, budget variance)",
        run_indicator="Full KPI dashboard: unit economics, efficiency ratios, coverage",
        weight=1.3,
    ),
    AssessmentQuestion(
        id="d2_q2", domain="Performance Tracking & Benchmarking",
        text="Is spend benchmarked against industry peers?",
        crawl_indicator="No benchmarking",
        walk_indicator="Annual benchmarking via Gartner/Flexera report",
        run_indicator="Continuous benchmarking against peer cohort",
        weight=1.0,
    ),
    AssessmentQuestion(
        id="d2_q3", domain="Performance Tracking & Benchmarking",
        text="Are budget variances reviewed and acted on?",
        crawl_indicator="Month-end only, after invoice arrives",
        walk_indicator="Weekly budget review meetings",
        run_indicator="Automated budget alerts with runbook-triggered responses",
        weight=1.2,
    ),
    AssessmentQuestion(
        id="d2_q4", domain="Performance Tracking & Benchmarking",
        text="How is forecast accuracy tracked?",
        crawl_indicator="Not tracked",
        walk_indicator="Monthly forecast vs. actuals comparison",
        run_indicator="ML forecasting with MAPE tracking and model retraining",
        weight=1.1,
    ),

    # Domain 3: Real-Time Decision Making
    AssessmentQuestion(
        id="d3_q1", domain="Real-Time Decision Making",
        text="How quickly are cost anomalies detected?",
        crawl_indicator=">1 week (monthly invoice review)",
        walk_indicator="Daily email digests with threshold alerts",
        run_indicator="Sub-hour anomaly detection with ML + PagerDuty integration",
        weight=1.5,
    ),
    AssessmentQuestion(
        id="d3_q2", domain="Real-Time Decision Making",
        text="Can engineers query cloud costs ad-hoc?",
        crawl_indicator="Must request reports from finance",
        walk_indicator="Self-service dashboards (e.g. AWS Cost Explorer)",
        run_indicator="Natural language cost Q&A, API for any query, Slack bot",
        weight=1.3,
    ),
    AssessmentQuestion(
        id="d3_q3", domain="Real-Time Decision Making",
        text="Are cost implications evaluated before deploying new services?",
        crawl_indicator="Not consistently",
        walk_indicator="Manual cost estimation in design docs",
        run_indicator="Automated cost estimation in CI/CD pipeline",
        weight=1.2,
    ),
    AssessmentQuestion(
        id="d3_q4", domain="Real-Time Decision Making",
        text="Are there automated cost guardrails (budgets/SCPs)?",
        crawl_indicator="No automated guardrails",
        walk_indicator="AWS Budgets alerts configured",
        run_indicator="SCP-enforced spend controls + auto-remediation Lambda",
        weight=1.4,
    ),

    # Domain 4: Cloud Rate Optimization
    AssessmentQuestion(
        id="d4_q1", domain="Cloud Rate Optimization",
        text="What is your RI/Savings Plan coverage?",
        crawl_indicator="<20% coverage — mostly on-demand",
        walk_indicator="40-60% coverage",
        run_indicator=">70% coverage with quarterly optimization reviews",
        weight=1.5,
    ),
    AssessmentQuestion(
        id="d4_q2", domain="Cloud Rate Optimization",
        text="Are Enterprise Discount Program (EDP) terms negotiated?",
        crawl_indicator="Pay-as-you-go, no commitment",
        walk_indicator="Casual discussion but no formal EDP",
        run_indicator="Multi-year EDP with volume discount + AWS TAM engagement",
        weight=1.0,
    ),
    AssessmentQuestion(
        id="d4_q3", domain="Cloud Rate Optimization",
        text="Are Spot Instances used for eligible workloads?",
        crawl_indicator="No Spot usage",
        walk_indicator="Spot for dev/test environments",
        run_indicator="Spot fleet for 30-50% of production compute with interruption handling",
        weight=1.2,
    ),
    AssessmentQuestion(
        id="d4_q4", domain="Cloud Rate Optimization",
        text="Are newer/cheaper instance families adopted (e.g. Graviton3)?",
        crawl_indicator="Legacy x86 instances, no migration plan",
        walk_indicator="Graviton2 for some services",
        run_indicator="Graviton3 default for all new services, migration roadmap for existing",
        weight=1.1,
    ),

    # Domain 5: Cloud Usage Optimization
    AssessmentQuestion(
        id="d5_q1", domain="Cloud Usage Optimization",
        text="How are idle/orphaned resources identified and eliminated?",
        crawl_indicator="Ad-hoc, when noticed",
        walk_indicator="Monthly automated waste report",
        run_indicator="Continuous scanning + auto-termination with approval workflow",
        weight=1.4,
    ),
    AssessmentQuestion(
        id="d5_q2", domain="Cloud Usage Optimization",
        text="Is rightsizing analysis run on EC2/RDS?",
        crawl_indicator="Not run",
        walk_indicator="Quarterly manual review using AWS Trusted Advisor",
        run_indicator="Automated weekly rightsizing via Compute Optimizer + auto-apply",
        weight=1.3,
    ),
    AssessmentQuestion(
        id="d5_q3", domain="Cloud Usage Optimization",
        text="Are S3 lifecycle policies and intelligent tiering configured?",
        crawl_indicator="Standard storage only, no lifecycle",
        walk_indicator="Lifecycle rules for objects >90 days",
        run_indicator="Intelligent Tiering on all buckets + Glacier for archives",
        weight=1.0,
    ),
    AssessmentQuestion(
        id="d5_q4", domain="Cloud Usage Optimization",
        text="Is serverless/PaaS used to reduce always-on compute?",
        crawl_indicator="Mostly EC2 instances (pet servers)",
        walk_indicator="Lambda for async workloads, Fargate for containers",
        run_indicator="Serverless-first architecture, EC2 only where required",
        weight=1.1,
    ),
    AssessmentQuestion(
        id="d5_q5", domain="Cloud Usage Optimization",
        text="Are data transfer costs actively managed?",
        crawl_indicator="Not tracked separately",
        walk_indicator="Monthly review of transfer costs",
        run_indicator="VPC endpoints for all S3/DynamoDB, NAT Gateway optimization",
        weight=1.2,
    ),

    # Domain 6: Organizational Alignment
    AssessmentQuestion(
        id="d6_q1", domain="Organizational Alignment",
        text="Is there a dedicated FinOps role or team?",
        crawl_indicator="No dedicated role — finance handles billing",
        walk_indicator="FinOps champion (part-time) embedded in platform team",
        run_indicator="Dedicated FinOps team with SRE/Finance/Product representation",
        weight=1.5,
    ),
    AssessmentQuestion(
        id="d6_q2", domain="Organizational Alignment",
        text="Do engineering teams have cost visibility for their services?",
        crawl_indicator="No — only finance sees billing",
        walk_indicator="Monthly email report per team",
        run_indicator="Self-service dashboard, teams own their cost budgets",
        weight=1.3,
    ),
    AssessmentQuestion(
        id="d6_q3", domain="Organizational Alignment",
        text="Are cloud costs included in sprint planning and estimates?",
        crawl_indicator="Never discussed in engineering",
        walk_indicator="Occasionally raised in architecture reviews",
        run_indicator="Cost estimate required in every feature spec; engineers own their service P&L",
        weight=1.2,
    ),
    AssessmentQuestion(
        id="d6_q4", domain="Organizational Alignment",
        text="Is there executive sponsorship for FinOps?",
        crawl_indicator="Cloud costs are IT's problem",
        walk_indicator="CTO/VP Engineering aware and supportive",
        run_indicator="CFO + CTO co-own cloud cost KPIs; reviewed in board meetings",
        weight=1.0,
    ),
    AssessmentQuestion(
        id="d6_q5", domain="Organizational Alignment",
        text="Is there a FinOps policy/runbook for common scenarios?",
        crawl_indicator="No documented policies",
        walk_indicator="Basic tagging policy + budget alert escalation path",
        run_indicator="Comprehensive FinOps playbook: anomaly response, commitment approval, waste elimination SLA",
        weight=1.1,
    ),
]

# Peer benchmarks: % of companies at CRAWL/WALK/RUN for each domain
# Source: FinOps Foundation State of FinOps 2024 (approximated)
PEER_BENCHMARKS: dict[str, dict[str, float]] = {
    "Understand Cloud Usage & Cost":    {"CRAWL": 35, "WALK": 45, "RUN": 20},
    "Performance Tracking & Benchmarking": {"CRAWL": 45, "WALK": 40, "RUN": 15},
    "Real-Time Decision Making":        {"CRAWL": 50, "WALK": 35, "RUN": 15},
    "Cloud Rate Optimization":          {"CRAWL": 40, "WALK": 40, "RUN": 20},
    "Cloud Usage Optimization":         {"CRAWL": 42, "WALK": 43, "RUN": 15},
    "Organizational Alignment":         {"CRAWL": 55, "WALK": 35, "RUN": 10},
}


# ---------------------------------------------------------------------------
# MaturityAssessment
# ---------------------------------------------------------------------------

class MaturityAssessment:
    """
    FinOps Foundation maturity assessment engine.

    Usage (interactive):
        assessment = MaturityAssessment()
        responses = assessment.score_from_profile(
            tagging_coverage=65,
            ri_sp_coverage=31,
            has_anomaly_detection=True,
            anomaly_detection_latency_hours=24,
            has_unit_economics=False,
            has_dedicated_finops=False,
            engineers=47,
            monthly_spend=340_000,
        )
        report = assessment.generate_report(responses, account_name="TechStartupCo")

    Usage (explicit):
        responses = [QuestionResponse(question_id="d1_q1", score=2, evidence="Daily reports"), ...]
        report = assessment.generate_report(responses, account_name="TechStartupCo")
    """

    def score_from_profile(
        self,
        tagging_coverage: float = 0.0,          # % 0-100
        ri_sp_coverage: float = 0.0,             # % 0-100
        has_anomaly_detection: bool = False,
        anomaly_detection_latency_hours: int = 168,  # hours to detect anomaly
        has_unit_economics: bool = False,
        has_dedicated_finops: bool = False,
        has_cur_enabled: bool = False,
        uses_spot: bool = False,
        uses_graviton: bool = False,
        has_rightsizing: bool = False,
        engineers: int = 0,
        monthly_spend: float = 0.0,
        has_executive_sponsorship: bool = False,
    ) -> list[QuestionResponse]:
        """
        Derive assessment scores from observable infrastructure signals.
        Avoids lengthy questionnaire — infers scores from data.
        """
        responses: list[QuestionResponse] = []

        def score(qid: str, s: int, evidence: str = "") -> None:
            responses.append(QuestionResponse(question_id=qid, score=s, evidence=evidence))

        # d1: Understand Cloud Usage & Cost
        if anomaly_detection_latency_hours < 2:
            score("d1_q1", 3, "Real-time anomaly detection < 2hrs")
        elif anomaly_detection_latency_hours < 24:
            score("d1_q1", 2, "Daily cost reports")
        else:
            score("d1_q1", 1, "Monthly invoice review only")

        if tagging_coverage >= 90:
            score("d1_q2", 3)
        elif tagging_coverage >= 60:
            score("d1_q2", 2)
        else:
            score("d1_q2", 1)

        score("d1_q3", 2 if monthly_spend > 100_000 else 1)  # at scale, assume walk
        score("d1_q4", 3 if has_unit_economics else 1)
        score("d1_q5", 3 if has_cur_enabled else 1)

        # d2: Performance Tracking
        score("d2_q1", 2 if monthly_spend > 50_000 else 1)
        score("d2_q2", 1)  # most companies don't benchmark
        score("d2_q3", 2 if has_anomaly_detection else 1)
        score("d2_q4", 2 if has_anomaly_detection else 1)

        # d3: Real-Time Decision Making
        if has_anomaly_detection and anomaly_detection_latency_hours < 2:
            score("d3_q1", 3, "ML anomaly detection with PagerDuty")
        elif has_anomaly_detection:
            score("d3_q1", 2, "Daily anomaly alerts")
        else:
            score("d3_q1", 1)

        score("d3_q2", 2 if monthly_spend > 100_000 else 1)
        score("d3_q3", 1)  # most companies don't do CI cost checks
        score("d3_q4", 2 if monthly_spend > 50_000 else 1)

        # d4: Rate Optimization
        if ri_sp_coverage >= 70:
            score("d4_q1", 3, f"{ri_sp_coverage:.0f}% coverage")
        elif ri_sp_coverage >= 40:
            score("d4_q1", 2)
        else:
            score("d4_q1", 1)

        score("d4_q2", 2 if monthly_spend > 200_000 else 1)
        score("d4_q3", 3 if uses_spot else 1)
        score("d4_q4", 3 if uses_graviton else (2 if monthly_spend > 100_000 else 1))

        # d5: Usage Optimization
        score("d5_q1", 2 if has_rightsizing else 1)
        score("d5_q2", 2 if has_rightsizing else 1)
        score("d5_q3", 2 if monthly_spend > 50_000 else 1)
        score("d5_q4", 2 if monthly_spend > 100_000 else 1)
        score("d5_q5", 1)  # data transfer rarely managed

        # d6: Organizational Alignment
        score("d6_q1", 3 if has_dedicated_finops else (2 if monthly_spend > 200_000 else 1))
        score("d6_q2", 2 if monthly_spend > 100_000 else 1)
        score("d6_q3", 1)  # rarely done
        score("d6_q4", 2 if has_executive_sponsorship else 1)
        score("d6_q5", 2 if monthly_spend > 200_000 else 1)

        return responses

    def generate_report(
        self,
        responses: list[QuestionResponse],
        account_name: str = "Your Organization",
        peer_profile: str = "50-200 engineers, growth-stage SaaS",
    ) -> MaturityReport:
        """Generate full maturity report from question responses."""
        response_map = {r.question_id: r for r in responses}

        domain_scores: list[DomainScore] = []
        for domain_name in DOMAINS:
            ds = self._score_domain(domain_name, response_map)
            domain_scores.append(ds)

        overall_score = sum(ds.score for ds in domain_scores) / len(domain_scores)
        if overall_score >= 0.66:
            overall_level = MaturityLevel.RUN
        elif overall_score >= 0.33:
            overall_level = MaturityLevel.WALK
        else:
            overall_level = MaturityLevel.CRAWL

        roadmap = self._build_roadmap(domain_scores, overall_level)
        quick_wins = self._identify_quick_wins(domain_scores)
        headline = self._headline(domain_scores, overall_level, overall_score)

        return MaturityReport(
            generated_at=date.today(),
            account_name=account_name,
            overall_level=overall_level,
            overall_score=round(overall_score, 3),
            domain_scores=domain_scores,
            peer_company_profile=peer_profile,
            roadmap=roadmap,
            quick_wins=quick_wins,
            headline_finding=headline,
        )

    # ------------------------------------------------------------------
    # Domain scoring
    # ------------------------------------------------------------------

    def _score_domain(
        self,
        domain_name: str,
        response_map: dict[str, QuestionResponse],
    ) -> DomainScore:
        domain_questions = [q for q in QUESTIONS if q.domain == domain_name]
        if not domain_questions:
            return DomainScore(
                domain=domain_name,
                display_name=domain_name,
                level=MaturityLevel.CRAWL,
                score=0.0,
                max_score=1.0,
                question_scores={},
                strengths=[],
                gaps=[],
                priority_actions=[],
                peer_benchmark_pct=0.0,
            )

        total_weight = sum(q.weight for q in domain_questions)
        weighted_score = 0.0
        question_scores: dict[str, int] = {}
        strengths: list[str] = []
        gaps: list[str] = []

        for q in domain_questions:
            resp = response_map.get(q.id)
            s = resp.score if resp else 1
            question_scores[q.id] = s
            weighted_score += (s - 1) / 2 * q.weight  # normalize: (1-3) -> (0-1)

            if s == 3:
                strengths.append(q.run_indicator)
            elif s == 1:
                gaps.append(f"[{q.text}] Currently: {q.crawl_indicator} → Target: {q.walk_indicator}")

        normalized = weighted_score / total_weight
        if normalized >= 0.66:
            level = MaturityLevel.RUN
        elif normalized >= 0.33:
            level = MaturityLevel.WALK
        else:
            level = MaturityLevel.CRAWL

        # Priority actions to reach next level
        priority_actions: list[str] = []
        if level == MaturityLevel.CRAWL:
            # Take the top 3 most-weighted crawl questions and suggest walk actions
            low_q = sorted(
                [(q, question_scores.get(q.id, 1)) for q in domain_questions if question_scores.get(q.id, 1) < 2],
                key=lambda x: x[0].weight, reverse=True
            )[:3]
            for q, _ in low_q:
                priority_actions.append(f"Achieve WALK: {q.walk_indicator}")
        elif level == MaturityLevel.WALK:
            walk_q = sorted(
                [(q, question_scores.get(q.id, 1)) for q in domain_questions if question_scores.get(q.id, 1) < 3],
                key=lambda x: x[0].weight, reverse=True
            )[:2]
            for q, _ in walk_q:
                priority_actions.append(f"Achieve RUN: {q.run_indicator}")

        # Peer benchmark
        bench = PEER_BENCHMARKS.get(domain_name, {})
        if level == MaturityLevel.RUN:
            peer_pct = 100.0 - bench.get("RUN", 15)
        elif level == MaturityLevel.WALK:
            peer_pct = bench.get("CRAWL", 40)
        else:
            peer_pct = 15.0

        return DomainScore(
            domain=domain_name,
            display_name=domain_name,
            level=level,
            score=round(normalized, 3),
            max_score=1.0,
            question_scores=question_scores,
            strengths=strengths[:3],
            gaps=gaps[:3],
            priority_actions=priority_actions[:3],
            peer_benchmark_pct=round(peer_pct, 0),
        )

    # ------------------------------------------------------------------
    # Roadmap + quick wins
    # ------------------------------------------------------------------

    def _build_roadmap(
        self,
        domain_scores: list[DomainScore],
        overall_level: MaturityLevel,
    ) -> list[dict[str, Any]]:
        """Ordered roadmap: lowest-score domains first, with highest-weight gaps."""
        roadmap: list[dict[str, Any]] = []
        sorted_domains = sorted(domain_scores, key=lambda d: d.score)

        for i, ds in enumerate(sorted_domains[:4], 1):
            if ds.priority_actions:
                roadmap.append({
                    "priority": i,
                    "domain": ds.domain,
                    "current_level": ds.level.value,
                    "target_level": "WALK" if ds.level == MaturityLevel.CRAWL else "RUN",
                    "actions": ds.priority_actions,
                    "estimated_impact": "MEDIUM" if i <= 2 else "LOW",
                })
        return roadmap

    def _identify_quick_wins(self, domain_scores: list[DomainScore]) -> list[str]:
        """Things achievable in < 2 weeks with low effort."""
        quick_wins = []
        for ds in domain_scores:
            if ds.level == MaturityLevel.CRAWL:
                # First action from each crawl domain is a quick win candidate
                if ds.priority_actions:
                    quick_wins.append(f"{ds.domain}: {ds.priority_actions[0]}")
        return quick_wins[:5]

    def _headline(
        self,
        domain_scores: list[DomainScore],
        overall_level: MaturityLevel,
        overall_score: float,
    ) -> str:
        worst = min(domain_scores, key=lambda d: d.score)
        best = max(domain_scores, key=lambda d: d.score)
        pct = round(overall_score * 100)

        return (
            f"Overall FinOps maturity: {overall_level.value} ({pct}% of RUN). "
            f"Strongest domain: {best.domain} ({best.level.value}). "
            f"Biggest gap: {worst.domain} ({worst.level.value}) — "
            f"{worst.priority_actions[0] if worst.priority_actions else 'review domain practices'}."
        )
