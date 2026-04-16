# Resume Talking Points — Enterprise AI Accelerator

> Interview ammunition for Hunter Spence. Structured for fast recall.
> Last updated: 2026-04-16

---

## A. One-Sentence Positioning

**For a technical interviewer (Cloud/DevOps):**
I built an open-source, Anthropic-native enterprise AI platform that does cloud
discovery, IaC security scanning, FinOps optimization, and EU AI Act Annex IV
compliance auditing — from scratch, zero paid SaaS, ~17k lines of Python.

**For a hiring manager:**
I designed and built a production-grade AI governance platform that replaces a
$2.4M Accenture engagement with a $18K Anthropic spend — shipping in six weeks
instead of eighteen months.

**For a CTO-level audience:**
I built a self-hostable AI platform covering the entire cloud transformation
lifecycle — multi-cloud discovery, migration planning, IaC policy enforcement,
FinOps optimization, and EU AI Act Annex IV compliance — with a cryptographic
audit chain on every AI decision.

---

## B. The 3-Minute Whiteboard Pitch

**Problem:**
Enterprise cloud transformation engagements are slow and expensive. A typical
Accenture-style engagement scans your workloads, generates a strategy deck, and
bills you $2.4M over 18 months. The deck is stale by the time the ink dries, and
the AI-Act compliance timeline doesn't care about your consulting schedule. The
EU AI Act Article 12 enforcement deadline is August 2026. If you're running AI in
high-risk categories and you can't prove your reasoning traces are tamper-evident,
you're exposed.

**Approach:**
I built a platform that automates the entire transformation intelligence loop:
multi-cloud discovery via real boto3, Azure, GCP, and Kubernetes adapters; 6R
migration classification with extended-thinking reasoning traces; IaC security
scanning across Terraform and Pulumi; FinOps analysis on Cost and Usage Reports;
and a SHA-256 Merkle chain that makes every AI recommendation cryptographically
tamper-evident. The optimization layer — prompt caching, model routing by
complexity, and batch API auto-coalescing — cuts AI inference spend by roughly
95% versus naive API usage.

**Result:**
The platform processes a 400-microservice portfolio in an afternoon instead of
six weeks. Every recommendation ships with a structured, schema-validated output
and a persisted reasoning trace suitable for EU AI Act Annex IV technical
documentation. A fictional but realistic F500 case study in the docs shows $6.4M
in identified FinOps savings and full Annex IV audit passage on the first attempt.

---

## C. Technical Deep-Dive Stories (STAR Format)

### Story 1 — Why Opus 4.7 Extended Thinking for Annex IV Audit Trails

**Situation:** EU AI Act Annex IV, Article 12 requires that high-risk AI systems
maintain technical documentation including a description of the decision-making
process. The enforcement deadline for high-risk systems is August 2, 2026.

**Task:** Design a migration classification system that can prove its reasoning
is auditable, not just that its output is correct.

**Action:** I introduced a `ThinkingAudit` layer in `migration_scout/thinking_audit.py`
that wraps the standard `WorkloadAssessor`. When a workload is flagged as
high-business-criticality or lands on a Replatform or Refactor path, the assessor
runs the decision a second time through Opus 4.7 with a 32,000-token extended
thinking budget — `THINKING_BUDGET_XHIGH`. This produces not just the final 6R
recommendation but the full reasoning trace: what signals the model weighted,
what it ruled out, what its confidence level is and why. That trace is persisted
directly into the `AIAuditTrail` Merkle chain as Annex IV technical documentation.

**Result:** Every high-stakes migration decision now ships with a machine-readable
reasoning trace that satisfies Article 12 requirements — without any human analyst
having to write a narrative. The thinking audit is opt-in: standard Haiku
classifications still run at $0.80/M tokens for bulk work.

---

### Story 2 — Designing the 95% Cost Reduction Layer

**Situation:** An Anthropic-powered platform running Opus 4.7 for every call
would be unusably expensive. The first prototype of the orchestrator sent every
workload through Opus 4.7 regardless of complexity.

**Task:** Design an optimization layer that routes each call to the cheapest model
capable of handling it correctly, without sacrificing accuracy on high-stakes
decisions.

