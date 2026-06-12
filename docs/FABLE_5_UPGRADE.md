# Claude Fable 5 Upgrade — Model Refresh (v0.4.0) + API Surface (v0.5.0)

**Supersedes:** `docs/OPUS_4_7_UPGRADE.md`
**Release date:** June 10, 2026
**Platform version:** v0.4.0

---

## Model Hierarchy — v0.4.0

| Role | Model ID | Input | Output | Notes |
|------|----------|-------|--------|-------|
| **Coordinator / extended thinking / exec chat** | `claude-fable-5` | $10 / MTok | $50 / MTok | 80.3% SWE-Bench Pro; replaces Opus 4.7 |
| **Alternative flagship** | `claude-opus-4-8` | — | — | Lower cost, slightly lower capability |
| **Report synthesis / moderate analysis** | `claude-sonnet-4-6` | unchanged | unchanged | Worker tier; no change |
| **High-volume workers / classification** | `claude-haiku-4-5-20251001` | unchanged | unchanged | Worker tier; no change |

**Default coordinator:** `claude-fable-5` (set in `core/models.py` as `MODEL_FABLE_5`).

To use Opus 4.8 as the coordinator instead:

```bash
export EAA_FLAGSHIP_MODEL=claude-opus-4-8
```

---

## What Changed from Opus 4.7

### Capabilities

Fable 5 (`claude-fable-5`) is the Anthropic flagship as of June 9, 2026. It replaces Opus 4.7 (`claude-opus-4-7`) in the coordinator role. Observed improvements relevant to this platform:

- Extended-thinking quality on multi-step compliance reasoning (Articles 9–15 evidence chains)
- Tool-use accuracy on complex IaC policy evaluations
- SWE-Bench Pro: 80.3% (Fable 5) vs prior Opus tier

### Pricing

| Model | Input | Output | vs Opus 4.7 |
|-------|-------|--------|-------------|
| Fable 5 | $10 / MTok | $50 / MTok | 2x the Opus-tier rate |
| Opus 4.8 | $5 / MTok | $25 / MTok | Same as Opus 4.7 |
| Opus 4.7 (previous gen, still active) | $5 / MTok | $25 / MTok | Was the flagship |

Fable 5 costs 2x the Opus tier per token — the routing layer keeps it reserved
for audit-grade and coordinator work, so the ~95% cost savings vs. always-flagship
baseline (documented in v0.2.0) still holds: Sonnet/Haiku absorb the volume.

### Tokenizer Change — Important Caveat

Opus 4.7 introduced a new tokenizer that produces approximately **35% more tokens** for the same fixed text compared to models prior to Opus 4.7 (Sonnet 4.6 / Haiku 4.5 era). Fable 5 uses the same tokenizer.

**Impact on published benchmark figures:**

Benchmark numbers in `README.md` and `docs/DEMO.md` (e.g., "50K-token executive briefing", batch processing throughput) were measured against the pre-Opus-4.7 tokenizer. With the current tokenizer, the same source text will consume approximately 35% more tokens, which means:

- Effective context window headroom is ~35% smaller for identically-sized inputs
- Batch API costs for the coordinator model are ~35% higher than the token count alone would suggest if you are comparing against pre-Opus-4.7 figures
- Cache hit rates may differ if your prompts were tuned to specific token boundaries

The platform's `CostEstimator` (`core/cost_estimator.py`) uses live token counts from the API response, not pre-tokenizer estimates, so runtime cost tracking is accurate. Only externally-published benchmark comparisons are affected.

---

## v0.5.0 — API Surface Completion (June 12, 2026)

v0.4.0 moved the model IDs to Fable 5 but kept the Opus 4.6-era request
shapes. Three of those shapes are **rejected or silently degraded** by
Fable 5; v0.5.0 replaces them platform-wide:

