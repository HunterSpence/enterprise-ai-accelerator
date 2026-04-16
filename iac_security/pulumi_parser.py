"""
iac_security/pulumi_parser.py
==============================

Parse Pulumi YAML stack files and Pulumi.json state files into a flat list
of PulumiResource objects compatible with the TerraformResource interface so
policies.py can run the same checks against both IaC flavours.

Supported inputs:
  - Pulumi.yaml / Pulumi.<stack>.yaml  — project + stack config
  - Pulumi.<stack>.yaml               — stack-level config overrides
  - .pulumi/stacks/<stack>.json       — exported JSON state (most complete)
  - Any **/Pulumi*.yaml anywhere in the tree

The parsed resource shape mirrors TerraformResource so policies.py only needs
one code path.  The `kind` field is always "resource"; `resource_type` is the
Pulumi type token (e.g. "aws:s3/bucket:Bucket").
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model (mirrors TerraformResource for policy compatibility)
# ---------------------------------------------------------------------------


@dataclass
class PulumiResource:
    """Normalised Pulumi resource, shape-compatible with TerraformResource."""

    kind: str = "resource"  # always "resource" for policy checks
    resource_type: str = ""  # Pulumi type token, e.g. "aws:s3/bucket:Bucket"
    name: str = ""           # logical resource name
    attributes: dict[str, Any] = field(default_factory=dict)
    source_file: str = ""
    source_line: int = 0

    @property
    def address(self) -> str:
        return f"{self.resource_type}.{self.name}"

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-path attribute lookup matching TerraformResource.get()."""
        parts = key.split(".")
        node: Any = self.attributes
        for part in parts:
            if not isinstance(node, dict):
                return default
            node = node.get(part, default)
            if node is default:
                return default
        return node

    # Allow policies designed for TerraformResource to work transparently
    @property
    def resource_type_short(self) -> str:
        """Last segment of the Pulumi type token, e.g. 'Bucket'."""
        return self.resource_type.split(":")[-1] if ":" in self.resource_type else self.resource_type


# ---------------------------------------------------------------------------
# YAML stack file parser
# ---------------------------------------------------------------------------


def _parse_pulumi_yaml(path: Path) -> list[PulumiResource]:
    """
    Parse a Pulumi YAML file.

    Expected shapes:
      - Pulumi.yaml: may contain 'resources:' block (Pulumi Automation API style)
      - Pulumi.<stack>.yaml: usually only config, no resources — returns []
    """
    try:
        import yaml  # PyYAML — already in requirements
    except ImportError:
        logger.error("PyYAML is not installed.")
        return []

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        data = yaml.safe_load(raw) or {}
    except Exception as exc:
        logger.warning("Skipping malformed Pulumi YAML %s: %s", path, exc)
        return []

    if not isinstance(data, dict):
        return []

    resources_block = data.get("resources", {})
    if not isinstance(resources_block, dict):
        return []

    result: list[PulumiResource] = []
    for logical_name, spec in resources_block.items():
        if not isinstance(spec, dict):
            continue
        rtype = spec.get("type", "")
        props = spec.get("properties", {}) or {}
        # Also capture component resources
        component = spec.get("component", False)
        result.append(
            PulumiResource(
                kind="resource",
                resource_type=rtype,
                name=logical_name,
                attributes={
                    **props,
                    "_component": component,
                    "_options": spec.get("options", {}),
                },
                source_file=str(path),
                source_line=0,  # YAML doesn't carry line info post-parse
            )
        )

    if result:
        logger.debug("Parsed %d resources from Pulumi YAML %s", len(result), path)
    return result


# ---------------------------------------------------------------------------
# JSON state file parser (.pulumi/stacks/<stack>.json)
# ---------------------------------------------------------------------------


def _parse_pulumi_json_state(path: Path) -> list[PulumiResource]:
    """
    Parse a Pulumi stack JSON state export.

    The state format has a top-level 'checkpoint' -> 'latest' -> 'resources'
    array.  Each entry has: type, urn, inputs, outputs.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Skipping malformed Pulumi JSON state %s: %s", path, exc)
        return []

    # Handle both direct state export and wrapped checkpoint format
    resources_list: list[dict] = []
    if "checkpoint" in data:
        latest = data["checkpoint"].get("latest", {}) or {}
        resources_list = latest.get("resources", []) or []
    elif "deployment" in data:
        # `pulumi stack export` format
        resources_list = data["deployment"].get("resources", []) or []
    elif isinstance(data.get("resources"), list):
        resources_list = data["resources"]

    result: list[PulumiResource] = []
    for entry in resources_list:
        if not isinstance(entry, dict):
            continue
        rtype = entry.get("type", "")
        # Skip the stack root pseudo-resource
        if rtype == "pulumi:pulumi:Stack":
            continue
        urn: str = entry.get("urn", "")
        # URN format: urn:pulumi:<stack>::<project>::<type>::<name>
        logical_name = urn.split("::")[-1] if "::" in urn else entry.get("id", "unknown")
        inputs: dict = entry.get("inputs", {}) or {}
        outputs: dict = entry.get("outputs", {}) or {}
        # Merge inputs + outputs; inputs represent desired state (policy-relevant)
        attrs = {**outputs, **inputs, "_urn": urn, "_id": entry.get("id", "")}
        result.append(
            PulumiResource(
                kind="resource",
                resource_type=rtype,
                name=logical_name,
                attributes=attrs,
                source_file=str(path),
                source_line=0,
            )
        )

    logger.debug("Parsed %d resources from Pulumi JSON state %s", len(result), path)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_pulumi(root: Path) -> list[PulumiResource]:
    """
    Recursively discover and parse Pulumi configuration files under *root*.

    Search order (highest fidelity first):
      1. .pulumi/stacks/*.json      — full state with resolved values
      2. Pulumi.yaml / Pulumi*.yaml — project/stack YAML definitions
    """
    if not root.is_dir():
        if root.suffix in {".yaml", ".yml"}:
            return _parse_pulumi_yaml(root)
        if root.suffix == ".json":
            return _parse_pulumi_json_state(root)
        logger.warning("pulumi_parser: unsupported path: %s", root)
        return []

    results: list[PulumiResource] = []

    # 1. JSON state files (most complete)
    state_dir = root / ".pulumi" / "stacks"
    if state_dir.is_dir():
        for json_file in sorted(state_dir.glob("*.json")):
            results.extend(_parse_pulumi_json_state(json_file))

    # 2. YAML project/stack files
    for yaml_file in sorted(root.rglob("Pulumi*.yaml")) + sorted(root.rglob("Pulumi*.yml")):
        # Skip node_modules and .pulumi cache
        if "node_modules" in yaml_file.parts or ".pulumi" in yaml_file.parts:
            continue
        results.extend(_parse_pulumi_yaml(yaml_file))

    # Deduplicate by address in case YAML + JSON both describe the same resource
    seen: set[str] = set()
    deduped: list[PulumiResource] = []
    for r in results:
        addr = r.address
        if addr not in seen:
            seen.add(addr)
            deduped.append(r)

    logger.info("Pulumi parser: found %d unique resources in %s", len(deduped), root)
    return deduped