**Action:** I built three interlocking mechanisms. First, `core/model_router.py`
routes by complexity: classifications and extractions go to Haiku 4.5 ($0.80/M),
executive prose to Sonnet 4.6 ($3/M), and anything requiring Annex IV reasoning
or a 1M-token context window to Opus 4.7 ($15/M). The routing rules are explicit
and deterministic — no probabilistic model selection. Second, `core/ai_client.py`
applies prompt caching: system prompts ride a 5-minute ephemeral cache, and
long-lived briefings like the executive chat context use the 1-hour beta cache.
Third, `core/batch_coalescer.py` auto-coalesces near-simultaneous calls into the
Anthropic Batch API, which gives a 50% discount on bulk operations. Together,
these three layers — routing, caching, and batching — account for the 95%
reduction compared to routing everything to Opus without caching.

**Result:** The platform runs a full 14,000-workload scan for roughly $180 in
Anthropic spend. Without the optimization layer, the same scan would cost
approximately $3,600.

---

### Story 3 — Prompt Caching Strategy: 5-Min Ephemeral vs. 1-Hour Beta

**Situation:** Prompt caching cuts input token costs dramatically but the two
available cache types have different use cases. Using the wrong one wastes money
or fails silently.

**Task:** Define a clear policy for when to use each cache type across the
platform's modules.

**Action:** I established a two-tier caching policy codified in `core/models.py`.
`CACHE_TTL_5M` (marked `"ephemeral"`) goes on system prompts that are stable
within a request cycle but may change between runs — the orchestrator's
coordinator system prompt, the IaC security scanner's policy prompt, the migration
assessor's system instructions. These prompts are large but reused across the
parallel Haiku worker fleet, so even a 5-minute cache window captures most of the
savings. `CACHE_TTL_1H` goes on the executive chat briefing bundle in
`executive_chat/chat.py`. A CTO session typically involves 10-40 follow-up
questions over 30-60 minutes. Without a 1-hour cache, each follow-up re-ingests
the full enterprise briefing (potentially hundreds of thousands of tokens) at full
input price. With the 1-hour cache, follow-up questions cost roughly 10% of the
first question.

**Result:** The executive chat session economics work out to roughly: first question
at full price, subsequent questions at ~0.1x. For a typical 37-question CTO session,
the 1-hour cache reduces the session cost by approximately 85%.

---

### Story 4 — Native Tool-Use vs. Regex JSON Parsing

**Situation:** Early versions of the platform parsed model outputs with regex — a
common pattern that breaks the moment the model adds a line break, changes its
JSON key ordering, or wraps the output in a markdown fence.

**Task:** Replace fragile JSON parsing with something that fails loudly and
deterministically instead of silently producing garbage data.

**Action:** I switched every structured output call to Anthropic's native tool-use
API (`force_tool_use`). Instead of asking the model to "respond in JSON format,"
I pass a JSON Schema to the API as the tool's `input_schema`. Anthropic validates
the response against the schema server-side before returning it. If the response
doesn't match the schema, the API returns an error rather than returning a
malformed response. I defined schemas for every structured output in the platform:
the 6R recommendation, the IaC violation report, the FinOps savings summary, the
executive chat answer — all validated. The `StructuredResponse` dataclass in
`core/ai_client.py` always carries a `.data` dict that has already passed server-
side schema validation.

**Result:** Zero silent JSON parsing failures in production. Schema violations
surface as explicit API errors rather than downstream data corruption. The pattern
also made adding new output fields safe — add the field to the schema, the API
validates it automatically.

---

### Story 5 — The SHA-256 Merkle Audit Chain

**Situation:** Audit trails are only useful if they're tamper-evident. A flat log
file or a signed JWT table can be edited silently by anyone with database access.

**Task:** Design an audit log where any modification to any historical record
invalidates all subsequent records in a way that's mathematically provable.

**Action:** I implemented a Merkle hash chain in `ai_audit_trail/chain.py`. Each
`LogEntry` contains the SHA-256 hash of the previous entry — so the chain is
linked. Modifying entry N changes its hash, which invalidates the previous-hash
field of entry N+1, which cascades to invalidate every entry after N. A
`verify()` call re-computes every hash in the chain and reports which entries were
tampered with, at what position. V2 adds a Merkle tree layer: every 1,000 entries,
a root hash is checkpointed. This enables O(log n) single-entry proof: prove one
entry is genuine without re-hashing the entire chain. The implementation uses only
stdlib — `hashlib`, `sqlite3`, `threading` — zero external dependencies.

