# Architecture Decision Records

> ADR format: Title, Status, Context, Decision, Consequences, Alternatives.
> These records capture the non-obvious choices made during platform design.
> Readers of the codebase should start here before modifying any module.

---

## ADR-001: Anthropic-Only LLM Provider

**Status:** Accepted

**Context:**
The platform uses AI models for tasks ranging from trivial classification
(labeling a service's primary language) to high-stakes compliance decisions
(Annex IV technical documentation for EU AI Act high-risk systems). A multi-
provider approach — routing some calls to OpenAI, Gemini, or Mistral based on
cost or availability — is a common pattern in AI platform engineering. The
`litellm` library makes this straightforward at the API level.

**Decision:**
All LLM calls in the platform go exclusively to Anthropic models via the
`anthropic` Python SDK. No fallback provider is configured. No routing layer
sends tokens to non-Anthropic endpoints.

**Consequences:**

Good:
- Audit trail consistency: the `AIAuditTrail` Merkle chain logs every decision
  with its model ID, token usage, and reasoning trace. When all models are from
  one provider, compliance reviewers can verify that the same capabilities
  (extended thinking, Citations API, schema-validated tool-use) were available
  on every logged call.
- Annex IV defensibility: EU AI Act Article 12 requires technical documentation
  of the AI system. A platform that silently falls back to a different model
  with different behavioral guarantees complicates the auditor's question "was
  this decision made by the documented AI system?"
- Simpler `core/models.py`: three model constants, two cache TTL constants, three
  thinking budget constants. No provider-routing conditionals.
- Extended thinking is an Anthropic-specific API feature with no direct OpenAI
  equivalent. Any fallback to OpenAI would silently lose extended-thinking
  capability on the calls that need it most.

Bad:
- Single vendor dependency. Anthropic outages affect the entire platform.
- No automatic cost arbitrage against cheaper non-Anthropic models.
- If Anthropic changes pricing or deprecates a model, migration affects the
  whole platform.

**Alternatives Considered:**

`litellm` multi-provider routing: Rejected. litellm normalizes the API surface
but does not normalize model behavior — tool-use schemas, extended thinking,
citation formats all differ. The audit trail would log "this call used the
structured output path" but the guarantee would be provider-specific.

OpenAI as fallback: Rejected. Same reasoning as litellm. Additionally, OpenAI
does not offer a Citations API equivalent (as of 2026-04), so any call that
hits the OpenAI fallback silently loses citation grounding for compliance Q&A.

---

## ADR-002: Native Tool-Use Structured Output Over Regex JSON Parsing

**Status:** Accepted

**Context:**
Every module in the platform needs structured output from the model — a 6R
recommendation with a confidence score, a compliance violation with severity and
remediation steps, a FinOps savings summary with prioritized recommendations.
The naive approach is to ask the model to "respond in JSON" and parse the response
with a regex or `json.loads()`. This is fragile: the model may add markdown fences,
insert a preamble sentence, or produce subtly invalid JSON.

**Decision:**
All structured output uses Anthropic's native tool-use API with `force_tool_use`.
A JSON Schema is passed as the tool's `input_schema`. Anthropic validates the
response server-side before returning it. The `StructuredResponse` dataclass in
`core/ai_client.py` always carries a `.data` dict that has already passed
server-side validation.

See: `core/ai_client.py` `AIClient.structured()` method.

**Consequences:**

Good:
- Schema violations surface as explicit API errors, not silent data corruption.
- Output is always a Python dict matching the schema — no parsing code anywhere
  in the codebase.
- Adding a new required field to an output schema automatically enforces it on
  the next call without updating any parsing logic.
- The `input_schema` doubles as documentation of what the model is expected to
  return — readable by humans and machines.

Bad:
- Tool-use API costs a small amount of additional tokens (tool definition overhead).
- Schema validation adds latency on the model side (minimal but non-zero).
- Tool-use cannot be combined with streaming text responses in all model versions.

**Alternatives Considered:**

Regex JSON extraction: Rejected. Fails on markdown-fenced output, multi-block
responses, and any model that decides to add a preamble. Produces silent failures
that corrupt downstream data.

Pydantic model parsing with retry: Rejected. Better than regex but still requires
a retry loop when the model produces invalid output. Moves the validation to the
client side, which means a broken response costs tokens twice.

Instructor library: Considered. Instructor is a well-designed wrapper around this
exact pattern. Rejected because it adds a dependency and wraps a pattern simple
enough to implement directly — `core/ai_client.py` is ~200 lines.

---

## ADR-003: Opus 4.7 Extended Thinking for Annex IV Article 12 Compliance

**Status:** Accepted

**Context:**
EU AI Act Annex IV, Article 12 requires that high-risk AI systems maintain
technical documentation including "a description of the decision-making process
of the system" and "the system's capabilities and limitations." For the platform's
migration classification and app_portfolio scoring, this means the documentation
must capture not just what the system decided but how it decided — the chain of
reasoning, the evidence weights, the alternatives considered and rejected.

**Decision:**
Any AI decision involving a HIGH-risk tier workload (per `RiskTier` in
`ai_audit_trail/chain.py`) or landing on a Refactor/Replatform classification
runs through `THINKING_BUDGET_XHIGH` (32,000 tokens) extended thinking via
Opus 4.7. The reasoning trace is stored alongside the structured output in the
AIAuditTrail Merkle chain.

See: `migration_scout/thinking_audit.py`, `app_portfolio/six_r_scorer.py`,
`core/models.py` (`THINKING_BUDGET_XHIGH = 32_000`).

**Consequences:**

Good:
- Extended thinking traces satisfy Annex IV Article 12 documentation requirements
  without requiring a human analyst to write a narrative.
- The thinking trace is machine-readable and can be queried programmatically.
- The reasoning audit is opt-in — standard Haiku classifications still run at
  $0.80/M tokens for bulk work.
- Auditors can verify that the documented reasoning is consistent with the final
  recommendation — the chain from evidence to decision is explicit.

Bad:
- Opus 4.7 extended thinking is significantly more expensive than standard calls
  ($15/M input + thinking token overhead vs. $0.80/M for Haiku).
- 32,000 thinking tokens per high-stakes classification adds 5-15 seconds of
  latency per call.
- If Annex IV requirements change, the thinking prompt in `thinking_audit.py`
  needs to be updated to match.

**Alternatives Considered:**

Human-written audit narratives: Rejected as not scalable. A 400-service portfolio
would require hundreds of analyst-hours to produce compliant documentation.

Standard (non-extended) Opus reasoning: Rejected. The visible response text can
be calibrated to look like a reasoning trace, but without the `thinking` block,
there is no provable separation between the model's reasoning process and its
output. Extended thinking externalizes the reasoning before the answer is
generated — this is the property that makes it defensible under Annex IV.

Post-hoc explanation generation: Rejected. Generating an explanation after the
fact from the output is not equivalent to capturing the reasoning that produced
the output — the explanation can be rationalized rather than causal. Annex IV
reviewers asking for technical documentation want the actual decision process.

---

## ADR-004: SHA-256 Merkle Hash Chain for Audit Trail

**Status:** Accepted

**Context:**
Every AI recommendation in the platform needs a tamper-evident log. Regulators
and internal audit committees need confidence that a log entry produced at a given
time has not been modified since. Simple append-only logs are not tamper-evident —
anyone with database access can modify historical records.

**Decision:**
All AI decisions are logged to a SHA-256 hash chain in `ai_audit_trail/chain.py`.
Each `LogEntry` stores the hash of the previous entry. Modification of any entry
invalidates all subsequent hashes. V2 adds Merkle tree checkpointing every 1,000
entries for O(log n) single-entry proof. Implementation uses only stdlib
(`hashlib`, `sqlite3`, `threading`).

**Consequences:**

Good:
- Tamper evidence is mathematical, not policy-based. An auditor does not need to
  trust access controls — they can verify the chain directly.
- Verification is fast: `verify()` re-computes all hashes and reports the exact
  position of any modification.
- The Merkle root can be externally anchored (Ethereum, Polygon, or a corporate
  transparency log) by swapping the `_anchor_root()` method — the integration
  point is already designed in.
- Zero external dependencies.

Bad:
- SQLite WAL mode is sufficient for single-instance deployments but not for
  distributed write scenarios. Multi-instance deployments need the PostgreSQL
  WAL advisory lock path (designed in but not the default).
- The chain is append-only — log entries cannot be corrected. If a logging bug
  produces a malformed entry, the entry must be marked REDACTED in-chain, not
  deleted.

**Alternatives Considered:**

Signed JWT log: Rejected. JWTs prove the entry was signed by a known key at
signing time, but they do not chain — an attacker who can add entries can also
delete old ones without invalidating signatures on remaining entries.

PostgreSQL row-level audit trigger: Rejected. Audit triggers require trusting
the database administrator. An admin with TRUNCATE or UPDATE privileges can
defeat row-level audit logs. The hash chain works even if the database is
compromised — the verifier detects the tampering regardless.

Immutable cloud log (AWS CloudTrail, Azure Monitor): Rejected for the platform's
core audit trail. CloudTrail is a valid secondary log but it audits API calls,
not AI decisions. The AI decision log needs to capture reasoning traces and
model metadata that CloudTrail doesn't natively record.

---

## ADR-005: MCP Server for Tool Exposure

**Status:** Accepted

**Context:**
The platform's audit, compliance, and analysis capabilities need to be accessible
to external systems — CI pipelines, SIEM platforms, governance dashboards, and
AI coding assistants like Claude Code and GitHub Copilot. The question is how to
expose them: REST API or Model Context Protocol (MCP) server.

**Decision:**
A 19-tool MCP server is implemented in `mcp_server.py`. The server exposes all
major platform capabilities as MCP tools callable from any MCP-compatible client.
Tools cover: audit chain query/append/verify, Annex IV package generation, FinOps
savings summary, migration wave plan, IaC violation list, executive chat, and more.

**Consequences:**

Good:
- MCP is the emerging standard for AI tool integration (adopted by Anthropic,
  GitHub, Cursor, Sourcegraph, and others).
- Claude Code and similar coding assistants can call platform tools directly
  in-context without a separate REST client.
- MCP tools are self-describing via their JSON schemas — no separate API
  documentation required.
- Adding a new tool is a single Python function with a decorator.

Bad:
- MCP is newer than REST — fewer client libraries, less tooling.
- Not suitable for high-throughput programmatic access patterns (bulk import,
  CI artifact upload) — REST or direct SDK would be more appropriate there.
- MCP server discovery is not standardized across all environments.

**Alternatives Considered:**

OpenAPI REST API: Rejected as the primary interface. REST is appropriate for
bulk data access and web client integration, but AI assistant integration is
better served by MCP's native tool-call semantics. The `api.py` files in several
modules expose FastAPI endpoints for web/CI integration — REST was not fully
rejected, just not chosen as the primary external interface.

GraphQL: Rejected. The query flexibility of GraphQL is not needed here — the
platform's outputs are well-defined schemas, not arbitrary graph traversals.

---

## ADR-006: Haiku 4.5 Workers, Sonnet 4.6 Reporter, Opus 4.7 Coordinator

**Status:** Accepted

**Context:**
The platform runs thousands of AI calls per full scan. Using the same model for
every call wastes money on simple tasks and risks under-investing on complex ones.
The question is how to partition work across the three available model tiers.

**Decision:**
Three-tier model assignment codified in `core/models.py`:
- `MODEL_WORKER = MODEL_HAIKU_4_5`: bulk classification, extraction, tagging,
  entity extraction, simple summaries, CVE severity tagging
- `MODEL_REPORTER = MODEL_SONNET_4_6`: executive prose synthesis, medium-
  complexity summarization, integration notification formatting
- `MODEL_COORDINATOR = MODEL_OPUS_4_7`: task decomposition, Annex IV reasoning
  traces, 1M-context executive chat, any call requiring extended thinking

The `ModelRouter` in `core/model_router.py` enforces this assignment with a
precedence rule system rather than ML-based routing.

**Consequences:**

Good:
- Cost savings: Haiku is ~19x cheaper than Opus on input tokens. Routing 65-70%
  of call volume to Haiku at $0.80/M vs. Opus at $15/M is the dominant driver
  of the platform's 95% cost reduction claim.
- Predictable behavior: deterministic routing rules are easier to audit and
  explain than probabilistic routing.
- Upgrading one tier (e.g., when Haiku 5 ships) requires changing one constant
  in `core/models.py`.

Bad:
- The tier boundaries are heuristic, not empirically validated. Some tasks routed
  to Haiku might produce better results with Sonnet.
- The routing rules are static — they don't adapt if Anthropic changes relative
  pricing.

**Alternatives Considered:**

Dynamic routing based on accuracy benchmarks: Rejected for v0.2.0. Would require
a validation pipeline that tests each task type against each model tier and
measures accuracy. This is a valuable future investment but out of scope for the
initial build.

Single model for all tasks: Rejected. Either Opus (prohibitively expensive for
bulk scans) or Haiku (insufficient quality for Annex IV reasoning).

---

## ADR-007: Prompt Caching Strategy — 5-Min Ephemeral on System Prompts, 1-Hour on Briefings

**Status:** Accepted

**Context:**
Anthropic's prompt caching stores the KV state of processed tokens on Anthropic's
servers. Repeated calls with the same cached prefix pay only cache-read prices
(approximately 10% of full input price). Two cache TTLs are available: a ~5-minute
ephemeral cache (default) and a 1-hour cache (beta feature requiring explicit
`cache_control`).

**Decision:**
Two-tier caching policy:
1. `CACHE_TTL_5M` (`"ephemeral"`) on system prompts for all modules. These are
   large but stable within a request burst — the orchestrator's coordinator
   system prompt, the IaC scanner's 20-policy prompt, the migration assessor's
   6R instruction block.
2. `CACHE_TTL_1H` (`"1h"`) exclusively on the `ExecutiveChat` briefing bundle in
   `executive_chat/chat.py`. A CTO session spans 30-60 minutes; the briefing
   bundle does not change within a session.

**Consequences:**

Good:
- The 5-minute cache captures savings for the common pattern of running a module
  against many workloads in parallel — all workers share the cached system prompt.
- The 1-hour cache makes follow-up questions in the executive chat cost ~10% of
  the first question, which is critical for the economics of the chat interface.
- Cache TTL mismatches (using 5-minute for briefings) would leave tokens on the
  table — the policy prevents this.

Bad:
- The 1-hour cache is a beta feature. Anthropic could change its semantics or
  pricing without notice.
- System prompt changes (policy updates, version bumps) may not take effect
  until the cache expires — up to 5 minutes for ephemeral, up to 1 hour for
  the briefing cache.

**Alternatives Considered:**

No caching: Rejected. Without caching, the orchestrator's system prompt is
re-processed for every parallel Haiku worker call. At 200 Haiku workers for a
400-service portfolio scan, that's 200x the system prompt token cost.

1-hour cache on all prompts: Rejected. Unnecessary for system prompts that are
only reused within a 5-minute burst window, and adds risk of stale prompts being
cached longer than needed.

---

## ADR-008: SQLite for Result Cache

**Status:** Accepted

**Context:**
The platform needs a result cache for expensive AI calls — if a workload's metadata
hasn't changed, returning a cached result avoids a redundant API call. The cache
needs: fast key lookup, TTL expiration, LRU eviction, and async access from
Python.

**Decision:**
SQLite via stdlib `sqlite3` in WAL mode, wrapped by `ResultCache` in
`core/result_cache.py`. Cache key is SHA-256 of `(model, system_prompt, user_prompt,
schema, tool_name, thinking_budget)`. LRU eviction fires when on-disk size exceeds
500MB (default), removing the oldest-accessed 5% of rows per pass. Zero external
dependencies.

**Consequences:**

Good:
- Zero additional infrastructure. No Redis container to manage.
- WAL mode enables concurrent reads from async worker coroutines.
- The cache survives process restarts — subsequent runs of the platform reuse
  results from previous runs on unchanged workloads.
- The cache is introspectable with any SQLite browser for debugging.

Bad:
- Single-file SQLite cannot scale to distributed deployments without wrapping it
  in a shared filesystem mount.
- WAL mode concurrent writes are serialized at the database level — this limits
  cache write throughput under high concurrency.
- Not suitable for multi-instance horizontal scaling without replacing the backend.

**Alternatives Considered:**

Redis: Rejected for the default deployment. Redis requires an additional container,
a connection pool, and monitoring. The platform's deployment target is `docker-
compose` on a single instance; adding Redis increases the deployment surface for
a caching use case that SQLite handles adequately at this scale.

In-memory `dict` cache: Rejected. Doesn't survive process restarts. For a platform
that may scan 14,000 workloads over several hours, a process crash or restart
would lose all cached results.

---

## ADR-009: Protocol-Based Duck Typing for Cross-Module State

**Status:** Accepted

**Context:**
Multiple modules need to pass data between them — the drift detector needs cloud
workload state from `cloud_iq`, the executive chat needs findings from every
module, the audit trail needs context from callers it was not designed with in
mind. The naive approach — importing base classes or shared dataclasses across
module boundaries — creates import coupling that constrains the module graph.

**Decision:**
Cross-module data sharing uses Python `typing.Protocol` with `@runtime_checkable`.
Modules define the minimal Protocol interface they need (e.g., `CloudWorkload` in
`iac_security/drift_detector.py`) rather than importing the concrete type from the
source module. Any object that structurally satisfies the Protocol passes an
`isinstance` check without formal inheritance.

**Consequences:**

Good:
- No circular imports between `iac_security` and `cloud_iq`.
- Each module is independently importable and testable — tests pass simple
  dataclasses that implement the Protocol.
- New adapters (a new cloud provider, a new IaC tool) work automatically if they
  implement the Protocol interface.
- The Protocol definitions are documentation of the expected interface.

Bad:
- Protocol mismatches fail at runtime with an `isinstance` check rather than
  at import time with a type error.
- Static type checkers may not always infer Protocol satisfaction without
  explicit annotations.

**Alternatives Considered:**

Shared base class (`cloud_iq.base.Workload`): Rejected. Forces all callers to
import from `cloud_iq`, creating coupling. Adding a field to `Workload` would
require updating every module that imports it.

Dataclass serialization (dict passing): Rejected. Passing `dict` between modules
loses type information and makes IDE navigation harder. The Protocol approach
preserves type checking without hard imports.

---

## ADR-010: Pure Python OTEL Instrumentation

**Status:** Accepted

**Context:**
The platform needs observability — metrics on AI call latency, token usage, cost,
cache hit rates, and agent pipeline timing. The choice is between: a managed
observability SaaS (Datadog, New Relic), a self-hosted agent-based collector
(Datadog Agent, New Relic Infrastructure), or OpenTelemetry with a self-hosted
Grafana/Prometheus stack.

**Decision:**
OpenTelemetry Python SDK with a self-hosted Grafana + Prometheus stack (defined
in `observability/`). Metrics use the emerging `gen_ai.*` semantic conventions
for AI observability (token counts, model ID, response latency). No paid SaaS
agent.

**Consequences:**

Good:
- Zero per-seat or per-host SaaS cost.
- `gen_ai.*` semantic conventions are the emerging standard for AI observability —
  building on them now positions the platform well as tooling matures.
- OTEL traces export to any OTEL-compatible backend — the platform is not
  locked into a specific observability vendor.
- The Grafana dashboards in `agent_ops/dashboard.py` surface AI-specific metrics
  (cache hit rate, model distribution, cost per pipeline run) that Datadog's
  default APM views don't show.

Bad:
- Self-hosted Grafana + Prometheus adds two containers to the deployment.
- OTEL Python SDK adds ~50ms cold-start overhead in Lambda-style environments
  (not relevant for the platform's deployment model).
- `gen_ai.*` conventions are not yet fully standardized — some metric names may
  change.

**Alternatives Considered:**

Datadog: Rejected. Per-host pricing for a platform designed to be self-hostable
by any team makes Datadog untenable in the cost model. Also, Datadog's AI
observability features (LLM Observability) are in beta and require the Datadog
Agent, adding another dependency.

New Relic: Same rejection reasoning as Datadog.

Prometheus without OTEL: Rejected. Instrument directly against `prometheus_client`
is simpler but doesn't give distributed trace context — you lose call-graph
visibility across the multi-agent pipeline.

---

## ADR-011: OSV.dev Batched Querying for CVE Scanning

**Status:** Accepted

**Context:**
The platform needs CVE scanning across all repository dependency manifests. Options
include: NVD feed downloads (NIST National Vulnerability Database), Snyk paid API,
GitHub Advisory Database, or OSV.dev (Google's Open Source Vulnerability database).

**Decision:**
OSV.dev via its `POST /v1/querybatch` endpoint, batching up to 1,000 package
queries per request. Implemented in `iac_security/osv_scanner.py`. Maximum 5
concurrent HTTP requests to respect the API's rate limits. No API key required.

**Consequences:**

Good:
- Free, no API key, no SaaS dependency.
- 1,000-package batching means a 10,000-package corpus is 10 HTTP requests.
- OSV aggregates data from NVD, GitHub Advisory Database, PyPI, npm, and others
  — broader coverage than any single source.
- Machine-readable JSON response format; no feed parsing.

Bad:
- OSV.dev is a third-party service — availability depends on Google's
  infrastructure.
- No SLA for the free tier.
- Some package ecosystems (particularly commercial/enterprise libraries) may have
  sparse OSV coverage.

**Alternatives Considered:**

NVD feeds: Rejected. NVD's CVE feeds require downloading and parsing large JSON
files (multi-GB), maintaining a local database, and handling NVD API rate limits
(10 requests/minute without an API key). OSV's querybatch endpoint is dramatically
simpler.

Snyk API: Rejected. Snyk's accuracy and coverage are excellent but the API is a
paid product. The platform's design principle is zero mandatory SaaS spend.

GitHub Advisory Database: Rejected as a standalone source. OSV aggregates the
GitHub Advisory Database, so using OSV directly provides a superset.

---

## ADR-012: DuckDB for CUR Analytics

**Status:** Accepted

**Context:**
AWS Cost and Usage Reports are large Parquet/CSV files — a 90-day CUR for a
$10M+/year account can be 5-20 GB. The platform needs to run SQL analytics over
this data to identify savings opportunities. Options: Apache Spark, AWS Athena,
Google BigQuery, or DuckDB.

**Decision:**
DuckDB, running in-process via the `duckdb` Python library. The `CURIngestor` in
`finops_intelligence/cur_ingestor.py` loads CUR data into DuckDB and the analytics
engine runs SQL directly against it. No external cluster, no S3 prerequisite, no
IAM configuration beyond CUR delivery.

**Consequences:**

Good:
- DuckDB runs entirely in-process — no cluster to provision, no external service.
- Performance at CUR file sizes (5-20 GB): DuckDB handles 20 GB Parquet on a
  single machine in minutes.
- DuckDB's SQL dialect is full-featured — window functions, lateral joins, and
  native Parquet reading work out of the box.
- Zero cost beyond the instance running the platform.

Bad:
- Single-machine constraint. An enterprise with multiple petabytes of billing data
  would need Spark or Athena for the analytics layer.
- DuckDB doesn't persist the CUR data across process restarts by default — for
  production deployments, the DB file should be written to persistent storage.

**Alternatives Considered:**

Apache Spark: Rejected. Spark requires a cluster (or Databricks) and significant
operational overhead. For the 5-20 GB CUR sizes typical of mid-enterprise accounts,
Spark is significantly over-engineered.

AWS Athena: Rejected. Athena requires S3 storage for CUR data and a Glue catalog
configuration. Adds AWS service dependencies that make the platform harder to
run outside AWS. Also has per-query costs.

BigQuery: Rejected. Google Cloud dependency; not appropriate for an AWS-primary
deployment.

---

## ADR-013: Extended-Thinking Audit Reasoning Traces as Annex IV Evidence

**Status:** Accepted

**Context:**
EU AI Act Annex IV requires "a general description of the AI system" and
specifically "the system's capabilities and limitations." For automated decision
systems, this should include the reasoning process. The industry norm is to write
a static technical documentation document. The question is whether AI-generated
reasoning traces can substitute for human-written documentation.

**Decision:**
This is a novel compliance pattern: Opus 4.7's extended-thinking traces, captured
at decision time and persisted in the Merkle-chained audit log, are treated as
primary Annex IV Article 12 technical documentation for each classified workload.
The thinking trace is not a post-hoc explanation — it is the actual reasoning
process executed before the output was generated.

See: `migration_scout/thinking_audit.py`, `ai_audit_trail/eu_ai_act.py`.

**Consequences:**

Good:
- Scales to 14,000 workloads — human-written narratives cannot.
- The reasoning trace is temporally authentic: it was generated as part of the
  decision, not reconstructed afterward.
- Each trace includes `evidence_weight` scores explaining which input signals
  drove the classification — this is the "decision factors" documentation that
  Annex IV Article 12 describes.
- The trace is stored in the tamper-evident Merkle chain — its existence and
  content at the time of decision can be verified.

Bad:
- The legal interpretation of whether an AI-generated reasoning trace satisfies
  Annex IV documentation requirements has not been tested in a real audit.
  Organizations should have counsel review before relying solely on this pattern.
- If the model produces a reasoning trace that diverges from what a human expert
  would write, the divergence may draw auditor attention.

**Alternatives Considered:**

Human-written technical documentation: Retained as a supplementary layer. The
Annex IV package includes both the automated reasoning traces and a human-authored
system description. The traces handle per-decision documentation; the human
document handles system-level description.

Static template-filled documentation: Rejected for per-decision documentation.
A template cannot capture decision-specific reasoning — it can only describe the
system's general approach.

---

## ADR-014: Batch API Auto-Coalescing for 50% Discount on Bulk Operations

**Status:** Accepted

**Context:**
The Anthropic Batch API offers a 50% price discount over the real-time API for
asynchronous workloads. The trade-off is a 24-hour processing window (no
real-time response). For bulk scanning operations — classifying thousands of
workloads, running CVE severity explanations across hundreds of findings — the
latency trade-off is acceptable.

**Decision:**
`core/batch_coalescer.py` implements automatic request coalescing. Callers submit
`BatchableRequest` objects which are queued. The coalescer flushes to the Batch
API every 60 seconds or when the queue reaches 1,000 items (the Batch API
maximum). Callers receive an `asyncio.Future` that resolves when the batch
completes. For near-real-time operations, the real-time API is used directly
via `AIClient.structured()`.

**Consequences:**

Good:
- 50% cost reduction on all batch-eligible operations (classification, extraction,
  bulk summarization).
- Auto-coalescing is transparent to callers — they submit a `BatchableRequest`
  and await a future; the coalescing logic is invisible.
- The 1,000-item flush threshold means a full 14,000-workload scan results in
  14 batch submissions rather than 14,000 real-time calls.

Bad:
- 24-hour batch window means batch results may not be available immediately after
  submission. Long-running scans need to account for this in their SLA.
- The `aclose()` shutdown path must flush the pending queue and await all in-flight
  batches — improper shutdown loses queued work.
- Batch API error handling differs from real-time: individual request failures
  within a batch are returned in the result set, not raised as exceptions.

**Alternatives Considered:**

Manual batch submission per module: Rejected. Each module managing its own batch
submissions leads to small batches that don't fully utilize the 1,000-item
maximum, leaving discount money on the table.

Real-time API for all calls: Rejected on cost grounds. At full price, a 14,000-
workload scan costs roughly 2x what it costs with batch coalescing on
classification-tier calls.
