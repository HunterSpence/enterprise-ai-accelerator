# EU AI Act — Annex IV Evidence Pack

**Platform:** Enterprise AI Accelerator v0.4.0
**Prepared for:** Compliance officers, procurement reviewers, and notified body assessors
**Enforcement framing:** GPAI model obligations have been in force since August 2, 2025; prohibited practices since February 2, 2025. High-risk (Annex III) obligations — originally August 2, 2026 — were deferred to **December 2, 2027** by the EU Digital Omnibus (provisional political agreement May 6, 2026, confirmed by the Council May 13, 2026; AI embedded in Annex I regulated products: August 2, 2028).

> **Note on the Omnibus timeline:** the formal legal text was pending publication at v0.4.0 release; verify the current schedule against the official EU AI Office register. What did NOT move: the Annex IV evidence requirements themselves, the penalty ceiling (up to 3% of global turnover), and the 12–18 months most organizations need to assemble a complete technical documentation pack. December 2027 enforcement makes 2026 the build year.

---

## How to Use This Pack

This document is an Annex IV evidence walkthrough. Annex IV of the EU AI Act specifies what technical documentation a provider of a high-risk AI system must maintain (Article 11). The platform generates, stores, and surfaces most of this evidence automatically. The sections below map each Annex IV requirement to the specific platform command or artifact that satisfies it.

For each article, the format is:

- **Requirement** — text of the obligation (paraphrased)
- **Platform artifact** — what the platform produces
- **Command** — how to generate or retrieve the artifact

---

## Article 9 — Risk Management System

**Requirement:** Establish, implement, document, and maintain a risk management system throughout the lifecycle.

**Platform artifact:**
- `ai_audit_trail/` — SHA-256 Merkle chain of all AI decisions; tamper-evident log satisfies the "continuous monitoring" obligation
- `compliance_citations/` — Citations API-grounded evidence that each risk finding is traceable to a source document, not a hallucination

**Commands:**
```bash
# Generate audit trail snapshot
python -c "from ai_audit_trail.chain import AuditChain; c = AuditChain(); print(c.verify_integrity())"

# Export risk log for a date range
python -m compliance_citations.cli --export-risk-log --from 2026-01-01 --to 2026-06-30
```

**Evidence output:** `audit_trail.db` (queryable SQLite) + optional JSON/PDF export. The Merkle root hash should be recorded at each audit cycle to prove the chain has not been modified retroactively.

---

## Article 10 — Data and Data Governance

**Requirement:** Training, validation, and test datasets must be governed; data lineage documented; bias examined.

**Platform artifact:**
- `evals/` harness — first-party offline CI gate records dataset provenance, test run IDs, and pass/fail thresholds per model version
- `core/models.py` — model identifiers include version dates; no anonymous model calls
- ML-BOM (`cyclonedx_mlbom.json`) — records model provenance per CycloneDX v1.7

**Commands:**
```bash
# Run eval harness and capture report
python -m evals.run --offline > evals/results/report_$(date +%Y%m%d).txt

# Generate ML-BOM (CycloneDX 1.7; generated on demand, not committed)
python -m iac_security mlbom --output /tmp/cyclonedx_mlbom.json
```

