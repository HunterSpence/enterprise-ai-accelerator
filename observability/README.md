# observability — OpenTelemetry, Prometheus, and Grafana Stack

Full observability for the Enterprise AI Accelerator platform. Covers distributed tracing (OTEL with gen_ai.* conventions), metrics (Prometheus + Grafana), and structured logs (structlog JSON). One docker-compose command brings up the complete stack.

---

## One-Command Bring-Up

```bash
cd observability
docker compose -f docker-compose.obs.yaml up -d
```

This starts:
- **Prometheus** — scrapes app metrics on `:9090`
- **Grafana** — dashboards on `http://localhost:3000` (admin/admin)
- **Jaeger** — trace UI on `http://localhost:16686`
- **OTEL Collector** — receives OTEL data on `:4317` (gRPC) and `:4318` (HTTP)

No configuration required — datasources and dashboards are auto-provisioned.

---

## Grafana Dashboards

### eaa_platform — Platform Overview

Shows overall platform health:

| Panel | Metric | Description |
|---|---|---|
| Request rate | `eaa_requests_total` | Requests/sec per module |
| Error rate | `eaa_errors_total` | Error % per module |
| P50/P95/P99 latency | `eaa_request_duration_seconds` | API call latency histogram |
| Active sessions | `eaa_active_sessions` | Concurrent sessions |
| Batch queue depth | `eaa_batch_queue_depth` | Pending Batch API jobs |

### eaa_cost — Cost Intelligence

Shows AI spend and optimization levers:

| Panel | Metric | Description |
|---|---|---|
| Token spend | `eaa_tokens_total{type="input|output|cache_read|cache_creation"}` | Tokens by type over time |
| Cache hit rate | `eaa_cache_hits_total / eaa_requests_total` | % requests served from ResultCache |
| Batch discount | `eaa_batch_requests_total` | Requests submitted via Batch API (50% discount) |
| Cost counter | `eaa_cost_usd_total{model="..."}` | Cumulative USD spend per model |
| Model routing | `eaa_model_selections_total{model="..."}` | Routing distribution: Opus/Sonnet/Haiku |

---

## Prometheus Metrics

8 metrics exported by `core/prometheus_exporter.py`:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `eaa_requests_total` | Counter | `module`, `status` | Total API requests |
| `eaa_request_duration_seconds` | Histogram | `module` | Request latency (buckets: 0.1s–30s) |
| `eaa_tokens_total` | Counter | `model`, `type` | Token counts by model and type |
| `eaa_cache_hits_total` | Counter | `cache_type` | Result cache + prompt cache hits |
| `eaa_batch_queue_depth` | Gauge | — | Pending BatchCoalescer jobs |
| `eaa_errors_total` | Counter | `module`, `error_type` | Error counts |
| `eaa_cost_usd_total` | Counter | `model` | Cumulative cost in USD |
| `eaa_active_sessions` | Gauge | — | Active concurrent sessions |

Prometheus scrape endpoint: `http://localhost:8000/metrics` (default port; configurable via `PROMETHEUS_PORT`).

---

## OpenTelemetry Traces

`core/telemetry.py` sets up an OTEL tracer using the `gen_ai.*` semantic conventions from the OpenTelemetry GenAI working group:

| Span attribute | Value | Description |
|---|---|---|
| `gen_ai.system` | `anthropic` | LLM provider |
| `gen_ai.request.model` | e.g. `claude-opus-4-7` | Requested model |
| `gen_ai.response.model` | model from response | Actual model used |
| `gen_ai.usage.input_tokens` | int | Input tokens charged |
| `gen_ai.usage.output_tokens` | int | Output tokens charged |
| `gen_ai.usage.cache_read_tokens` | int | Prompt cache read tokens |
| `gen_ai.usage.cache_creation_tokens` | int | Prompt cache creation tokens |
| `gen_ai.request.max_tokens` | int | max_tokens parameter |

Each `AIClient` call creates a span. Nested agent calls create child spans, giving a full call tree in Jaeger.

Traces are sent to the OTEL Collector at `localhost:4317` (gRPC) by default. Override with:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4317
```

---

## Wiring the App

The observability stack is auto-wired when you import from `core`:

```python
from core.telemetry import get_tracer
from core.prometheus_exporter import metrics

# Telemetry is initialized on first import of core.ai_client
# No manual setup required for standard usage

# To add a custom span in your module:
tracer = get_tracer("my_module")
with tracer.start_as_current_span("my_operation") as span:
    span.set_attribute("my.custom.attr", "value")
    result = do_work()
```

For Prometheus metrics:

```python
from core.prometheus_exporter import metrics

metrics.requests_total.labels(module="my_module", status="success").inc()
```

---

## Structured Logs

`core/logging.py` configures structlog with JSON output:

```json
{"event": "api_call", "model": "claude-opus-4-7", "module": "iac_security",
 "input_tokens": 1240, "output_tokens": 384, "duration_ms": 2341,
 "cache_hit": false, "timestamp": "2026-04-16T18:34:12Z", "level": "info"}
```

Log level configurable via `LOG_LEVEL` env var (default: `INFO`). Log format configurable via `LOG_FORMAT` env var (`json` or `console`).

---

## OTEL Collector Config (`otel-collector.yaml`)

The OTEL Collector is configured to:
1. Receive spans via OTLP gRPC (`:4317`) and HTTP (`:4318`)
2. Export to Jaeger for trace visualization
3. Export Prometheus-compatible metrics via the Prometheus exporter

To send traces to an external backend (e.g. Honeycomb, Grafana Cloud), add an exporter to `otel-collector.yaml`:

```yaml
exporters:
  otlp/external:
    endpoint: api.honeycomb.io:443
    headers:
      x-honeycomb-team: "${HONEYCOMB_API_KEY}"
```
