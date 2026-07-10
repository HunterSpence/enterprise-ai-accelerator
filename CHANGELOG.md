# Changelog

All notable changes to Enterprise AI Accelerator are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed — truth & safety pass (docs/marketing)
- Added an "Evaluation prototype — pre-production, solo-maintained. Not a certification and not a compliance determination." banner to `README.md` and `PRICING.md`.
- Corrected fabricated "25,000 agents deployed" PwC claim to "250+" (as of 2025, per PwC public statements) in `README.md`.
- Reworded AWS Migration Hub framing: AWS retired it in favor of AWS Transform, which AWS states has equivalent+enhanced capabilities; the platform now competes on openness/cross-cloud coverage instead of an abandoned-service narrative.
- `PRICING.md` — clearly relabeled "Accelerator Cloud" managed hosting (SSO/SAML, unlimited users, per-tier support) as **planned, not available today**; softened Enterprise Self-Hosted "24×7" support language to best-effort (solo maintainer, no staffed on-call).
- `PRICING.md` / `README.md` — reframed the "3-year TCO" tables as fee-only, illustrative cost-of-support comparisons (excludes infra/API usage/implementation/operations), not a real total-cost-of-ownership calculator.
- Replaced "tamper-proof" with "tamper-evident (single trust boundary; no external anchor)" in the competitor comparison table.
- Added a "Current capability status" table to `README.md` marking each module implemented / partial / demo-only / planned honestly.
- Fixed the IaC quick-start command in `README.md` and `docs/DEMO.md`: `python -m iac_security scan .` (was missing the `scan` subcommand).
- Replaced "Article 62" / universal "72-hour" EU AI Act incident-deadline references with "Article 73 (tiered deadlines — verify against primary source)" and added a "not legal advice" note.
- Removed `docs/CASE_STUDY.md` (fictional Accenture/Ironside case study with invented executives, quotes, and dollar figures; was already labeled fictional and orphaned/unlinked).
- Reconciled the version banner in `README.md` to v0.5.0 (was still showing v0.4.0 despite `pyproject.toml` already at 0.5.0).

---

## [0.5.0] -- 2026-06-12

The v0.4.0 release moved the model IDs to Fable 5 but kept Opus 4.6-era request
shapes -- three of which Fable 5 rejects or silently degrades. v0.5.0 completes
the migration: every call path is now on the June-2026 API surface, with refusal
resilience and model-aware budgeting on top. **Zero new runtime dependencies.**

### Fixed -- Fable 5 API correctness (production-breaking before this release)
- `core/ai_client.py`, `core/streaming.py`, `core/interleaved_thinking.py` -- the
  legacy `thinking={"type": "enabled", "budget_tokens": N}` shape returned **HTTP 400
  on every Fable 5 call** (the flagship thinking path was non-functional in v0.4.0).
  All paths now use adaptive thinking; depth is controlled via `output_config.effort`.
- Annex IV reasoning traces were **silently empty** on Fable 5 (thinking display
  defaults to omitted). All audit-trail paths now send
  `thinking={"type": "adaptive", "display": "summarized"}` -- the summarized trace
  is what gets persisted as Article 12 evidence (the raw chain of thought is never
  returned by the API on Fable 5).
- `ThinkingResponse.thinking_tokens` was incorrectly populated from
  `cache_read_input_tokens`; thinking spend is folded into `output_tokens` by the
  API and the field now reports 0 (kept for backward compatibility).
- `core/models.py` -- `CTX_WINDOW_SONNET_4_6` corrected to 1M (was 200K; Sonnet 4.6
  has a 1M window).
- `docs/FABLE_5_UPGRADE.md` -- corrected Opus 4.7 pricing ($5/$25, not $15/$75),
  the fabricated `claude-opus-4-7-20250514` ID, and the inverted "Fable 5 is
  cheaper than Opus 4.7" claim.

