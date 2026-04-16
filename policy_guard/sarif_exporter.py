"""
PolicyGuard — SARIF 2.1.0 Exporter
=====================================
Exports compliance findings to Static Analysis Results Interchange Format (SARIF) 2.1.0.

SARIF is the industry-standard output format consumed by:
  - GitHub Security tab (zero-friction upload via code-scanning/upload-sarif action)
  - VS Code Problems panel (via SARIF Viewer extension)
  - Azure DevOps Security (native SARIF import)
  - SonarQube, Snyk, Semgrep, Veracode, Checkmarx — all accept SARIF
  - Any CI pipeline via the ocsf/sarif schema

This is the single highest-leverage output format addition: one file enables
every security toolchain that teams already use, with zero additional work.

Usage:
    from policy_guard.sarif_exporter import SARIFExporter
    from policy_guard.scanner import ComplianceReport

    exporter = SARIFExporter(report)
    path = exporter.export("./output/")            # → policyguard_YYYYMMDD.sarif
    sarif_dict = exporter.to_dict()                # → dict for API responses
    sarif_json = exporter.to_json()                # → str for embedding in pipelines

GitHub Actions integration (add to your workflow):
    - name: Upload PolicyGuard SARIF
      uses: github/codeql-action/upload-sarif@v3
      with:
        sarif_file: policyguard_findings.sarif
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# SARIF 2.1.0 schema URI — required by spec
_SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
_SARIF_VERSION = "2.1.0"

# PolicyGuard tool metadata
_TOOL_NAME = "PolicyGuard"
_TOOL_VERSION = "2.0.0"
_TOOL_URI = "https://github.com/HunterSpence/enterprise-ai-accelerator"
_TOOL_DESCRIPTION = (
    "Enterprise AI Governance and Cloud Compliance Platform. "
    "Scans IaC and AI system configurations against EU AI Act, NIST AI RMF, "
    "CIS AWS Foundations, SOC 2, and HIPAA frameworks."
)

# Map PolicyGuard severity → SARIF level
# SARIF levels: none | note | warning | error
_SEVERITY_TO_SARIF_LEVEL: dict[str, str] = {
    "CRITICAL": "error",
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
    "INFO": "none",
}

# Map PolicyGuard severity → SARIF security-severity score (CVSS-like, 0.0–10.0)
# Required by GitHub Advanced Security for triage filtering
_SEVERITY_TO_SECURITY_SCORE: dict[str, float] = {
    "CRITICAL": 9.5,
    "HIGH": 7.5,
    "MEDIUM": 5.0,
    "LOW": 2.5,
    "INFO": 0.0,
}

# Map framework name → CWE/taxonomy tags for richer tool integration
_FRAMEWORK_TAGS: dict[str, list[str]] = {
    "cis_aws": ["security", "cloud", "aws", "cis-benchmark"],
    "eu_ai_act": ["compliance", "ai-governance", "eu-ai-act", "article-12"],
    "nist_ai_rmf": ["compliance", "ai-risk", "nist-ai-rmf"],
    "soc2": ["compliance", "soc2", "trust-service-criteria"],
    "hipaa": ["compliance", "hipaa", "phi-protection"],
}


@dataclass
class SARIFRule:
    """Represents a SARIF rule (one PolicyGuard check)."""
    rule_id: str
    name: str
    short_description: str
    full_description: str
    help_text: str
    severity: str
    framework: str
    tags: list[str] = field(default_factory=list)
    help_uri: str = ""

    def to_sarif(self) -> dict[str, Any]:
        level = _SEVERITY_TO_SARIF_LEVEL.get(self.severity, "warning")
        security_score = _SEVERITY_TO_SECURITY_SCORE.get(self.severity, 5.0)

        rule: dict[str, Any] = {
            "id": self.rule_id,
            "name": self.name,
            "shortDescription": {
                "text": self.short_description[:200],  # SARIF spec recommends < 200 chars
            },
            "fullDescription": {
                "text": self.full_description,
            },
            "help": {
                "text": self.help_text,
                "markdown": f"**{self.short_description}**\n\n{self.help_text}",
            },
            "defaultConfiguration": {
                "level": level,
            },
            "properties": {
                "tags": self.tags or _FRAMEWORK_TAGS.get(self.framework, ["compliance"]),
                "security-severity": str(security_score),
                "policyguard-framework": self.framework,
                "policyguard-severity": self.severity,
            },
        }
        if self.help_uri:
            rule["helpUri"] = self.help_uri
        return rule


@dataclass
class SARIFResult:
    """Represents a single SARIF finding result."""
    rule_id: str
    message: str
    level: str
    resource: str
    framework: str
    severity: str
    remediation: str
    # Optional location info — for IaC scanning, this is the file:line
    artifact_uri: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    # For suppression
    suppressed: bool = False
    suppression_justification: str = ""

    def to_sarif(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ruleId": self.rule_id,
            "level": self.level,
            "message": {
                "text": self.message,
            },
            "properties": {
                "policyguard-resource": self.resource,
                "policyguard-framework": self.framework,
                "policyguard-severity": self.severity,
                "remediation": self.remediation[:500] if self.remediation else "",
            },
        }

        # Add location if we have file info
        if self.artifact_uri:
            location: dict[str, Any] = {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": self.artifact_uri,
                        "uriBaseId": "%SRCROOT%",
                    },
                },
            }
            if self.start_line:
                location["physicalLocation"]["region"] = {
                    "startLine": self.start_line,
                }
                if self.end_line and self.end_line != self.start_line:
                    location["physicalLocation"]["region"]["endLine"] = self.end_line
            result["locations"] = [location]
        else:
            # SARIF requires at least one location, even if synthetic
            result["locations"] = [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": f"cloud://{self.resource or 'unknown'}",
                            "uriBaseId": "%SRCROOT%",
                        },
                    },
                }
            ]

        # Add suppression info if applicable
        if self.suppressed:
            result["suppressions"] = [
                {
                    "kind": "inSource",
                    "justification": self.suppression_justification or "Manually suppressed",
                }
            ]

        return result


class SARIFExporter:
    """
    Converts a PolicyGuard ComplianceReport to SARIF 2.1.0 format.

    SARIF structure:
      SarifLog
        └── runs[]
              ├── tool (PolicyGuard metadata + rules)
              └── results[] (one per FAIL finding)

    Only FAIL findings are exported — PASS findings have no security value
    in the SARIF model and inflate result counts in GitHub Security.

    Example:
        exporter = SARIFExporter(report)
        sarif_path = exporter.export("./policyguard_reports/")
        print(f"Upload to GitHub: {sarif_path}")
    """

    def __init__(self, report: Any) -> None:
        """
        Args:
            report: PolicyGuard ComplianceReport (from scanner.py).
                    Accepts any object with framework_scores and framework-specific
                    report attributes (cis_aws, eu_ai_act, etc.).
        """
        self.report = report
        self._rules: dict[str, SARIFRule] = {}
        self._results: list[SARIFResult] = []
        self._built = False

    def _build(self) -> None:
        """Extract all FAIL findings into SARIF rules + results."""
        if self._built:
            return

        framework_configs = [
            ("cis_aws",       "CIS AWS Foundations",   "cis_aws",       "control_id"),
            ("eu_ai_act",     "EU AI Act",              "eu_ai_act",     "control_id"),
            ("nist_ai_rmf",   "NIST AI RMF",            "nist_ai_rmf",   "subcategory"),
            ("soc2",          "SOC 2",                  "soc2",          "control_id"),
            ("hipaa",         "HIPAA",                  "hipaa",         "control_id"),
        ]

        for fw_attr, fw_label, fw_key, id_field in framework_configs:
            fw_report = getattr(self.report, fw_attr, None)
            if fw_report is None:
                continue

            findings = getattr(fw_report, "findings", [])
            for finding in findings:
                if not hasattr(finding, "status") or finding.status != "FAIL":
                    continue

                # Build a stable rule ID: PG-{FRAMEWORK}-{CONTROL_ID}
                raw_id = getattr(finding, id_field, None) or getattr(finding, "control_id", "UNKNOWN")
                # Sanitize for SARIF rule IDs (no spaces, dots OK)
                safe_id = str(raw_id).replace(" ", "_").replace("/", "_")
                rule_id = f"PG-{fw_key.upper()}-{safe_id}"

                severity = getattr(finding, "severity", "MEDIUM")
                title = getattr(finding, "title", raw_id)
                details = getattr(finding, "details", "")
                remediation = getattr(finding, "remediation", "")
                resource = getattr(finding, "resource", "")

                # Register rule (deduped by rule_id)
                if rule_id not in self._rules:
                    tags = _FRAMEWORK_TAGS.get(fw_key, ["compliance"])
                    # Add EU AI Act article reference if available
                    article = getattr(finding, "article", None)
                    if article:
                        tags = tags + [f"article-{article}"]

                    self._rules[rule_id] = SARIFRule(
                        rule_id=rule_id,
                        name=f"{fw_label}: {title}"[:64],
                        short_description=title,
                        full_description=details or title,
                        help_text=remediation or f"Review {fw_label} requirements for {title}.",
                        severity=severity,
                        framework=fw_key,
                        tags=tags,
                        help_uri=(
                            "https://github.com/HunterSpence/enterprise-ai-accelerator"
                            f"/blob/main/portfolio_modules/policy_guard/README.md#{fw_key}"
                        ),
                    )

                level = _SEVERITY_TO_SARIF_LEVEL.get(severity, "warning")

                # Build message with finding details
                msg_parts = [title]
                if details:
                    msg_parts.append(details[:300])
                if resource:
                    msg_parts.append(f"Resource: {resource}")
                message = " | ".join(p for p in msg_parts if p)

                # Check for artifact location (IaC findings have file paths)
                artifact_uri = getattr(finding, "artifact_uri", None)
                start_line = getattr(finding, "start_line", None)
                end_line = getattr(finding, "end_line", None)

                self._results.append(
                    SARIFResult(
                        rule_id=rule_id,
                        message=message,
                        level=level,
                        resource=resource,
                        framework=fw_key,
                        severity=severity,
                        remediation=remediation,
                        artifact_uri=artifact_uri,
                        start_line=start_line,
                        end_line=end_line,
                    )
                )

        self._built = True

    def to_dict(self) -> dict[str, Any]:
        """Return the full SARIF 2.1.0 document as a Python dict."""
        self._build()

        # Build rules list (sorted by severity for readability)
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        sorted_rules = sorted(
            self._rules.values(),
            key=lambda r: severity_order.get(r.severity, 5),
        )

        # Tool component with all rules
        tool_component: dict[str, Any] = {
            "name": _TOOL_NAME,
            "version": _TOOL_VERSION,
            "informationUri": _TOOL_URI,
            "fullDescription": {"text": _TOOL_DESCRIPTION},
            "rules": [r.to_sarif() for r in sorted_rules],
        }

        # Build results list
        results = [r.to_sarif() for r in self._results]

        # Compute summary properties
        critical_count = sum(1 for r in self._results if r.severity == "CRITICAL")
        high_count = sum(1 for r in self._results if r.severity == "HIGH")
        medium_count = sum(1 for r in self._results if r.severity == "MEDIUM")
        low_count = sum(1 for r in self._results if r.severity == "LOW")

        # SARIF run
        run: dict[str, Any] = {
            "tool": {
                "driver": tool_component,
            },
            "results": results,
            "properties": {
                "policyguard-scan-id": getattr(self.report, "scan_id", ""),
                "policyguard-overall-score": getattr(self.report, "overall_score", 0),
                "policyguard-risk-rating": getattr(self.report, "risk_rating", "Unknown"),
                "policyguard-total-findings": len(results),
                "policyguard-critical": critical_count,
                "policyguard-high": high_count,
                "policyguard-medium": medium_count,
                "policyguard-low": low_count,
                "policyguard-scan-timestamp": (
                    getattr(self.report, "timestamp", datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if hasattr(self.report, "timestamp") else
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                ),
            },
            # Artifact notation for tools that show file origin
            "versionControlProvenance": [],
            # Schema-required: automation details
            "automationDetails": {
                "id": f"policyguard/{getattr(self.report, 'scan_id', 'unknown')}",
                "description": {
                    "text": (
                        f"PolicyGuard compliance scan. "
                        f"Frameworks: EU AI Act, NIST AI RMF, CIS AWS, SOC 2, HIPAA. "
                        f"Findings: {len(results)} violations "
                        f"({critical_count} Critical, {high_count} High)."
                    )
                },
            },
        }

        return {
            "$schema": _SARIF_SCHEMA,
            "version": _SARIF_VERSION,
            "runs": [run],
        }

    def to_json(self, indent: int = 2) -> str:
        """Return the SARIF document as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def export(self, output_dir: str = ".") -> str:
        """
        Write SARIF file to disk.

        Returns:
            Absolute path to the written .sarif file.

        Example GitHub Actions upload:
            - uses: github/codeql-action/upload-sarif@v3
              with:
                sarif_file: policyguard_findings.sarif
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        scan_id = getattr(self.report, "scan_id", "scan")
        filename = f"policyguard_{scan_id}_{timestamp}.sarif"
        output_path = os.path.join(output_dir, filename)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

        return output_path

    def summary(self) -> dict[str, Any]:
        """Return a compact summary of what was exported."""
        self._build()
        return {
            "total_findings_exported": len(self._results),
            "unique_rules": len(self._rules),
            "by_severity": {
                "CRITICAL": sum(1 for r in self._results if r.severity == "CRITICAL"),
                "HIGH": sum(1 for r in self._results if r.severity == "HIGH"),
                "MEDIUM": sum(1 for r in self._results if r.severity == "MEDIUM"),
                "LOW": sum(1 for r in self._results if r.severity == "LOW"),
            },
            "by_framework": {
                fw: sum(1 for r in self._results if r.framework == fw)
                for fw in ["cis_aws", "eu_ai_act", "nist_ai_rmf", "soc2", "hipaa"]
            },
            "github_upload_command": (
                "gh api /repos/{owner}/{repo}/code-scanning/sarifs "
                "--field sarif=@policyguard_findings.sarif "
                "--field ref=refs/heads/main "
                "--field commit_sha=$(git rev-parse HEAD)"
            ),
        }