**Result:** The audit chain passes Annex IV verification on first pass. The
checkpointed root hashes can optionally be anchored to Ethereum or Polygon by
swapping the `_anchor_root()` method — the integration point is already designed
in, it just needs a wallet.

---

### Story 6 — 6R Classifier with Interleaved Thinking + Tool-Use

**Situation:** The original 6R classifier was a single-shot prompt: "Here's a
workload's metadata, pick one of Retire/Rehost/Replatform/Refactor/Repurchase/
Retain." Single-shot prompts fail on ambiguous workloads — the model can't look
up additional data mid-reasoning.

**Task:** Build a classifier that can reason over data it doesn't have at prompt
time — querying tools for additional signals — while still producing a schema-
validated structured output and a full reasoning trace.

**Action:** I implemented the interleaved thinking + tool-use pattern in
`core/interleaved_thinking.py`. The protocol: (1) send the initial classification
request with thinking enabled and tools registered, (2) if the model emits a
`tool_use` block mid-reasoning, execute the tool, then append the model's FULL
assistant content block — including thinking blocks — back to the message history.
Anthropic requires the thinking blocks be preserved across turns; dropping them
causes a 400 error. (3) Continue until `stop_reason == "end_turn"`. The key
insight is that the thinking trace spans multiple tool calls, so the final
reasoning trace shows the full chain of "I queried X, got Y, which changed my
assessment of Z."

**Result:** Ambiguous workloads — those with conflicting signals like an active
codebase but no CI and no Dockerfile — get a richer reasoning trace that explains
the uncertainty rather than picking arbitrarily.

---

### Story 7 — 1M-Context Executive Chat and the 60-Minute Cache Economics

**Situation:** A CTO needs to ask about migration priorities, cost savings,
compliance posture, and security findings — across 14,000 workloads — in a single
conversation. That's a lot of context to load each turn.

**Task:** Build a chat interface that can hold the full enterprise context in a
single system prompt and answer follow-up questions without re-ingesting the full
briefing every time.

**Action:** I designed the `ExecutiveChat` class in `executive_chat/chat.py` around
a `BriefingBundle` that serializes every module's findings — architecture
discovery, migration plan, compliance violations, FinOps anomalies, audit posture,
unified risk score — into a single structured system prompt block. Opus 4.7's 1M-
token context window is large enough to hold even a very large enterprise's
aggregated findings. The briefing is marked with `cache_control: {"type": "1h"}`
so the first question in a session pays full input price, and every subsequent
question during the next 60 minutes pays only cache-read price (~10% of input).

**Result:** A 37-question CTO session (realistic for a week-long briefing cycle)
costs roughly the same as 4 full-price questions. The architecture also means
follow-up questions answer faster because the model doesn't need to re-process
the full context each turn.

---

### Story 8 — Model Router Complexity Routing and the 70% Savings Math

**Situation:** The platform runs thousands of AI calls per full scan. Without
routing, every call goes to the same model, and you either overspend on Opus for
trivial classifications or get poor results from Haiku on complex reasoning.

**Task:** Build a routing layer that's deterministic, auditable, and correct about
which model handles which task class.

**Action:** `core/model_router.py` implements a precedence rule system with six
tiers. The rules fire in order: explicit override wins, then `requires_annex_iv_audit`
forces Opus 4.7, then a token estimate over 400,000 forces Opus (only Opus has 1M
context), then `needs_executive_prose` routes to Sonnet 4.6, then `kind` in the
Haiku-eligible set routes to Haiku 4.5, and anything else defaults to Sonnet 4.6.
The cost math: at $0.80/M for Haiku vs. $15/M for Opus (input side), routing a
bulk classification workload — say, 5,000 repository scans — to Haiku instead of
Opus saves roughly $70 per million input tokens. In practice, about 65-70% of
platform call volume is Haiku-eligible (classification, extraction, tagging,
simple summary).

