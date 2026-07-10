# Pricing — Enterprise AI Accelerator

> **Evaluation prototype — pre-production, solo-maintained. Not a certification and not a compliance determination.**

This document describes commercial options for organizations that need support, hosting, or delivery services around the open-source codebase. All numbers are starting points for conversation, not binding quotes. **Only "OSS Core" and "Fixed-Scope Delivery Services" are things you can actually buy today.** Every other section below is a planned offering, not a live product — see the status note on each.

---

## OSS Core — Free

The full platform is MIT-licensed and free to use, modify, and deploy. No registration, no license key, no usage reporting back to the maintainer.

What you get: every module in this repository, including compliance frameworks (11 frameworks in v0.4.0), MCP server, FinOps intelligence, app portfolio scanning, IaC security, observability stack, and the complete eval harness.

What you do not get with the free tier: SLAs, support response times, or hosted infrastructure.

---

## Accelerator Cloud — Managed Hosting (PLANNED — NOT AVAILABLE TODAY)

> **Status: not built.** There is no managed multi-tenant hosting, no per-seat billing infrastructure, and no SSO/SAML implementation in the platform today (see [ROADMAP.md](ROADMAP.md) — multi-tenant RBAC and web UI are both "Planned"). The tiers below describe a *future* offering, not something you can purchase or provision right now. Do not send payment against this section.

For teams that will want the platform running without managing infrastructure, once built:

| Tier (planned) | Target price | Would include |
|------|-------|---------|
| **Starter** | $299 / month | Single tenant, up to 5 users, 50K API calls/month, email support (2-business-day response) |
| **Professional** | $499 / month | Single tenant, up to 20 users, 200K API calls/month, Slack support (next-business-day response), compliance report exports |
| **Business** | $799 / month | Single tenant, unlimited users, 1M API calls/month, priority Slack support (4-hour response), SSO/SAML, custom retention |

Overage (planned): $0.0008 per API call above tier limit. Annual billing (planned): 2 months free (equivalent to ~17% discount).

---

## Enterprise Self-Hosted — License + Support

For organizations that require all computation inside their own cloud or data center. **Note: this is a solo-maintained project.** Support is delivered by one person on business hours (US Eastern); there is no on-call team behind these tiers today, so "24×7" below is aspirational, not a staffed SLA — treat it as best-effort until a support team exists.

| Tier | Annual Price | Included |
|------|-------------|---------|
| **Starter** | $25,000 / year | Deployment assistance (up to 16 hours), 6-month support contract (8×5, 1-business-day best-effort response), one model-refresh update |
| **Standard** | $50,000 / year | Deployment assistance (up to 40 hours), 12-month support contract (8×5, same-business-day best-effort response), all model-refresh updates, compliance evidence pack walkthrough |
| **Enterprise** | $80,000 / year | Deployment assistance (up to 80 hours), 12-month support contract (best-effort P1 response outside business hours — NOT a staffed 24×7 SLA; same-business-day for P2), all updates, dedicated Slack channel, architecture review session |

All tiers include: source code access (already MIT), right to deploy in client cloud, training session (2 hours), and access to the private issue tracker for security disclosures.

AWS Bedrock / GCP Vertex routing (planned, see ROADMAP.md) will be included in all self-hosted tiers once available — no price increase.

---

## Fixed-Scope Delivery Services

For organizations that need implementation work, not just software.

| Engagement | Price Range | Scope |
|-----------|-------------|-------|
| **EU AI Act Evidence Pack** | $15,000 – $25,000 | Annex IV documentation, Article 9–15 gap assessment, compliance officer walkthrough, deliverable: `docs/EU_AI_ACT_EVIDENCE_PACK.md` template populated for client's specific systems |
| **FinOps Baseline + Optimization** | $20,000 – $35,000 | CUR ingestion setup, right-sizing analysis, RI/SP optimizer tuned to client fleet, FOCUS 1.3 export, deliverable: board-ready savings report |
| **Full Platform Deployment** | $35,000 – $50,000 | All modules deployed in client cloud, CI/CD pipeline, SSO integration, compliance framework mapping, 30-day hypercare |

Pricing varies by environment complexity and number of cloud accounts. Engagements are fixed-scope (change orders for out-of-scope work). Travel not included.

---

## FinOps Outcome Pricing

For clients with documented, attributable cloud spend that the platform will optimize.

**Structure:** No upfront fee. At month 6, the client pays **10% of realized savings** for the prior 6 months as a one-time success fee. Realized savings = (baseline spend) − (actual spend) over the period, validated against FOCUS 1.3 CUR exports.

**Guardrails:**
- Minimum engagement: $200K/month cloud spend (otherwise fixed-scope is more efficient).
- Savings calculation methodology agreed in writing before engagement start.
- Cap: success fee not to exceed $200K in the first 6-month period.
- After month 6, the client owns the platform and tooling with no recurring payments.

This model follows patterns used by FinOps-native vendors for outcome-linked engagements. It is not appropriate for all clients; fixed-scope is lower-risk for smaller environments.

---

## 3-Year Cost Comparison — support/license fees only (illustrative, not a TCO)

> **This table is illustrative and incomplete — it is not a total cost of ownership.** It compares only support/license/consulting fees. It excludes cloud infrastructure, Anthropic API usage, implementation and integration labor, and ongoing operations for every row, including this platform's own. A real TCO comparison would need to add those costs to all four rows before they're comparable. Actual costs depend on scope, team size, and vendor negotiation. Big-6 figures are drawn from publicly available case studies and industry analyst estimates (Gartner, Forrester) — not independently audited.

| Option | Year 1 (fees only) | Year 2 (fees only) | Year 3 (fees only) | 3-Year Total (fees only) |
|--------|--------|--------|--------|-------------|
| **Enterprise AI Accelerator (self-hosted, Standard tier support)** | $50K | $50K | $50K | **$150K** |
| **Enterprise AI Accelerator (self-hosted, Enterprise tier support)** | $80K | $80K | $80K | **$240K** |
| **Commercial AI governance platform (mid-market)** | $180K–$400K | $180K–$400K | $180K–$400K | **$540K–$1.2M** |
| **Big-6 consulting-led AI transformation (typical scope)** | $1.1M–$4M | $1.1M–$4M | $1.1M–$4M | **$3.2M–$12M** |

Big-6 range reflects engagements from Accenture AI Refinery (NVIDIA NIM-locked, co-built with NVIDIA), Deloitte AI advisory (hallucination incidents documented publicly; see `docs/SOVEREIGN_DEPLOYMENT.md`), IBM watsonx advisory, and comparable large-scale programs. The range is wide because scope varies significantly.

This platform's *support fee* is lower primarily because: (1) MIT license eliminates per-seat or per-use licensing; (2) self-hosted deployment keeps cloud costs inside existing contracts; (3) no proprietary dependencies means no vendor renegotiation risk at renewal. This is not a claim of "90-95% savings" on your total program cost — your infra, API usage, and integration labor still apply on top of every row above.

---

## Procurement Notes

- All listed prices exclude cloud infrastructure costs (compute, storage, Anthropic API calls). Anthropic API costs at current Fable 5 pricing ($10/$50 MTok) typically run $200–$2,000/month depending on volume.
- Prices are starting points. Multi-year commitments, non-profit, and government education rates available — ask.
- Invoiced in USD. Wire transfer or ACH. Net-30 standard; Net-15 for annual prepay.
- No purchase order minimum for cloud tiers. Enterprise self-hosted engagements require a signed statement of work.
