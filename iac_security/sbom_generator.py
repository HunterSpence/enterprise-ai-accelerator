"""
iac_security/sbom_generator.py
================================

Generate CycloneDX 1.5 SBOM JSON for a repository's dependencies.

Supported ecosystems:
  - Python  : requirements.txt, pyproject.toml (PEP 508), poetry.lock
  - Node.js : package-lock.json (v2/v3)
  - Go      : go.sum
  - Java    : pom.xml (direct dependencies section)
  - Docker  : Dockerfile FROM image parsing

Uses cyclonedx-python-lib (Apache 2.0) for the canonical CycloneDX object
model and serialisation.  Falls back to raw JSON generation if the library
is unavailable (no hard crash).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lightweight component model (used before CDX serialisation)
# ---------------------------------------------------------------------------


@dataclass
class DetectedComponent:
    """Raw component detected from a manifest file."""

    ecosystem: str      # "pypi" | "npm" | "go" | "maven" | "container"
    name: str
    version: str
    source_file: str
    purl: str = ""      # populated during normalisation


def _make_purl(ecosystem: str, name: str, version: str) -> str:
    """Build a minimal PackageURL string."""
    eco_map = {
        "pypi": "pypi",
        "npm": "npm",
        "go": "golang",
        "maven": "maven",
        "container": "oci",
    }
    purl_type = eco_map.get(ecosystem, ecosystem)
    name_enc = name.replace("/", "%2F")
    if version:
        return f"pkg:{purl_type}/{name_enc}@{version}"
    return f"pkg:{purl_type}/{name_enc}"


# ---------------------------------------------------------------------------
# Manifest parsers
# ---------------------------------------------------------------------------


def _parse_requirements_txt(path: Path) -> list[DetectedComponent]:
    """Parse a requirements.txt file."""
    components: list[DetectedComponent] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip inline comments
        line = line.split("#")[0].strip()
        # Handle pinned: package==1.2.3
        m = re.match(
            r"^([A-Za-z0-9_.\-]+)\s*(?:[=<>!~]{1,3})\s*([A-Za-z0-9_.\-+]+)", line
        )
        if m:
            name, version = m.group(1), m.group(2)
        else:
            name = re.split(r"[=<>!~\s;@\[]", line)[0].strip()
            version = ""
        if name:
            c = DetectedComponent(
                ecosystem="pypi",
                name=name.lower(),
                version=version,
                source_file=str(path),
            )
            c.purl = _make_purl("pypi", c.name, c.version)
            components.append(c)
    return components


def _parse_pyproject_toml(path: Path) -> list[DetectedComponent]:
    """Parse pyproject.toml [project] and [tool.poetry] dependency sections."""
    try:
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            import tomli as tomllib  # pip install tomli
    except ImportError:
        logger.debug("tomllib/tomli not available — skipping pyproject.toml parse")
        return _parse_requirements_txt_fallback(path)

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse pyproject.toml %s: %s", path, exc)
        return []

    components: list[DetectedComponent] = []

    # PEP 517/518 [project] dependencies
    for dep in data.get("project", {}).get("dependencies", []):
        m = re.match(r"^([A-Za-z0-9_.\-]+)", dep)
        if m:
            c = DetectedComponent("pypi", m.group(1).lower(), "", str(path))
            c.purl = _make_purl("pypi", c.name, c.version)
            components.append(c)

    # Poetry [tool.poetry.dependencies]
    for name, spec in data.get("tool", {}).get("poetry", {}).get("dependencies", {}).items():
        if name == "python":
            continue
        version = spec if isinstance(spec, str) else (spec.get("version", "") if isinstance(spec, dict) else "")
        c = DetectedComponent("pypi", name.lower(), str(version).lstrip("^~>="), str(path))
        c.purl = _make_purl("pypi", c.name, c.version)
        components.append(c)

    return components


def _parse_requirements_txt_fallback(path: Path) -> list[DetectedComponent]:
    """Used when tomllib is unavailable."""
    return []


def _parse_poetry_lock(path: Path) -> list[DetectedComponent]:
    """Parse poetry.lock for exact pinned versions."""
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
    except ImportError:
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse poetry.lock %s: %s", path, exc)
        return []

    components: list[DetectedComponent] = []
    for pkg in data.get("package", []):
        if not isinstance(pkg, dict):
            continue
        name = pkg.get("name", "")
        version = pkg.get("version", "")
        if name:
            c = DetectedComponent("pypi", name.lower(), version, str(path))
            c.purl = _make_purl("pypi", c.name, c.version)
            components.append(c)
    return components


def _parse_package_lock_json(path: Path) -> list[DetectedComponent]:
    """Parse npm package-lock.json (v2/v3)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse package-lock.json %s: %s", path, exc)
        return []

    components: list[DetectedComponent] = []
    # v2/v3 format uses 'packages' key
    packages = data.get("packages", {}) or {}
    for pkg_path, info in packages.items():
        if not pkg_path or pkg_path == "":  # skip root
            continue
        if not isinstance(info, dict):
            continue
        # pkg_path is like "node_modules/express" or "node_modules/foo/node_modules/bar"
        name = pkg_path.split("node_modules/")[-1]
        version = info.get("version", "")
        c = DetectedComponent("npm", name, version, str(path))
        c.purl = _make_purl("npm", c.name, c.version)
        components.append(c)

    # v1 fallback: 'dependencies' key
    if not components:
        deps = data.get("dependencies", {}) or {}
        for name, info in deps.items():
            if not isinstance(info, dict):
                continue
            version = info.get("version", "")
            c = DetectedComponent("npm", name, version, str(path))
            c.purl = _make_purl("npm", c.name, c.version)
            components.append(c)

    return components


