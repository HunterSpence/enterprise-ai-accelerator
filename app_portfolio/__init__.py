"""
app_portfolio — App Portfolio Analyzer
========================================

Auto-scores 6R migration strategy from a repo's actual state.
CAST Highlight / vFunction competitor powered by Opus 4.7 extended thinking.

Public API::

    from app_portfolio import RepoAnalyzer, PortfolioReport, SixRRecommendation

    analyzer = RepoAnalyzer()
    report = await analyzer.analyze(Path("/path/to/repo"))

    # Optional AI scoring (requires ANTHROPIC_API_KEY)
    from app_portfolio import score_six_r
    from core import get_client
    report.six_r_recommendation = await score_six_r(report, get_client())

    print(report.render_markdown())
    print(report.render_json())
"""

from app_portfolio.report import PortfolioReport, Dependency, Vulnerability, SixRRecommendation
from app_portfolio.analyzer import RepoAnalyzer
from app_portfolio.six_r_scorer import score_six_r
from app_portfolio.language_detector import detect_languages
from app_portfolio.dependency_scanner import scan_dependencies
from app_portfolio.cve_scanner import scan_cves
from app_portfolio.containerization_scorer import score_containerization
from app_portfolio.ci_maturity_scorer import score_ci_maturity
from app_portfolio.test_coverage_scanner import scan_test_coverage

__all__ = [
    # Core types
    "PortfolioReport",
    "Dependency",
    "Vulnerability",
    "SixRRecommendation",
    # Orchestrator
    "RepoAnalyzer",
    # Scorer
    "score_six_r",
    # Individual scanners (for use in custom pipelines)
    "detect_languages",
    "scan_dependencies",
    "scan_cves",
    "score_containerization",
    "score_ci_maturity",
    "scan_test_coverage",
]
