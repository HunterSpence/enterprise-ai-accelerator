"""
iac_security/__init__.py
========================

Infrastructure-as-Code Security + SBOM + CVE scanning module for the
Enterprise AI Accelerator.

Public surface:
  - IaCScanner      — Terraform/Pulumi policy scanning with SARIF export
  - SBOMGenerator   — CycloneDX 1.5 SBOM generation for multi-ecosystem repos
  - CVEScanner      — OSV.dev-backed CVE lookup for detected dependencies
  - DriftDetector   — Declared IaC state vs. actual cloud state diff
"""

from __future__ import annotations

from iac_security.scanner import IaCScanner, ScanReport, Finding
from iac_security.sbom_generator import SBOMGenerator
from iac_security.osv_scanner import CVEScanner, Vulnerability
from iac_security.drift_detector import DriftDetector, DriftReport

__all__ = [
    "IaCScanner",
    "ScanReport",
    "Finding",
    "SBOMGenerator",
    "CVEScanner",
    "Vulnerability",
    "DriftDetector",
    "DriftReport",
]

__version__ = "0.1.0"