| Pre-v0.5.0 (broken on Fable 5) | v0.5.0 |
|---|---|
| `thinking={"type": "enabled", "budget_tokens": N}` -> **HTTP 400 on every call** | `thinking={"type": "adaptive", "display": "summarized"}` + `output_config={"effort": ...}` |
| Default thinking display -> **empty reasoning traces** (Annex IV evidence silently blank) | `display: "summarized"` restores a readable trace (the raw chain of thought is never returned on Fable 5) |
| Forced tool_choice for structured output (incompatible with always-on thinking) | Structured outputs via `output_config.format` (schema-guaranteed JSON, thinking-compatible) |
| No `stop_reason: "refusal"` handling -- content read unconditionally | Typed `RefusalError` + **server-side fallback to Opus 4.8** in the same round trip (`EAA_ENABLE_FALLBACKS=0` to disable) |

New capability flags in `core/models.py`: `EFFORT_LOW...EFFORT_MAX`,
`MODEL_FALLBACK`, `BETA_SERVER_SIDE_FALLBACK`, `BETA_TASK_BUDGETS`,
`BETA_COMPACTION`. The deprecated `THINKING_BUDGET_*` constants and
`budget_tokens` kwargs still import and run -- they are translated to the
nearest effort level with a `DeprecationWarning`.

Orchestrator runs under a token budget now also pass an **API-native task
budget** (`output_config.task_budget`, beta) so the model sees a running
countdown and self-moderates, complementing BudgetGuard's hard client-side
enforcement.

---

## Migration from Opus 4.7

### Automatic

No code changes required if you are running the platform in its default configuration. `core/models.py` has been updated:

```python
# v0.4.0
MODEL_FABLE_5 = os.environ.get("EAA_FLAGSHIP_MODEL", "claude-fable-5")
MODEL_OPUS_4_8 = "claude-opus-4-8"
MODEL_SONNET_4_6 = "claude-sonnet-4-6"
MODEL_HAIKU_4_5 = "claude-haiku-4-5-20251001"

MODEL_COORDINATOR = MODEL_FABLE_5  # was MODEL_OPUS_4_7; override via EAA_FLAGSHIP_MODEL env var
```

### Manual overrides

If you have hardcoded `claude-opus-4-7-20250514` in any configuration file or environment variable, update to `claude-fable-5` (or `claude-opus-4-8` if cost is the priority).

```bash
# Search for stale model references
grep -r "opus-4-7" . --include="*.py" --include="*.yaml" --include="*.env"
```

### Eval harness

Run the eval harness after upgrading to confirm output quality has not regressed for your specific use case:

```bash
python -m pytest evals/ -v --tb=short
```

The CI gate (`evals/thresholds.py`) defines pass/fail thresholds. All thresholds were validated against Fable 5 outputs before release.

---

## Opus 4.8 as an Alternative

`claude-opus-4-8` is available as a lower-cost coordinator alternative. Use it when:

- Cost is the primary constraint
- Extended-thinking depth requirements are moderate
- You are processing very high volumes of coordination tasks

Set `EAA_FLAGSHIP_MODEL=claude-opus-4-8` to use it. All platform features (extended thinking, tool use, Citations API, Batch API) are supported on Opus 4.8.

---

## EU AI Act / Compliance Implications

The model change requires an ML-BOM update. Generate the ML-BOM on demand with `python -m iac_security mlbom --output <path>` (CycloneDX 1.7); it is not a committed artifact. For Article 11 technical documentation purposes, the CHANGELOG.md entry for v0.4.0 records the model transition.

If your organization registered the platform as a high-risk AI system with the EU AI Office under an earlier model version, notify your compliance officer of the model refresh. A change in AI model provider or version may require an updated conformity assessment depending on the risk classification and scope of the registration.

---

## Related Files

- `core/models.py` — canonical model ID definitions
- `core/ai_client.py` — model routing implementation
- `evals/thresholds.py` — per-model quality thresholds
- ML-BOM (generated on demand: `python -m iac_security mlbom --output <path>`) — reflecting v0.4.0 model inventory
- `CHANGELOG.md` — full v0.4.0 change log
- `docs/OPUS_4_7_UPGRADE.md` — **deprecated; historical reference only**
