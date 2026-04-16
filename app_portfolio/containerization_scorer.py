"""
app_portfolio/containerization_scorer.py
=========================================

Grades a repository on containerization readiness.

Scoring rubric (total 100 pts):
  +20  Dockerfile present
  +15  Multi-stage build (multiple FROM statements)
  +10  Non-root user (USER directive, non-root username)
  +10  Pinned base image tag (no :latest, no untagged FROM)
  +10  HEALTHCHECK directive present
  +10  Explicit EXPOSE directive present
  +10  .dockerignore present
  +10  docker-compose.yml or docker-compose.yaml present
  +5   Helm chart present (Chart.yaml in any subdirectory)

Each missing item becomes an entry in the issues list.
Never raises — returns score=0 on any error.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _find_dockerfiles(all_files: list[Path]) -> list[Path]:
    """Return all Dockerfile* paths."""
    return [
        p for p in all_files
        if p.name == "Dockerfile" or p.name.startswith("Dockerfile.")
    ]


def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _score_dockerfile(content: str) -> tuple[int, list[str]]:
    """Score a single Dockerfile content. Returns (points, issues)."""
    score = 0
    issues: list[str] = []

    lines = [ln.strip() for ln in content.splitlines()]
    from_lines = [ln for ln in lines if re.match(r"^FROM\s", ln, re.IGNORECASE)]

    # Multi-stage build
    if len(from_lines) > 1:
        score += 15
    else:
        issues.append("No multi-stage Dockerfile build (single FROM statement)")

    # Pinned base image tag (no :latest or bare image with no tag)
    pinned = True
    for frm in from_lines:
        # FROM image AS alias — check image part
        parts = frm.split()
        image = parts[1] if len(parts) > 1 else ""
        image = image.split(" ")[0]  # strip AS
        if image.upper() == "SCRATCH":
            continue  # scratch is valid
        if ":" not in image or image.endswith(":latest"):
            pinned = False
            break
    if pinned:
        score += 10
    else:
        issues.append("Base image not pinned to a specific tag (avoid :latest)")

    # Non-root user
    user_lines = [ln for ln in lines if re.match(r"^USER\s+", ln, re.IGNORECASE)]
    has_nonroot = False
    for ul in user_lines:
        user_val = ul.split()[-1].lower()
        # root UID 0 or literal "root" → bad
        if user_val not in ("0", "root"):
            has_nonroot = True
            break
    if has_nonroot:
        score += 10
    else:
        issues.append("No non-root USER directive in Dockerfile")

    # HEALTHCHECK
    if any(re.match(r"^HEALTHCHECK\s", ln, re.IGNORECASE) for ln in lines):
        score += 10
    else:
        issues.append("No HEALTHCHECK directive in Dockerfile")

    # EXPOSE
    if any(re.match(r"^EXPOSE\s", ln, re.IGNORECASE) for ln in lines):
        score += 10
    else:
        issues.append("No EXPOSE directive in Dockerfile")

    return score, issues


def score_containerization(
    repo_path: Path,
    all_files: list[Path],
) -> tuple[int, list[str]]:
    """Score repo containerization readiness.

    Args:
        repo_path: Repository root (used to check for files directly).
        all_files: Pre-filtered list of all repo files.

    Returns:
        (score: int 0-100, issues: list[str]) — never raises.
    """
    try:
        return _score_containerization_inner(repo_path, all_files)
    except Exception as exc:  # noqa: BLE001
        logger.warning("containerization_scorer failed: %s", exc)
        return 0, [f"Scorer error: {exc}"]


def _score_containerization_inner(
    repo_path: Path,
    all_files: list[Path],
) -> tuple[int, list[str]]:
    score = 0
    issues: list[str] = []

    file_names = {p.name for p in all_files}
    file_set = set(all_files)

    # --- Dockerfile presence ---
    dockerfiles = _find_dockerfiles(all_files)
    if dockerfiles:
        score += 20
        # Score the first (or root-level) Dockerfile
        root_dockerfiles = [p for p in dockerfiles if p.parent == repo_path]
        target = root_dockerfiles[0] if root_dockerfiles else dockerfiles[0]
        content = _read_safe(target)
        df_score, df_issues = _score_dockerfile(content)
        score += df_score
        issues.extend(df_issues)
    else:
        issues.append("No Dockerfile found — repo is not containerized")
        # All sub-checks also fail implicitly
        issues.append("No multi-stage Dockerfile build (single FROM statement)")
        issues.append("Base image not pinned to a specific tag (avoid :latest)")
        issues.append("No non-root USER directive in Dockerfile")
        issues.append("No HEALTHCHECK directive in Dockerfile")
        issues.append("No EXPOSE directive in Dockerfile")

    # --- .dockerignore ---
    dockerignore_present = any(
        p.name == ".dockerignore" for p in all_files
    )
    if dockerignore_present:
        score += 10
    else:
        issues.append(".dockerignore missing — build context may be bloated")

    # --- docker-compose ---
    compose_present = any(
        p.name in ("docker-compose.yml", "docker-compose.yaml") for p in all_files
    )
    if compose_present:
        score += 10
    else:
        issues.append("No docker-compose file found — local orchestration undefined")

    # --- Helm chart ---
    helm_present = any(p.name == "Chart.yaml" for p in all_files)
    if helm_present:
        score += 5
    # Helm is optional — no issue logged if absent

    # Cap at 100
    return min(score, 100), issues