def _parse_go_sum(path: Path) -> list[DetectedComponent]:
    """Parse go.sum for Go module dependencies."""
    components: list[DetectedComponent] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        module = parts[0]
        version = parts[1].split("/")[0]  # strip /go.mod suffix
        key = f"{module}@{version}"
        if key in seen:
            continue
        seen.add(key)
        c = DetectedComponent("go", module, version, str(path))
        c.purl = _make_purl("go", module, version)
        components.append(c)
    return components


def _parse_pom_xml(path: Path) -> list[DetectedComponent]:
    """Parse Maven pom.xml — extracts <dependency> elements."""
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(str(path))
        root = tree.getroot()
    except Exception as exc:
        logger.warning("Failed to parse pom.xml %s: %s", path, exc)
        return []

    # Strip XML namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    components: list[DetectedComponent] = []
    for dep in root.findall(f".//{ns}dependency"):
        group_id = (dep.findtext(f"{ns}groupId") or "").strip()
        artifact_id = (dep.findtext(f"{ns}artifactId") or "").strip()
        version = (dep.findtext(f"{ns}version") or "").strip()
        scope = (dep.findtext(f"{ns}scope") or "compile").strip()
        if scope in {"test", "provided"}:
            continue
        if group_id and artifact_id:
            name = f"{group_id}:{artifact_id}"
            c = DetectedComponent("maven", name, version, str(path))
            c.purl = _make_purl("maven", name, version)
            components.append(c)
    return components


def _parse_dockerfile(path: Path) -> list[DetectedComponent]:
    """Parse Dockerfile FROM lines for base image components."""
    components: list[DetectedComponent] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip().upper()
        if not stripped.startswith("FROM"):
            continue
        # FROM image:tag [AS alias]
        m = re.match(r"FROM\s+([^\s]+)(?:\s+AS\s+\S+)?", line.strip(), re.IGNORECASE)
        if not m:
            continue
        image_ref = m.group(1)
        if image_ref.lower() == "scratch":
            continue
        # Split name:tag
        if ":" in image_ref:
            name, tag = image_ref.rsplit(":", 1)
        else:
            name, tag = image_ref, "latest"
        c = DetectedComponent("container", name, tag, str(path))
        c.purl = _make_purl("container", name, tag)
        components.append(c)
    return components


# ---------------------------------------------------------------------------
# CycloneDX serialisation
# ---------------------------------------------------------------------------


def _to_cyclonedx_json(
    components: list[DetectedComponent],
    repo_name: str,
    version: str = "0.0.0",
) -> dict[str, Any]:
    """
    Produce a CycloneDX 1.5 SBOM dict using cyclonedx-python-lib if available,
    falling back to raw dict construction otherwise.
    """
    try:
        return _to_cyclonedx_via_lib(components, repo_name, version)
    except ImportError:
        logger.debug("cyclonedx-python-lib not installed — using raw JSON fallback")
        return _to_cyclonedx_raw(components, repo_name, version)


