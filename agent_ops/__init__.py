"""
agent_ops — Multi-agent Claude orchestration for enterprise IT analysis.

Demonstrates parallel agent coordination using Claude Opus (coordinator)
and Claude Haiku (specialized sub-agents) via the Anthropic SDK.
"""

from agent_ops.agents import (
    ArchitectureAgent,
    ComplianceAgent,
    MigrationAgent,
    ReportAgent,
)
from agent_ops.dashboard import Dashboard
from agent_ops.orchestrator import AgentActivity, Orchestrator, PipelineResult

__all__ = [
    "Orchestrator",
    "PipelineResult",
    "AgentActivity",
    "ArchitectureAgent",
    "MigrationAgent",
    "ComplianceAgent",
    "ReportAgent",
    "Dashboard",
]

__version__ = "1.0.0"
