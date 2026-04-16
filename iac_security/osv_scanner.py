"""
iac_security/osv_scanner.py
============================

CVEScanner — query OSV.dev for known vulnerabilities in a set of packages.

API: POST https://api.osv.dev/v1/querybatch
Docs: https://google.github.io/osv.dev/post-v1-querybatch/

Supports: PyPI, npm, Go, Maven (crates.io also works, ecosystem="crates.io").
Batches: max 1000 queries per request (OSV limit).
Rate limiting: no hard limit documented; we cap at 5 concurrent requests
and add a brief delay between batches to be a good citizen.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OSV ecosystem mapping
# ---------------------------------------------------------------------------

ECOSYSTEM_MAP: dict[str, str] = {
    "pypi": "PyPI",
    "pip": "PyPI",
    "npm": "npm",
    "node": "npm",
    "go": "Go",
    "golang": "Go",
    "maven": "Maven",
    "java": "Maven",
    "cargo": "crates.io",
    "crates.io": "crates.io",
    "rubygems": "RubyGems",
    "nuget": "NuGet",
    "hex": "Hex",
}

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_BATCH_SIZE = 1000  # OSV hard maximum per request
OSV_CONCURRENT = 5     # max simultaneous HTTP requests


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class AffectedVersion:
    introduced: str = ""
    fixed: str = ""


@dataclass
class Vulnerability:
    """A vulnerability returned from OSV.dev for a given package version."""

    osv_id: str           # e.g. "GHSA-xxxx-xxxx-xxxx" or "CVE-2024-XXXXX"
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    details: str = ""
    severity: str = ""    # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | ""
    cvss_score: Optional[float] = None
    affected_versions: list[str] = field(default_factory=list)
    fix_version: str = ""  # earliest fixed version, if known
    references: list[str] = field(default_factory=list)
    # Which package this was found for (populated by scanner)
    ecosystem: str = ""
    package_name: str = ""
    queried_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.osv_id,
            "aliases": self.aliases,
            "summary": self.summary,
            "severity": self.severity,
            "cvss_score": self.cvss_score,
            "fix_version": self.fix_version,
            "package": {
                "ecosystem": self.ecosystem,
                "name": self.package_name,
                "version": self.queried_version,
            },
            "references": self.references,
        }


# ---------------------------------------------------------------------------
# OSV response parsing helpers
# ---------------------------------------------------------------------------


def _extract_severity(vuln: dict[str, Any]) -> tuple[str, Optional[float]]:
    """
    Extract severity label and CVSS score from an OSV vuln dict.
    OSV severity is in vuln['severity'] (list of {type, score} dicts).
    """
    severity_list = vuln.get("severity") or []
    for sev in severity_list:
        if not isinstance(sev, dict):
            continue
        score_str = sev.get("score", "")
        sev_type = sev.get("type", "")
        if sev_type in {"CVSS_V3", "CVSS_V4"}:
            try:
                score = float(score_str.split("/")[0]) if "/" in score_str else float(score_str)
            except (ValueError, TypeError):
                score = None
            if score is not None:
                if score >= 9.0:
                    label = "CRITICAL"
                elif score >= 7.0:
                    label = "HIGH"
                elif score >= 4.0:
                    label = "MEDIUM"
                else:
                    label = "LOW"
                return label, score
    # Fallback: database_specific severity
    db_specific = vuln.get("database_specific") or {}
    sev_str = str(db_specific.get("severity", "")).upper()
    if sev_str in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
        return sev_str, None
    return "", None


def _extract_fix_version(vuln: dict[str, Any], ecosystem: str, pkg_name: str) -> str:
    """Find the earliest 'fixed' version in the affected ranges."""
    affected = vuln.get("affected") or []
    for aff in affected:
        if not isinstance(aff, dict):
            continue
        aff_pkg = aff.get("package") or {}
        if aff_pkg.get("name", "").lower() != pkg_name.lower():
            continue
        for rng in aff.get("ranges") or []:
            if not isinstance(rng, dict):
                continue
            for event in rng.get("events") or []:
                if isinstance(event, dict) and "fixed" in event:
                    return event["fixed"]
    return ""


def _parse_osv_vuln(
    vuln: dict[str, Any],
    ecosystem: str,
    pkg_name: str,
    queried_version: str,
) -> Vulnerability:
    severity_label, cvss = _extract_severity(vuln)
    fix_ver = _extract_fix_version(vuln, ecosystem, pkg_name)
    refs = [r.get("url", "") for r in (vuln.get("references") or []) if isinstance(r, dict)]

    return Vulnerability(
        osv_id=vuln.get("id", ""),
        aliases=[a for a in (vuln.get("aliases") or []) if a],
        summary=vuln.get("summary", ""),
        details=(vuln.get("details") or "")[:500],  # truncate long details
        severity=severity_label,
        cvss_score=cvss,
        fix_version=fix_ver,
        references=[r for r in refs if r][:10],  # cap references
        ecosystem=ecosystem,
        package_name=pkg_name,
        queried_version=queried_version,
    )


# ---------------------------------------------------------------------------
# Batch HTTP logic
# ---------------------------------------------------------------------------


async def _query_batch(
    queries: list[dict[str, Any]],
    http_client: Any,  # httpx.AsyncClient
) -> list[dict[str, Any]]:
    """
    POST a single batch of up to 1000 queries to OSV.dev.
    Returns list of vuln result dicts (one per query, may be empty).
    """
    payload = {"queries": queries}
    try:
        resp = await http_client.post(
            OSV_BATCH_URL,
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except Exception as exc:
        logger.warning("OSV batch query failed: %s", exc)
        return [{} for _ in queries]


# ---------------------------------------------------------------------------
# Public scanner
# ---------------------------------------------------------------------------


class CVEScanner:
    """
    Scan a list of (ecosystem, package_name, version) tuples against OSV.dev.

    Usage::

        from iac_security import CVEScanner
        vulns = CVEScanner().scan([
            ("pypi", "cryptography", "41.0.0"),
            ("npm", "lodash", "4.17.20"),
        ])
        for v in vulns:
            print(v.osv_id, v.severity, v.package_name, v.fix_version)
    """

    def scan(
        self,
        packages: list[tuple[str, str, str]],
    ) -> list[Vulnerability]:
        """
        Synchronous wrapper around async scan logic.
        packages: list of (ecosystem, name, version)
        """
        if not packages:
            return []
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(asyncio.run, self._scan_async(packages))
                    return future.result()
            return loop.run_until_complete(self._scan_async(packages))
        except RuntimeError:
            return asyncio.run(self._scan_async(packages))

    async def _scan_async(
        self,
        packages: list[tuple[str, str, str]],
    ) -> list[Vulnerability]:
        try:
            import httpx
        except ImportError:
            logger.error("httpx is required for OSV scanning. Run: pip install httpx")
            return []

        # Normalise ecosystem names
        normalised: list[tuple[str, str, str]] = []
        for eco, name, version in packages:
            osv_eco = ECOSYSTEM_MAP.get(eco.lower(), eco)
            normalised.append((osv_eco, name, version))

        # Build OSV query objects
        queries: list[dict[str, Any]] = []
        for osv_eco, name, version in normalised:
            q: dict[str, Any] = {
                "package": {
                    "ecosystem": osv_eco,
                    "name": name,
                }
            }
            if version:
                q["version"] = version
            queries.append(q)

        # Chunk into batches
        all_vulns: list[Vulnerability] = []
        semaphore = asyncio.Semaphore(OSV_CONCURRENT)

        async with httpx.AsyncClient(
            headers={"User-Agent": "enterprise-ai-accelerator/iac_security 0.1.0"},
            follow_redirects=True,
        ) as client:
            batches = [
                queries[i : i + OSV_BATCH_SIZE]
                for i in range(0, len(queries), OSV_BATCH_SIZE)
            ]
            pkg_batches = [
                normalised[i : i + OSV_BATCH_SIZE]
                for i in range(0, len(normalised), OSV_BATCH_SIZE)
            ]

            for batch_queries, batch_pkgs in zip(batches, pkg_batches):
                async with semaphore:
                    results = await _query_batch(batch_queries, client)

                for (osv_eco, pkg_name, version), result in zip(batch_pkgs, results):
                    if not result:
                        continue
                    for vuln in result.get("vulns") or []:
                        if not isinstance(vuln, dict):
                            continue
                        all_vulns.append(
                            _parse_osv_vuln(vuln, osv_eco, pkg_name, version)
                        )

                # Brief pause between batches
                if len(batches) > 1:
                    await asyncio.sleep(0.5)

        logger.info(
            "CVEScanner: queried %d packages, found %d vulnerabilities",
            len(packages),
            len(all_vulns),
        )
        return all_vulns

    def scan_from_sbom(self, sbom: dict[str, Any]) -> list[Vulnerability]:
        """
        Convenience method: accept a CycloneDX SBOM dict and scan all
        components with a purl.
        """
        packages: list[tuple[str, str, str]] = []
        for comp in sbom.get("components") or []:
            purl = comp.get("purl", "")
            if not purl:
                continue
            # Parse purl: pkg:pypi/requests@2.28.0
            try:
                # Simple regex parse
                import re
                m = re.match(r"pkg:([^/]+)/([^@]+)(?:@(.+))?", purl)
                if m:
                    eco = m.group(1)
                    name = m.group(2).replace("%2F", "/")
                    version = m.group(3) or ""
                    packages.append((eco, name, version))
            except Exception:
                continue
        return self.scan(packages)
