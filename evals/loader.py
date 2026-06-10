"""
evals/loader.py
===============

Load and validate JSONL golden datasets.

Each line must be valid JSON with at minimum an 'id' field.
Suite-specific required fields are validated per suite name.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATASETS_DIR = Path(__file__).parent / "datasets"

# Required top-level keys per suite
_REQUIRED_FIELDS: dict[str, list[str]] = {
    "six_r_classification": ["id", "description", "expected_label", "rationale"],
    "iac_policy_detection": [
        "id",
        "resource_type",
        "resource_name",
        "attributes",
        "expected_policy_ids",
    ],
    "prompt_injection_redteam": [
        "id",
        "attack_class",
        "input",
        "expected_behavior",
    ],
}

_SUITE_FILES: dict[str, str] = {
    "six_r_classification": "six_r_classification.jsonl",
    "iac_policy_detection": "iac_policy_detection.jsonl",
    "prompt_injection_redteam": "prompt_injection_redteam.jsonl",
}

VALID_6R_LABELS = {
    "Rehost",
    "Replatform",
    "Repurchase",
    "Refactor",
    "Retire",
    "Retain",
}

VALID_BEHAVIORS = {"must_flag", "must_not_execute"}


@dataclass
class LoadResult:
    suite: str
    cases: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def integrity_score(self) -> float:
        """1.0 if no errors, 0.0 if any errors."""
        return 1.0 if not self.errors else 0.0

    @property
    def ok(self) -> bool:
        return not self.errors


def load_suite(suite_name: str) -> LoadResult:
    """Load and validate a golden dataset for the named suite."""
    result = LoadResult(suite=suite_name)

    if suite_name not in _SUITE_FILES:
        result.errors.append(f"Unknown suite: {suite_name!r}")
        return result

    path = DATASETS_DIR / _SUITE_FILES[suite_name]
    if not path.exists():
        result.errors.append(f"Dataset file not found: {path}")
        return result

    required = _REQUIRED_FIELDS.get(suite_name, ["id"])

    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            result.errors.append(f"Line {lineno}: JSON parse error — {exc}")
            continue

        missing = [f for f in required if f not in case]
        if missing:
            cid = case.get("id", f"line-{lineno}")
            result.errors.append(
                f"Case {cid!r}: missing required fields {missing}"
            )
            continue

        # Suite-specific value validation
        if suite_name == "six_r_classification":
            label = case.get("expected_label", "")
            if label not in VALID_6R_LABELS:
                result.errors.append(
                    f"Case {case['id']!r}: invalid expected_label {label!r}"
                )
                continue

        elif suite_name == "iac_policy_detection":
            if not isinstance(case.get("expected_policy_ids"), list):
                result.errors.append(
                    f"Case {case['id']!r}: expected_policy_ids must be a list"
                )
                continue
            if not isinstance(case.get("attributes"), dict):
                result.errors.append(
                    f"Case {case['id']!r}: attributes must be a dict"
                )
                continue

        elif suite_name == "prompt_injection_redteam":
            behavior = case.get("expected_behavior", "")
            if behavior not in VALID_BEHAVIORS:
                result.errors.append(
                    f"Case {case['id']!r}: invalid expected_behavior {behavior!r}"
                )
                continue

        result.cases.append(case)

    if not result.cases and not result.errors:
        result.errors.append(f"Dataset {path.name} is empty")

    logger.debug(
        "Loaded suite %r: %d cases, %d errors",
        suite_name,
        len(result.cases),
        len(result.errors),
    )
    return result


def list_suites() -> list[str]:
    return list(_SUITE_FILES.keys())
