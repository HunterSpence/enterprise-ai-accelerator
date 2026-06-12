"""
core — Shared Anthropic client layer for Enterprise AI Accelerator
==================================================================

Centralizes:
- Model selection (Fable 5 coordinator, Sonnet 4.6 reporter, Haiku 4.5 worker)
- Adaptive thinking + effort levels (the June-2026 depth/cost control)
- Refusal handling with server-side fallback to Opus 4.8
- Prompt caching (5-minute ephemeral cache on heavy system prompts)
- Structured output via output_config.format (schema-guaranteed JSON)
- Citations + Files API helpers for compliance evidence
- Batch API helper for bulk scoring workloads

Every module imports from here so model IDs, caching, and effort levels
are governed in one place.
"""

from core.ai_client import (
    AIClient,
    RefusalError,
    StructuredResponse,
    ThinkingResponse,
    get_client,
)
from core.models import (
    DEFAULT_EFFORT,
    EFFORT_HIGH,
    EFFORT_LOW,
    EFFORT_MAX,
    EFFORT_MEDIUM,
    EFFORT_XHIGH,
    MODEL_COORDINATOR,
    MODEL_FABLE_5,
    MODEL_FALLBACK,
    MODEL_HAIKU_4_5,
    MODEL_OPUS_4_7,
    MODEL_OPUS_4_8,
    MODEL_REPORTER,
    MODEL_SONNET_4_6,
    MODEL_WORKER,
    THINKING_BUDGET_HIGH,
    THINKING_BUDGET_STANDARD,
    THINKING_BUDGET_XHIGH,
    effort_for_budget,
)

__all__ = [
    "MODEL_COORDINATOR",
    "MODEL_REPORTER",
    "MODEL_WORKER",
    "MODEL_FABLE_5",
    "MODEL_OPUS_4_8",
    "MODEL_OPUS_4_7",
    "MODEL_SONNET_4_6",
    "MODEL_HAIKU_4_5",
    "MODEL_FALLBACK",
    "EFFORT_LOW",
    "EFFORT_MEDIUM",
    "EFFORT_HIGH",
    "EFFORT_XHIGH",
    "EFFORT_MAX",
    "DEFAULT_EFFORT",
    "THINKING_BUDGET_STANDARD",
    "THINKING_BUDGET_HIGH",
    "THINKING_BUDGET_XHIGH",
    "effort_for_budget",
    "AIClient",
    "RefusalError",
    "StructuredResponse",
    "ThinkingResponse",
    "get_client",
]
