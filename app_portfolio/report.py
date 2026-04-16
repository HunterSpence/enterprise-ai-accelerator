"""
app_portfolio/report.py
=======================

PortfolioReport dataclass — the canonical in-memory representation of a
single repo scan.  Every sub-scanner returns its partial result; RepoAnalyzer
aggregates them into one PortfolioReport that then flows into six_r_scorer
and the CLI.

Also provides render_markdown() and render_json() for human/machine consumers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Dependency / vulnerability primitives
# ---------------------------------------------------------------------------

@dataclass
class Dependency:
    name: str
    version: str                     # empty string if unpinned
    ecosystem: str                   # pypi | npm | go | maven | gradle
    is_dev: bool = False
    latest_version: str = ""         # filled in by staleness check
    days_since_latest: int | None = None  # None = unknown
    cves: list["Vulnerability"] = field(default_factory=list)

    @property
    def is_stale(self) -> bool:
        return self.days_since_latest is not None and self.days_since_latest > 365

    @property
    def has_cves(self) -> bool:
        return bool(self.cves)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "ecosystem": self.ecosystem,
            "is_dev": self.is_dev,
            "latest_version": self.latest_version,
            "days_since_latest": self.days_since_latest,
            "is_stale": self.is_stale,
            "cves": [c.to_dict() for c in self.cves],
        }


@dataclass
class Vulnerability:
    id: str               # OSV id e.g. GHSA-xxxx or CVE-xxxx
    severity: str         # CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN
    summary: str
    fix_version: str      # empty if no fix available
    source: str = "osv"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "summary": self.summary,
            "fix_version": self.fix_version,
        }


# ---------------------------------------------------------------------------
# Six-R recommendation (filled by six_r_scorer)
# ---------------------------------------------------------------------------

@dataclass
class SixRRecommendation:
    strategy: str           # retire|retain|rehost|replatform|refactor|repurchase
    confidence: float       # 0-1
    rationale: str
    effort_weeks: int
    risk: str               # low|medium|high
    blockers: list[str] = field(default_factory=list)
    quick_wins: list[str] = field(default_factory=list)
    thinking_trace: str = ""   # Opus 4.7 extended thinking — audit record

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "effort_weeks": self.effort_weeks,
            "risk": self.risk,
            "blockers": self.blockers,
            "quick_wins": self.quick_wins,
        }


# ---------------------------------------------------------------------------
# Top-level portfolio report
# ---------------------------------------------------------------------------

@dataclass
class PortfolioReport:
    # Identity
    repo_name: str
    repo_path: str
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Language breakdown
    languages: dict[str, int] = field(default_factory=dict)   # lang -> LoC
    total_loc: int = 0

    # Dependencies + security
    dependencies: list[Dependency] = field(default_factory=list)

    # Infrastructure maturity scores
    containerization_score: int = 0          # 0-100
    containerization_issues: list[str] = field(default_factory=list)
    ci_maturity_score: int = 0               # 0-100
    ci_maturity_issues: list[str] = field(default_factory=list)

    # Test coverage
    test_file_count: int = 0
    source_file_count: int = 0
    test_ratio: float = 0.0
    test_config_found: bool = False

    # Convenience aggregates (computed from deps)
    security_hotspots: list[str] = field(default_factory=list)

    # Six-R recommendation (None until scorer runs)
    six_r_recommendation: SixRRecommendation | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def primary_language(self) -> str:
        if not self.languages:
            return "unknown"
        return max(self.languages, key=lambda k: self.languages[k])

    @property
    def dep_count(self) -> int:
        return len([d for d in self.dependencies if not d.is_dev])

    @property
    def vulnerable_dep_count(self) -> int:
        return len([d for d in self.dependencies if d.has_cves])

    @property
    def stale_dep_count(self) -> int:
        return len([d for d in self.dependencies if d.is_stale])

    @property
    def critical_cve_count(self) -> int:
        total = 0
        for dep in self.dependencies:
            total += sum(1 for c in dep.cves if c.severity in ("CRITICAL", "HIGH"))
        return total

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    def render_json(self, indent: int = 2) -> str:
        """Full JSON dump — suitable for machine consumers / CI artefact."""
        payload: dict[str, Any] = {
            "repo_name": self.repo_name,
            "repo_path": self.repo_path,
            "scanned_at": self.scanned_at.isoformat(),
            "languages": self.languages,
            "total_loc": self.total_loc,
            "primary_language": self.primary_language,
            "dependencies": {
                "total": len(self.dependencies),
                "production": self.dep_count,
                "vulnerable": self.vulnerable_dep_count,
                "stale": self.stale_dep_count,
                "critical_or_high_cves": self.critical_cve_count,
                "items": [d.to_dict() for d in self.dependencies],
            },
            "containerization": {
                "score": self.containerization_score,
                "issues": self.containerization_issues,
            },
            "ci_maturity": {
                "score": self.ci_maturity_score,
                "issues": self.ci_maturity_issues,
            },
            "test_coverage": {
                "test_files": self.test_file_count,
                "source_files": self.source_file_count,
                "ratio": round(self.test_ratio, 3),
                "config_found": self.test_config_found,
            },
            "security_hotspots": self.security_hotspots,
            "six_r_recommendation": (
                self.six_r_recommendation.to_dict()
                if self.six_r_recommendation
                else None
            ),
            "metadata": self.metadata,
        }
        return json.dumps(payload, indent=indent, default=str)

    def render_markdown(self) -> str:
        """Human-readable Markdown — suitable for GitHub PR comments / reports."""
        lines: list[str] = []

        lines.append(f"# Portfolio Analysis: {self.repo_name}")
        lines.append(f"\n_Scanned {self.scanned_at.strftime('%Y-%m-%d %H:%M UTC')}_\n")

        # --- Language breakdown ---
        lines.append("## Language Breakdown")
        if self.languages:
            for lang, loc in sorted(self.languages.items(), key=lambda x: -x[1]):
                pct = (loc / self.total_loc * 100) if self.total_loc else 0
                lines.append(f"- **{lang}**: {loc:,} LoC ({pct:.1f}%)")
        else:
            lines.append("- No source files detected.")
        lines.append(f"\n**Total LoC:** {self.total_loc:,}\n")

        # --- Dependencies ---
        lines.append("## Dependencies")
        lines.append(f"- Production deps: **{self.dep_count}**")
        lines.append(f"- Vulnerable: **{self.vulnerable_dep_count}** "
                     f"({self.critical_cve_count} CRITICAL/HIGH CVEs)")
        lines.append(f"- Stale (>1yr behind): **{self.stale_dep_count}**\n")

        if self.vulnerable_dep_count:
            lines.append("### Vulnerable Dependencies")
            for dep in self.dependencies:
                if dep.has_cves:
                    cve_ids = ", ".join(c.id for c in dep.cves[:3])
                    if len(dep.cves) > 3:
                        cve_ids += f" +{len(dep.cves)-3} more"
                    lines.append(f"- `{dep.name}@{dep.version}` — {cve_ids}")
            lines.append("")

        # --- Infrastructure scores ---
        lines.append("## Infrastructure Maturity")
        lines.append(f"| Dimension | Score |")
        lines.append(f"|-----------|-------|")
        lines.append(f"| Containerization | {self.containerization_score}/100 |")
        lines.append(f"| CI Maturity | {self.ci_maturity_score}/100 |")
        lines.append(f"| Test Coverage | {self.test_ratio:.0%} |")
        lines.append("")

        if self.containerization_issues:
            lines.append("**Containerization gaps:**")
            for issue in self.containerization_issues:
                lines.append(f"- {issue}")
            lines.append("")

        if self.ci_maturity_issues:
            lines.append("**CI gaps:**")
            for issue in self.ci_maturity_issues:
                lines.append(f"- {issue}")
            lines.append("")

        # --- Security hotspots ---
        if self.security_hotspots:
            lines.append("## Security Hotspots")
            for h in self.security_hotspots:
                lines.append(f"- {h}")
            lines.append("")

        # --- 6R recommendation ---
        if self.six_r_recommendation:
            r = self.six_r_recommendation
            lines.append("## 6R Migration Recommendation")
            lines.append(f"**Strategy:** `{r.strategy.upper()}` "
                         f"(confidence: {r.confidence:.0%})")
            lines.append(f"**Effort:** ~{r.effort_weeks} weeks | "
                         f"**Risk:** {r.risk}")
            lines.append(f"\n{r.rationale}\n")
            if r.quick_wins:
                lines.append("**Quick wins:**")
                for qw in r.quick_wins:
                    lines.append(f"- {qw}")
                lines.append("")
            if r.blockers:
                lines.append("**Blockers:**")
                for bl in r.blockers:
                    lines.append(f"- {bl}")
                lines.append("")
        else:
            lines.append("## 6R Migration Recommendation\n_Not yet scored._\n")

        return "\n".join(lines)
