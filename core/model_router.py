"""
core/model_router.py
====================

Anthropic-native model routing layer — routes each AI call to the cheapest
model that can handle it, without touching any non-Anthropic provider.

WIRING (one-liner):
    from core.model_router import ModelRouter, RoutingTask
    router = ModelRouter()
    model = router.route(RoutingTask(kind="extraction", token_count_estimate=800))
    resp = await ai.structured(system=..., user=..., schema=..., model=model)

Routing precedence (first match wins):
    1. override_model — explicit caller override
    2. requires_annex_iv_audit=True → Opus 4.7 (audit-grade reasoning required)
    3. token_count_estimate > 400_000 → Opus 4.7 (only model with 1M context)
    4. needs_executive_prose=True → Sonnet 4.6
    5. kind in {classification, extraction, simple_summary} → Haiku 4.5
    6. default → Sonnet 4.6

Cost assumptions ($/1M tokens, used only for savings estimates):
    Opus 4.7:   $15 input / $75 output
    Sonnet 4.6: $3  input / $15 output
    Haiku 4.5:  $0.80 input / $4 output
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Literal, Optional

from core.models import MODEL_HAIKU_4_5, MODEL_OPUS_4_7, MODEL_SONNET_4_6

# ---------------------------------------------------------------------------
# Task kinds that are cheap enough for Haiku
# ---------------------------------------------------------------------------

_HAIKU_KINDS: frozenset[str] = frozenset(
    {"classification", "extraction", "simple_summary", "tagging", "entity_extraction"}
)

# ---------------------------------------------------------------------------
# Cost table ($/1M tokens)  — input_cost, output_cost
# ---------------------------------------------------------------------------

_COST_TABLE: dict[str, tuple[float, float]] = {
    MODEL_OPUS_4_7:   (15.00, 75.00),
    MODEL_SONNET_4_6: (3.00,  15.00),
    MODEL_HAIKU_4_5:  (0.80,   4.00),
}

# Assumed output/input ratio for savings estimates (conservative: 25% output)
_OUTPUT_RATIO = 0.25

# Threshold above which only Opus has enough context window
_OPUS_CONTEXT_THRESHOLD: int = 400_000


# ---------------------------------------------------------------------------
# RoutingTask dataclass
# ---------------------------------------------------------------------------

@dataclass
class RoutingTask:
    """Descriptor for a single AI call, used by ModelRouter to pick the model.

    Attributes
    ----------
    kind:
        Semantic task type. Haiku-eligible: "classification", "extraction",
        "simple_summary", "tagging", "entity_extraction". All others default
        to Sonnet unless another rule fires first.
    token_count_estimate:
        Rough estimate of total tokens (system + user + expected output).
        If > 400_000, only Opus has sufficient context.
    requires_annex_iv_audit:
        Set True for any decision that must produce an EU AI Act Annex IV
        audit trail. Forces Opus with extended thinking.
    needs_executive_prose:
        Set True when output quality / prose style matters (board reports,
        executive summaries). Routes to Sonnet.
    override_model:
        If set, bypasses all heuristics. Must be a canonical model ID from
        core.models (MODEL_OPUS_4_7 / MODEL_SONNET_4_6 / MODEL_HAIKU_4_5).
    metadata:
        Arbitrary caller-supplied dict passed through to stats. Useful for
        tagging routed calls by pipeline name, tenant, etc.
    """

    kind: str = "generic"
    token_count_estimate: int = 0
    requires_annex_iv_audit: bool = False
    needs_executive_prose: bool = False
    override_model: Optional[str] = None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-model stats accumulator
# ---------------------------------------------------------------------------

@dataclass
class _ModelStats:
    calls: int = 0
    input_tokens_est: int = 0

    def add(self, token_estimate: int) -> None:
        self.calls += 1
        self.input_tokens_est += token_estimate


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------

class ModelRouter:
    """Routes RoutingTask descriptors to the cheapest capable Anthropic model.

    Thread-safe: uses a simple lock around the stats dict so it is safe to
    share across asyncio tasks and background threads.

    Usage
    -----
    >>> router = ModelRouter()
    >>> model = router.route(RoutingTask(kind="extraction"))
    >>> router.stats()   # { "claude-haiku-4-5-..": {"calls": 1, ...}, ... }
    """

    def __init__(
        self,
        *,
        opus_context_threshold: int = _OPUS_CONTEXT_THRESHOLD,
        haiku_kinds: frozenset[str] | None = None,
    ) -> None:
        self._opus_threshold = opus_context_threshold
        self._haiku_kinds = haiku_kinds if haiku_kinds is not None else _HAIKU_KINDS
        self._lock = threading.Lock()
        self._stats: dict[str, _ModelStats] = {
            MODEL_OPUS_4_7:   _ModelStats(),
            MODEL_SONNET_4_6: _ModelStats(),
            MODEL_HAIKU_4_5:  _ModelStats(),
        }
        # Track hypothetical Opus-always baseline for savings delta
        self._opus_baseline: _ModelStats = _ModelStats()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, task: RoutingTask) -> str:
        """Return the model ID best suited for ``task``.

        Precedence (first match wins):
        1. explicit override
        2. requires_annex_iv_audit → Opus
        3. token_count_estimate > threshold → Opus
        4. needs_executive_prose → Sonnet
        5. kind in haiku_kinds → Haiku
        6. default → Sonnet
        """
        model = self._pick(task)
        self._record(model, task.token_count_estimate)
        return model

    def stats(self) -> dict[str, object]:
        """Return per-model call counts + estimated cost savings vs always-Opus.

        Returns a dict with:
        - per_model: {model_id: {"calls": int, "input_tokens_est": int,
                                 "estimated_cost_usd": float}}
        - baseline_opus_cost_usd: float   (what it would have cost if every
                                            call used Opus)
        - actual_cost_usd: float
        - savings_usd: float
        - savings_pct: float
        """
        with self._lock:
            per_model: dict[str, dict] = {}
            actual_cost = 0.0
            for model_id, s in self._stats.items():
                in_cost, out_cost = _COST_TABLE[model_id]
                input_tok = s.input_tokens_est
                output_tok = int(input_tok * _OUTPUT_RATIO)
                cost = (input_tok / 1_000_000) * in_cost + (output_tok / 1_000_000) * out_cost
                actual_cost += cost
                per_model[model_id] = {
                    "calls": s.calls,
                    "input_tokens_est": input_tok,
                    "estimated_cost_usd": round(cost, 6),
                }

            # Baseline: every call on Opus
            opus_in, opus_out = _COST_TABLE[MODEL_OPUS_4_7]
            total_input = self._opus_baseline.input_tokens_est
            total_output = int(total_input * _OUTPUT_RATIO)
            baseline_cost = (total_input / 1_000_000) * opus_in + (total_output / 1_000_000) * opus_out

            savings = baseline_cost - actual_cost
            savings_pct = (savings / baseline_cost * 100) if baseline_cost > 0 else 0.0

            return {
                "per_model": per_model,
                "baseline_opus_cost_usd": round(baseline_cost, 6),
                "actual_cost_usd": round(actual_cost, 6),
                "savings_usd": round(savings, 6),
                "savings_pct": round(savings_pct, 2),
            }

    def reset_stats(self) -> None:
        """Reset all counters (useful between test runs)."""
        with self._lock:
            for s in self._stats.values():
                s.calls = 0
                s.input_tokens_est = 0
            self._opus_baseline.calls = 0
            self._opus_baseline.input_tokens_est = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pick(self, task: RoutingTask) -> str:
        if task.override_model:
            return task.override_model
        if task.requires_annex_iv_audit:
            return MODEL_OPUS_4_7
        if task.token_count_estimate > self._opus_threshold:
            return MODEL_OPUS_4_7
        if task.needs_executive_prose:
            return MODEL_SONNET_4_6
        if task.kind in self._haiku_kinds:
            return MODEL_HAIKU_4_5
        return MODEL_SONNET_4_6

    def _record(self, model: str, token_estimate: int) -> None:
        with self._lock:
            self._stats[model].add(token_estimate)
            self._opus_baseline.add(token_estimate)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_SHARED_ROUTER: ModelRouter | None = None


def get_router() -> ModelRouter:
    """Return a process-wide shared ModelRouter (lazy-constructed)."""
    global _SHARED_ROUTER
    if _SHARED_ROUTER is None:
        _SHARED_ROUTER = ModelRouter()
    return _SHARED_ROUTER
