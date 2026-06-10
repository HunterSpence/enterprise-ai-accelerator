# Sovereign Deployment Guide

**Platform:** Enterprise AI Accelerator v0.4.0

This document describes how to deploy the platform so that all computation and data storage remain inside the client's cloud environment, with no data sent to external parties except for Anthropic API inference calls.

---

## Data Flow Overview

```
Client Cloud Boundary
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────────┐   │
│  │ Enterprise  │    │   Platform   │    │   audit_trail.db  │   │
│  │ Cloud Data  │───▶│   Modules    │───▶│   (SQLite/PG)     │   │
│  │ (CUR, IaC,  │    │ (compute in  │    │                   │   │
│  │  app repos) │    │ client VMs)  │    │ All logs stay     │   │
│  └─────────────┘    └──────┬───────┘    │ inside boundary   │   │
│                             │            └───────────────────┘   │
└─────────────────────────────┼───────────────────────────────────┘
                               │  HTTPS (TLS 1.3)
                               │  Prompts only — no source data
                               ▼
                    ┌──────────────────────┐
                    │  Anthropic API       │
                    │  (single external    │
                    │   call point)        │
                    └──────────────────────┘
```

**What crosses the boundary:** Prompts sent to the Anthropic API. These prompts contain analysis requests and context windows, not raw customer data (e.g., a prompt asks the model to analyze a finding description, not to ingest a full production database).

**What stays inside the boundary:** Cloud inventory data, IaC files, CUR/billing data, compliance evidence, audit logs, ML-BOM, all platform state.

---

## Anthropic API as the Only External Call

The platform makes exactly one category of external network call: HTTPS POST to `api.anthropic.com`. No other external calls are made at runtime.

Dependencies that might be expected to call home:

| Dependency | External call? | Notes |
|-----------|---------------|-------|
| Anthropic SDK | Yes — to `api.anthropic.com` only | All model inference |
| boto3 (AWS) | Yes — to AWS APIs | Only when cloud discovery is enabled; uses client's own credentials |
| azure-mgmt-* | Yes — to Azure APIs | Same; client credentials only |
| google-cloud-* | Yes — to GCP APIs | Same; client credentials only |
| kubernetes client | Yes — to client k8s API server | Client-internal |
| DuckDB | No | Local process only |
| SQLite | No | Local process only |
| structlog, OpenTelemetry | No external calls | OTEL exports only where explicitly configured |
| `core/guardrails.py` (first-party, no external calls) | No | First-party; no external calls |
| `evals/` (first-party offline runner, no telemetry) | No | First-party; no external calls |

To verify: `python -m compliance_citations.cli --network-audit` lists all external hosts the platform will contact given the current configuration.

---

## No Telemetry

The platform contains no analytics, crash reporting, license check, or usage telemetry that contacts the maintainer or any third-party service. The MIT license requires no registration. There is no "phone home" mechanism.

The only way telemetry leaves the client environment is if the operator explicitly configures:
- An OTEL Collector endpoint (`OTEL_EXPORTER_OTLP_ENDPOINT` env var) — operator-controlled
- A Prometheus remote write target — operator-controlled

Neither is configured by default.

---

## AWS Bedrock / GCP Vertex Routing

**Status: roadmap item (not yet available in v0.4.0).**

Future releases will support routing Fable 5 / Claude model calls through AWS Bedrock or GCP Vertex AI instead of the direct Anthropic API. This eliminates the single external call point entirely for clients who require all traffic to stay within a hyperscaler's network boundary.

When available, the routing will be controlled by a single environment variable:

```bash
# Direct Anthropic API (current default)
ANTHROPIC_TRANSPORT=direct

# AWS Bedrock (planned)
ANTHROPIC_TRANSPORT=bedrock
AWS_BEDROCK_REGION=us-east-1

# GCP Vertex AI (planned)
ANTHROPIC_TRANSPORT=vertex
VERTEX_PROJECT_ID=my-project
VERTEX_LOCATION=us-east1
```

