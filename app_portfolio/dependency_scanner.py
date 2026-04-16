"""
app_portfolio/dependency_scanner.py
=====================================

Multi-ecosystem dependency scanner + staleness checker.

Supported manifests:
  Python  — requirements*.txt, pyproject.toml [project.dependencies],
             Pipfile.lock
  Node.js — package.json, package-lock.json, yarn.lock
  Go      — go.mod, go.sum
  Java    — pom.xml, build.gradle

Staleness check: free public APIs, no auth required.
  PyPI   → https://pypi.org/pypi/{pkg}/json
  npm    → https://registry.npmjs.org/{pkg}/latest
  Go     → https://proxy.golang.org/{module}/@latest
  Maven  → https://search.maven.org/solrsearch/select

Results are cached to <repo>/.eaa_cache/staleness.json to avoid hammering
public APIs on re-scans.  Cache TTL is 24 hours.

Never raises to caller — returns empty list on any error.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

from app_portfolio.report import Dependency

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 86_400  # 24 hours
_HTTP_TIMEOUT = 6.0


# ---------------------------------------------------------------------------
# Internal cache helpers
# ---------------------------------------------------------------------------

def _cache_path(repo_path: Path) -> Path:
    cache_dir = repo_path / ".eaa_cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / "staleness.json"


def _load_cache(repo_path: Path) -> dict[str, Any]:
    p = _cache_path(repo_path)
    try:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_cache(repo_path: Path, data: dict[str, Any]) -> None:
    try:
        _cache_path(repo_path).write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        pass


def _cache_key(ecosystem: str, name: str) -> str:
    return f"{ecosystem}:{name}"


# ---------------------------------------------------------------------------
# Staleness fetchers (one per ecosystem)
# ---------------------------------------------------------------------------

async def _fetch_pypi_latest(client: httpx.AsyncClient, name: str) -> str:
    try:
        r = await client.get(
            f"https://pypi.org/pypi/{name}/json", timeout=_HTTP_TIMEOUT
        )
        r.raise_for_status()
        return r.json()["info"]["version"]
    except Exception:  # noqa: BLE001
        return ""


async def _fetch_npm_latest(client: httpx.AsyncClient, name: str) -> str:
    try:
        # URL-encode scoped packages (@org/pkg → %40org%2Fpkg)
        encoded = name.replace("@", "%40").replace("/", "%2F")
        r = await client.get(
            f"https://registry.npmjs.org/{encoded}/latest",
            timeout=_HTTP_TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("version", "")
    except Exception:  # noqa: BLE001
        return ""


async def _fetch_go_latest(client: httpx.AsyncClient, module: str) -> str:
    try:
        r = await client.get(
            f"https://proxy.golang.org/{module}/@latest", timeout=_HTTP_TIMEOUT
        )
        r.raise_for_status()
        return r.json().get("Version", "")
    except Exception:  # noqa: BLE001
        return ""


async def _fetch_maven_latest(
    client: httpx.AsyncClient, group_id: str, artifact_id: str
) -> str:
    try:
        q = f"g:{group_id}+AND+a:{artifact_id}"
        r = await client.get(
            f"https://search.maven.org/solrsearch/select?q={q}&rows=1&wt=json",
            timeout=_HTTP_TIMEOUT,
        )
        r.raise_for_status()
        docs = r.json().get("response", {}).get("docs", [])
        return docs[0].get("latestVersion", "") if docs else ""
    except Exception:  # noqa: BLE001
        return ""


def _days_behind(current: str, latest: str) -> int | None:
    """Very rough staleness: count semver major/minor distance as days.

    We don't have release dates from all registries, so we use a simple
    heuristic: different == stale, and we return 0 if equal, 999 if we
    can't parse.  The OSV scanner provides the real security signal.
    """
    if not current or not latest:
        return None
    if current == latest:
        return 0
    # Try to parse semver to give a rough distance
    def _parts(v: str) -> tuple[int, int, int]:
        m = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", v.lstrip("v=~^"))
        if not m:
            return (0, 0, 0)
        return (int(m.group(1) or 0), int(m.group(2) or 0), int(m.group(3) or 0))

    cp = _parts(current)
    lp = _parts(latest)
    if lp[0] > cp[0]:
        return 730  # major version behind → ~2yr stale marker
    if lp[1] > cp[1]:
        return 180  # minor version behind → ~6mo stale marker
    if lp[2] > cp[2]:
        return 30   # patch behind → ~1mo stale marker
    return 0


# ---------------------------------------------------------------------------
# Manifest parsers
# ---------------------------------------------------------------------------

def _parse_requirements_txt(content: str, is_dev: bool = False) -> list[Dependency]:
    deps: list[Dependency] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-r", "--")):
            continue
        # Strip extras, env markers
        line = re.split(r"\s*[;#]", line)[0].strip()
        m = re.match(r"^([A-Za-z0-9_\-\.]+)\s*(?:[=<>!~^]+\s*([^\s,]+))?", line)
        if m:
            name = m.group(1)
            version = (m.group(2) or "").lstrip("=<>!~^")
            deps.append(Dependency(name=name, version=version,
                                   ecosystem="pypi", is_dev=is_dev))
    return deps


def _parse_pyproject_toml(content: str) -> list[Dependency]:
    """Extract [project.dependencies] and [project.optional-dependencies.dev]."""
    deps: list[Dependency] = []
    in_section: str | None = None
    is_dev = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            if "project.dependencies" in stripped and "optional" not in stripped:
                in_section = "prod"
                is_dev = False
            elif "optional-dependencies" in stripped:
                in_section = "opt"
                # guess dev if key contains dev/test/lint
                is_dev = any(k in stripped for k in ("dev", "test", "lint", "docs"))
            elif stripped.startswith("["):
                in_section = None
            continue

        if in_section and stripped.startswith('"') or stripped.startswith("'"):
            dep_str = stripped.strip("\"',")
            m = re.match(r"^([A-Za-z0-9_\-\.]+)\s*(?:[=<>!~^]+\s*([^\s,;]+))?", dep_str)
            if m:
                name = m.group(1)
                version = (m.group(2) or "").lstrip("=<>!~^")
                deps.append(Dependency(name=name, version=version,
                                       ecosystem="pypi", is_dev=is_dev))
    return deps


def _parse_pipfile_lock(content: str) -> list[Dependency]:
    deps: list[Dependency] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return deps

    for section, is_dev in (("default", False), ("develop", True)):
        for name, meta in data.get(section, {}).items():
            version = str(meta.get("version", "")).lstrip("=")
            deps.append(Dependency(name=name, version=version,
                                   ecosystem="pypi", is_dev=is_dev))
    return deps


def _parse_package_json(content: str) -> list[Dependency]:
    deps: list[Dependency] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return deps

    for key, is_dev in (("dependencies", False), ("devDependencies", True)):
        for name, version_range in data.get(key, {}).items():
            version = str(version_range).lstrip("^~>=<")
            deps.append(Dependency(name=name, version=version,
                                   ecosystem="npm", is_dev=is_dev))
    return deps


def _parse_package_lock_json(content: str) -> list[Dependency]:
    """Lock file v2/v3 — prefer this over package.json for exact versions."""
    deps: list[Dependency] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return deps

    # v2/v3 uses 'packages'
    packages = data.get("packages", {})
    for pkg_path, meta in packages.items():
        if not pkg_path or pkg_path == "":
            continue
        name = pkg_path.split("node_modules/")[-1]
        version = meta.get("version", "")
        is_dev = meta.get("dev", False)
        deps.append(Dependency(name=name, version=version,
                               ecosystem="npm", is_dev=is_dev))
    return deps


def _parse_yarn_lock(content: str) -> list[Dependency]:
    """Parse yarn.lock (v1) — extract package@version blocks."""
    deps: list[Dependency] = []
    current_name: str | None = None

    for line in content.splitlines():
        # e.g. "lodash@^4.17.21:" or "@babel/core@^7.0.0:"
        header = re.match(r'^"?(@?[a-z0-9@/_\-\.]+)@.*?"?:', line)
        if header:
            raw = header.group(1)
            current_name = raw.split("/")[-1] if "@" not in raw[1:] else raw
            continue
        if current_name and line.strip().startswith("version"):
            m = re.search(r'"([^"]+)"', line)
            if m:
                deps.append(Dependency(name=current_name, version=m.group(1),
                                       ecosystem="npm", is_dev=False))
            current_name = None
    return deps


def _parse_go_mod(content: str) -> list[Dependency]:
    deps: list[Dependency] = []
    in_require = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require = True
            continue
        if in_require:
            if stripped == ")":
                in_require = False
                continue
            parts = stripped.split()
            if len(parts) >= 2:
                name, version = parts[0], parts[1]
                is_indirect = "indirect" in stripped
                deps.append(Dependency(name=name, version=version,
                                       ecosystem="go", is_dev=is_indirect))
        elif stripped.startswith("require "):
            parts = stripped.split()
            if len(parts) >= 3:
                deps.append(Dependency(name=parts[1], version=parts[2],
                                       ecosystem="go", is_dev=False))
    return deps


def _parse_pom_xml(content: str) -> list[Dependency]:
    deps: list[Dependency] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return deps

    ns_match = re.match(r"\{([^}]+)\}", root.tag)
    ns = f"{{{ns_match.group(1)}}}" if ns_match else ""

    for dep in root.iter(f"{ns}dependency"):
        group_id_el = dep.find(f"{ns}groupId")
        artifact_id_el = dep.find(f"{ns}artifactId")
        version_el = dep.find(f"{ns}version")
        scope_el = dep.find(f"{ns}scope")

        if group_id_el is None or artifact_id_el is None:
            continue

        name = f"{group_id_el.text}:{artifact_id_el.text}"
        version = version_el.text if version_el is not None else ""
        is_dev = scope_el is not None and scope_el.text in ("test", "provided")
        deps.append(Dependency(name=name, version=version or "",
                               ecosystem="maven", is_dev=is_dev))
    return deps


def _parse_build_gradle(content: str) -> list[Dependency]:
    """Heuristic Gradle parser — handles both Groovy and Kotlin DSL."""
    deps: list[Dependency] = []
    # Match: implementation 'group:artifact:version' or
    #        implementation("group:artifact:version")
    pattern = re.compile(
        r"(implementation|api|runtimeOnly|compileOnly|testImplementation|annotationProcessor)"
        r"""[(\s]+['"]([a-zA-Z0-9_.\-]+):([a-zA-Z0-9_.\-]+):([^'")\s]+)['")]""",
    )
    for m in pattern.finditer(content):
        config, group_id, artifact_id, version = m.groups()
        is_dev = "test" in config.lower()
        name = f"{group_id}:{artifact_id}"
        deps.append(Dependency(name=name, version=version,
                               ecosystem="gradle", is_dev=is_dev))
    return deps


# ---------------------------------------------------------------------------
# Staleness enrichment
# ---------------------------------------------------------------------------

async def _enrich_staleness(
    deps: list[Dependency],
    repo_path: Path,
) -> None:
    """Mutate *deps* in-place to add latest_version + days_since_latest.

    Uses a disk cache keyed by (ecosystem, name) to avoid re-hitting APIs.
    """
    cache = _load_cache(repo_path)
    now = time.time()
    updated = False

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for dep in deps:
            key = _cache_key(dep.ecosystem, dep.name)
            entry = cache.get(key)

            # Use cache if fresh
            if entry and (now - entry.get("ts", 0)) < _CACHE_TTL_SECONDS:
                dep.latest_version = entry.get("latest", "")
                dep.days_since_latest = entry.get("days", None)
                continue

            # Fetch live
            latest = ""
            try:
                if dep.ecosystem == "pypi":
                    latest = await _fetch_pypi_latest(client, dep.name)
                elif dep.ecosystem == "npm":
                    latest = await _fetch_npm_latest(client, dep.name)
                elif dep.ecosystem == "go":
                    latest = await _fetch_go_latest(client, dep.name)
                elif dep.ecosystem in ("maven", "gradle"):
                    if ":" in dep.name:
                        group, artifact = dep.name.split(":", 1)
                        latest = await _fetch_maven_latest(client, group, artifact)
            except Exception as exc:  # noqa: BLE001
                logger.debug("staleness fetch failed for %s — %s", dep.name, exc)

            days = _days_behind(dep.version, latest)
            dep.latest_version = latest
            dep.days_since_latest = days

            cache[key] = {"latest": latest, "days": days, "ts": now}
            updated = True

    if updated:
        _save_cache(repo_path, cache)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def scan_dependencies(
    repo_path: Path,
    all_files: list[Path],
) -> list[Dependency]:
    """Scan *repo_path* for known manifests and return enriched Dependency list.

    Args:
        repo_path: Root of the repository (used for cache path).
        all_files: Pre-filtered list of files (post .gitignore filtering).

    Returns:
        List[Dependency] — never raises, returns [] on error.
    """
    deps: list[Dependency] = []

    # Build a quick lookup by filename
    by_name: dict[str, list[Path]] = {}
    for p in all_files:
        by_name.setdefault(p.name, []).append(p)
        # Also index by filename pattern (e.g. requirements-dev.txt)
        if p.name.startswith("requirements") and p.suffix == ".txt":
            by_name.setdefault("requirements*.txt", []).append(p)

    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return ""

    processed_manifests: set[str] = set()

    # --- Python ---
    for p in all_files:
        if p.name.startswith("requirements") and p.suffix == ".txt":
            if str(p) not in processed_manifests:
                is_dev = any(k in p.name for k in ("dev", "test", "lint"))
                deps.extend(_parse_requirements_txt(_read(p), is_dev=is_dev))
                processed_manifests.add(str(p))

    for p in by_name.get("pyproject.toml", []):
        if str(p) not in processed_manifests:
            deps.extend(_parse_pyproject_toml(_read(p)))
            processed_manifests.add(str(p))

    for p in by_name.get("Pipfile.lock", []):
        if str(p) not in processed_manifests:
            deps.extend(_parse_pipfile_lock(_read(p)))
            processed_manifests.add(str(p))

    # --- Node ---
    # Prefer lock file; fall back to package.json
    lock_paths = by_name.get("package-lock.json", [])
    yarn_paths = by_name.get("yarn.lock", [])

    if lock_paths:
        for p in lock_paths:
            if str(p) not in processed_manifests:
                deps.extend(_parse_package_lock_json(_read(p)))
                processed_manifests.add(str(p))
    elif yarn_paths:
        for p in yarn_paths:
            if str(p) not in processed_manifests:
                deps.extend(_parse_yarn_lock(_read(p)))
                processed_manifests.add(str(p))
    else:
        for p in by_name.get("package.json", []):
            if str(p) not in processed_manifests:
                content = _read(p)
                # Skip workspace root package.json with no dependencies
                try:
                    data = json.loads(content)
                    if "dependencies" in data or "devDependencies" in data:
                        deps.extend(_parse_package_json(content))
                        processed_manifests.add(str(p))
                except json.JSONDecodeError:
                    pass

    # --- Go ---
    for p in by_name.get("go.mod", []):
        if str(p) not in processed_manifests:
            deps.extend(_parse_go_mod(_read(p)))
            processed_manifests.add(str(p))

    # --- Java/Maven ---
    for p in by_name.get("pom.xml", []):
        if str(p) not in processed_manifests:
            deps.extend(_parse_pom_xml(_read(p)))
            processed_manifests.add(str(p))

    # --- Gradle ---
    for p in all_files:
        if p.name in ("build.gradle", "build.gradle.kts"):
            if str(p) not in processed_manifests:
                deps.extend(_parse_build_gradle(_read(p)))
                processed_manifests.add(str(p))

    # Deduplicate by (ecosystem, name) — keep first seen
    seen: set[str] = set()
    unique_deps: list[Dependency] = []
    for dep in deps:
        key = f"{dep.ecosystem}:{dep.name}"
        if key not in seen:
            seen.add(key)
            unique_deps.append(dep)

    # Enrich with staleness data
    try:
        await _enrich_staleness(unique_deps, repo_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("staleness enrichment failed: %s", exc)

    return unique_deps
