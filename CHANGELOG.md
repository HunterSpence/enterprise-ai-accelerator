# Changelog

All notable changes to Enterprise AI Accelerator are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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

[Unreleased]: https://github.com/HunterSpence/enterprise-ai-accelerator/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/HunterSpence/enterprise-ai-accelerator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HunterSpence/enterprise-ai-accelerator/releases/tag/v0.1.0