### Changed -- structured outputs replace forced tool calls
- `AIClient.structured()` / `structured_with_thinking()` now use **structured
  outputs** (`output_config.format` with a JSON schema): generation is constrained
  server-side so the response text is guaranteed-valid JSON, and -- unlike forced
  `tool_choice` -- the mechanism is compatible with thinking, which is always on
  for Fable 5. `tool_name`/`tool_description` parameters are retained as no-ops.
- Schemas are normalized automatically (`additionalProperties: false` injected
  recursively). `migration_scout`'s open-map `evidence_weight` schema was rewritten
  as an `{attribute, weight}` array (strict-mode compatible) and folded back into a
  dict after parsing.
- Default `max_tokens` raised to 16,000 on non-streaming calls (adaptive thinking
  spends from the same cap; 1-2K ceilings starve it) and 64,000 on streaming.

### Added -- refusal resilience (server-side fallbacks)
- Fable 5 safety classifiers can decline a request as a *successful* HTTP 200 with
  `stop_reason: "refusal"`. The client now (1) routes Fable 5 calls through the
  server-side fallbacks beta so a refusal is retried on **Opus 4.8 in the same
  round trip** (`MODEL_FALLBACK`, env-overridable; kill-switch
  `EAA_ENABLE_FALLBACKS=0`), and (2) raises a typed `RefusalError` (with
  `stop_details` category/explanation for the audit trail) when the whole chain
  declines. `StructuredResponse.served_by_fallback` reports when a fallback model
  produced the answer. Graceful degradation on providers that reject the beta.
- `core/interleaved_thinking.py` -- handles `refusal` (typed error) and
  `pause_turn` (server-tool resume) stop reasons in the agentic loop.

### Added -- effort-aware routing + model-aware budgets
- `core/models.py` -- `EFFORT_LOW/MEDIUM/HIGH/XHIGH/MAX`, `effort_for_budget()`
  translation, `MODEL_FALLBACK`, beta-header constants
  (`BETA_SERVER_SIDE_FALLBACK`, `BETA_TASK_BUDGETS`, `BETA_COMPACTION`), capability
  helpers (`is_fable`, `supports_effort`, `supports_adaptive_thinking`), and
  max-output-token reference values. `describe_model()` now reports adaptive
  thinking, effort, structured outputs, always-on-thinking, and refusal capability.
- `core/model_router.py` -- `route_decision()` returns a `RoutingDecision`
  (model + recommended effort). Routing fixes: long-context tasks (>400K) now route
  to **Sonnet 4.6** (same 1M window as Fable 5 at 30% of the input price), and
  Haiku-eligible task kinds that exceed Haiku's 200K window are promoted to Sonnet
  instead of overflowing.
- `agent_ops/orchestrator.py` -- pipelines run under `max_tokens_budget` now also
  pass an **API-native task budget** (`output_config.task_budget`, beta, min 20K)
  so the model sees a running countdown and self-moderates -- complementing
  BudgetGuard's hard client-side abort.
- `AIClient.count_tokens()` -- model-specific token counting via the
  count_tokens endpoint (never tiktoken).

### Deprecated
- `THINKING_BUDGET_*` constants and every `budget_tokens` / `thinking_budget`
  kwarg -- still accepted, translated to the nearest effort level with a
  `DeprecationWarning`. Removal targeted for v0.6.0.

---

## [0.4.0] — 2026-06-10

Six parallel capability tracks: model refresh to Claude Fable 5, a first-party offline eval
harness with a CI gate, a first-party guardrail layer, MCP Streamable HTTP + audited tool
calls, compliance currency to June 2026 law (11 frameworks), and a governance/pricing
documentation pack. **Zero new runtime dependencies** — evals and guardrails are first-party
code; `mcp>=1.27.0` (already a runtime requirement) is now correctly declared in
`pyproject.toml`.

