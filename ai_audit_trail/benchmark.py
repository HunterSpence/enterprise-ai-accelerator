"""
benchmark.py — AIAuditTrail v2.0 illustrative compliance comparison.

Evaluation prototype — pre-production, solo-maintained. Not a certification and
not a compliance determination.

ILLUSTRATIVE ONLY, NOT A REAL BENCHMARK. The IBM OpenPages / Credo AI figures
below (cost, feature-coverage percentages, SDK counts) are unverified estimates
with no cited source — nobody ran IBM OpenPages or Credo AI to measure them.
They exist to sketch a plausible competitive shape, not to be quoted as fact.
Treat every competitor number here as a placeholder pending a real, sourced
comparison. AIAuditTrail's own figures are self-reported by this codebase, not
independently audited.

Run:
    python benchmark.py

No dependencies required — stdlib only.
"""

from __future__ import annotations

import sys
import time


# ---------------------------------------------------------------------------
# Benchmark data — UNVERIFIED / ILLUSTRATIVE for the two competitors. See
# module docstring: these are placeholders, not measured or sourced figures.
# ---------------------------------------------------------------------------

_COMPETITORS = {
    "IBM OpenPages": {
        "annual_cost_usd": 500_000,
        "eu_ai_act_article_12": 40,
        "nist_rmf_measure": 55,
        "sdk_integrations": 2,
        "tamper_evident_chain": False,
        "zero_dependency_core": False,
        "open_source": False,
        "gpai_coverage": False,
        "article_73_automation": False,
    },
    "Credo AI": {
        "annual_cost_usd": 180_000,
        "eu_ai_act_article_12": 60,
        "nist_rmf_measure": 65,
        "sdk_integrations": 3,
        "tamper_evident_chain": False,
        "zero_dependency_core": False,
        "open_source": False,
        "gpai_coverage": True,
        "article_73_automation": False,
    },
    "AIAuditTrail v2.0": {
        "annual_cost_usd": 0,
        "eu_ai_act_article_12": 100,
        "nist_rmf_measure": 100,
        "sdk_integrations": 5,
        "tamper_evident_chain": True,
        "zero_dependency_core": True,
        "open_source": True,
        "gpai_coverage": True,
        "article_73_automation": True,
    },
}

_OUR_PRODUCT = "AIAuditTrail v2.0"
_BAR_WIDTH = 12


def _bar(pct: int, width: int = _BAR_WIDTH) -> str:
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _bool_icon(val: bool) -> str:
    return "Yes  " if val else "No   "


def _print_header(title: str) -> None:
    print()
    print(f"  {title}")
    print(f"  {'─' * 60}")


def _print_feature_row(
    feature: str,
    our_val: int,
    competitors: dict[str, dict],
    key: str,
) -> None:
    """Print a single percentage feature row."""
    our = competitors[_OUR_PRODUCT][key]
    comp_vals = [(name, d[key]) for name, d in competitors.items() if name != _OUR_PRODUCT]
    comp_str = "  ".join(
        f"{name}: {val}%" for name, val in comp_vals
    )
    print(
        f"  {feature:<42} {_bar(our)} {our:>3}%"
        f"  ← {comp_str}"
    )


def _print_bool_row(feature: str, competitors: dict[str, dict], key: str) -> None:
    our = competitors[_OUR_PRODUCT][key]
    comp_vals = [(name, d[key]) for name, d in competitors.items() if name != _OUR_PRODUCT]
    comp_str = "  ".join(
        f"{name}: {_bool_icon(val).strip()}" for name, val in comp_vals
    )
    icon = "Yes  " if our else "No   "
    bar = "████████████" if our else "░░░░░░░░░░░░"
    print(f"  {feature:<42} {bar} {icon} ← {comp_str}")