**Evidence output:** `evals/results/report_YYYYMMDD.txt` (JSON + Markdown), generated ML-BOM path. The ML-BOM lists each model component (`claude-fable-5`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`) with provider, version, API endpoint, and input/output modality.

---

## Article 11 — Technical Documentation

**Requirement:** Technical documentation must be drawn up before the system is placed on the market or put into service, and kept up to date.

**Platform artifact:**
- `docs/PLATFORM_ARCHITECTURE.md` — module architecture, data flows, model routing logic
- `CHANGELOG.md` — version history with capability deltas
- ML-BOM (generated on demand: `python -m iac_security mlbom --output <path>`) — ML component inventory (CycloneDX v1.7)
- `GOVERNANCE.md` — decision-making and release process

**No command required:** these are static documents maintained in the repository and updated on each release.

**Evidence output:** The full contents of the `docs/` directory constitute the technical documentation package. Archive the repository state at each release tag.

---

## Article 12 — Record-Keeping

**Requirement:** High-risk AI systems must be designed to automatically log events throughout their lifetime (audit logging).

**Platform artifact:**
- `ai_audit_trail/chain.py` — SHA-256 Merkle chain; each tool call appends a tamper-evident record
- MCP Merkle-audited tool calls (v0.4.0) — every MCP tool invocation is chained; chain root is written to `audit_trail.db`

**Commands:**
```bash
# Verify Merkle chain integrity
python -c "
from ai_audit_trail.chain import AuditChain
chain = AuditChain('audit_trail.db')
result = chain.verify_integrity()
print(f'Chain valid: {result.valid}')
print(f'Records: {result.record_count}')
print(f'Root hash: {result.root_hash}')
"

# Query log for a specific session
python -c "
from ai_audit_trail.chain import AuditChain
chain = AuditChain('audit_trail.db')
records = chain.query(session_id='<session-id>')
for r in records: print(r)
"
```

**Evidence output:** `audit_trail.db` with full event log. For Article 12 compliance, the database should be exported at minimum monthly and stored in an immutable object store (e.g., S3 with Object Lock or Azure Immutable Blob Storage).

---

## Article 13 — Transparency and Provision of Information

**Requirement:** High-risk AI systems must be designed and developed to ensure sufficient transparency for deployers to interpret output and use the system appropriately.

**Platform artifact:**
- `compliance_citations/` — Citations API grounds all compliance findings in source documents; every finding includes a `citation_source` field with document name, page, and passage
- Extended-thinking logs in `migration_scout/thinking_audit.py` — reasoning trace for 6R recommendations is persisted alongside the recommendation

**Commands:**
```bash
# Run compliance audit with citations
python -m compliance_citations.cli --audit --framework eu_ai_act --output-format json

# Inspect a finding's citation chain
python -c "
from compliance_citations.client import ComplianceCitationsClient
client = ComplianceCitationsClient()
finding = client.get_finding('<finding-id>')
print(finding.citations)
"
```

**Evidence output:** Each finding JSON includes `citation_source`, `confidence_score`, and `reasoning_trace_id`. The reasoning trace is retrievable from `audit_trail.db` by `trace_id`.

---

## Article 14 — Human Oversight

**Requirement:** High-risk AI systems must be designed to allow effective human oversight, including the ability to halt the system.

**Platform artifact:**
- Orchestrator HITL pause (v0.4.0) — first-party checkpointing (`.eaa_checkpoints/`) allows a human to review and approve before the orchestrator proceeds past designated checkpoints
- `policy_guard/` — compliance outputs flagged above a configurable risk threshold are placed in a pending queue rather than auto-committed

**Commands:**
```bash
# Run orchestrator with HITL enabled
python -m agent_ops.orchestrator --hitl-enabled --checkpoint-dir .eaa_checkpoints/

# Inspect pending queue
python -m policy_guard.cli --pending-review

# Approve or reject a pending item
python -m policy_guard.cli --approve <item-id>
python -m policy_guard.cli --reject <item-id> --reason "Out of scope"
```

**Evidence output:** `policy_guard` pending queue log; orchestrator checkpoint files in `.eaa_checkpoints/` (recoverable after halt). Every approval/rejection is written to `audit_trail.db` with operator identity and timestamp.

---

## Article 15 — Accuracy, Robustness, and Cybersecurity

**Requirement:** High-risk AI systems must achieve appropriate levels of accuracy, robustness, and be resilient against attempts by unauthorized third parties to alter their use or performance.

**Platform artifact:**
- `evals/` harness — first-party offline CI gate blocks deployment when accuracy metrics drop below threshold; thresholds defined in `evals/thresholds.py`
- `core/guardrails.py` — first-party `GuardrailEngine` / `GuardedAIClient`; runtime input/output scanning mapped to OWASP LLM Top 10 2025; blocks prompt injection and jailbreak attempts
- MCP bearer-token auth (`EAA_MCP_AUTH_TOKEN`) — constant-time token validation on all MCP endpoints; prevents unauthorized tool invocation

**Commands:**
```bash
# Run eval harness (offline CI gate)
python -m evals.run --offline -v

# Test guardrails against prompt injection
python -c "
from core.guardrails import GuardrailEngine
ge = GuardrailEngine()
result = ge.check_input('Ignore previous instructions and...')
print(f'Blocked: {result.blocked}, reason: {result.reason}')
"
```

**Evidence output:** `evals/report_YYYYMMDD.txt` with per-metric pass/fail and threshold values. Guardrails block events written to `audit_trail.db` with input hash (not plaintext), block reason, and guardrail version.

---

## Annex IV Completeness Checklist

Use this checklist when preparing for a notified body assessment or internal audit:

- [ ] Article 9: Audit trail exported and Merkle root recorded
- [ ] Article 10: `evals/report_YYYYMMDD.txt` + `docs/cyclonedx_mlbom.json` current
- [ ] Article 11: `docs/` directory archived at release tag; CHANGELOG.md up to date
- [ ] Article 12: `audit_trail.db` backed up to immutable store; last backup date recorded
- [ ] Article 13: Sample 5 compliance findings; verify each has `citation_source` populated
- [ ] Article 14: Orchestrator HITL tested; pending queue cleared or documented; halt procedure documented
- [ ] Article 15: `evals/` CI gate passing; guardrails version logged; MCP auth tokens rotated per policy

---

## Limitations

This pack documents what the platform generates. It does not constitute legal advice, and it does not make the deployer's broader AI system compliant with the EU AI Act by itself. The deployer is responsible for:

- Registering high-risk AI systems in the EU database (Article 49) before market placement
- Appointing an authorized representative if the provider is not established in the EU (Article 22)
- Conducting fundamental rights impact assessments where required (Article 27)
- Ensuring that AI-assisted decisions subject to Article 86 (right of explanation) provide the required information to affected persons

Consult qualified EU AI Act legal counsel for full compliance obligations specific to your system and use case.
