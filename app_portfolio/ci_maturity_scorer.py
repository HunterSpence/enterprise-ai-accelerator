"""
app_portfolio/ci_maturity_scorer.py
=====================================

Grades a repository on CI/CD pipeline maturity.

Scoring rubric (total 100 pts):
  +20  CI config present (GitHub Actions, GitLab CI, CircleCI, Jenkins,
       Azure Pipelines, Bitbucket Pipelines)
  +15  Has a test/lint step (keywords: test, pytest, jest, rspec, go test)
  +15  Has a security/SAST scan step (trivy, snyk, semgrep, bandit, gosec,
       codeql, gitleaks, dependency-review)
  +15  Has a build/deploy step (docker build, push, helm upgrade, kubectl apply,
       terraform apply, eb deploy, fly deploy)
  +10  Matrix builds (strategy.matrix, parallel, matrix in GitLab)
  +10  Dependency caching (actions/cache, cache: pip, cache: npm, etc.)
  +10  Artifact upload / release step
  +5   Workflow file count ≥ 2 (separate lint/test/deploy pipelines)

Never raises — returns score=0 on any error.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CI system detection
# ---------------------------------------------------------------------------

_CI_PATTERNS: list[tuple[str, str]] = [
    # (glob-like suffix or name, label)
    (".github/workflows", "GitHub Actions"),
    (".gitlab-ci.yml", "GitLab CI"),
    (".circleci/config.yml", "CircleCI"),
    ("Jenkinsfile", "Jenkins"),
    ("azure-pipelines.yml", "Azure Pipelines"),
    ("bitbucket-pipelines.yml", "Bitbucket Pipelines"),
    (".travis.yml", "Travis CI"),
    ("cloudbuild.yaml", "Google Cloud Build"),
    ("buildkite.yml", "Buildkite"),
    (".drone.yml", "Drone CI"),
]

_TEST_KEYWORDS = re.compile(
    r"\b(pytest|jest|rspec|mocha|karma|vitest|go\s+test|cargo\s+test|mvn\s+test"
    r"|gradle\s+test|phpunit|unittest|test|lint|eslint|flake8|ruff|mypy)\b",
    re.IGNORECASE,
)

_SECURITY_KEYWORDS = re.compile(
    r"\b(trivy|snyk|semgrep|bandit|gosec|codeql|gitleaks|trufflehog"
    r"|dependency.review|safety|checkov|tfsec|grype|syft|anchore)\b",
    re.IGNORECASE,
)

_DEPLOY_KEYWORDS = re.compile(
    r"\b(docker\s+(build|push)|helm\s+upgrade|kubectl\s+apply|terraform\s+apply"
    r"|eb\s+deploy|fly\s+deploy|vercel|netlify|serverless\s+deploy"
    r"|aws\s+deploy|gcloud\s+deploy|cf\s+push|cargo\s+publish"
    r"|npm\s+publish|pypi|twine\s+upload)\b",
    re.IGNORECASE,
)

_MATRIX_KEYWORDS = re.compile(
    r"\b(strategy\s*:\s*\n?\s*matrix|matrix\s*:|\bparallel\b|extends:\s*\.template)\b",
    re.IGNORECASE,
)

_CACHE_KEYWORDS = re.compile(
    r"\b(actions/cache|cache:\s*pip|cache:\s*npm|cache:\s*yarn|cache:\s*gradle"
    r"|cache:\s*maven|cache:\s*bundler|restore-keys|cache-dependency-path)\b",
    re.IGNORECASE,
)

_ARTIFACT_KEYWORDS = re.compile(
    r"\b(upload-artifact|actions/upload-artifact|artifacts:|release:|"
    r"publish|deploy\s+to\s+pages|gh\s+release)\b",
    re.IGNORECASE,
)


def _detect_ci_files(all_files: list[Path]) -> list[tuple[Path, str]]:
    """Return list of (path, ci_system_label) for all detected CI configs."""
    detected: list[tuple[Path, str]] = []

    for path in all_files:
        path_str = path.as_posix()
        name = path.name

        for pattern, label in _CI_PATTERNS:
            if pattern in path_str or name == pattern:
                detected.append((path, label))
                break

    return detected


def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def score_ci_maturity(
    repo_path: Path,
    all_files: list[Path],
) -> tuple[int, list[str]]:
    """Score repo CI/CD pipeline maturity.

    Args:
        repo_path: Repository root.
        all_files: Pre-filtered list of all repo files.

    Returns:
        (score: int 0-100, issues: list[str]) — never raises.
    """
    try:
        return _score_ci_inner(repo_path, all_files)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ci_maturity_scorer failed: %s", exc)
        return 0, [f"Scorer error: {exc}"]


def _score_ci_inner(
    repo_path: Path,
    all_files: list[Path],
) -> tuple[int, list[str]]:
    score = 0
    issues: list[str] = []

    ci_files = _detect_ci_files(all_files)

    if not ci_files:
        issues.append("No CI/CD configuration found (GitHub Actions, GitLab CI, CircleCI, etc.)")
        return 0, issues

    score += 20
    ci_labels = list({label for _, label in ci_files})
    ci_file_paths = [p for p, _ in ci_files]

    # Combine all CI config content for keyword scanning
    combined = "\n".join(_read_safe(p) for p in ci_file_paths)

    # --- Test step ---
    if _TEST_KEYWORDS.search(combined):
        score += 15
    else:
        issues.append("No test/lint step detected in CI pipeline")

    # --- Security scan step ---
    if _SECURITY_KEYWORDS.search(combined):
        score += 15
    else:
        issues.append(
            "No security scan step (trivy, snyk, semgrep, bandit, codeql, etc.)"
        )

    # --- Deploy step ---
    if _DEPLOY_KEYWORDS.search(combined):
        score += 15
    else:
        issues.append("No build/deploy step detected in CI pipeline")

    # --- Matrix builds ---
    if _MATRIX_KEYWORDS.search(combined):
        score += 10
    else:
        issues.append("No matrix builds configured (multi-OS or multi-version testing)")

    # --- Dependency caching ---
    if _CACHE_KEYWORDS.search(combined):
        score += 10
    else:
        issues.append("No dependency caching configured in CI (slower builds)")

    # --- Artifact upload / release ---
    if _ARTIFACT_KEYWORDS.search(combined):
        score += 10
    else:
        issues.append("No artifact upload or release step found")

    # --- Multiple pipeline files ---
    gha_files = [p for p in ci_file_paths if ".github/workflows" in p.as_posix()]
    if len(gha_files) >= 2 or len(ci_file_paths) >= 2:
        score += 5
    # No issue — single pipeline is fine for small repos

    return min(score, 100), issues