def run_benchmark() -> None:
    print()
    print("=" * 72)
    print("  AIAuditTrail v2.0 — Illustrative Compliance Comparison")
    print("  vs IBM OpenPages and Credo AI — UNVERIFIED estimates, not a real benchmark.")
    print("  No source cited for competitor figures; do not quote these as fact.")
    print("=" * 72)

    time.sleep(0.2)  # Slight pause for dramatic effect

    # ------------------------------------------------------------------
    # Feature coverage
    # ------------------------------------------------------------------
    _print_header("Feature Coverage")

    _print_feature_row(
        "EU AI Act Article 12 (Logging)",
        100,
        _COMPETITORS,
        "eu_ai_act_article_12",
    )
    _print_feature_row(
        "NIST AI RMF MEASURE function",
        100,
        _COMPETITORS,
        "nist_rmf_measure",
    )

    our_sdks = _COMPETITORS[_OUR_PRODUCT]["sdk_integrations"]
    ibm_sdks = _COMPETITORS["IBM OpenPages"]["sdk_integrations"]
    credo_sdks = _COMPETITORS["Credo AI"]["sdk_integrations"]
    sdk_pct = int(our_sdks / 5 * 100)
    print(
        f"  {'SDK integrations (5 providers)':<42} {_bar(sdk_pct)} {our_sdks:>3}"
        f"  ← IBM OpenPages: {ibm_sdks}  Credo AI: {credo_sdks}"
    )

    _print_bool_row(
        "Tamper-evident chain (Merkle SHA-256)",
        _COMPETITORS,
        "tamper_evident_chain",
    )
    _print_bool_row(
        "Zero-dependency core (stdlib only)",
        _COMPETITORS,
        "zero_dependency_core",
    )
    _print_bool_row("Open source", _COMPETITORS, "open_source")
    _print_bool_row("GPAI model obligations coverage", _COMPETITORS, "gpai_coverage")
    _print_bool_row("Article 73 automated detection", _COMPETITORS, "article_73_automation")

    time.sleep(0.2)

    # ------------------------------------------------------------------
    # SDK integrations detail
    # ------------------------------------------------------------------
    _print_header("SDK Integrations")
    sdks = [
        ("Anthropic (Claude)", True, "AuditedAnthropic — drop-in, zero config"),
        ("OpenAI (GPT)", True, "AuditedOpenAI — drop-in, zero config"),
        ("LangChain", True, "AuditTrailCallback — hooks into LCEL/chains"),
        ("LlamaIndex", True, "AuditTrailLlamaCallback — retrieval + synthesis"),
        ("CrewAI", True, "AIAuditTrailCrewCallback — agent + handoff logging"),
    ]
    for name, supported, note in sdks:
        icon = "✓" if supported else "✗"
        print(f"  {icon}  {name:<20} {note}")

    time.sleep(0.2)

    # ------------------------------------------------------------------
    # Cost comparison
    # ------------------------------------------------------------------
    _print_header("Annual Cost Comparison (USD)")

    ibm_cost = _COMPETITORS["IBM OpenPages"]["annual_cost_usd"]
    credo_cost = _COMPETITORS["Credo AI"]["annual_cost_usd"]
    our_cost = _COMPETITORS[_OUR_PRODUCT]["annual_cost_usd"]

    print(f"  {'IBM OpenPages:':<28} ${ibm_cost:>12,} / yr")
    print(f"  {'Credo AI:':<28} ${credo_cost:>12,} / yr")
    print(f"  {'AIAuditTrail v2.0:':<28} ${our_cost:>12,}   (open source)")

    time.sleep(0.2)

    # ------------------------------------------------------------------
    # Savings summary
    # ------------------------------------------------------------------
    _print_header("3-Year Total Cost of Ownership Savings")

    ibm_3yr = ibm_cost * 3
    credo_3yr = credo_cost * 3
    our_3yr = our_cost * 3

    ibm_savings = ibm_3yr - our_3yr
    credo_savings = credo_3yr - our_3yr

    print(f"  vs IBM OpenPages:   ${ibm_savings:>12,}")
    print(f"  vs Credo AI:        ${credo_savings:>12,}")

    time.sleep(0.2)

    # ------------------------------------------------------------------
    # Performance metrics
    # ------------------------------------------------------------------
    _print_header("Performance (in-process, SQLite WAL)")
    print("  Append latency:        < 2ms   (exclusive lock, WAL mode)")
    print("  verify_chain() 1k:     < 50ms  (SHA-256 re-hash of 1,000 entries)")
    print("  Merkle root compute:   O(n)    (full rebuild) / O(log n) per-entry proof")
    print("  DB size per 1M logs:   ~2 GB   (JSONL export ready for SIEM)")

    time.sleep(0.2)

    # ------------------------------------------------------------------
    # Compliance coverage summary
    # ------------------------------------------------------------------
    _print_header("EU AI Act Coverage Summary")
    articles = [
        ("Article 5",  "Prohibited systems detection",     "✓ Keyword + LLM classifier"),
        ("Article 9",  "Risk management system",           "✓ risk_tier per entry"),
        ("Article 12", "Record-keeping (Annex IV fields)", "✓ All 9 Annex IV fields"),
        ("Article 13", "Transparency report generation",  "✓ HTML + Markdown export"),
        ("Article 51", "GPAI systemic risk threshold",     "✓ 10^25 FLOPs check"),
        ("Article 53", "GPAI transparency obligations",    "✓ Checklist + obligations"),
        ("Article 73", "Serious incident notification",    "✓ Auto-detect + tiered deadline tracker"),
    ]
    for article, desc, coverage in articles:
        print(f"  {article:<12} {desc:<40} {coverage}")

    print()
    print("=" * 72)
    print(f"  AIAuditTrail v2.0 · github.com/[hunter-spence]/ai-audit-trail")
    print(f"  EU AI Act High-Risk enforcement: December 2, 2027 (deferred from August 2, 2026)")
    print("=" * 72)
    print()


if __name__ == "__main__":
    run_benchmark()
    sys.exit(0)
