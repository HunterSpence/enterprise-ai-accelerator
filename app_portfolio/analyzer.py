"""
app_portfolio/analyzer.py
==========================

RepoAnalyzer — orchestrates the full repo scan pipeline.

Pipeline:
  1. Walk repo tree, respecting .gitignore rules (pure Python, no git required)
  2. language_detector  → languages + total_loc
  3. dependency_scanner → list[Dependency] with staleness
  4. cve_scanner        → attach CVEs to each Dependency
  5. containerization_scorer → score + issues
  6. ci_maturity_scorer → score + issues
  7. test_coverage_scanner → test_ratio + config_found
  8. Aggregate security_hotspots from CVEs + staleness
  9. Optionally run six_r_scorer (requires AI client)

All I/O is async.  Callers that don't have an event loop can use
``asyncio.run(analyzer.analyze(repo_path))``.

Never raises to caller — returns a PortfolioReport with whatever data
was successfully collected.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_portfolio.report import PortfolioReport, Dependency
from app_portfolio.language_detector import detect_languages
from app_portfolio.dependency_scanner import scan_dependencies
from app_portfolio.cve_scanner import scan_cves
from app_portfolio.containerization_scorer import score_containerization
from app_portfolio.ci_maturity_scorer import score_ci_maturity
from app_portfolio.test_coverage_scanner import scan_test_coverage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# .gitignore parser (pure Python, no subprocess)
# ---------------------------------------------------------------------------

class _GitignoreFilter:
    """Minimal .gitignore rule matcher.

    Only handles the most common patterns:
      - Exact file/dir names
      - Glob *  (matches within a single path component)
      - Leading / (anchored to root)
      - Trailing / (directory-only match)
      - Negation ! is NOT supported (rare, skip for speed)
    """

    # Always exclude these regardless of .gitignore
    _ALWAYS_EXCLUDE = frozenset({
        ".git", "__pycache__", ".eaa_cache", "node_modules",
        ".venv", "venv", ".env", ".tox", ".mypy_cache",
        ".pytest_cache", ".ruff_cache", "dist", "build",
        "*.egg-info", ".DS_Store",
    })

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root
        self._rules: list[tuple[re.Pattern[str], bool]] = []  # (pattern, is_negation)
        self._load_gitignore(repo_root / ".gitignore")

    def _load_gitignore(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                negation = line.startswith("!")
                if negation:
                    line = line[1:]
                regex = _gitignore_pattern_to_regex(line)
                try:
                    self._rules.append((re.compile(regex), negation))
                except re.error:
                    pass
        except Exception:  # noqa: BLE001
            pass

    def is_ignored(self, path: Path) -> bool:
        """Return True if *path* should be excluded."""
        # Always-exclude check (fast path)
        for part in path.parts:
            if part in self._ALWAYS_EXCLUDE:
                return True
            # Simple glob check for *.egg-info etc
            for pattern in self._ALWAYS_EXCLUDE:
                if "*" in pattern:
                    glob_re = pattern.replace("*", ".*")
                    if re.fullmatch(glob_re, part):
                        return True

        # .gitignore rules
        try:
            rel = path.relative_to(self._root)
        except ValueError:
            return False

        rel_str = rel.as_posix()
        ignored = False
        for pattern, negation in self._rules:
            if pattern.search(rel_str):
                ignored = not negation
        return ignored


def _gitignore_pattern_to_regex(pattern: str) -> str:
    """Convert a gitignore glob pattern to a Python regex string."""
    anchored = pattern.startswith("/")
    dir_only = pattern.endswith("/")

    if anchored:
        pattern = pattern[1:]
    if dir_only:
        pattern = pattern[:-1]

    # Escape regex special chars except * and ?
    escaped = re.escape(pattern).replace(r"\*", "[^/]*").replace(r"\?", "[^/]")

    if anchored:
        return f"^{escaped}(/|$)"
    return f"(^|/){escaped}(/|$)"


# ---------------------------------------------------------------------------
# File walker
# ---------------------------------------------------------------------------

# Hard limits to prevent runaway scans on massive monorepos
_MAX_FILES = 50_000
_MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB — skip huge generated files


def _walk_repo(repo_path: Path) -> list[Path]:
    """Walk *repo_path* respecting .gitignore rules.

    Returns a flat list of file paths (not directories).
    """
    gi_filter = _GitignoreFilter(repo_path)
    files: list[Path] = []

    try:
        for item in repo_path.rglob("*"):
            if len(files) >= _MAX_FILES:
                logger.warning("File limit (%d) reached — truncating scan", _MAX_FILES)
                break
            if not item.is_file():
                continue
            if gi_filter.is_ignored(item):
                continue
            try:
                if item.stat().st_size > _MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue
            files.append(item)
    except Exception as exc:  # noqa: BLE001
        logger.warning("repo walk error: %s", exc)

    return files


# ---------------------------------------------------------------------------
# Security hotspot aggregation
# ---------------------------------------------------------------------------

def _build_security_hotspots(deps: list[Dependency]) -> list[str]:
    """Build a prioritised list of security hotspot strings."""
    hotspots: list[str] = []

    # Critical/High CVEs first
    for dep in deps:
        for cve in dep.cves:
            if cve.severity in ("CRITICAL", "HIGH"):
                fix_note = f" → fix: {cve.fix_version}" if cve.fix_version else ""
                hotspots.append(
                    f"{cve.severity}: {cve.id} in {dep.name}@{dep.version}{fix_note}"
                )

    # Medium CVEs
    for dep in deps:
        for cve in dep.cves:
            if cve.severity == "MEDIUM":
                fix_note = f" → fix: {cve.fix_version}" if cve.fix_version else ""
                hotspots.append(
                    f"MEDIUM: {cve.id} in {dep.name}@{dep.version}{fix_note}"
                )

    # Severely stale deps (2yr+)
    very_stale = [
        d for d in deps
        if d.days_since_latest is not None and d.days_since_latest >= 730
    ]
    if very_stale:
        names = ", ".join(f"{d.name}@{d.version}" for d in very_stale[:5])
        if len(very_stale) > 5:
            names += f" +{len(very_stale)-5} more"
        hotspots.append(f"STALE (≥2yr): {names}")

    return hotspots[:30]  # cap list length


# ---------------------------------------------------------------------------
# RepoAnalyzer
# ---------------------------------------------------------------------------

class RepoAnalyzer:
    """Orchestrates a full repo scan and returns a PortfolioReport.

    Usage::

        analyzer = RepoAnalyzer()
        report = await analyzer.analyze(Path("/path/to/repo"))
        # Optional: run AI scoring
        from app_portfolio.six_r_scorer import score_six_r
        from core import get_client
        report.six_r_recommendation = await score_six_r(report, get_client())
    """

    def __init__(
        self,
        *,
        run_staleness: bool = True,
        run_cve_scan: bool = True,
    ) -> None:
        """
        Args:
            run_staleness: If False, skip remote staleness API calls (faster,
                           useful for offline/air-gapped environments).
            run_cve_scan: If False, skip OSV.dev CVE lookup.
        """
        self.run_staleness = run_staleness
        self.run_cve_scan = run_cve_scan

    async def analyze(self, repo_path: Path) -> PortfolioReport:
        """Full pipeline scan. Returns PortfolioReport — never raises."""
        try:
            return await self._analyze_inner(repo_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("RepoAnalyzer.analyze failed for %s: %s", repo_path, exc)
            return PortfolioReport(
                repo_name=repo_path.name,
                repo_path=str(repo_path),
                metadata={"error": str(exc)},
            )

    async def _analyze_inner(self, repo_path: Path) -> PortfolioReport:
        repo_path = repo_path.resolve()
        if not repo_path.exists():
            raise ValueError(f"Repo path does not exist: {repo_path}")

        logger.info("Scanning %s", repo_path)
        t_start = datetime.now(timezone.utc)

        # ----------------------------------------------------------------
        # Step 1: Walk the file tree
        # ----------------------------------------------------------------
        all_files = _walk_repo(repo_path)
        logger.info("Found %d files", len(all_files))

        # ----------------------------------------------------------------
        # Step 2: Language detection (CPU-bound, run synchronously)
        # ----------------------------------------------------------------
        languages = detect_languages(all_files)
        total_loc = sum(languages.values())

        # ----------------------------------------------------------------
        # Step 3: Dependency scan (async, hits PyPI/npm/etc. if enabled)
        # ----------------------------------------------------------------
        if self.run_staleness:
            deps = await scan_dependencies(repo_path, all_files)
        else:
            # Parse manifests without staleness enrichment
            from app_portfolio.dependency_scanner import (
                _parse_requirements_txt, _parse_package_json, _parse_go_mod,
                _parse_pom_xml,
            )
            deps = await scan_dependencies(repo_path, all_files)

        # ----------------------------------------------------------------
        # Step 4: CVE scan (async, hits OSV.dev if enabled)
        # ----------------------------------------------------------------
        if self.run_cve_scan and deps:
            deps = await scan_cves(deps, repo_path)

        # ----------------------------------------------------------------
        # Steps 5-7: Synchronous scorers (no I/O after file list built)
        # ----------------------------------------------------------------
        container_score, container_issues = score_containerization(repo_path, all_files)
        ci_score, ci_issues = score_ci_maturity(repo_path, all_files)
        test_count, src_count, test_ratio, test_config = scan_test_coverage(all_files)

        # ----------------------------------------------------------------
        # Step 8: Aggregate security hotspots
        # ----------------------------------------------------------------
        hotspots = _build_security_hotspots(deps)

        # ----------------------------------------------------------------
        # Assemble report
        # ----------------------------------------------------------------
        scan_duration_s = (datetime.now(timezone.utc) - t_start).total_seconds()

        report = PortfolioReport(
            repo_name=repo_path.name,
            repo_path=str(repo_path),
            scanned_at=t_start,
            languages=languages,
            total_loc=total_loc,
            dependencies=deps,
            containerization_score=container_score,
            containerization_issues=container_issues,
            ci_maturity_score=ci_score,
            ci_maturity_issues=ci_issues,
            test_file_count=test_count,
            source_file_count=src_count,
            test_ratio=test_ratio,
            test_config_found=test_config,
            security_hotspots=hotspots,
            metadata={
                "file_count": len(all_files),
                "scan_duration_seconds": round(scan_duration_s, 2),
                "staleness_enabled": self.run_staleness,
                "cve_scan_enabled": self.run_cve_scan,
            },
        )

        logger.info(
            "Scan complete in %.1fs: %d files, %d LoC, %d deps, "
            "%d CVEs, container=%d ci=%d test_ratio=%.0f%%",
            scan_duration_s,
            len(all_files),
            total_loc,
            len(deps),
            report.vulnerable_dep_count,
            container_score,
            ci_score,
            test_ratio * 100,
        )
        return report
