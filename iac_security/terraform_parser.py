"""
iac_security/terraform_parser.py
=================================

Parse Terraform HCL source trees into a flat list of TerraformResource
objects for downstream policy evaluation.

Design decisions:
  - Uses python-hcl2 (Apache 2.0) for parsing — no subprocess, no checkov.
  - Recursively walks all *.tf files under the given root.
  - Malformed HCL is silently skipped with a logged warning (resilient).
  - Modules, data sources, and variables are captured; only resources trigger
    policy checks but all types are available for context.
  - source_line is best-effort; python-hcl2 does not expose token positions
    so we record the file position via a pre-scan line index built from the
    raw text. This gives us the opening-brace line of each resource block.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TerraformResource:
    """Normalised representation of one Terraform block."""

    kind: str  # "resource" | "data" | "module" | "variable" | "output" | "provider"
    resource_type: str  # e.g. "aws_s3_bucket" or "" for module/variable
    name: str  # logical name given in the .tf file
    attributes: dict[str, Any] = field(default_factory=dict)
    source_file: str = ""
    source_line: int = 0

    # Convenience helpers used by policies.py
    @property
    def address(self) -> str:
        if self.resource_type:
            return f"{self.resource_type}.{self.name}"
        return f"{self.kind}.{self.name}"

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-path attribute lookup, e.g. get('server_side_encryption_configuration.rule')."""
        parts = key.split(".")
        node: Any = self.attributes
        for part in parts:
            if not isinstance(node, dict):
                return default
            node = node.get(part, default)
            if node is default:
                return default
        return node


# ---------------------------------------------------------------------------
# Line-index builder (best-effort source_line resolution)
# ---------------------------------------------------------------------------


def _build_line_index(raw: str) -> dict[str, int]:
    """
    Return a mapping of 'resource_type.name' -> line_number by scanning
    the raw HCL text with a regex.  This runs before hcl2 parsing so errors
    here do not affect the structured parse.
    """
    index: dict[str, int] = {}
    # Matches: resource "aws_s3_bucket" "my_bucket" {
    pattern = re.compile(
        r'^(resource|data|module|variable|output|provider)\s+"([^"]+)"\s*(?:"([^"]+)")?\s*\{',
        re.MULTILINE,
    )
    for m in pattern.finditer(raw):
        kind = m.group(1)
        type_or_name = m.group(2)
        logical_name = m.group(3) or ""
        line = raw[: m.start()].count("\n") + 1
        key = f"{kind}.{type_or_name}.{logical_name}"
        index[key] = line
    return index


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _parse_file(path: Path) -> list[TerraformResource]:
    """Parse a single .tf file. Returns [] and logs a warning on any error."""
    try:
        import hcl2  # python-hcl2
    except ImportError:
        logger.error(
            "python-hcl2 is not installed. Run: pip install python-hcl2>=4.3.3"
        )
        return []

    raw = path.read_text(encoding="utf-8", errors="replace")
    line_index = _build_line_index(raw)

    try:
        data: dict[str, Any] = hcl2.loads(raw)
    except Exception as exc:  # hcl2 raises lark.exceptions.* or similar
        logger.warning("Skipping malformed HCL file %s: %s", path, exc)
        return []

    resources: list[TerraformResource] = []

    # hcl2 returns {'resource': [{'aws_s3_bucket': {'my_bucket': {...}}}], ...}
    for block_type, block_list in data.items():
        if not isinstance(block_list, list):
            continue
        for block in block_list:
            if not isinstance(block, dict):
                continue
            for type_or_name, inner in block.items():
                if not isinstance(inner, dict):
                    continue
                if block_type == "resource":
                    # inner = {'logical_name': {attrs}}
                    for logical_name, attrs in inner.items():
                        key = f"resource.{type_or_name}.{logical_name}"
                        resources.append(
                            TerraformResource(
                                kind="resource",
                                resource_type=type_or_name,
                                name=logical_name,
                                attributes=attrs if isinstance(attrs, dict) else {},
                                source_file=str(path),
                                source_line=line_index.get(key, 0),
                            )
                        )
                elif block_type == "data":
                    for logical_name, attrs in inner.items():
                        key = f"data.{type_or_name}.{logical_name}"
                        resources.append(
                            TerraformResource(
                                kind="data",
                                resource_type=type_or_name,
                                name=logical_name,
                                attributes=attrs if isinstance(attrs, dict) else {},
                                source_file=str(path),
                                source_line=line_index.get(key, 0),
                            )
                        )
                elif block_type == "module":
                    key = f"module.{type_or_name}."
                    resources.append(
                        TerraformResource(
                            kind="module",
                            resource_type="",
                            name=type_or_name,
                            attributes=inner if isinstance(inner, dict) else {},
                            source_file=str(path),
                            source_line=line_index.get(key, 0),
                        )
                    )
                elif block_type == "variable":
                    key = f"variable.{type_or_name}."
                    resources.append(
                        TerraformResource(
                            kind="variable",
                            resource_type="",
                            name=type_or_name,
                            attributes=inner if isinstance(inner, dict) else {},
                            source_file=str(path),
                            source_line=line_index.get(key, 0),
                        )
                    )
                elif block_type == "output":
                    key = f"output.{type_or_name}."
                    resources.append(
                        TerraformResource(
                            kind="output",
                            resource_type="",
                            name=type_or_name,
                            attributes=inner if isinstance(inner, dict) else {},
                            source_file=str(path),
                            source_line=line_index.get(key, 0),
                        )
                    )
                elif block_type == "provider":
                    key = f"provider.{type_or_name}."
                    resources.append(
                        TerraformResource(
                            kind="provider",
                            resource_type="",
                            name=type_or_name,
                            attributes=inner if isinstance(inner, dict) else {},
                            source_file=str(path),
                            source_line=line_index.get(key, 0),
                        )
                    )

    return resources


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_terraform(root: Path) -> list[TerraformResource]:
    """
    Recursively parse all *.tf files under *root* and return a flat list
    of TerraformResource objects.

    Skips:
      - .terraform/ directories (provider cache)
      - **/.terraform.lock.hcl (lock files, not HCL2 compliant)
      - Files larger than 5 MB (pathological generated configs)
    """
    if not root.is_dir():
        # Accept single-file invocations too
        if root.suffix == ".tf":
            return _parse_file(root)
        logger.warning("terraform_parser: path is not a directory or .tf file: %s", root)
        return []

    results: list[TerraformResource] = []
    for tf_file in sorted(root.rglob("*.tf")):
        # Skip provider cache and lock files
        if ".terraform" in tf_file.parts:
            continue
        if tf_file.stat().st_size > 5 * 1024 * 1024:
            logger.warning("Skipping oversized .tf file: %s", tf_file)
            continue
        results.extend(_parse_file(tf_file))

    logger.info(
        "Terraform parser: found %d resources in %s", len(results), root
    )
    return results
