"""
iac_security/scanner.py
========================

IaCScanner — top-level entry point for infrastructure-as-code security scanning.

Detects whether a path contains Terraform or Pulumi (or both), runs the
appropriate parser, evaluates all 20 built-in policies, and optionally
generates AI-powered remediation summaries using claude-haiku-4-5 for cost
efficiency.

Output is a ScanReport containing:
  - list[Finding]  — policy violations with severity + compliance refs
  - summary stats  — counts by severity
  - scan_path, timestamp, resource_count

The ScanReport can be serialised to JSON or exported to SARIF via
sarif_exporter.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from iac_security.policies import CheckResult, run_all_policies

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """A single policy violation found during an IaC scan."""

    policy_id: str
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW | INFO
    title: str
    description: str
    compliance_refs: list[str]
    resource_address: str
    resource_file: str
    resource_line: int
    detail: str
    remediation_ai: str = ""  # populated if AI remediation is enabled

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "compliance_refs": self.compliance_refs,
            "resource": {
                "address": self.resource_address,
                "file": self.resource_file,
                "line": self.resource_line,
            },
            "detail": self.detail,
            "remediation_ai": self.remediation_ai,
        }


@dataclass
class ScanReport:
    """Aggregated results from a single IaCScanner.scan() call."""

    scan_path: str
    iac_type: str  # "terraform" | "pulumi" | "mixed" | "unknown"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    resource_count: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "CRITICAL")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "HIGH")

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "MEDIUM")

    @property
    def low_count(self) -> int:
        return sum(1 for f in self.findings if f.severity in {"LOW", "INFO"})

    @property
    def passed(self) -> bool:
        return self.critical_count == 0 and self.high_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_path": self.scan_path,
            "iac_type": self.iac_type,
            "timestamp": self.timestamp,
            "resource_count": self.resource_count,
            "summary": {
                "total_findings": len(self.findings),
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "low_info": self.low_count,
                "passed": self.passed,
            },
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append(f"# IaC Security Scan Report")
        lines.append(f"")
        lines.append(f"**Path:** `{self.scan_path}`  ")
        lines.append(f"**Type:** {self.iac_type}  ")
        lines.append(f"**Scanned:** {self.timestamp}  ")
        lines.append(f"**Resources:** {self.resource_count}  ")
        lines.append(f"")
        lines.append(f"## Summary")
        lines.append(f"")
        lines.append(f"| Severity | Count |")
        lines.append(f"|----------|-------|")
        lines.append(f"| CRITICAL | {self.critical_count} |")
        lines.append(f"| HIGH     | {self.high_count} |")
        lines.append(f"| MEDIUM   | {self.medium_count} |")
        lines.append(f"| LOW/INFO | {self.low_count} |")
        lines.append(f"")
        if not self.findings:
            lines.append(f"No findings. All checks passed.")
            return "\n".join(lines)
        lines.append(f"## Findings")
        lines.append(f"")
        for f in sorted(
            self.findings,
            key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}.get(
                x.severity, 5
            ),
        ):
            lines.append(f"### [{f.severity}] {f.policy_id} — {f.title}")
            lines.append(f"")
            lines.append(f"**Resource:** `{f.resource_address}`  ")
            if f.resource_file:
                loc = f"{f.resource_file}"
                if f.resource_line:
                    loc += f":{f.resource_line}"
                lines.append(f"**Location:** `{loc}`  ")
            lines.append(f"**Detail:** {f.detail}  ")
            lines.append(f"**Compliance:** {', '.join(f.compliance_refs)}  ")
            lines.append(f"**Fix:** {f.description}  ")
            if f.remediation_ai:
                lines.append(f"")
                lines.append(f"**AI Remediation:**")
                lines.append(f"> {f.remediation_ai}")
            lines.append(f"")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# IaC type detection
# ---------------------------------------------------------------------------


def _detect_iac_type(path: Path) -> str:
    """
    Determine what IaC flavour is present under *path*.
    Returns 'terraform', 'pulumi', 'mixed', or 'unknown'.
    """
    has_tf = bool(list(path.rglob("*.tf"))) if path.is_dir() else path.suffix == ".tf"
    has_pulumi = False
    if path.is_dir():
        has_pulumi = (
            bool(list(path.rglob("Pulumi.yaml")))
            or bool(list(path.rglob("Pulumi.yml")))
            or (path / ".pulumi" / "stacks").is_dir()
        )
    elif path.suffix in {".yaml", ".yml"} and "Pulumi" in path.name:
        has_pulumi = True
    elif path.suffix == ".json" and ".pulumi" in str(path):
        has_pulumi = True

    if has_tf and has_pulumi:
        return "mixed"
    if has_tf:
        return "terraform"
    if has_pulumi:
        return "pulumi"
    return "unknown"


# ---------------------------------------------------------------------------
# AI remediation helper
# ---------------------------------------------------------------------------


async def _generate_remediation(
    finding: Finding,
    ai_client: Any,
    model: str,
) -> str:
    """
    Call claude-haiku-4-5 to generate a concise one-paragraph remediation
    for a single finding.  Returns empty string on any error.
    """
    try:
        prompt = (
            f"You are a cloud security engineer. Provide a concise, actionable "
            f"one-paragraph remediation for the following Terraform/IaC finding.\n\n"
            f"Policy: {finding.policy_id} — {finding.title}\n"
            f"Resource: {finding.resource_address}\n"
            f"Issue: {finding.detail}\n"
            f"Compliance: {', '.join(finding.compliance_refs)}\n\n"
            f"Respond with only the remediation paragraph. No headers, no lists."
        )
        resp = await ai_client.complete(
            model=model,
            prompt=prompt,
            max_tokens=300,
        )
        return resp.strip()
    except Exception as exc:
        logger.debug("AI remediation failed for %s: %s", finding.policy_id, exc)
        return ""


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class IaCScanner:
    """
    Top-level IaC security scanner.

    Usage::

        from iac_security import IaCScanner
        report = IaCScanner().scan(Path("./terraform"))
        print(report.to_dict())

    With AI remediation::

        from core.ai_client import AIClient
        ai = AIClient()
        report = IaCScanner(ai_client=ai, ai_remediation=True).scan(Path("./terraform"))
    """

    def __init__(
        self,
        ai_client: Any = None,
        ai_remediation: bool = False,
        ai_model: Optional[str] = None,
    ) -> None:
        self.ai_client = ai_client
        self.ai_remediation = ai_remediation and ai_client is not None
        # Default to Haiku for cost; caller can override
        self.ai_model = ai_model or os.environ.get(
            "IAC_REMEDIATION_MODEL", "claude-haiku-4-5-20251001"
        )

    def scan(self, path: Path) -> ScanReport:
        """
        Synchronous entry point.  Internally runs async logic via asyncio.run()
        so callers that are not already in an event loop can use it directly.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We are inside an existing event loop (e.g. Jupyter, FastAPI test)
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(asyncio.run, self._scan_async(path))
                    return future.result()
            return loop.run_until_complete(self._scan_async(path))
        except RuntimeError:
            return asyncio.run(self._scan_async(path))

    async def _scan_async(self, path: Path) -> ScanReport:
        path = Path(path).resolve()
        iac_type = _detect_iac_type(path)

        report = ScanReport(
            scan_path=str(path),
            iac_type=iac_type,
        )

        resources: list[Any] = []

        if iac_type in {"terraform", "mixed"}:
            from iac_security.terraform_parser import parse_terraform
            resources.extend(parse_terraform(path))

        if iac_type in {"pulumi", "mixed"}:
            from iac_security.pulumi_parser import parse_pulumi
            resources.extend(parse_pulumi(path))

        if iac_type == "unknown":
            logger.warning("No Terraform or Pulumi files found in %s", path)

        report.resource_count = len(resources)

        # Run policies
        raw_findings: list[CheckResult] = []
        for resource in resources:
            if resource.kind not in {"resource", "data"}:
                continue  # Skip modules, variables, outputs for policy checks
            raw_findings.extend(run_all_policies(resource))

        # Convert to Finding objects
        findings: list[Finding] = []
        for cr in raw_findings:
            # Retrieve file/line from the matching resource
            matched = next(
                (r for r in resources if r.address == cr.resource_address), None
            )
            findings.append(
                Finding(
                    policy_id=cr.policy_id,
                    severity=cr.severity,
                    title=cr.title,
                    description=cr.description,
                    compliance_refs=cr.compliance_refs,
                    resource_address=cr.resource_address,
                    resource_file=matched.source_file if matched else "",
                    resource_line=matched.source_line if matched else 0,
                    detail=cr.detail,
                )
            )

        # Optionally generate AI remediations (Haiku, parallel)
        if self.ai_remediation and findings:
            ai_tasks = [
                _generate_remediation(f, self.ai_client, self.ai_model)
                for f in findings
            ]
            remediations = await asyncio.gather(*ai_tasks, return_exceptions=True)
            for finding, rem in zip(findings, remediations):
                if isinstance(rem, str):
                    finding.remediation_ai = rem

        report.findings = findings
        logger.info(
            "IaCScanner: %d resources, %d findings (%d CRITICAL, %d HIGH)",
            report.resource_count,
            len(findings),
            report.critical_count,
            report.high_count,
        )
        return report
