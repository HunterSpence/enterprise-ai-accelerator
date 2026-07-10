"""
app_portfolio/cve_scanner.py
=============================

CVE/vulnerability scanner using the OSV.dev free batch API.

API: POST https://api.osv.dev/v1/querybatch
  - No auth required, no key needed.
  - Accepts up to 1000 queries per request.
  - Returns matched OSV advisories with aliases (CVE IDs), severity, etc.

We chunk large dep lists into batches of 100 to stay well within rate limits.
Results are cached alongside the staleness cache to avoid re-scanning.

Never raises to caller — returns the original dep list with empty .cves on any
network or parse failure.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app_portfolio.report import Dependency, Vulnerability

logger = logging.getLogger(__name__)

_OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
_OSV_BATCH_SIZE = 100
_HTTP_TIMEOUT = 15.0
_CACHE_TTL_SECONDS = 86_400  # 24 hours

# Ecosystem name mapping (OSV uses specific casing)
_ECOSYSTEM_MAP: dict[str, str] = {
    "pypi": "PyPI",
    "npm": "npm",
    "go": "Go",
    "maven": "Maven",
    "gradle": "Maven",  # Maven ecosystem in OSV
}

# OSV severity → our severity string
_SEVERITY_MAP: dict[str, str] = {
    "CRITICAL": "CRITICAL",
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
}


def _osv_cache_path(repo_path: Path) -> Path:
    cache_dir = repo_path / ".eaa_cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / "osv_results.json"


def _load_osv_cache(repo_path: Path) -> dict[str, Any]:
    p = _osv_cache_path(repo_path)
    try:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_osv_cache(repo_path: Path, data: dict[str, Any]) -> None:
    try:
        _osv_cache_path(repo_path).write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        pass


def _cache_key(ecosystem: str, name: str, version: str) -> str:
    return f"{ecosystem}:{name}@{version}"


def _parse_severity(vuln: dict[str, Any]) -> str:
    """Extract highest severity from OSV vuln object."""
    # Try database_specific CVSS first
    for sev in vuln.get("severity", []):
        score = sev.get("score", "")
        # CVSS v3 score → severity bucket
        try:
            v = float(score)
            if v >= 9.0:
                return "CRITICAL"
            if v >= 7.0:
                return "HIGH"
            if v >= 4.0:
                return "MEDIUM"
            return "LOW"
        except (ValueError, TypeError):
            pass
        # Type field
        sev_type = sev.get("type", "")
        if sev_type in _SEVERITY_MAP:
            return _SEVERITY_MAP[sev_type]

    # Fallback: check affected[].severity
    for affected in vuln.get("affected", []):
        sev = affected.get("database_specific", {}).get("severity", "")
        if sev.upper() in _SEVERITY_MAP:
            return _SEVERITY_MAP[sev.upper()]

    return "UNKNOWN"


def _parse_fix_version(vuln: dict[str, Any], ecosystem: str) -> str:
    """Extract the earliest fixed version from OSV affected ranges."""
    osv_ecosystem = _ECOSYSTEM_MAP.get(ecosystem, ecosystem)
    for affected in vuln.get("affected", []):
        pkg_eco = affected.get("package", {}).get("ecosystem", "")
        if pkg_eco != osv_ecosystem:
            continue
        for r in affected.get("ranges", []):
            for event in r.get("events", []):
                fixed = event.get("fixed", "")
                if fixed:
                    return fixed
    return ""


def _vuln_id(vuln: dict[str, Any]) -> str:
    """Return the most human-friendly ID (prefer CVE over OSV-xxxx)."""
    osv_id = vuln.get("id", "")
    aliases = vuln.get("aliases", [])
    for alias in aliases:
        if alias.startswith("CVE-"):
            return alias
    return osv_id


def _build_osv_queries(deps: list[Dependency]) -> list[dict[str, Any]]:
    """Build OSV querybatch query list from dep list."""
    queries = []
    for dep in deps:
        osv_eco = _ECOSYSTEM_MAP.get(dep.ecosystem)
        if not osv_eco:
            continue
        name = dep.name
        # Maven: OSV uses groupId:artifactId format
        # We already store it that way
        query: dict[str, Any] = {
            "package": {"name": name, "ecosystem": osv_eco},
        }
        if dep.version:
            query["version"] = dep.version
        queries.append(query)
    return queries


async def _query_osv_batch(
    client: httpx.AsyncClient,
    queries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Send one batch to OSV. Returns (results, ok).

    ok=False means the request itself failed (network/HTTP error) — the
    caller must NOT treat the placeholder empty results as "queried, no
    vulnerabilities found" (P0-26: an OSV outage must not be cached as a
    clean/empty result).
    """
    try:
        resp = await client.post(
            _OSV_BATCH_URL,
            json={"queries": queries},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", []), True
    except Exception as exc:  # noqa: BLE001
        logger.warning("OSV batch query failed: %s", exc)
        return [{}] * len(queries), False


async def scan_cves(
    deps: list[Dependency],
    repo_path: Path,
) -> list[Dependency]:
    """Query OSV.dev for each dependency and attach Vulnerability objects.

    Mutates *deps* in-place (sets dep.cves + dep.cve_scan_status) and
    returns the same list. Never raises — returns deps unchanged on any
    setup error.

    P0-26: a failed/errored OSV lookup sets cve_scan_status="FAILED" and is
    NEVER cached — only a genuine "queried successfully" result (even if it
    found zero vulnerabilities) is cached as clean. This prevents an OSV
    outage from being remembered for 24h as "0 vulnerabilities".

    Args:
        deps: List of Dependency objects (from dependency_scanner).
        repo_path: Repo root for cache storage.

    Returns:
        The same list, with .cves/.cve_scan_status populated.
    """
    cache = _load_osv_cache(repo_path)
    now = time.time()
    updated = False

    # Separate cached / queryable / unsupported-ecosystem deps up front so
    # the query list built below stays index-aligned 1:1 with to_fetch
    # (previously an unmapped ecosystem silently dropped out of the query
    # list while to_fetch kept it, misattributing results to the wrong dep).
    to_fetch: list[tuple[int, Dependency]] = []  # (original index, dep)
    for i, dep in enumerate(deps):
        key = _cache_key(dep.ecosystem, dep.name, dep.version)
        entry = cache.get(key)
        if entry and (now - entry.get("ts", 0)) < _CACHE_TTL_SECONDS:
            # Restore from cache
            dep.cves = [
                Vulnerability(
                    id=v["id"],
                    severity=v["severity"],
                    summary=v["summary"],
                    fix_version=v["fix_version"],
                )
                for v in entry.get("vulns", [])
            ]
            dep.cve_scan_status = "OK"
        elif dep.ecosystem not in _ECOSYSTEM_MAP:
            # OSV has no ecosystem mapping for this dep — not an error, just
            # unsupported. Leave cves=[] but don't claim it was queried.
            dep.cve_scan_status = "UNSCANNED"
        else:
            to_fetch.append((i, dep))

    if not to_fetch:
        return deps

    # Build queries — 1:1 with to_fetch now that unsupported ecosystems are
    # filtered out above.
    queries = _build_osv_queries([dep for _, dep in to_fetch])

    # Chunk into batches, tracking per-query success so a partial outage
    # only marks the affected deps FAILED (not the whole scan).
    query_ok: list[bool] = [True] * len(queries)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        all_results: list[dict[str, Any]] = []
        for chunk_start in range(0, len(queries), _OSV_BATCH_SIZE):
            chunk_queries = queries[chunk_start : chunk_start + _OSV_BATCH_SIZE]
            chunk_results, chunk_ok = await _query_osv_batch(client, chunk_queries)
            all_results.extend(chunk_results)
            if not chunk_ok:
                for j in range(len(chunk_queries)):
                    query_ok[chunk_start + j] = False

    # Process results
    for query_idx, (dep_idx, dep) in enumerate(to_fetch):
        if query_idx >= len(all_results):
            break

        if not query_ok[query_idx]:
            # OSV lookup failed for this dep — do NOT cache, do NOT report
            # as clean. Leave any prior .cves untouched (stale-but-labeled
            # beats silently-wrong-clean) and mark the failure explicitly.
            dep.cve_scan_status = "FAILED"
            continue

        result = all_results[query_idx]
        vulns_raw = result.get("vulns", [])

        vuln_objects: list[Vulnerability] = []
        for vuln in vulns_raw:
            vuln_id = _vuln_id(vuln)
            severity = _parse_severity(vuln)
            summary = vuln.get("summary", vuln.get("details", ""))[:200]
            fix_version = _parse_fix_version(vuln, dep.ecosystem)

            vuln_objects.append(Vulnerability(
                id=vuln_id,
                severity=severity,
                summary=summary,
                fix_version=fix_version,
            ))

        dep.cves = vuln_objects
        dep.cve_scan_status = "OK"

        # Cache only genuine successful lookups.
        key = _cache_key(dep.ecosystem, dep.name, dep.version)
        cache[key] = {
            "ts": now,
            "vulns": [
                {
                    "id": v.id,
                    "severity": v.severity,
                    "summary": v.summary,
                    "fix_version": v.fix_version,
                }
                for v in vuln_objects
            ],
        }
        updated = True

    if updated:
        _save_osv_cache(repo_path, cache)

    return deps