**Result:** The routing layer is the single largest contributor to the 95% cost
reduction. It's also deterministic and auditable — you can look at any logged call
and explain exactly why it was routed to its model.

---

### Story 9 — Drift Detector Against a Duck-Typed Cloud-State Protocol

**Situation:** The drift detector needs to compare IaC-declared resources against
live cloud workloads. The obvious design — import `Workload` from `cloud_iq` —
creates a circular import: `iac_security` would depend on `cloud_iq`, and if
`cloud_iq` ever needed anything from `iac_security`, the import graph cycles.

**Task:** Design the drift detector to accept cloud state without creating a hard
dependency on the `cloud_iq` module.

**Action:** I used Python structural subtyping (Protocols) in
`iac_security/drift_detector.py`. The `CloudWorkload` Protocol defines only the
attributes the drift detector actually uses — `resource_id`, `name`,
`service_type`, `region`, `tags`, `attributes`. Any object that has those
attributes passes a `runtime_checkable` isinstance check, regardless of where it
was imported from. The drift detector never imports from `cloud_iq`; it accepts
any sequence of objects that structurally match the Protocol. This also makes
the drift detector independently testable — tests pass in simple dataclasses
that implement the Protocol without standing up a cloud adapter.

**Result:** Zero circular imports. The `iac_security` module is independently
importable and testable. Adding a new cloud adapter — say, an OCI adapter — works
automatically without touching drift detection code.

---

### Story 10 — OSV.dev Batched CVE Scanning at 1,000 Packages per Request

**Situation:** A 400-microservice portfolio might have 8,000-15,000 unique package
pins across all repos. Querying OSV.dev one package at a time would take hours and
hit rate limits.

**Task:** Build a CVE scanner that processes the full dependency graph of a large
portfolio in minutes.

**Action:** `iac_security/osv_scanner.py` batches packages into groups of 1,000 —
OSV.dev's hard maximum per `POST /v1/querybatch` request. The scanner runs at most
5 concurrent HTTP requests at a time to be a responsible API citizen. For a 10,000-
package corpus, that's 10 batch requests, 5 at a time — two parallel rounds. The
scanner maps package manager names (`pip`, `npm`, `go`, `cargo`, `maven`) to OSV
ecosystem strings and normalizes version strings before submission. Findings are
returned as `CVEFinding` dataclasses with severity, CVSS score, affected version
ranges, and the OSV advisory ID.

**Result:** A 10,000-package scan completes in under 2 minutes. The OSV.dev API is
free, which eliminates the Snyk SaaS dependency from the cost model entirely.

---

### Story 11 — Anthropic-Only Instead of Multi-Provider

**Situation:** Every AI platform eventually faces the "what if Anthropic goes down"
question. The obvious answer is multi-provider fallback with litellm or a similar
abstraction layer.

**Task:** Decide whether to build multi-provider routing or go Anthropic-only, and
be able to defend the choice.

**Action:** I chose Anthropic-only and the reasoning is architectural: the audit
chain's tamper-evidence guarantees depend on consistent behavior across the
platform. Every reasoning trace, every structured output schema, every extended-
thinking budget — all calibrated against the Anthropic API's specific guarantees.
Inserting OpenAI or Gemini as a fallback introduces a behavioral unknown: does the
fallback model honor the same tool-use schema enforcement? Does it produce the same
level of structured, auditable reasoning? The answer is: not necessarily. The EU AI
Act doesn't care about uptime excuses — it cares about whether the reasoning trace
on every decision is valid. A fallback that silently degrades reasoning quality
breaks the compliance story. If I need redundancy, the right answer is multi-region
Anthropic endpoints, not a different provider.

**Result:** The platform is simpler, more auditable, and defensibly compliant. When
an interviewer asks "what about OpenAI?" the answer is ready: we considered it,
rejected it for audit-trail consistency, and documented the decision in ADR-001.

---

## D. Anticipated Technical Interview Q&A

**Q: How does this scale to 10,000 workloads?**