Model availability on Bedrock and Vertex for Fable 5 / Opus 4.8 is unconfirmed at time of writing — these depend on Anthropic's partner agreements with each hyperscaler. The routing interface will be implemented when Anthropic confirms availability.

---

## Air-Gap Considerations

Full air-gap (no internet access at all) is not supported in v0.4.0. The Anthropic API cannot be reached from an air-gapped environment.

Partial mitigations for restricted networks:

1. **Allowlist approach:** Restrict outbound HTTPS to `api.anthropic.com` only. All other traffic can be blocked.
2. **Proxy:** Standard HTTP proxy (`HTTPS_PROXY` env var) is respected by the Anthropic SDK.
3. **Bedrock/Vertex routing (planned):** When available, routes all inference through the client's existing hyperscaler connectivity (VPC endpoint or Private Service Connect), removing the direct Anthropic internet dependency.

Full offline / air-gap support (local model serving) is a later-horizon roadmap item. See `ROADMAP.md`.

---

## Counter to Big-6 Lock-In

### Accenture AI Refinery

Accenture's AI Refinery is co-built with NVIDIA, using NeMo and NIM as the inference layer. This creates a two-vendor dependency: Accenture professional services + NVIDIA GPU infrastructure. Clients who deploy AI Refinery cannot swap the inference layer without re-engagement. There is no OSS core; the platform is delivered as a managed service.

**Enterprise AI Accelerator approach:** MIT license. No NVIDIA dependency. The inference provider is a single env var. Switching from Anthropic to any OpenAI-compatible API requires a one-file change to `core/models.py`.

### Deloitte AI Advisory

In October 2025, Deloitte Australia's use of Azure OpenAI GPT-4o for a government welfare audit became public. The AI fabricated a court case (*Amato v Commonwealth*) and academic citations. The contract was valued at AU$440,000 (~$291,245 USD); a partial refund was agreed. The incident occurred because the system had no grounding mechanism — model outputs were not anchored to source documents.

**Enterprise AI Accelerator approach:** `compliance_citations/` uses Anthropic's Citations API to anchor every compliance finding to a source passage. Fabricated citations are structurally prevented: the API returns the exact text span from the source document alongside the finding. See Article 13 section in `docs/EU_AI_ACT_EVIDENCE_PACK.md`.

### IBM watsonx

IBM watsonx is delivered as a SaaS-first platform; on-premises options exist but require IBM hardware partnerships and IBM Cloud Pak licensing. Exit costs are high due to proprietary data formats and vendor-managed model versions.

**Enterprise AI Accelerator approach:** All data is stored in standard formats (SQLite/Postgres, JSON, CycloneDX v1.7). No proprietary storage layer. Backup/export requires no vendor cooperation.

### General Big-6 Pattern

Large consulting-led AI transformation programs typically involve:
- Proprietary orchestration frameworks (no source access)
- Vendor-managed model versions (client cannot freeze or roll back)
- Usage telemetry sent to the vendor
- Exit clauses that require re-licensing or data migration fees

The MIT license and the platform's architecture (documented in `docs/PLATFORM_ARCHITECTURE.md`, no proprietary runtime dependencies) are the structural counters to each of these patterns.

---

## Deployment Checklist for Sovereign Environments

```
[ ] Clone repository into internal git mirror (or approved code artifact store)
[ ] Build Docker image from Dockerfile.demo in client's container registry (no external pulls at runtime)
[ ] Set ANTHROPIC_API_KEY in client's secrets manager (Vault, AWS Secrets Manager, Azure Key Vault)
[ ] Restrict outbound HTTPS to api.anthropic.com (and cloud provider APIs if discovery is enabled)
[ ] Set OTEL_EXPORTER_OTLP_ENDPOINT to internal OTEL Collector (or leave unset to disable telemetry)
[ ] Verify audit_trail.db backup to immutable store is configured
[ ] Run python -m compliance_citations.cli --network-audit to confirm no unexpected external calls
[ ] Run python -m pytest tests/ to confirm all offline tests pass
```

All tests in `tests/` run without internet access. Anthropic API calls are mocked. A passing test suite in an air-restricted environment confirms the platform binary is functional before any live credentials are injected.
