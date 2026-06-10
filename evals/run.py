"""
evals/run.py
============

Entry point: python -m evals.run [--offline] [--suite NAME] [--report PATH]

Offline mode (default in CI):
  - IaC suite: runs real PolicyEngine, scores F1 against golden dataset.
  - 6R suite: validates dataset integrity (label correctness, schema).
  - Injection suite: calls core.guardrails if available; SKIP if absent.

Live mode (ANTHROPIC_API_KEY set AND --offline not passed):
  - Additionally runs 6R cases through the real model path and scores
    predicted labels against golden expected labels.

Exit codes:
  0 — all non-skipped suites passed their thresholds
  1 — one or more suites failed their threshold
  2 — argument / setup error
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure the repo root is importable when run as `python -m evals.run`
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals.loader import LoadResult, list_suites, load_suite
from evals.report import write_report
from evals.scorers import (
    SuiteScore,
    score_iac_policy_detection,
    score_prompt_injection,
    score_six_r_integrity,
)
from evals.thresholds import THRESHOLDS

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(name)s  %(message)s",
)
logger = logging.getLogger("evals.run")


# ---------------------------------------------------------------------------
# Optional live 6R scorer
# ---------------------------------------------------------------------------


def _score_six_r_live(cases: list[dict]) -> SuiteScore:
    """
    Run 6R cases through the real model and score label accuracy.
    Only called when ANTHROPIC_API_KEY is set and --offline is not passed.
    """
    import anthropic  # type: ignore[import]
    from evals.loader import VALID_6R_LABELS

    client = anthropic.Anthropic()

    SYSTEM = (
        "You are a cloud migration expert. Given a workload description, "
        "classify it into exactly one of the 6R strategies: "
        "Rehost, Replatform, Repurchase, Refactor, Retire, Retain. "
        "Reply with ONLY the strategy name — no explanation."
    )

    results: list = []
    passed = 0

    for case in cases:
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=16,
                system=SYSTEM,
                messages=[{"role": "user", "content": case["description"]}],
            )
            predicted = response.content[0].text.strip()
        except Exception as exc:
            logger.warning("API call failed for case %s: %s", case["id"], exc)
            predicted = "ERROR"

        expected = case["expected_label"]
        ok = predicted == expected
        if ok:
            passed += 1

        from evals.scorers import CaseResult
        results.append(
            CaseResult(
                case_id=case["id"],
                passed=ok,
                detail=f"predicted={predicted!r} expected={expected!r}",
            )
        )

    accuracy = passed / len(cases) if cases else 0.0
    return SuiteScore(
        suite="six_r_classification",
        metric="label_accuracy",
        score=round(accuracy, 4),
        case_results=results,
        total_cases=len(cases),
        passed_cases=passed,
    )


# ---------------------------------------------------------------------------
# Gate check
# ---------------------------------------------------------------------------


def _check_gate(scores: list[SuiteScore]) -> bool:
    """Return True if all non-skipped suites passed their thresholds."""
    all_passed = True
    for score in scores:
        if score.skipped:
            continue
        threshold = THRESHOLDS.get(score.suite)
        if threshold is None:
            continue
        if score.score < threshold.min_value:
            logger.error(
                "GATE FAIL  suite=%s  metric=%s  score=%.4f  threshold=%.2f",
                score.suite,
                score.metric,
                score.score,
                threshold.min_value,
            )
            all_passed = False
        else:
            logger.info(
                "GATE PASS  suite=%s  metric=%s  score=%.4f  threshold=%.2f",
                score.suite,
                score.metric,
                score.score,
                threshold.min_value,
            )
    return all_passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.run",
        description="Run the Enterprise AI Accelerator eval harness.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force offline mode even if ANTHROPIC_API_KEY is set.",
    )
    parser.add_argument(
        "--suite",
        metavar="NAME",
        help=(
            "Run only the named suite "
            f"(choices: {', '.join(list_suites())}). "
            "Default: all suites."
        ),
    )
    parser.add_argument(
        "--report",
        metavar="PATH",
        help="Write report to this path (without extension). "
        "Default: evals/results/eval-<mode>-<timestamp>",
    )
    args = parser.parse_args(argv)

    offline = args.offline or not os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-")
    mode_label = "offline" if offline else "live"
    logger.info("Eval harness starting  mode=%s", mode_label)

    suites_to_run: list[str] = (
        [args.suite] if args.suite else list_suites()
    )
    if args.suite and args.suite not in list_suites():
        logger.error(
            "Unknown suite %r. Valid suites: %s",
            args.suite,
            ", ".join(list_suites()),
        )
        return 2

    scores: list[SuiteScore] = []

    for suite_name in suites_to_run:
        logger.info("Loading suite: %s", suite_name)
        load_result: LoadResult = load_suite(suite_name)

        if not load_result.ok:
            for err in load_result.errors:
                logger.error("Loader error [%s]: %s", suite_name, err)
            # Dataset integrity failure — emit a zero score so the gate fails
            scores.append(
                SuiteScore(
                    suite=suite_name,
                    metric="dataset_integrity",
                    score=0.0,
                    total_cases=0,
                    passed_cases=0,
                )
            )
            continue

        logger.info("Scoring suite: %s  cases=%d", suite_name, len(load_result.cases))

        if suite_name == "iac_policy_detection":
            scores.append(score_iac_policy_detection(load_result.cases))

        elif suite_name == "six_r_classification":
            if not offline:
                logger.info("Live mode: running 6R cases through model")
                scores.append(_score_six_r_live(load_result.cases))
            else:
                scores.append(score_six_r_integrity(load_result.cases))

        elif suite_name == "prompt_injection_redteam":
            scores.append(score_prompt_injection(load_result.cases))

    # Print a compact summary to stdout
    print()
    print(f"{'Suite':<35} {'Metric':<20} {'Score':>7}  {'Status'}")
    print("-" * 75)
    gate_pass = _check_gate(scores)
    for score in scores:
        from evals.thresholds import THRESHOLDS as _T
        threshold = _T.get(score.suite)
        if score.skipped:
            status = "SKIP"
            score_display = "    —  "
        else:
            status = (
                "PASS"
                if threshold is None or score.score >= threshold.min_value
                else "FAIL"
            )
            score_display = f"{score.score:7.4f}"
        print(f"{score.suite:<35} {score.metric:<20} {score_display}  {status}")
    print()

    report_path = Path(args.report) if args.report else None
    md_path = write_report(scores, report_path=report_path, offline=offline)
    logger.info("Report written: %s", md_path)

    return 0 if gate_pass else 1


if __name__ == "__main__":
    sys.exit(main())