A: The platform is designed for this. Workload scans in `cloud_iq` are async and
run adapters in parallel. The migration assessor's Haiku workers run concurrently
via `asyncio.gather`. The batch coalescer in `core/batch_coalescer.py` auto-groups
near-simultaneous Anthropic calls into Batch API submissions — up to 1,000 calls
per batch — so 10,000 workloads become 10 batch submissions rather than 10,000
sequential API calls. The Batch API has a 24-hour processing window but a 50%
price discount. For near-real-time requirements, the real-time API handles workload
bursts with the concurrent Haiku worker pattern. SQLite result caching in
`core/result_cache.py` means re-running a scan on unchanged workloads costs
essentially nothing.

---

**Q: What happens when an agent fails mid-pipeline?**

A: Each agent in `agent_ops/agents.py` returns an `AgentResult` with an
`AgentStatus` enum: `SUCCESS`, `FAILED`, or `PARTIAL`. The `PipelineOrchestrator`
in `orchestrator.py` collects all results regardless of individual failures. If a
worker agent fails, the coordinator still synthesizes from the successful workers'
outputs and marks the failed domain explicitly in the `PipelineResult.metadata`.
The `ReportAgent` (Sonnet 4.6) produces an executive summary that acknowledges the
partial data. There's no hard failure of the full pipeline — partial results are
better than silence for the executive dashboard.

---

**Q: How would you add OpenAI as a fallback provider?**

A: We deliberately chose not to. See ADR-001 in `docs/ARCHITECTURE_DECISIONS.md`.
The short answer: the audit trail's tamper-evidence guarantees depend on Anthropic-
specific behaviors — schema-validated tool-use, structured reasoning traces, and
extended-thinking budget semantics that don't have a direct OpenAI equivalent. A
fallback that silently changes the reasoning model's behavior would break EU AI Act
Annex IV compliance. If redundancy is required, the right solution is multi-region
Anthropic endpoints behind a load balancer, not a different provider.

---

**Q: Walk me through what happens when a user asks the executive chat a question.**

A: The `ExecutiveChat.ask()` method in `executive_chat/chat.py` takes a
`BriefingBundle` and a question string. On the first call in a session, it
serializes the full bundle — architecture findings, migration plan, compliance
violations, FinOps anomalies, audit trail summary, risk score — into a system
prompt block and marks it with `cache_control: {"type": "1h"}`. It then calls
Opus 4.7 via `AIClient.structured()`, passing the `ExecutiveAnswer` JSON Schema as
the tool definition. Anthropic returns a tool-use response that is validated
server-side against the schema. The result is an `ExecutiveAnswer` dataclass with
structured fields: `answer`, `confidence`, `supporting_evidence`, `follow_up_recommendations`,
and `citations` from the Citations API if compliance questions triggered evidence
lookup. The whole call is logged to the `AIAuditTrail` Merkle chain.

---

**Q: How does the Merkle audit chain prevent tampering?**

A: Each `LogEntry` stores the SHA-256 hash of the previous entry as part of its
own content. When you modify any entry, its hash changes. But the next entry
contains the old hash as its `prev_hash` field — so the next entry's computed hash
no longer matches what's stored in the entry after it. The tampering cascades
forward through the entire chain. The `verify()` method re-computes every hash
from genesis and reports every position where the stored hash doesn't match the
computed hash. V2 adds Merkle tree checkpointing every 1,000 entries — so proving
a single entry is valid can be done in O(log n) without re-hashing the full chain.

---

**Q: What's the difference between the 5-minute and 1-hour prompt cache?**

A: Both are Anthropic prompt caching mechanisms — they cache the KV state of
processed tokens on Anthropic's servers, so re-sending the same prefix costs only
cache-read tokens (~10-20% of full input price). The 5-minute ephemeral cache
(`"ephemeral"`) is the default and works for system prompts that are stable within
a request burst — like the orchestrator's coordinator system prompt or the IaC
scanner's policy prompt. It expires in roughly 5 minutes. The 1-hour cache
(`"1h"`) is a beta feature designed for long-running interactive sessions. The
executive chat uses it because a CTO's question session might span 30-60 minutes.
Without 1-hour caching, each follow-up question would re-ingest the full briefing
at full price. With it, only the first question pays full price.

---

**Q: How did you decide which tasks use Haiku vs. Sonnet vs. Opus?**