def _to_cyclonedx_via_lib(
    components: list[DetectedComponent],
    repo_name: str,
    version: str,
) -> dict[str, Any]:
    """Use cyclonedx-python-lib for canonical serialisation."""
    from cyclonedx.model.bom import Bom
    from cyclonedx.model.component import Component, ComponentType
    from cyclonedx.output.json import JsonV1Dot5
    from packageurl import PackageURL

    bom = Bom()
    bom.metadata.component = Component(
        component_type=ComponentType.APPLICATION,
        name=repo_name,
        version=version,
    )

    for dc in components:
        try:
            purl = PackageURL.from_string(dc.purl) if dc.purl else None
        except Exception:
            purl = None
        comp = Component(
            component_type=ComponentType.LIBRARY,
            name=dc.name,
            version=dc.version or None,
            purl=purl,
        )
        bom.components.add(comp)

    serialiser = JsonV1Dot5(bom)
    return json.loads(serialiser.output_as_string())


def _to_cyclonedx_raw(
    components: list[DetectedComponent],
    repo_name: str,
    version: str,
) -> dict[str, Any]:
    """Minimal raw CycloneDX 1.5 JSON without external library."""
    sbom_components = []
    for dc in components:
        entry: dict[str, Any] = {
            "type": "library",
            "bom-ref": str(uuid.uuid4()),
            "name": dc.name,
        }
        if dc.version:
            entry["version"] = dc.version
        if dc.purl:
            entry["purl"] = dc.purl
        sbom_components.append(entry)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [{"name": "enterprise-ai-accelerator/iac_security", "version": "0.1.0"}],
            "component": {
                "type": "application",
                "bom-ref": str(uuid.uuid4()),
                "name": repo_name,
                "version": version,
            },
        },
        "components": sbom_components,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class SBOMGenerator:
    """
    Generate a CycloneDX 1.5 SBOM for a repository.

    Usage::

        from iac_security import SBOMGenerator
        sbom = SBOMGenerator().generate(Path("./my-repo"))
        with open("sbom.cdx.json", "w") as f:
            json.dump(sbom, f, indent=2)
    """

    def generate(
        self,
        root: Path,
        repo_name: Optional[str] = None,
        version: str = "0.0.0",
    ) -> dict[str, Any]:
        """
        Walk *root* for supported manifest files and produce a CycloneDX 1.5
        SBOM.  Returns the SBOM as a Python dict ready for json.dump().
        """
        root = Path(root).resolve()
        repo_name = repo_name or root.name
        components: list[DetectedComponent] = []

        PARSERS: list[tuple[str, Any]] = [
            ("requirements.txt", _parse_requirements_txt),
            ("pyproject.toml", _parse_pyproject_toml),
            ("poetry.lock", _parse_poetry_lock),
            ("package-lock.json", _parse_package_lock_json),
            ("go.sum", _parse_go_sum),
            ("pom.xml", _parse_pom_xml),
            ("Dockerfile", _parse_dockerfile),
        ]

        for filename, parser_fn in PARSERS:
            for match in sorted(root.rglob(filename)):
                # Skip node_modules and .terraform
                if any(
                    part in match.parts
                    for part in {"node_modules", ".terraform", ".git", "__pycache__"}
                ):
                    continue
                try:
                    found = parser_fn(match)
                    components.extend(found)
                    logger.debug("SBOM: parsed %d components from %s", len(found), match)
                except Exception as exc:
                    logger.warning("SBOM parser failed on %s: %s", match, exc)

        # Deduplicate by PURL
        seen_purls: set[str] = set()
        deduped: list[DetectedComponent] = []
        for c in components:
            key = c.purl or f"{c.ecosystem}:{c.name}@{c.version}"
            if key not in seen_purls:
                seen_purls.add(key)
                deduped.append(c)

        logger.info(
            "SBOMGenerator: %d unique components found in %s", len(deduped), root
        )
        return _to_cyclonedx_json(deduped, repo_name, version)

    def generate_to_file(
        self,
        root: Path,
        output_path: Path,
        repo_name: Optional[str] = None,
        version: str = "0.0.0",
    ) -> Path:
        """Generate SBOM and write to a file. Returns the output path."""
        sbom = self.generate(root, repo_name, version)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(sbom, f, indent=2)
        logger.info("SBOM written to %s", output_path)
        return output_path
