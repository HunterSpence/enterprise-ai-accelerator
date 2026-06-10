# Roadmap — Enterprise AI Accelerator

Items are grouped by horizon: **NOW** (in v0.4.0 or already shipped), **NEXT** (next release cycle), **LATER** (future consideration). No specific dates. Status indicates current state.

---

## NOW — v0.4.0 (current release)

| Item | Rationale | Status |
|------|-----------|--------|
| **Fable 5 (`claude-fable-5`) as flagship model** | Replaces Opus 4.7; 80.3% SWE-Bench Pro, $10/$50 MTok — better capability at lower cost | ✅ Shipped |
| **`core/guardrails.py` — first-party guardrail engine** | Runtime input/output scanning mapped to OWASP LLM Top 10 2025; no external dependency | ✅ Shipped |
| **`evals/` harness — first-party offline CI gate** | Prevents capability regression on model upgrades; three suites (iac_policy_detection, six_r_classification, prompt_injection_redteam) | ✅ Shipped |
| **Orchestrator: first-party checkpoint/resume + HITL pause** | Enables long-running workflows to survive failures via `.eaa_checkpoints/`; human-in-the-loop for high-stakes decisions | ✅ Shipped |
| **Orchestrator: retry budget + cost-cap checkpoint** | Prevents runaway spend on stuck agentic loops | ✅ Shipped |
| **MCP Streamable HTTP transport (MCP 2025-03-26)** | Replaces HTTP+SSE; required for compatibility with major MCP clients that default to Streamable HTTP | ✅ Shipped |
| **MCP bearer-token auth (`EAA_MCP_AUTH_TOKEN`)** | Constant-time token validation on all MCP endpoints; prevents unauthorized tool invocation | ✅ Shipped |
| **MCP Merkle-audited tool calls** | SHA-256 chain over tool invocations; Article 12 / OWASP MCP08 mitigation | ✅ Shipped |
| **CO SB 26-189 + TX TRAIGA compliance frameworks (9→11)** | Colorado SB 26-205 repealed; replaced by SB 26-189 (eff. Jan 1, 2027). Texas TRAIGA eff. Jan 1, 2026 — already enforceable | ✅ Shipped |
| **NIST AI RMF 2.0 dashboard** | Control-level gap visibility; maps to existing compliance evidence | ✅ Shipped |
| **Anthropic Citations API anchor backends** | Grounds compliance evidence in source documents; reduces hallucination risk on audit queries | ✅ Shipped |
| **ML-BOM (CycloneDX v1.7)** | EU AI Act Article 11 / Annex IV implicitly requires model component inventory for high-risk systems | ✅ Shipped |
| **GOVERNANCE.md + PRICING.md + ROADMAP.md** | Procurement reviewers and open-source contributors require these before engagement | ✅ Shipped |

---

## NEXT — next release cycle

| Item | Rationale | Status |
|------|-----------|--------|
| **AWS Bedrock / GCP Vertex routing for Fable 5** | Eliminates direct Anthropic API dependency for sovereign deployments; no data leaves client cloud | Planned |
| **Multi-tenant RBAC** | Required for SaaS delivery model and enterprise customer isolation | Planned |
| **FOCUS 1.4 AI token economics columns** | FOCUS 1.4 announced at FinOps X June 2026; adds LLM token cost tracking to the CUR ingestor | Planned |
| **SOC 2 Type II evidence automation** | Automate evidence collection for the trust service criteria already instrumented | Planned |
| **Web UI (dashboard)** | Current interface is CLI + API; a read-only evidence dashboard reduces integration burden for procurement | Planned |
| **OWASP MCP Top 10 full coverage** | v0.4.0 closes MCP08; MCP01/MCP03/MCP05/MCP07 mitigations remain | Planned |
| **Claude Agent SDK migration** | `claude-agent-sdk` (pip) provides first-class agent lifecycle management; replaces current orchestrator custom loop | Evaluated |

---

## LATER — future consideration

| Item | Rationale | Status |
|------|-----------|--------|
| **MCP tool marketplace** | Community-contributed tools; requires governance + security review pipeline first | Idea |
| **High-availability (HA) deployment option** | Active-active Postgres + distributed audit trail for uptime SLAs; current architecture is single-node | Idea |
| **On-premises air-gap bundle** | Some government and defense customers cannot reach any external API; requires local model serving | Idea |
| **Eval benchmark publishing** | Published eval-suite results per model tier on each release; builds transparency for procurement | Idea |
| **ISO 27001 control mapping** | Complements ISO 42001 and SOC 2; overlapping evidence reduces collection burden | Idea |

---

## Known Non-Goals

The following are explicitly out of scope to keep the platform focused:

- **Becoming an LLM provider.** This platform consumes models; it does not train or host them.
- **Replacing cloud vendors.** The platform analyzes cloud infrastructure; it does not provision or manage it.
- **General-purpose agent framework.** The orchestrator is purpose-built for governance + FinOps workflows; it is not a replacement for LangChain or AutoGen.
