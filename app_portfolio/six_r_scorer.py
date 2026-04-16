"""
app_portfolio/six_r_scorer.py
===============================

The killer feature: Opus 4.7 extended-thinking 6R migration strategy scorer.

Feeds the full PortfolioReport into Claude Opus 4.7 with THINKING_BUDGET_HIGH
(16k tokens of interleaved reasoning) and returns a SixRRecommendation with
a persisted reasoning trace.

6R Framework:
  Retire      — decommission; no cloud value (high CVE, 0 LoC activity,
                 zero test coverage, minimal CI)
  Retain       — keep on-prem for now; cloud migration not yet justified
  Rehost       — lift-and-shift; already containerized + pinned deps
  Replatform   — minor cloud optimisations (managed DB, autoscaling)
  Refactor     — re-architect for cloud-native; high complexity, active codebase
  Repurchase   — replace with SaaS; commodity function + stale custom code

The tool schema is strictly typed so the model cannot hallucinate free-form
JSON — Anthropic validates on the server side.

Reasoning trace is returned alongside the recommendation for audit persistence
(caller can store in AIAuditTrail or write to disk).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core import AIClient, MODEL_OPUS_4_7, THINKING_BUDGET_HIGH
from app_portfolio.report import PortfolioReport, SixRRecommendation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

_SIX_R_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "strategy": {
            "type": "string",
            "enum": ["retire", "retain", "rehost", "replatform", "refactor", "repurchase"],
            "description": (
                "The recommended 6R migration strategy. "
                "retire=decommission, retain=keep on-prem, rehost=lift-and-shift, "
                "replatform=minor cloud optimisations, refactor=re-architect, "
                "repurchase=replace with SaaS."
            ),
        },
        "confidence": {
            "type": "number",
            "description": (
                "Confidence in this recommendation, 0.0 (low) to 1.0 (high). "
                "Driven by data completeness and signal strength."
            ),
        },
        "rationale": {
            "type": "string",
            "description": (
                "2-4 sentence rationale grounded in the actual repo metrics "
                "(languages, LoC, CVE count, staleness, CI score, container score, "
                "test ratio). Do not speculate beyond the data provided."
            ),
        },
        "effort_weeks": {
            "type": "integer",
            "description": "Estimated migration effort in calendar weeks (1-104).",
        },
        "risk": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Overall migration risk level.",
        },
        "blockers": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Concrete blockers that must be resolved before migration "
                "(e.g. 'Unpatched CRITICAL CVE in requests 2.19', "
                "'No Dockerfile', '0% test coverage'). 0-5 items."
            ),
        },
        "quick_wins": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Actionable quick wins achievable in < 1 week that improve "
                "cloud readiness (e.g. 'Add .dockerignore', "
                "'Pin base image to python:3.12-slim', "
                "'Add GitHub Actions test workflow'). 0-5 items."
            ),
        },
    },
    "required": [
        "strategy", "confidence", "rationale",
        "effort_weeks", "risk", "blockers", "quick_wins",
    ],
}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert cloud migration architect specialising in the AWS 6R framework.

## The 6R Strategies (in order from least to most transformation)
- **Retire**: Application is EOL or redundant — recommend decommission.
- **Retain**: App is not ready or not worth migrating — recommend on-prem for now.
- **Rehost** (lift-and-shift): Migrate as-is, typically via containers or VM.
  Signals: already containerized, pinned deps, decent CI, no critical CVEs.
- **Replatform** (lift-tinker-and-shift): Minor cloud optimisations without
  re-architecture. Signals: containerizable, some stale deps, CI gaps.
- **Refactor** (re-architect): Significant redesign to leverage cloud-native.
  Signals: active codebase (high LoC), but no containers, many CVEs, poor CI.
- **Repurchase**: Replace with SaaS/managed service.
  Signals: commodity function, highly stale, low unique LoC, minimal test coverage.

## Decision heuristics
- containerization_score ≥ 70 AND ci_maturity_score ≥ 60 AND critical_cves == 0
  → strong Rehost signal
- total_loc ≥ 50k AND test_ratio ≥ 0.2 AND containerization_score < 40
  → strong Refactor signal
- critical_cves ≥ 5 AND stale_deps > 30% of total → add to blockers
- test_ratio == 0 → mention as blocker
- total_loc < 2000 AND dep_count < 10 → consider Repurchase

## Output rules
- Base ALL claims on the provided JSON metrics. Never invent details.
- effort_weeks: Retire=1, Retain=2, Rehost=4-12, Replatform=8-20,
  Refactor=16-52, Repurchase=8-24.
- Provide 2-4 blockers and 2-4 quick wins maximum.
- confidence should reflect data completeness (0.9 if all scanners ran,
  0.6 if several returned zeros due to unsupported ecosystem).
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def score_six_r(
    report: PortfolioReport,
    ai: AIClient,
) -> SixRRecommendation:
    """Use Opus 4.7 extended thinking to recommend a 6R migration strategy.

    Args:
        report: Fully populated PortfolioReport (all sub-scanners should have run).
        ai: AIClient instance (uses MODEL_OPUS_4_7 + THINKING_BUDGET_HIGH).

    Returns:
        SixRRecommendation with thinking_trace populated for audit trail.
        Falls back to a conservative 'retain' recommendation on any error.
    """
    try:
        return await _score_inner(report, ai)
    except Exception as exc:  # noqa: BLE001
        logger.error("six_r_scorer failed: %s", exc)
        return SixRRecommendation(
            strategy="retain",
            confidence=0.1,
            rationale=(
                f"Scoring failed due to an error: {exc}. "
                "Defaulting to Retain — manual review required."
            ),
            effort_weeks=2,
            risk="high",
            blockers=["Automated scoring error — review manually"],
            quick_wins=[],
            thinking_trace="",
        )


async def _score_inner(
    report: PortfolioReport,
    ai: AIClient,
) -> SixRRecommendation:
    # Build a compact but complete summary of the report for the model
    dep_summary = _build_dep_summary(report)
    user_payload = json.dumps(
        {
            "repo_name": report.repo_name,
            "primary_language": report.primary_language,
            "languages": report.languages,
            "total_loc": report.total_loc,
            "dependencies": dep_summary,
            "containerization_score": report.containerization_score,
            "containerization_issues": report.containerization_issues,
            "ci_maturity_score": report.ci_maturity_score,
            "ci_maturity_issues": report.ci_maturity_issues,
            "test_coverage": {
                "test_files": report.test_file_count,
                "source_files": report.source_file_count,
                "ratio": round(report.test_ratio, 3),
                "config_found": report.test_config_found,
            },
            "security_hotspots": report.security_hotspots,
        },
        indent=2,
        default=str,
    )

    user_message = (
        "Analyse this application portfolio report and recommend the optimal "
        "6R migration strategy. Use the tool to return your structured recommendation.\n\n"
        "```json\n"
        f"{user_payload}\n"
        "```"
    )

    structured_resp, thinking_trace = await ai.structured_with_thinking(
        system=_SYSTEM_PROMPT,
        user=user_message,
        schema=_SIX_R_SCHEMA,
        tool_name="recommend_migration_strategy",
        tool_description=(
            "Return the 6R migration strategy recommendation with full rationale, "
            "effort estimate, risk level, blockers, and quick wins."
        ),
        model=MODEL_OPUS_4_7,
        max_tokens=4096,
        budget_tokens=THINKING_BUDGET_HIGH,
    )

    data = structured_resp.data

    return SixRRecommendation(
        strategy=data.get("strategy", "retain"),
        confidence=float(data.get("confidence", 0.5)),
        rationale=data.get("rationale", ""),
        effort_weeks=int(data.get("effort_weeks", 8)),
        risk=data.get("risk", "medium"),
        blockers=list(data.get("blockers", [])),
        quick_wins=list(data.get("quick_wins", [])),
        thinking_trace=thinking_trace,
    )


def _build_dep_summary(report: PortfolioReport) -> dict[str, Any]:
    """Build a compact dep summary to keep the prompt token-efficient."""
    critical_deps = [
        {
            "name": d.name,
            "version": d.version,
            "ecosystem": d.ecosystem,
            "cves": [{"id": c.id, "severity": c.severity} for c in d.cves[:3]],
        }
        for d in report.dependencies
        if d.has_cves
    ][:20]  # cap at 20 vulnerable deps

    stale_count = report.stale_dep_count
    total_count = len(report.dependencies)
    prod_count = report.dep_count

    return {
        "total": total_count,
        "production": prod_count,
        "stale_count": stale_count,
        "stale_pct": round(stale_count / total_count * 100, 1) if total_count else 0,
        "vulnerable_count": report.vulnerable_dep_count,
        "critical_or_high_cves": report.critical_cve_count,
        "vulnerable_deps_sample": critical_deps,
    }
