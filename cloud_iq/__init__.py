"""
CloudIQ — AI-powered cloud infrastructure intelligence.

Discovers AWS infrastructure, identifies cost waste, detects configuration drift,
generates production-quality Terraform, and answers questions in natural language.
"""

from cloud_iq.scanner import InfrastructureScanner, InfrastructureSnapshot
from cloud_iq.cost_analyzer import CostAnalyzer, CostReport, WasteItem
from cloud_iq.terraform_generator import TerraformGenerator
from cloud_iq.nl_query import NLQueryEngine
from cloud_iq.dashboard import Dashboard

__version__ = "1.0.0"
__author__ = "CloudIQ"

__all__ = [
    "InfrastructureScanner",
    "InfrastructureSnapshot",
    "CostAnalyzer",
    "CostReport",
    "WasteItem",
    "TerraformGenerator",
    "NLQueryEngine",
    "Dashboard",
]
