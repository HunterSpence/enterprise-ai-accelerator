"""
core — Shared Anthropic client layer for Enterprise AI Accelerator
==================================================================

Centralizes:
- Model selection (Opus 4.7 coordinator, Sonnet 4.6 reporter, Haiku 4.5 worker)
- Prompt caching (5-minute ephemeral cache on heavy system prompts)
- Extended thinking budgets for high-stakes classifiers
- Structured output via native tool use (replaces fragile JSON regex)
- Citations + Files API helpers for compliance evidence
- Batch API helper for bulk scoring workloads

Every module imports from here so model IDs, caching, and thinking budgets
are governed in one place.
"""

from core.models import (
    MODEL_COORDINATOR,
    MODEL_REPORTER,
    MODEL_WORKER,
    MODEL_OPUS_4_7,
    MODEL_SONNET_4_6,
    MODEL_HAIKU_4_5,
    THINKING_BUDGET_STANDARD,
    THINKING_BUDGET_HIGH,
    THINKING_BUDGET_XHIGH,
)
from core.ai_client import (
    AIClient,
    StructuredResponse,
    ThinkingResponse,
    get_client,
)

__all__ = [
    "MODEL_COORDINATOR",
    "MODEL_REPORTER",
    "MODEL_WORKER",
    "MODEL_OPUS_4_7",
    "MODEL_SONNET_4_6",
    "MODEL_HAIKU_4_5",
    "THINKING_BUDGET_STANDARD",
    "THINKING_BUDGET_HIGH",
    "THINKING_BUDGET_XHIGH",
    "AIClient",
    "StructuredResponse",
    "ThinkingResponse",
    "get_client",
]
