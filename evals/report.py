"""
evals/report.py
===============

Write JSON and Markdown evaluation reports to evals/results/.

Results directory is gitignored (see evals/.gitignore).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.scorers import SuiteScore
from evals.thresholds import THRESHOLDS

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent / "results"


def _threshold_status(score: SuiteScore) -> str:
    if score.skipped:
        return "SKIP"
    threshold = THRESHOLDS.get(score.suite)
    if threshold is None:
        return "PASS"
    return "PASS" if score.score >= threshold.min_value else "FAIL"


def write_report(
    scores: list[SuiteScore],
    report_path: Path | None = None,
    offline: bool = True,
) -> Path:
    """
    Write JSON + Markdown reports.  Returns the path to the markdown file.

    If report_path is None, files are written to evals/results/ with a
    timestamp in the filename.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode_tag = "offline" if offline else "live"

    if report_path is None:
        base = RESULTS_DIR / f"eval-{mode_tag}-{ts}"
    else:
        base = Path(str(report_path).removesuffix(".md").removesuffix(".json"))

    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")

    # Build JSON payload
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode_tag,
        "suites": [],
    }

    overall_pass = True
    for score in scores:
        status = _threshold_status(score)
        if status == "FAIL":
            overall_pass = False

        threshold = THRESHOLDS.get(score.suite)
        entry: dict[str, Any] = {
            "suite": score.suite,
            "metric": score.metric,
            "score": score.score,
            "status": status,
            "threshold": threshold.min_value if threshold else None,
            "total_cases": score.total_cases,
            "passed_cases": score.passed_cases,
            "skipped": score.skipped,
            "skip_reason": score.skip_reason,
            "failures": [
                {"id": r.case_id, "detail": r.detail}
                for r in score.failed_cases
            ],
        }
        payload["suites"].append(entry)

    payload["overall_status"] = "PASS" if overall_pass else "FAIL"

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("JSON report written to %s", json_path)

    # Build Markdown report
    lines: list[str] = [
        "# Enterprise AI Accelerator — Eval Report",
        "",
        f"**Generated:** {payload['generated_at']}  ",
        f"**Mode:** {mode_tag}  ",
        f"**Overall:** `{payload['overall_status']}`",
        "",
        "## Suite Summary",
        "",
        "| Suite | Metric | Score | Threshold | Status |",
        "|-------|--------|-------|-----------|--------|",
    ]

    for entry in payload["suites"]:
        thresh_display = (
            f"≥{entry['threshold']:.2f}" if entry["threshold"] is not None else "—"
        )
        score_display = f"{entry['score']:.4f}" if not entry["skipped"] else "—"
        lines.append(
            f"| {entry['suite']} | {entry['metric']} | {score_display} "
            f"| {thresh_display} | `{entry['status']}` |"
        )

    lines += ["", "## Per-Suite Details", ""]

    for entry in payload["suites"]:
        lines.append(f"### {entry['suite']}")
        lines.append("")

        if entry["skipped"]:
            lines.append(f"> **SKIPPED** — {entry['skip_reason']}")
            lines.append("")
            continue

        lines.append(
            f"- Cases: {entry['passed_cases']}/{entry['total_cases']} passed"
        )
        lines.append(
            f"- {entry['metric']}: **{entry['score']:.4f}** "
            f"(threshold {'≥' + str(entry['threshold']) if entry['threshold'] is not None else 'none'})"
        )
        lines.append(f"- Status: `{entry['status']}`")

        if entry["failures"]:
            lines += ["", f"**{len(entry['failures'])} failure(s):**", ""]
            for fail in entry["failures"]:
                lines.append(f"- `{fail['id']}`: {fail['detail']}")

        lines.append("")

    lines += [
        "---",
        "",
        "## How to Add Cases",
        "",
        "See `evals/README.md` for instructions on extending each golden dataset.",
        "",
    ]

    md_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Markdown report written to %s", md_path)

    return md_path