### Changed — Model Refresh + Packaging (W1)
- `core/models.py` — `MODEL_FABLE_5 = "claude-fable-5"` is the flagship/coordinator model, overridable via `EAA_FLAGSHIP_MODEL`; `MODEL_OPUS_4_7` retained as a deprecated alias resolving to Fable 5 so existing imports keep working; Sonnet 4.6 / Haiku 4.5 worker tiers unchanged
- `core/model_router.py` + `core/cost_estimator.py` — pricing tables updated to June 2026 list prices: Fable 5 $10/$50 per MTok (cache read $1, cache write $12.50, batch −50%), Sonnet 4.6 $3/$15, Haiku 4.5 $1/$5
- Stale model-ID strings updated across `core/`, `cloud_iq/`, `finops_intelligence/`, `agent_ops/`, `observability/` (Grafana cost dashboard re-priced), `.env.example` (was two generations stale), and module READMEs
- `pyproject.toml` — version 0.4.0; `mcp>=1.27.0` added to dependencies (was missing — clean installs could not start the MCP server); `anthropic>=0.69.0,<1.0`; pytest `testpaths` now includes all six test directories (per-module suites were silently excluded)
- **Fixed:** `cloud_iq` demo mode made live (billable) API calls — demo mode now never calls the Anthropic API; the two affected tests pass offline
- `cloud_iq/models.py` — Pydantic V1 `@validator` migrated to V2 `@field_validator`
- `finops_intelligence/README.md` — FOCUS 1.4 (June 2026, AI token-economics columns) noted on roadmap; exporter remains FOCUS 1.3-conformant
- **Tokenizer caveat (corrected in v0.5.0):** Fable 5 shares the Opus 4.7/4.8-era tokenizer; counts are roughly unchanged vs Opus 4.7/4.8. The ~35% inflation applies only when comparing against pre-Opus-4.7 (Sonnet/Haiku-era) measurements -- pre-v0.4.0 benchmark token counts and dollar figures remain stale for that reason. See `docs/FABLE_5_UPGRADE.md`.

### Added — Eval Harness + CI (W2)
- `evals/` — first-party, offline-first eval harness (no third-party eval dependency): JSONL golden datasets (`six_r_classification` 23 cases, `iac_policy_detection` 20 cases incl. true-negatives, `prompt_injection_redteam` 25 cases), deterministic scorers, per-suite thresholds, JSON + markdown reports
- The IaC suite scores the real `iac_security.PolicyEngine`: F1 0.894 against a 0.85 gate at release
- `python -m evals.run --offline` exits non-zero below threshold — wired into CI as a quality gate
- Optional live mode (`ANTHROPIC_API_KEY` set, `--offline` omitted) runs 6R golden cases through the real model path
- `.github/workflows/ci.yml` — first CI for the repo: full offline test suite + the eval gate on every push/PR
- `evals/tests/` — 40 harness self-tests

### Added — Guardrails + Orchestrator Hardening (W3)
- `core/guardrails.py` — first-party `GuardrailEngine` with input rail (prompt-injection detection: instruction-override, role-smuggling, suspicious encodings, unicode direction/zero-width tricks, tool-arg smuggling), output rail (secret/PII redaction), execution rail (tool allowlists + call caps); `BudgetGuard` (per-run token/USD caps); `GuardedAIClient` wrapper; mapped to OWASP LLM Top 10 2025 in the module docstring; 77 offline tests
- `agent_ops/orchestrator.py` — exponential-backoff retries on transient API errors; per-run token/cost budgets via `BudgetGuard` with clean partial-results abort; stage checkpoints persisted to `.eaa_checkpoints/` with `Orchestrator.resume(run_id)`; optional human-in-the-loop `approval_handler` gate with auto-approvals recorded in result telemetry; 52 new tests

### Changed — MCP Modernization + Security (W4)
- `mcp_transports.py` — Streamable HTTP transport added via the official SDK (`StreamableHTTPSessionManager`, endpoint `/mcp`) per MCP spec 2025-03-26; SSE retained but labeled legacy; stdio unchanged as default
- Bearer-token auth on both network transports via `EAA_MCP_AUTH_TOKEN` (constant-time compare; `/health` exempt; stdio exempt)
- Every MCP tool invocation is appended to the platform's own Merkle chain (`.eaa_audit/mcp_tools.db`): tool name, SHA-256 of args, duration, status — fail-open, default on, opt-out via `EAA_MCP_AUDIT` (OWASP MCP08)
- Argument validation before dispatch: path-traversal rejection, enum and numeric-bounds checks, clean MCP errors (OWASP MCP03/05)
- `tests/test_mcp_server.py` — 26 new tests (transports, auth, audit chain, validation); 74 total passing