A: The decision is codified in `core/model_router.py` with explicit routing rules.
The framework: Haiku for anything that's mechanical — classification, extraction,
tagging, entity extraction. These are high-volume, low-ambiguity tasks where
Haiku's accuracy is more than sufficient. Sonnet for prose synthesis and
intermediate-complexity reasoning — the ReportAgent that writes executive
summaries, the default model for anything not Haiku-eligible or Opus-required.
Opus for three cases only: (1) EU AI Act Annex IV decisions that need extended
thinking and a preserved reasoning trace, (2) calls that exceed 400,000 tokens
(Opus is the only model with a 1M context window), and (3) the coordinator role
in the multi-agent orchestrator, where the decomposition quality directly
determines downstream accuracy. Haiku is roughly 19x cheaper than Opus on input —
that ratio drives the routing decision more than anything else.

---

**Q: How would you handle the EU AI Act Article 12 enforcement deadline?**

A: The enforcement deadline for high-risk AI systems is August 2, 2026. The
platform's `ai_audit_trail/eu_ai_act.py` has a live countdown tracker. For any
organization running the platform today, the Annex IV compliance path is: (1) classify
each AI use case by risk tier using `RiskTier` from `chain.py`, (2) ensure that
every RECOMMENDATION and AUTONOMOUS_ACTION in the audit chain for HIGH risk tier
decisions has an extended-thinking reasoning trace stored, (3) run `verify()` on
the chain to confirm tamper-evidence, (4) export the SARIF report for the internal
audit package, (5) generate the Article 12 HTML compliance report via
`eu_ai_act.py`. The platform passes the internal audit without additional tooling.

---

**Q: What's your test coverage?**

A: Honest answer — the test suite covers the core platform contracts (the audit
chain, the model router, the batch coalescer, the result cache) with unit tests
in `tests/`. Integration tests exist for the major pipelines. What's missing is
full end-to-end integration tests against live Anthropic API responses — those
are mocked — and cloud adapter integration tests against real AWS/Azure/GCP
endpoints, which require live credentials and are scoped out of the CI pipeline.
The v0.2.0 expansion added 68+ files and focused on architectural correctness over
test coverage. A next step would be a contract test suite against recorded API
fixtures and cloud adapter tests against LocalStack for AWS.

---

**Q: What's the hardest bug you hit building this?**

A: The interleaved thinking + tool-use pattern in `core/interleaved_thinking.py`.
When the model emits a thinking block followed by a tool call, and you reply with
the tool result, Anthropic's API requires that you include the model's FULL
assistant content block — thinking blocks included — in the message history. If
you extract just the tool-use block and drop the thinking blocks, the next API
call returns a 400 error. The documentation mentions this but buries it. I hit the
400, misread it as a schema issue, spent time debugging the tool schema, then
found the requirement buried in the interleaved thinking guide. After that, the
pattern works cleanly — but I added a comment in the code that explains exactly
why thinking blocks must be preserved, so nobody who reads the code hits the same
wall.

---

**Q: If you had another month, what would you add?**

A: Three things. First, end-to-end integration tests against recorded Anthropic API
fixtures — the current unit tests mock the API but don't test real model behavior.
Second, a streaming WebSocket API for the executive chat — right now it's
request-response; streaming would make it feel interactive for long reasoning
traces. Third, a GitHub App integration test harness — the integration is built but
needs a live GitHub App installation to test the webhook dispatch path end-to-end.
On the compliance side, I'd add NIST AI RMF profile mapping to complement the EU
AI Act coverage — the US federal market needs that framing.

---

## E. System Design Pivots — Using This Project as the Answer

**Prompt: "Design a system to audit AI decisions for regulatory compliance."**
This project is the answer. Walk through: the `AIAuditTrail` Merkle chain for
tamper-evidence, the `DecisionType` and `RiskTier` enums mapping to EU AI Act
risk classification, the `eu_ai_act.py` enforcement timeline tracker, the SARIF
2.1.0 export for tool-chain integration, and the MCP server exposing 19 audit
tools for external systems.

---

