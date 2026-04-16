"""
iac_security/sarif_exporter.py
================================

Export IaC scan findings as SARIF 2.1.0 for ingestion by:
  - GitHub Advanced Security (Code Scanning)
  - DefectDojo
  - SonarQube
  - Any SARIF-compatible CI/CD tool

Spec: https://docs.oasis-open.org/sarif/sarif/v2.1.0/

Key design decisions:
  - Each policy check becomes a 'rule' in the tool.driver
  - Compliance refs are emitted as rule.properties.tags
  - Each Finding becomes a 'result' in the run
  - Severity is mapped: CRITICAL/HIGH -> error, MEDIUM -> warning, LOW/INFO -> note
  - physicalLocation is populated when source_file/source_line is available
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from iac_security.policies import ALL_POLICIES


# ---------------------------------------------------------------------------
# SARIF severity mapping
# ---------------------------------------------------------------------------

_SARIF_LEVEL: dict[str, str] = {
    "CRITICAL": "error",
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
    "INFO": "note",
}

_SARIF_SECURITY_SEVERITY: dict[str, str] = {
    "CRITICAL": "9.5",
    "HIGH": "7.5",
    "MEDIUM": "5.0",
    "LOW": "2.0",
    "INFO": "0.0",
}


# ---------------------------------------------------------------------------
# Rule builder
# ---------------------------------------------------------------------------


def _build_rules() -> list[dict[str, Any]]:
    """Build SARIF tool.driver.rules from the policy registry."""
    rules: list[dict[str, Any]] = []
    for policy in ALL_POLICIES:
        rule: dict[str, Any] = {
            "id": policy.id,
            "name": policy.title.replace(" ", ""),
            "shortDescription": {
                "text": policy.title,
            },
            "fullDescription": {
                "text": policy.description,
            },
            "helpUri": f"https://github.com/HunterSpence/enterprise-ai-accelerator/blob/main/iac_security/policies.py#{policy.id}",
            "help": {
                "text": policy.description,
                "markdown": f"**{policy.title}**\n\n{policy.description}\n\n**Compliance:** {', '.join(policy.compliance_refs)}",
            },
            "defaultConfiguration": {
                "level": _SARIF_LEVEL.get(policy.severity, "warning"),
            },
            "properties": {
                "tags": list(policy.compliance_refs),
                "security-severity": _SARIF_SECURITY_SEVERITY.get(policy.severity, "5.0"),
                "iac_severity": policy.severity,
            },
        }
        rules.append(rule)
    return rules


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------


def _build_result(finding: Any, scan_root: str) -> dict[str, Any]:
    """Convert a single Finding to a SARIF result object."""
    level = _SARIF_LEVEL.get(finding.severity, "warning")

    result: dict[str, Any] = {
        "ruleId": finding.policy_id,
        "level": level,
        "message": {
            "text": f"{finding.detail} — {finding.description}",
        },
        "fingerprints": {
            # Stable fingerprint: policy_id + resource address
            "primaryLocationLineHash/v1": f"{finding.policy_id}:{finding.resource_address}",
        },
        "properties": {
            "severity": finding.severity,
            "compliance_refs": finding.compliance_refs,
            "resource_address": finding.resource_address,
        },
    }

    # Physical location (file + line)
    if finding.resource_file:
        # Make path relative to scan root for portability
        try:
            rel_path = str(
                Path(finding.resource_file).relative_to(Path(scan_root))
            ).replace("\\", "/")
        except ValueError:
            rel_path = finding.resource_file.replace("\\", "/")

        location: dict[str, Any] = {
            "physicalLocation": {
                "artifactLocation": {
                    "uri": rel_path,
                    "uriBaseId": "%SRCROOT%",
                },
            }
        }
        if finding.resource_line and finding.resource_line > 0:
            location["physicalLocation"]["region"] = {
                "startLine": finding.resource_line,
            }

        # Logical location (resource address)
        location["logicalLocations"] = [
            {
                "name": finding.resource_address,
                "kind": "resource",
            }
        ]
        result["locations"] = [location]

    # AI remediation as a fix suggestion
    if getattr(finding, "remediation_ai", ""):
        result["fixes"] = [
            {
                "description": {
                    "text": finding.remediation_ai,
                }
            }
        ]

    return result


# ---------------------------------------------------------------------------
# Public exporter
# ---------------------------------------------------------------------------


def export_sarif(report: Any, indent: int = 2) -> str:
    """
    Convert a ScanReport to a SARIF 2.1.0 JSON string.

    Args:
        report: iac_security.scanner.ScanReport instance
        indent: JSON indentation level

    Returns:
        SARIF JSON string ready for writing to a file or uploading to GHAS.
    """
    sarif: dict[str, Any] = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "enterprise-ai-accelerator/iac_security",
                        "version": "0.1.0",
                        "informationUri": "https://github.com/HunterSpence/enterprise-ai-accelerator",
                        "rules": _build_rules(),
                        "properties": {
                            "tags": [
                                "security",
                                "iac",
                                "terraform",
                                "pulumi",
                                "cloud",
                            ]
                        },
                    }
                },
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "commandLine": f"iac_security scan {report.scan_path}",
                        "startTimeUtc": report.timestamp,
                    }
                ],
                "originalUriBaseIds": {
                    "%SRCROOT%": {
                        "uri": Path(report.scan_path).as_uri() + "/",
                    }
                },
                "results": [
                    _build_result(finding, report.scan_path)
                    for finding in report.findings
                ],
                "properties": {
                    "iac_type": report.iac_type,
                    "resource_count": report.resource_count,
                    "summary": {
                        "critical": report.critical_count,
                        "high": report.high_count,
                        "medium": report.medium_count,
                        "low_info": report.low_count,
                    },
                },
            }
        ],
    }

    return json.dumps(sarif, indent=indent)


def export_sarif_to_file(report: Any, output_path: Path) -> Path:
    """
    Write SARIF output to a file.  Returns the written path.

    Typical usage (GitHub Actions)::

        export_sarif_to_file(report, Path("results.sarif"))
        # Then: github/codeql-action/upload-sarif@v3 with sarif_file: results.sarif
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sarif_str = export_sarif(report)
    output_path.write_text(sarif_str, encoding="utf-8")
    return output_path


class SARIFExporter:
    """
    Class-based wrapper for import convenience.

    Usage::

        from iac_security.sarif_exporter import SARIFExporter
        exporter = SARIFExporter()
        exporter.export(report, Path("scan.sarif"))
    """

    def export(self, report: Any, output_path: Optional[Path] = None) -> str:
        """Return SARIF as string; optionally write to file."""
        sarif_str = export_sarif(report)
        if output_path:
            export_sarif_to_file(report, output_path)
        return sarif_str
