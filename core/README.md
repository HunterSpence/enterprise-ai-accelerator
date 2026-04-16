# core — Anthropic Optimization Layer

The `core` package is the single integration point for all Anthropic API calls across the platform. It provides complexity-based model routing, SQLite result caching, auto-coalescing Batch API submission, SSE streaming, Files API access, interleaved thinking+tools loops, cost estimation, OTEL telemetry, Prometheus metrics, and structured logging. Combined, these levers reduce cost by approximately 95% compared to routing every call to Opus 4.7 at list price.

---

## Components

### `AIClient` (`ai_client.py`)

Single Anthropic wrapper. All platform modules use `AIClient` — no direct `anthropic.Anthropic` calls elsewhere.

Features baked in:
- 5-minute ephemeral prompt cache on all system prompts
- 1-hour prompt cache for `executive_chat` briefings
- Native tool-use (schema-validated; no regex JSON parsing)
- Extended-thinking support (`thinking_budget_tokens` parameter)
- OTEL span creation on every call (via `_hooks.py`)
- Prometheus metric increments on every call
- Structured log emission on every call

```python
from core.ai_client import AIClient

client = AIClient()

response = await client.complete(
    model="claude-opus-4-7-20250514",
    system="You are a cloud migration expert.",
    messages=[{"role": "user", "content": "Classify this workload..."}],
    tools=[my_tool_schema],
    max_tokens=4096,
)
```

### `ModelRouter` (`model_router.py`)

Complexity-based model selection. Scores each task on factors including:
- Token budget required
- Number of tool calls expected
- Whether extended thinking is requested
- Module context (iac_security always gets at least Sonnet)

Routes to:
- **Opus 4.7** — coordination, extended thinking, executive chat, high-stakes compliance
- **Sonnet 4.6** — report synthesis, moderate-complexity analysis
- **Haiku 4.5** — high-volume worker tasks, simple classification

At reference workload (1,000 6R classifications), routing vs. all-Opus saves ~60× on worker calls and ~4× on synthesis calls.

```python
from core.model_router import ModelRouter

router = ModelRouter()
model = router.select(task="classify_workload", token_estimate=800)
# Returns "claude-haiku-4-5-20250514" for simple classification
```

### `ResultCache` (`result_cache.py`)

SQLite-backed cache. Cache key = SHA-256 of (model + system_prompt + user_message + tools). TTL configurable per call (default 3600 seconds).

```python
from core.result_cache import ResultCache

cache = ResultCache(db_path=".eaa_cache/results.db")
result = cache.get(key)  # None if miss or expired
cache.set(key, result, ttl=3600)
```

### `BatchCoalescer` (`batch_coalescer.py`)

Accumulates requests and submits them to the Anthropic Batch API for a 50% discount. Works as a context manager or async queue.

- Batches accumulate until `flush_size` (default 50) or `flush_interval` (default 60 seconds)
- Each batch job polls for completion (up to 24 hours per Batch API guarantee)
- Results are delivered via callback or `await coalescer.get_result(request_id)`

```python
from core.batch_coalescer import BatchCoalescer

async with BatchCoalescer(flush_size=100) as coalescer:
    request_id = await coalescer.submit(
        model="claude-haiku-4-5-20250514",
        messages=[{"role": "user", "content": "Classify: ..."}],
    )
    result = await coalescer.get_result(request_id)
```

### `StreamHandler` (`streaming.py`)

SSE streaming response handler. Iterates over the stream and yields content deltas. Handles `content_block_start`, `content_block_delta`, and `message_stop` events.

```python
from core.streaming import StreamHandler

handler = StreamHandler(client)
async for chunk in handler.stream(model=..., messages=...):
    print(chunk, end="", flush=True)
```

### `FilesAPIClient` (`files_api.py`)

Wrapper for the Anthropic Files API. Upload documents once; reference by `file_id` in subsequent calls to avoid re-uploading large compliance documents.

```python
from core.files_api import FilesAPIClient

files = FilesAPIClient()
file_id = await files.upload("cis_aws_benchmark.pdf", media_type="application/pdf")
# Use file_id in compliance_citations EvidenceLibrary
```

### `InterleavedThinkingLoop` (`interleaved_thinking.py`)

Runs an agentic loop where extended thinking and tool calls interleave. The model thinks, calls a tool, gets the result, thinks again, and repeats until it emits a final response. Reasoning traces at each step are optionally persisted to `ai_audit_trail`.

```python
from core.interleaved_thinking import InterleavedThinkingLoop

loop = InterleavedThinkingLoop(client, tools=[...])
result = await loop.run(
    system="You are a migration planning expert.",
    user_message="Plan the migration for this 75-workload inventory...",
    thinking_budget_tokens=16000,
    persist_traces=True,  # write reasoning to AIAuditTrail
)
```

### `CostEstimator` (`cost_estimator.py`)

Per-call and per-session cost estimation. Uses current Anthropic list pricing (pinned in `cost_estimator.py` — update when pricing changes).

| Token type | Opus 4.7 | Sonnet 4.6 | Haiku 4.5 |
|---|---|---|---|
| Input | $15/MTok | $3/MTok | $0.25/MTok |
| Output | $75/MTok | $15/MTok | $1.25/MTok |
| Cache read | $1.50/MTok | $0.30/MTok | $0.025/MTok |
| Cache creation | $18.75/MTok | $3.75/MTok | $0.30/MTok |
| Batch (input) | $7.50/MTok | $1.50/MTok | $0.125/MTok |

```python
from core.cost_estimator import CostEstimator

estimator = CostEstimator()
cost = estimator.estimate(
    model="claude-opus-4-7-20250514",
    input_tokens=1240,
    output_tokens=384,
    cache_read_tokens=8000,
)
print(f"${cost:.4f}")
```

---

## Wiring Snippets

### Minimal setup (all defaults)

```python
import os
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-..."

from core.ai_client import AIClient

client = AIClient()
# OTEL, Prometheus, logging all initialize on first import
```

### Full custom setup

```python
from core.ai_client import AIClient
from core.model_router import ModelRouter
from core.result_cache import ResultCache
from core.batch_coalescer import BatchCoalescer

client = AIClient(
    cache_db_path=".eaa_cache/results.db",
    otel_endpoint="http://localhost:4317",
    prometheus_port=8000,
)
router = ModelRouter(complexity_threshold_opus=0.8)
cache = ResultCache(db_path=".eaa_cache/results.db", default_ttl=3600)
coalescer = BatchCoalescer(flush_size=100, flush_interval=60)
```

---

## Environment Variables

```
ANTHROPIC_API_KEY            # Required for all API calls
OTEL_EXPORTER_OTLP_ENDPOINT  # OTEL Collector endpoint (default: http://localhost:4317)
PROMETHEUS_PORT              # Prometheus metrics port (default: 8000)
LOG_LEVEL                    # Logging level: DEBUG|INFO|WARNING|ERROR (default: INFO)
LOG_FORMAT                   # Log format: json|console (default: json)
EAA_CACHE_DIR                # Cache directory (default: .eaa_cache/)
EAA_RESULT_CACHE_TTL         # Default cache TTL in seconds (default: 3600)
EAA_BATCH_FLUSH_SIZE         # BatchCoalescer flush size (default: 50)
EAA_BATCH_FLUSH_INTERVAL     # BatchCoalescer flush interval in seconds (default: 60)
```
