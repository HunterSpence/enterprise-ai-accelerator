"""
core/models.py
==============

Canonical model IDs, effort levels, and beta-feature flags for the
Enterprise AI Accelerator.

Rules of the road:
  - Fable 5 is the coordinator / high-stakes classifier / executive chat model
  - Sonnet 4.6 is the report writer / medium-stakes summarizer / long-context workhorse
  - Haiku 4.5 is the high-volume worker (bulk scans, anomaly explanations)
  - Opus 4.8 is the refusal-fallback model (Fable 5's safety classifiers can
    decline a request with ``stop_reason: "refusal"``; Opus 4.8 picks it up)

Thinking & effort (June 2026 API surface):
  Fable 5 has *always-on* adaptive thinking — the legacy
  ``thinking={"type": "enabled", "budget_tokens": N}`` shape returns a 400,
  and an explicit ``{"type": "disabled"}`` also returns a 400. Depth is
  controlled with ``output_config={"effort": ...}`` instead of token budgets.
  The EFFORT_* constants below are the platform-wide vocabulary for that.

Every module imports the constants from here. If Anthropic ships a new
generation, bumping two lines in this file upgrades the whole platform.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Canonical model IDs (as of 2026-06-12)
# ---------------------------------------------------------------------------

# Flagship: Claude Fable 5 — $10/MTok input, $50/MTok output (June 2026)
# Override via EAA_FLAGSHIP_MODEL env var.
MODEL_FABLE_5: str = os.environ.get("EAA_FLAGSHIP_MODEL", "claude-fable-5")
MODEL_OPUS_4_8: str = "claude-opus-4-8"
MODEL_SONNET_4_6: str = "claude-sonnet-4-6"
MODEL_HAIKU_4_5: str = "claude-haiku-4-5-20251001"

# Refusal fallback: Fable 5 requests can come back with stop_reason="refusal"
# (safety classifiers; HTTP 200, not an exception). The platform retries
# server-side on this model via the fallbacks beta. Override via env.
MODEL_FALLBACK: str = os.environ.get("EAA_FALLBACK_MODEL", MODEL_OPUS_4_8)

# Deprecated aliases — kept so importing modules continue to work unchanged.
# These resolve to Fable 5 (the current flagship tier).
MODEL_OPUS_4_7: str = MODEL_FABLE_5  # deprecated: was "claude-opus-4-7"

# ---------------------------------------------------------------------------
# Role aliases — what the platform uses semantically
# ---------------------------------------------------------------------------

MODEL_COORDINATOR: str = MODEL_FABLE_5
MODEL_REPORTER: str = MODEL_SONNET_4_6
MODEL_WORKER: str = MODEL_HAIKU_4_5

# ---------------------------------------------------------------------------
# Effort levels — output_config={"effort": ...}
#
# This replaced fixed thinking-token budgets across the Claude 4.6+ family.
# Supported on Fable 5, Opus 4.6+, and Sonnet 4.6 (errors on Haiku 4.5).
#
#   low     — short scoped tasks, latency-sensitive worker calls
#   medium  — cost-sensitive report generation
#   high    — default for intelligence-sensitive work (API default too)
#   xhigh   — agentic / audit-grade reasoning (Claude Code's default tier)
#   max     — correctness over cost; EU AI Act Annex III high-risk decisions
# ---------------------------------------------------------------------------

EFFORT_LOW: str = "low"
EFFORT_MEDIUM: str = "medium"
EFFORT_HIGH: str = "high"
EFFORT_XHIGH: str = "xhigh"
EFFORT_MAX: str = "max"

DEFAULT_EFFORT: str = EFFORT_HIGH

_EFFORT_LEVELS: tuple[str, ...] = (
    EFFORT_LOW, EFFORT_MEDIUM, EFFORT_HIGH, EFFORT_XHIGH, EFFORT_MAX,
)

# ---------------------------------------------------------------------------
# DEPRECATED — extended-thinking token budgets (pre-Fable era)
#
# ``budget_tokens`` is removed on Fable 5 / Opus 4.7+ (the API returns 400).
# These constants remain only so legacy call sites keep importing; the
# AIClient translates them to effort levels via effort_for_budget().
# ---------------------------------------------------------------------------

THINKING_BUDGET_STANDARD: int = 4_000   # deprecated → EFFORT_MEDIUM
THINKING_BUDGET_HIGH: int = 16_000      # deprecated → EFFORT_HIGH
THINKING_BUDGET_XHIGH: int = 32_000     # deprecated → EFFORT_XHIGH


def effort_for_budget(budget_tokens: int) -> str:
    """Map a legacy thinking-token budget onto the nearest effort level.

    Used by AIClient/streaming to keep deprecated ``budget_tokens`` call
    sites working: the budget number is discarded and replaced with the
    semantically closest ``output_config.effort`` value.
    """
    if budget_tokens <= 0:
        return DEFAULT_EFFORT
    if budget_tokens <= THINKING_BUDGET_STANDARD:
        return EFFORT_MEDIUM
    if budget_tokens <= THINKING_BUDGET_HIGH:
        return EFFORT_HIGH
    return EFFORT_XHIGH


def validate_effort(effort: str) -> str:
    """Validate an effort string, returning it unchanged or raising ValueError."""
    if effort not in _EFFORT_LEVELS:
        raise ValueError(
            f"Unknown effort level {effort!r} — expected one of {_EFFORT_LEVELS}"
        )
    return effort

# ---------------------------------------------------------------------------
# Beta feature headers (June 2026)
# ---------------------------------------------------------------------------

# Server-side refusal fallbacks: fallbacks=[{"model": ...}] on beta.messages.create.
# On a Fable 5 policy decline, the API re-runs the request on the fallback
# model in the same round trip. NOTE: the header carries the earliest date of
# the beta series — do not "correct" it to a newer-looking date.
BETA_SERVER_SIDE_FALLBACK: str = "server-side-fallback-2026-06-01"

# Task budgets: output_config.task_budget — the model sees a running token
# countdown for a whole agentic run and self-moderates (min 20,000 tokens).
BETA_TASK_BUDGETS: str = "task-budgets-2026-03-13"
TASK_BUDGET_MIN_TOKENS: int = 20_000

# Server-side compaction for long conversations (executive chat):
# context_management={"edits": [{"type": "compact_20260112"}]}.
BETA_COMPACTION: str = "compact-2026-01-12"
COMPACTION_EDIT_TYPE: str = "compact_20260112"

# ---------------------------------------------------------------------------
# Prompt caching TTLs (Anthropic ephemeral cache supports 5m default, 1h)
# ---------------------------------------------------------------------------

CACHE_TTL_5M: str = "ephemeral"   # default — ~5 min TTL
CACHE_TTL_1H: str = "1h"          # 1 hour TTL (2x write cost; for bursty traffic)

# ---------------------------------------------------------------------------
# Context window / output sizes (reference values for callers sizing payloads)
# ---------------------------------------------------------------------------

CTX_WINDOW_FABLE_5: int = 1_000_000
CTX_WINDOW_OPUS_4_8: int = 1_000_000
CTX_WINDOW_SONNET_4_6: int = 1_000_000   # 1M as of Sonnet 4.6 (was 200K on 4.5)
CTX_WINDOW_HAIKU_4_5: int = 200_000

MAX_OUTPUT_FABLE_5: int = 128_000        # streaming required above ~16K
MAX_OUTPUT_OPUS_4_8: int = 128_000
MAX_OUTPUT_SONNET_4_6: int = 64_000
MAX_OUTPUT_HAIKU_4_5: int = 64_000

# Deprecated alias kept for backward compatibility.
CTX_WINDOW_OPUS_4_7: int = CTX_WINDOW_FABLE_5

# Default max_tokens for non-streaming calls. Below ~16K keeps responses
# inside SDK HTTP timeouts; anything larger should stream.
DEFAULT_MAX_TOKENS: int = 16_000
# Default max_tokens for streaming calls (timeouts are not a concern there;
# BudgetGuard caps actual spend).
DEFAULT_MAX_TOKENS_STREAMING: int = 64_000


def describe_model(model_id: str) -> dict[str, object]:
    """Return capability metadata for a given model ID.

    Used by the MCP server and dashboards to surface 'which model handled
    this call and what can it do' without hardcoding capability strings.

    For *live* capability data (new models, changed limits), prefer the
    Models API: ``client.models.retrieve(model_id)`` — this table is the
    offline fallback.
    """
    if model_id in (MODEL_FABLE_5, MODEL_OPUS_4_8):
        family = "fable" if "fable" in model_id else "opus"
        return {
            "model": model_id,
            "family": family,
            "context_window": CTX_WINDOW_FABLE_5,
            "max_output_tokens": MAX_OUTPUT_FABLE_5,
            "supports_extended_thinking": True,   # adaptive only — no budget_tokens
            "supports_adaptive_thinking": True,
            "supports_effort": True,
            "always_on_thinking": family == "fable",  # Fable 5: thinking cannot be disabled
            "supports_structured_outputs": True,
            "supports_citations": True,
            "supports_files": True,
            "supports_batch": True,
            "can_refuse": family == "fable",  # safety classifiers → stop_reason "refusal"
            "role": "coordinator",
        }
    if model_id == MODEL_SONNET_4_6:
        return {
            "model": MODEL_SONNET_4_6,
            "family": "sonnet",
            "context_window": CTX_WINDOW_SONNET_4_6,
            "max_output_tokens": MAX_OUTPUT_SONNET_4_6,
            "supports_extended_thinking": True,
            "supports_adaptive_thinking": True,
            "supports_effort": True,
            "always_on_thinking": False,
            "supports_structured_outputs": True,
            "supports_citations": True,
            "supports_files": True,
            "supports_batch": True,
            "can_refuse": False,
            "role": "reporter",
        }
    if model_id == MODEL_HAIKU_4_5:
        return {
            "model": MODEL_HAIKU_4_5,
            "family": "haiku",
            "context_window": CTX_WINDOW_HAIKU_4_5,
            "max_output_tokens": MAX_OUTPUT_HAIKU_4_5,
            "supports_extended_thinking": True,   # budget-style thinking only
            "supports_adaptive_thinking": False,
            "supports_effort": False,             # effort param errors on Haiku 4.5
            "always_on_thinking": False,
            "supports_structured_outputs": True,
            "supports_citations": True,
            "supports_files": True,
            "supports_batch": True,
            "can_refuse": False,
            "role": "worker",
        }
    return {
        "model": model_id,
        "family": "unknown",
        "context_window": 0,
        "max_output_tokens": 0,
        "supports_extended_thinking": False,
        "supports_adaptive_thinking": False,
        "supports_effort": False,
        "always_on_thinking": False,
        "supports_structured_outputs": False,
        "supports_citations": False,
        "supports_files": False,
        "supports_batch": False,
        "can_refuse": False,
        "role": "unknown",
    }


def supports_effort(model_id: str) -> bool:
    """True when the model accepts ``output_config={"effort": ...}``."""
    return bool(describe_model(model_id).get("supports_effort"))


def supports_adaptive_thinking(model_id: str) -> bool:
    """True when the model accepts ``thinking={"type": "adaptive"}``."""
    return bool(describe_model(model_id).get("supports_adaptive_thinking"))


def is_fable(model_id: str) -> bool:
    """True for Fable-family models (always-on thinking, refusal classifiers)."""
    return "fable" in model_id or "mythos" in model_id