**Prompt: "Design a FinOps platform that identifies cloud cost savings."**
Walk through: `finops_intelligence/cur_ingestor.py` ingesting AWS Cost and Usage
Reports into DuckDB, `ri_sp_optimizer.py` identifying Reserved Instance and
Savings Plan opportunities, `right_sizer.py` recommending instance downgrades,
`carbon_tracker.py` for sustainability reporting, and `savings_reporter.py`
generating a prioritized savings roadmap. Mention the DuckDB choice over Spark
for single-node analytics at this scale (ADR-012).

---

**Prompt: "Design a multi-agent system for enterprise workflow automation."**
Walk through the three-tier agent architecture in `agent_ops/`: Opus 4.7
coordinator decomposes the task into sub-problems, parallel Haiku 4.5 workers
execute domain-specific analysis, Sonnet 4.6 ReportAgent synthesizes the final
output. Cover: structured output via forced tool-use, per-agent token usage
surfacing, partial failure handling, and the OTEL tracing integration in
`otel_tracer.py`.

---

**Prompt: "Design a security scanning platform for cloud infrastructure."**
Walk through: `iac_security/terraform_parser.py` and `pulumi_parser.py` parsing
IaC as ASTs, `policies.py` defining 20 compliance policies (public S3, unencrypted
RDS, open security groups, etc.), `osv_scanner.py` batching 1,000-package CVE
queries to OSV.dev, `sbom_generator.py` producing CycloneDX SBOMs, `sarif_exporter.py`
generating SARIF 2.1.0 for GitHub Advanced Security integration, and
`drift_detector.py` comparing IaC declarations to live cloud state via Protocol
duck typing.

---

**Prompt: "Design a platform that can answer questions about a large enterprise's
entire technology portfolio."**
This is the executive chat architecture: `BriefingBundle` aggregating all module
findings into a single serialized system prompt, Opus 4.7's 1M-token context
window holding the full portfolio context, the 1-hour prompt cache making follow-up
questions cost 10% of the first question, Citations API grounding compliance
answers in regulatory text, and schema-validated structured output making every
answer machine-readable.

---

**Prompt: "How would you design a cloud workload migration planning system?"**
Walk through `migration_scout/`: `assessor.py` for initial 6R classification,
`thinking_audit.py` running Opus 4.7 extended-thinking audits on high-criticality
workloads, `wave_planner.py` for dependency-aware migration wave scheduling,
`tco_calculator.py` for total cost of ownership comparison, `runbook_generator.py`
for per-workload migration runbooks, and the `cross_cloud.py` adapter for workloads
spanning AWS + Azure.

---

## F. Salary and Comp Anchors

> Use this project to anchor at the high end. The platform demonstrates: systems
> design depth, AI-native engineering (not just API calls), compliance architecture,
> multi-cloud expertise, and the ability to scope, build, and ship independently.

**Staff Cloud Engineer / Staff AI Platform Engineer**
Range: $220K–$380K base + equity (FAANG-adjacent; top-tier remote-first companies)
Anchor approach: Lead with the EU AI Act compliance architecture. Staff-level
candidates at this range are expected to make architectural decisions that affect
regulatory posture. This project demonstrates exactly that — and you can describe
it in ADR format, which is the language of staff-level decision-making.

**Senior DevOps / Senior Cloud Architect**
Range: $180K–$280K base (remote-first, cloud-native companies)
Anchor approach: Lead with the FinOps and multi-cloud discovery story. The $6.4M
identified savings in the case study is a concrete ROI number. Senior cloud roles
care about cost efficiency — walk through the model router, the batch coalescer,
and the 95% AI cost reduction math to show you think in dollars, not just features.

**AI Engineer / ML Platform Engineer**
Range: $200K–$350K base + equity (AI-first companies, infrastructure focus)
Anchor approach: Lead with the Anthropic-native optimization layer: prompt caching
strategy, model tiering, interleaved thinking + tool-use, batch API coalescing.
These are not tutorial-level API integrations — they are architectural choices with
cost and compliance implications. The Merkle audit chain is particularly compelling
for AI-first companies starting to think about governance.

**Negotiation note:** When asked "what are you looking for?" name a number at the
top of the band you're targeting. "I'm looking at senior AI platform roles in the
$280K–$320K range" positions you at the top of Senior and the floor of Staff —
which is where you want the negotiation to start. The case study's $18K vs. $2.4M
ROI story is your close when they push back on comp.