### Added — Compliance Currency + ML-BOM (W5)
- `policy_guard/` — **Colorado SB 24-205 was repealed**; coverage added for its replacement **SB 26-189** (signed May 14, 2026, effective Jan 1, 2027) and for **Texas TRAIGA** (effective Jan 1, 2026; penalties $10K–$200K per violation) — 15 controls each. Framework count: 9 → 11, cross-framework traceability updated
- `ai_audit_trail/chain.py` — the placeholder blockchain anchor is gone; replaced by a real `AnchorBackend` protocol with `FileAnchor` (append-only, fsync'd, thread-safe) and `WebhookAnchor` (POST with retry) implementations
- `ai_audit_trail/web_ui.py` — NIST AI RMF MANAGE 2.2 (human-oversight events from the audit chain) and GOVERN 5.2 (third-party AI inventory from the ML-BOM + model registry) implemented; TODO markers removed
- `iac_security/` — CycloneDX 1.7 **ML-BOM** generation: `python -m iac_security mlbom` emits machine-learning-model components for the platform's model stack (provider, version, API ID)
- EU AI Act timeline updated to the Digital Omnibus reality: high-risk (Annex III) enforcement December 2, 2027 (deferred from August 2, 2026); GPAI obligations in force since August 2025

### Added — Documentation (W6)
- `GOVERNANCE.md` — solo maintainer model, decision process, release cadence, security report handling, bus-factor mitigation, contribution acceptance criteria
- `PRICING.md` — OSS Core (free); Accelerator Cloud ($299–$799/mo, roadmap); Enterprise Self-Hosted Support ($25K–$80K/yr); Fixed-Scope Services ($15K–$50K); FinOps outcome pricing (10% of realized savings, month 6); 3-year TCO contrast vs Big-6
- `ROADMAP.md` — NOW / NEXT / LATER horizon buckets with per-item rationale and status
- `docs/FABLE_5_UPGRADE.md` — v0.4.0 model refresh reference: Fable 5 pricing, tokenizer caveat, Opus 4.8 alternative, migration guide; `docs/OPUS_4_7_UPGRADE.md` carries a deprecation banner
- `docs/EU_AI_ACT_EVIDENCE_PACK.md` — Annex IV evidence walkthrough; Articles 9–15 mapped to platform commands and artifacts; Digital Omnibus timeline (high-risk: Dec 2, 2027)
- `docs/SOVEREIGN_DEPLOYMENT.md` — all computation in the client's cloud; Anthropic API as sole external call; no telemetry; air-gap notes; Bedrock/Vertex routing flagged as unconfirmed options to evaluate
- `README.md` — full rewrite: problem-first positioning, verifiability table, lock-in answer, time-to-value quickstart, pricing, corrected regulatory dates
- `docs/RESUME_TALKING_POINTS.md` — removed from the repository (interview-preparation content does not belong in a product repo)

---

## [0.2.0] — 2026-04-16

Seven parallel capability tracks. 68 new files. 16,931 lines of code added.
Zero paid SaaS dependencies introduced. All 15 new dependencies are OSS (Apache 2.0 / MIT).

### Added — Multi-Cloud Discovery (`cloud_iq/adapters/`)
- `AWSAdapter` — real boto3-backed EC2/EKS/RDS/S3/ECS/Lambda/VPC discovery
- `AzureAdapter` — azure-mgmt-compute + azure-mgmt-resource discovery
- `GCPAdapter` — google-cloud-compute discovery
- `KubernetesAdapter` — kubernetes Python client discovery
- `UnifiedDiscovery.auto()` — credential probe + graceful degradation; returns combined asset inventory across all reachable clouds
- `cloud_iq/adapters/README.md`

### Added — App Portfolio Intelligence (`app_portfolio/`)
- `LanguageDetector` — 11 programming languages by file extension + content heuristics
- `DependencyScanner` — 9 manifest formats (requirements.txt, package.json, go.mod, Gemfile, pom.xml, build.gradle, Cargo.toml, composer.json, pyproject.toml)
- `CVEScanner` — OSV.dev batch CVE scanner with severity bucketing
- `ContainerizationScorer` — Dockerfile + .dockerignore + k8s manifest detection
- `CIMaturityScorer` — GitHub Actions / GitLab CI / Jenkins / CircleCI detection
- `TestCoverageScanner` — pytest / jest / go test coverage file detection
- `SixRScorer` — Opus 4.7 extended-thinking 6R recommendation per repository
- CLI entry point: `python -m app_portfolio.cli <path>`
- `app_portfolio/README.md`

### Added — Integration Hub (`integrations/`)
- `SlackAdapter` — webhook-based finding notifications
- `JiraAdapter` — Jira Cloud REST API ticket creation
- `ServiceNowAdapter` — ServiceNow incident creation
- `GitHubIssueAdapter` — GitHub Issues creation
- `GitHubAppAdapter` — GitHub App PR check-runs with inline annotations
- `TeamsAdapter` — Microsoft Teams webhook notifications
- `SMTPAdapter` — SMTP email notifications
- `PagerDutyAdapter` — PagerDuty event creation
- `FindingRouter` — severity/type-based routing rules
- `WebhookDispatcher` — retry (exponential backoff) + circuit-breaker + rate-limit
- Dry-run mode on all adapters
- `integrations/README.md`

### Added — IaC Security (`iac_security/`)
- `TerraformParser` — python-hcl2-based HCL parser
- `PulumiParser` — Pulumi YAML/JSON parser
- `PolicyEngine` — 20 built-in policies covering CIS AWS / PCI-DSS / SOC 2 / HIPAA with severity and remediation
- `SBOMGenerator` — CycloneDX SBOM generation from parsed IaC dependency graph
- `OSVScanner` — OSV.dev batched CVE scanner for IaC-declared dependencies
- `DriftDetector` — IaC declared state vs. live cloud state diff
- `SARIFExporter` — SARIF 2.1.0 output compatible with GitHub Security tab upload
- `iac_security/README.md`

### Added — Full Observability Stack (`observability/` + `core/telemetry.py` + `core/prometheus_exporter.py` + `core/logging.py`)
- OpenTelemetry SDK integration with gen_ai.* semantic conventions
- 8 Prometheus metrics: request count, latency histogram, token usage, cache hit rate, batch queue depth, error rate, cost counter, active sessions
- structlog JSON structured logging
- `core/_hooks.py` — OTEL span hooks wired into AIClient
- Grafana dashboard: `eaa_platform` (request rates, latency, error rates)
- Grafana dashboard: `eaa_cost` (token spend, cache savings, batch discount)
- `otel-collector.yaml` — OTEL Collector pipeline config
- `docker-compose.obs.yaml` — one-command bring-up: Prometheus + Grafana + Jaeger + OTEL Collector
- `observability/README.md`

### Added — Advanced FinOps (`finops_intelligence/`)
- `CURIngestor` — AWS Cost and Usage Report ingestion via DuckDB with Parquet support
- `RISPOptimizer` — Reserved Instance + Savings Plan optimizer with 80% coverage cap (avoids over-commitment)
- `RightSizer` — CloudWatch metrics + curated AWS instance catalog right-sizer
- `CarbonTracker` — carbon emissions tracker with open-source regional grid coefficients
- `SavingsReporter` — executive savings report with CFO-ready summary
- `finops_intelligence/README.md`

### Added — Anthropic-Native Cost Optimization Layer (`core/`)
- `ModelRouter` — complexity-based routing (Opus 4.7 / Sonnet 4.6 / Haiku 4.5); ~95% cost savings vs. always-Opus baseline
- `ResultCache` — SQLite-backed result cache with TTL; identical requests return cached results
- `BatchCoalescer` — auto-accumulates requests and submits to Anthropic Batch API (50% discount)
- `StreamHandler` — SSE streaming response handler
- `FilesAPIClient` — Files API wrapper for document upload + reuse
- `InterleavedThinkingLoop` — interleaved thinking + tool-use loop for agentic tasks
- `CostEstimator` — per-call and per-session cost estimation with model-specific pricing
- `core/README.md`

### Changed — Existing Modules
- `agent_ops/` — orchestrator now wires through `core.AIClient` and `core.ModelRouter`
- `migration_scout/` — `batch_classifier.py` and `thinking_audit.py` added to existing module
- `policy_guard/` — `thinking_audit.py` added; extended-thinking path on high-stakes audits
- `finops_intelligence/` — `batch_processor.py` wired to new `BatchCoalescer`
- All modules — OTEL traces via `core.telemetry`; Prometheus metrics via `core.prometheus_exporter`

### Infrastructure
- `docker-compose.yml` — updated with observability sidecar ports
- `requirements.txt` — 15 new OSS dependencies added
- `.gitignore` — added `.eaa_cache/`, `*.db` entries

### Documentation
- `README.md` — full rewrite preserving badges + announcement blockquote; restructured for v0.2.0 platform scope
- `CHANGELOG.md` — created (this file)
- `docs/OPUS_4_7_UPGRADE.md` — v0.2.0 expansion section appended
- `docs/PLATFORM_ARCHITECTURE.md` — full platform architecture reference
- `docs/DEMO.md` — 5-min exec demo, 15-min technical demo, 3-min pitch scripts
- Per-module READMEs in `cloud_iq/adapters/`, `app_portfolio/`, `integrations/`, `iac_security/`, `observability/`, `finops_intelligence/`, `core/`

---

## [0.1.0] — 2026-04-10

Initial Opus 4.7 executive upgrade. Commit: `cdb8bdb`.

### Added
- `core/ai_client.py` — single Anthropic wrapper with 5-min + 1-hour prompt caching, native tool-use, extended-thinking support
- `core/models.py` — centralized model identifiers (Opus 4.7 / Sonnet 4.6 / Haiku 4.5)
- `agent_ops/orchestrator.py` — multi-agent orchestrator; Opus 4.7 coordinator + Sonnet 4.6 reporter + Haiku 4.5 workers
- `executive_chat/` — 1M-context unified briefing Q&A with 1-hour prompt cache
- `compliance_citations/` — Anthropic Citations API for grounded compliance evidence
- `migration_scout/batch_classifier.py` — Batch API bulk 6R scoring (50% discount)
- `migration_scout/thinking_audit.py` — extended-thinking 6R with Annex IV trace persistence
- `policy_guard/thinking_audit.py` — extended-thinking compliance audit path
- `finops_intelligence/batch_processor.py` — Batch API bulk FinOps scoring
- `mcp_server.py` — 19 MCP tools across all modules
- `docs/OPUS_4_7_UPGRADE.md` — executive brief, token economics, compliance mapping

### Changed
- Coordinator model upgraded from Opus 4.6 to Opus 4.7
- Report synthesizer upgraded from Haiku 4.5 to Sonnet 4.6
- Structured output switched from regex JSON parsing to native tool-use (schema-validated)
- Per-call telemetry extended to token-level: input / output / cache-read / cache-creation

### Fixed
- Thread-safety issues in AIAuditTrail chain writes
- API auth handling for MCP server tool dispatch
- Datetime serialization in SARIF export

---

[Unreleased]: https://github.com/HunterSpence/enterprise-ai-accelerator/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/HunterSpence/enterprise-ai-accelerator/compare/v0.2.0...v0.4.0
[0.2.0]: https://github.com/HunterSpence/enterprise-ai-accelerator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HunterSpence/enterprise-ai-accelerator/releases/tag/v0.1.0
