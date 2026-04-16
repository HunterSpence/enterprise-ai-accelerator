"""
core/models.py
==============

Canonical model IDs and thinking budgets for the Enterprise AI Accelerator.

Rules of the road:
  - Opus 4.7 is the coordinator / high-stakes classifier / executive chat model
  - Sonnet 4.6 is the report writer / medium-stakes summarizer
  - Haiku 4.5 is the high-volume worker (bulk scans, anomaly explanations)

Every module imports the constants from here. If Anthropic ships a new
generation, bumping two lines in this file upgrades the whole platform.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical model IDs (as of 2026-04-16)
# ---------------------------------------------------------------------------

MODEL_OPUS_4_7: str = "claude-opus-4-7"
MODEL_SONNET_4_6: str = "claude-sonnet-4-6"
MODEL_HAIKU_4_5: str = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Role aliases — what the platform uses semantically
# ---------------------------------------------------------------------------

MODEL_COORDINATOR: str = MODEL_OPUS_4_7
MODEL_REPORTER: str = MODEL_SONNET_4_6
MODEL_WORKER: str = MODEL_HAIKU_4_5

# ---------------------------------------------------------------------------
# Extended thinking budgets (token counts allowed for interleaved reasoning)
#
# Standard:  enough for light reflection on simple classifications
# High:      sufficient for multi-step compliance reasoning
# XHigh:     "Opus 4.7 xhigh" — full audit-trail reasoning for high-risk AI
#            decisions covered by EU AI Act Annex III
# ---------------------------------------------------------------------------

THINKING_BUDGET_STANDARD: int = 4_000
THINKING_BUDGET_HIGH: int = 16_000
THINKING_BUDGET_XHIGH: int = 32_000

# ---------------------------------------------------------------------------
# Prompt caching TTLs (Anthropic ephemeral cache supports 5m default, 1h beta)
# ---------------------------------------------------------------------------

CACHE_TTL_5M: str = "ephemeral"   # default — ~5 min TTL
CACHE_TTL_1H: str = "1h"          # beta — 1 hour TTL (enable via cache_control)

# ---------------------------------------------------------------------------
# Context window sizes (reference values for callers sizing payloads)
# ---------------------------------------------------------------------------

CTX_WINDOW_OPUS_4_7: int = 1_000_000
CTX_WINDOW_SONNET_4_6: int = 200_000
CTX_WINDOW_HAIKU_4_5: int = 200_000


def describe_model(model_id: str) -> dict[str, object]:
    """Return capability metadata for a given model ID.

    Used by the MCP server and dashboards to surface 'which model handled
    this call and what can it do' without hardcoding capability strings.
    """
    if model_id == MODEL_OPUS_4_7:
        return {
            "model": MODEL_OPUS_4_7,
            "family": "opus",
            "context_window": CTX_WINDOW_OPUS_4_7,
            "supports_extended_thinking": True,
            "supports_citations": True,
            "supports_files": True,
            "supports_batch": True,
            "role": "coordinator",
        }
    if model_id == MODEL_SONNET_4_6:
        return {
            "model": MODEL_SONNET_4_6,
            "family": "sonnet",
            "context_window": CTX_WINDOW_SONNET_4_6,
            "supports_extended_thinking": True,
            "supports_citations": True,
            "supports_files": True,
            "supports_batch": True,
            "role": "reporter",
        }
    if model_id == MODEL_HAIKU_4_5:
        return {
            "model": MODEL_HAIKU_4_5,
            "family": "haiku",
            "context_window": CTX_WINDOW_HAIKU_4_5,
            "supports_extended_thinking": False,
            "supports_citations": True,
            "supports_files": True,
            "supports_batch": True,
            "role": "worker",
        }
    return {
        "model": model_id,
        "family": "unknown",
        "context_window": 0,
        "supports_extended_thinking": False,
        "supports_citations": False,
        "supports_files": False,
        "supports_batch": False,
        "role": "unknown",
    }
