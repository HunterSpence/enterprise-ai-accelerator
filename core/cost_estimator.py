"""
core/cost_estimator.py
======================

Anthropic-native cost estimation for Opus 4.7 / Sonnet 4.6 / Haiku 4.5.
Zero external dependencies — all arithmetic in pure Python.

WIRING (one-liner):
    from core.cost_estimator import CostEstimator
    est = CostEstimator()
    cost = est.estimate(MODEL_HAIKU_4_5, input_tokens=1000, output_tokens=300)
    print(f"${cost:.4f}")

Full pipeline summary:
    from core.cost_estimator import CostEstimator, TokenUsageSummary
    summary = TokenUsageSummary()
    summary.add(model=MODEL_OPUS_4_7, input_tokens=500, output_tokens=200)
    summary.add(model=MODEL_HAIKU_4_5, input_tokens=8000, output_tokens=1200, via_batch=True)
    breakdown = est.summary(summary)
    print(breakdown.render_markdown())

Pricing reference (Anthropic as of 2026-04, USD per 1M tokens):
    Opus 4.7:   $15.00 input / $75.00 output
                Cache read: $1.50 (10% of input)
                Cache creation: $18.75 (125% of input)
                Batch: 50% off input + output
    Sonnet 4.6: $3.00 input / $15.00 output
                Cache read: $0.30
                Cache creation: $3.75
                Batch: 50% off
    Haiku 4.5:  $0.80 input / $4.00 output
                Cache read: $0.08
                Cache creation: $1.00
                Batch: 50% off
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.models import MODEL_HAIKU_4_5, MODEL_OPUS_4_7, MODEL_SONNET_4_6

# ---------------------------------------------------------------------------
# Pricing table  — (input, output, cache_read, cache_creation) per 1M tokens
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _ModelPricing:
    input_per_m: float        # $/1M input tokens (real-time)
    output_per_m: float       # $/1M output tokens (real-time)
    cache_read_per_m: float   # $/1M cache-read tokens (10% of input)
    cache_creation_per_m: float  # $/1M cache-creation tokens (125% of input)
    batch_discount: float     # fraction off real-time (0.5 = 50% off)


_PRICING: dict[str, _ModelPricing] = {
    MODEL_OPUS_4_7: _ModelPricing(
        input_per_m=15.00,
        output_per_m=75.00,
        cache_read_per_m=1.50,
        cache_creation_per_m=18.75,
        batch_discount=0.50,
    ),
    MODEL_SONNET_4_6: _ModelPricing(
        input_per_m=3.00,
        output_per_m=15.00,
        cache_read_per_m=0.30,
        cache_creation_per_m=3.75,
        batch_discount=0.50,
    ),
    MODEL_HAIKU_4_5: _ModelPricing(
        input_per_m=0.80,
        output_per_m=4.00,
        cache_read_per_m=0.08,
        cache_creation_per_m=1.00,
        batch_discount=0.50,
    ),
}


# ---------------------------------------------------------------------------
# TokenUsageSummary — accumulates multi-call usage
# ---------------------------------------------------------------------------

@dataclass
class _CallRecord:
    model: str
    input_tokens: int
    output_tokens: int
    cache_read: int
    cache_creation: int
    via_batch: bool


@dataclass
class TokenUsageSummary:
    """Accumulates token usage records across multiple API calls.

    Use this to collect usage from a pipeline and then call
    ``CostEstimator.summary(usage_summary)`` for a full breakdown.

    Usage::
        usage = TokenUsageSummary()
        # after each AI call:
        usage.add(
            model=MODEL_SONNET_4_6,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cache_read=resp.cache_read_tokens,
            cache_creation=resp.cache_creation_tokens,
        )
    """

    _records: list[_CallRecord] = field(default_factory=list)

    def add(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
        cache_creation: int = 0,
        via_batch: bool = False,
    ) -> None:
        """Record token usage for one API call."""
        self._records.append(
            _CallRecord(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read=cache_read,
                cache_creation=cache_creation,
                via_batch=via_batch,
            )
        )

    def add_from_response(self, response: object, *, via_batch: bool = False) -> None:
        """Convenience: pull usage fields from a StructuredResponse or ThinkingResponse."""
        model = getattr(response, "model", MODEL_SONNET_4_6)
        self.add(
            model=model,
            input_tokens=getattr(response, "input_tokens", 0),
            output_tokens=getattr(response, "output_tokens", 0),
            cache_read=getattr(response, "cache_read_tokens", 0),
            cache_creation=getattr(response, "cache_creation_tokens", 0),
            via_batch=via_batch,
        )

    def total_calls(self) -> int:
        return len(self._records)


# ---------------------------------------------------------------------------
# CostBreakdown
# ---------------------------------------------------------------------------

@dataclass
class CostBreakdown:
    """Detailed cost breakdown from ``CostEstimator.summary()``.

    Attributes
    ----------
    total_usd:
        Grand total cost across all calls.
    per_model:
        Dict keyed by model ID → {input_usd, output_usd, cache_read_usd,
        cache_creation_usd, batch_savings_usd, subtotal_usd, calls}.
    regular_usd:
        Cost of real-time (non-batch, non-cached) tokens.
    cached_usd:
        Cost of cache-read tokens (already computed, cheaper).
    batch_usd:
        Cost of tokens submitted via batch API (50% discount applied).
    cache_creation_usd:
        Cost of cache-creation tokens (slightly more expensive than input).
    savings_vs_no_cache_usd:
        How much cheaper this was vs. sending all tokens without caching.
    savings_vs_no_batch_usd:
        How much cheaper this was vs. sending all tokens at real-time rates.
    """

    total_usd: float
    per_model: dict[str, dict]
    regular_usd: float
    cached_usd: float
    batch_usd: float
    cache_creation_usd: float
    savings_vs_no_cache_usd: float
    savings_vs_no_batch_usd: float

    def render_markdown(self) -> str:
        """Render a Markdown cost summary table."""
        lines = [
            "## Cost Estimate",
            "",
            f"**Total: ${self.total_usd:.4f}**",
            "",
            "| Model | Calls | Input | Output | Cache-Read | Batch | Subtotal |",
            "|-------|-------|-------|--------|------------|-------|----------|",
        ]
        for model_id, row in self.per_model.items():
            short = _short_model_name(model_id)
            lines.append(
                f"| {short} "
                f"| {row['calls']} "
                f"| ${row['input_usd']:.4f} "
                f"| ${row['output_usd']:.4f} "
                f"| ${row['cache_read_usd']:.4f} "
                f"| ${row['batch_usd']:.4f} "
                f"| **${row['subtotal_usd']:.4f}** |"
            )

        lines += [
            "",
            "### Savings",
            f"- vs no prompt-caching: **${self.savings_vs_no_cache_usd:.4f}**",
            f"- vs no batch API:      **${self.savings_vs_no_batch_usd:.4f}**",
        ]
        return "\n".join(lines)

    def render_text(self) -> str:
        """Render a short one-line text summary."""
        return (
            f"Cost: ${self.total_usd:.4f} "
            f"(saved ${self.savings_vs_no_cache_usd + self.savings_vs_no_batch_usd:.4f} "
            f"via cache+batch)"
        )


# ---------------------------------------------------------------------------
# CostEstimator
# ---------------------------------------------------------------------------

class CostEstimator:
    """Estimates Anthropic API costs using hardcoded per-model pricing tables.

    No external network calls — all arithmetic is local.

    Parameters
    ----------
    pricing_overrides:
        Dict of {model_id: _ModelPricing} to override the built-in table.
        Useful when Anthropic updates pricing or when testing.
    """

    def __init__(
        self, *, pricing_overrides: Optional[dict[str, _ModelPricing]] = None
    ) -> None:
        self._pricing: dict[str, _ModelPricing] = {**_PRICING}
        if pricing_overrides:
            self._pricing.update(pricing_overrides)

    # ------------------------------------------------------------------
    # Single call estimate
    # ------------------------------------------------------------------

    def estimate(
        self,
        model: str,
        *,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
        cache_creation: int = 0,
        via_batch: bool = False,
    ) -> float:
        """Estimate cost in USD for a single API call.

        Parameters
        ----------
        model:
            Model ID (MODEL_OPUS_4_7 / MODEL_SONNET_4_6 / MODEL_HAIKU_4_5).
        input_tokens:
            Number of non-cached input tokens.
        output_tokens:
            Number of output tokens.
        cache_read:
            Tokens served from prompt cache (billed at 10% of input price).
        cache_creation:
            Tokens written to prompt cache (billed at 125% of input price).
        via_batch:
            If True, apply the 50% batch API discount to input + output.

        Returns
        -------
        float
            Estimated cost in USD.
        """
        p = self._pricing.get(model)
        if p is None:
            # Unknown model — fall back to Sonnet pricing
            p = self._pricing[MODEL_SONNET_4_6]

        discount = p.batch_discount if via_batch else 0.0
        multiplier = 1.0 - discount

        cost = (
            (input_tokens / 1_000_000) * p.input_per_m * multiplier
            + (output_tokens / 1_000_000) * p.output_per_m * multiplier
            + (cache_read / 1_000_000) * p.cache_read_per_m
            + (cache_creation / 1_000_000) * p.cache_creation_per_m
        )
        return cost

    # ------------------------------------------------------------------
    # Full pipeline summary
    # ------------------------------------------------------------------

    def summary(self, usage: TokenUsageSummary) -> CostBreakdown:
        """Compute a full cost breakdown for a TokenUsageSummary.

        Parameters
        ----------
        usage:
            Accumulated usage records from ``TokenUsageSummary.add()``.

        Returns
        -------
        CostBreakdown
            Detailed per-model and bucket breakdown with savings figures.
        """
        per_model: dict[str, dict] = {
            MODEL_OPUS_4_7:   _zero_row(),
            MODEL_SONNET_4_6: _zero_row(),
            MODEL_HAIKU_4_5:  _zero_row(),
        }

        total_usd = 0.0
        regular_usd = 0.0
        cached_usd = 0.0
        batch_usd = 0.0
        cache_creation_usd = 0.0

        # For savings computation
        total_input_no_cache = 0
        total_output_no_cache = 0
        total_input_no_batch = 0
        total_output_no_batch = 0

        for rec in usage._records:
            p = self._pricing.get(rec.model, self._pricing[MODEL_SONNET_4_6])
            discount = p.batch_discount if rec.via_batch else 0.0
            mult = 1.0 - discount

            in_cost     = (rec.input_tokens    / 1_000_000) * p.input_per_m    * mult
            out_cost    = (rec.output_tokens   / 1_000_000) * p.output_per_m   * mult
            cr_cost     = (rec.cache_read      / 1_000_000) * p.cache_read_per_m
            cc_cost     = (rec.cache_creation  / 1_000_000) * p.cache_creation_per_m
            call_total  = in_cost + out_cost + cr_cost + cc_cost

            # Accumulate into per-model row
            row = per_model.setdefault(rec.model, _zero_row())
            row["calls"] += 1
            row["input_usd"] += in_cost
            row["output_usd"] += out_cost
            row["cache_read_usd"] += cr_cost
            row["cache_creation_usd"] += cc_cost
            row["subtotal_usd"] += call_total
            if rec.via_batch:
                row["batch_usd"] += in_cost + out_cost

            total_usd += call_total
            cache_creation_usd += cc_cost
            cached_usd += cr_cost

            if rec.via_batch:
                batch_usd += in_cost + out_cost
            else:
                regular_usd += in_cost + out_cost

            # Savings baselines
            total_input_no_cache  += rec.input_tokens + rec.cache_read
            total_output_no_cache += rec.output_tokens
            total_input_no_batch  += rec.input_tokens
            total_output_no_batch += rec.output_tokens

        # Savings vs no prompt cache (cache_read tokens billed at full input rate)
        # This is already captured in the pricing; compute the delta
        cache_savings = sum(
            (rec.cache_read / 1_000_000) * (
                self._pricing.get(rec.model, self._pricing[MODEL_SONNET_4_6]).input_per_m
                - self._pricing.get(rec.model, self._pricing[MODEL_SONNET_4_6]).cache_read_per_m
            )
            for rec in usage._records
        )

        # Savings vs no batch (batch tokens billed at full real-time rate)
        batch_savings = sum(
            (
                (rec.input_tokens / 1_000_000) * p.input_per_m * p.batch_discount
                + (rec.output_tokens / 1_000_000) * p.output_per_m * p.batch_discount
            )
            for rec in usage._records
            if rec.via_batch
            for p in [self._pricing.get(rec.model, self._pricing[MODEL_SONNET_4_6])]
        )

        # Remove models with zero calls
        per_model = {k: v for k, v in per_model.items() if v["calls"] > 0}

        return CostBreakdown(
            total_usd=round(total_usd, 6),
            per_model={k: {sk: round(sv, 6) if isinstance(sv, float) else sv
                          for sk, sv in v.items()}
                      for k, v in per_model.items()},
            regular_usd=round(regular_usd, 6),
            cached_usd=round(cached_usd, 6),
            batch_usd=round(batch_usd, 6),
            cache_creation_usd=round(cache_creation_usd, 6),
            savings_vs_no_cache_usd=round(cache_savings, 6),
            savings_vs_no_batch_usd=round(batch_savings, 6),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _zero_row() -> dict:
    return {
        "calls": 0,
        "input_usd": 0.0,
        "output_usd": 0.0,
        "cache_read_usd": 0.0,
        "cache_creation_usd": 0.0,
        "batch_usd": 0.0,
        "subtotal_usd": 0.0,
    }


def _short_model_name(model_id: str) -> str:
    if "opus" in model_id:
        return "Opus 4.7"
    if "sonnet" in model_id:
        return "Sonnet 4.6"
    if "haiku" in model_id:
        return "Haiku 4.5"
    return model_id


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_SHARED_ESTIMATOR: CostEstimator | None = None


def get_estimator() -> CostEstimator:
    """Return the process-wide shared CostEstimator."""
    global _SHARED_ESTIMATOR
    if _SHARED_ESTIMATOR is None:
        _SHARED_ESTIMATOR = CostEstimator()
    return _SHARED_ESTIMATOR
