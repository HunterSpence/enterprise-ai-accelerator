"""
PolicyGuard — AI Compliance and Governance Scanner
===================================================
The only open-source tool combining EU AI Act + NIST AI RMF + CIS AWS +
SOC 2 + HIPAA in a single platform. Automates the compliance scanning that
EY, Deloitte, and KPMG charge $100K–$2M for.

Quick start:
    python -m policy_guard.demo
"""

from policy_guard.scanner import ComplianceScanner, ComplianceReport, ScanConfig
from policy_guard.reporter import ReportGenerator

__all__ = [
    "ComplianceScanner",
    "ComplianceReport",
    "ScanConfig",
    "ReportGenerator",
]

__version__ = "1.0.0"
__author__ = "Hunter Spence"
