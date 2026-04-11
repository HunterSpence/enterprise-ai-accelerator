# AIAuditTrail

**EU AI Act enforcement begins August 2, 2026. This is the open-source compliance tool.**

Tamper-evident AI decision logging for EU AI Act Article 12/13 compliance.
SHA-256 hash chain. SQLite backend. Zero heavy dependencies.

---

## The Problem

Any company running AI for hiring, credit scoring, medical, fraud detection, or
law enforcement is a **high-risk AI system** under EU AI Act Annex III.
Article 12 requires an immutable, auditable log of every AI decision.

| Solution | Cost | Open Source |
|----------|------|-------------|
| IBM OpenPages AI Risk Management | ~$500,000/year | No |
| Credo AI | ~$180,000/year | No |
| **AIAuditTrail** | **$0** | **Yes** |

---

## One-Line Integration

```python
# Before
client = Anthropic()

# After — full EU AI Act Article 12 compliance
from ai_audit_trail.integrations.anthropic_sdk import AuditedAnthropic
from ai_audit_trail import AuditChain, RiskTier

chain = AuditChain("audit.db")
client = AuditedAnthropic(audit_chain=chain, risk_tier=RiskTier.HIGH)
# Everything else stays the same.
```

Or use the decorator:

```python
from ai_audit_trail import AuditChain, DecisionType, RiskTier
from ai_audit_trail.decorators import audit_llm_call

chain = AuditChain("audit.db")

@audit_llm_call(
    chain=chain,
    decision_type=DecisionType.CLASSIFICATION,
    risk_tier=RiskTier.HIGH,
)
def screen_job_application(prompt: str) -> str:
    return call_your_llm(prompt)
```

---

## Architecture

```
Your Application
       │
       ▼
┌─────────────────────────────────────────────────┐
│            AIAuditTrail SDK                     │
│                                                 │
│  @audit_llm_call  /  AuditedAnthropic           │
│  AuditedOpenAI    /  AuditTrailCallback         │
│                        │                        │
│          ┌─────────────▼──────────────┐         │
│          │      AuditChain            │         │
│          │                            │         │
│          │  LogEntry {                │         │
│          │    entry_id: UUID          │         │
│          │    timestamp: ISO 8601     │         │
│          │    session_id: UUID        │         │
│          │    model: str              │         │
│          │    input_hash: SHA-256     │  ← no   │
│          │    output_hash: SHA-256    │  plaintext
│          │    input_tokens: int       │         │
│          │    output_tokens: int      │         │
│          │    latency_ms: float       │         │
│          │    decision_type: enum     │         │
│          │    risk_tier: enum         │         │
│          │    prev_hash: SHA-256      │  ← chain│
│          │    entry_hash: SHA-256     │  ← link │
│          │  }                         │         │
│          └─────────────┬──────────────┘         │
│                        │                        │
│          ┌─────────────▼──────────────┐         │
│          │  SQLite WAL (append-only)  │         │
│          └────────────────────────────┘         │
└─────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────┐  ┌──────────────────┐
│  QueryEngine     │  │  ReportGenerator │
│  - filter()      │  │  - generate()    │
│  - aggregate()   │  │  - to_html()     │
│  - export_csv()  │  │  - to_json()     │
│  - explain()     │  │                  │
└──────────────────┘  └──────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│  eu_ai_act.py                                    │
│  - classify_risk_tier()                          │
│  - check_article_12_compliance()                 │
│  - generate_article_13_transparency_report()     │
│  - generate_article_11_technical_doc()           │
│  - days_until_enforcement()                      │
└──────────────────────────────────────────────────┘
```

---

## How the Hash Chain Works

Each log entry contains a `prev_hash` — the SHA-256 hash of the preceding entry.
The `entry_hash` is a SHA-256 over all fields of the current entry (including `prev_hash`).

```
GENESIS (0x000…)
    │
    ▼
Entry 1: entry_hash = SHA256(entry_1_fields + prev="000…")
    │
    ▼
Entry 2: entry_hash = SHA256(entry_2_fields + prev=entry_1_hash)
    │
    ▼
Entry 3: entry_hash = SHA256(entry_3_fields + prev=entry_2_hash)
```

If anyone modifies Entry 2, its `entry_hash` no longer matches what Entry 3
expects as `prev_hash`. The entire downstream chain fails verification.
`verify_chain()` detects this in O(n) time.

---

## Privacy by Design

Prompts and responses are **never stored**. Only their SHA-256 hashes are logged.
This means:
- The audit trail proves a decision was made without revealing sensitive content
- GDPR right-to-erasure is not triggered (no personal data stored)
- Token counts + latency are captured for compliance without content exposure

Development mode only: `AuditChain("audit.db", store_plaintext=True)` stores plaintext.
Never use in production with personal data.

---

## EU AI Act Coverage

| Article | Requirement | AIAuditTrail |
|---------|-------------|--------------|
| Art. 6/7 | Risk classification | `classify_risk_tier()` |
| Art. 9 | Risk management | Risk tier on every entry |
| Art. 11 | Technical documentation | `generate_article_11_technical_doc()` |
| Art. 12 | Record-keeping | SHA-256 hash chain ledger |
| Art. 12.2 | Tamper-evident logs | `verify_chain()` detects any modification |
| Art. 13 | Transparency | `generate_article_13_transparency_report()` |
| Art. 14 | Human oversight | Logged per decision, queryable |
| Annex III | High-risk detection | `detect_annex_iii_categories()` |

---

## Dependencies

**Core (zero extra installs):**
- Python 3.12+
- `hashlib`, `sqlite3`, `uuid`, `dataclasses`, `datetime` — all stdlib

**Optional:**
- `anthropic` — for `AuditedAnthropic` and LLM-powered risk classification
- `openai` — for `AuditedOpenAI`
- `langchain-core` — for `AuditTrailCallback`
- `rich` — for colorized demo output

---

## Run the Demo

```bash
# No API key required
python -m ai_audit_trail.demo
```

Shows:
1. Decorator wrapping — watch entries appear in real time
2. `AuditedAnthropic` drop-in — 5 simulated calls logged automatically
3. Compliance report — Article 12 attestation, tamper detection proof, countdown

---

## Enforcement Countdown

```python
from ai_audit_trail import days_until_enforcement
print(days_until_enforcement("high_risk_systems"))  # Days until Aug 2, 2026
```

High-risk AI systems (hiring, credit, medical, law enforcement) must comply by
**August 2, 2026**. Penalties up to €30 million or 6% of global annual turnover.

---

*Part of [enterprise-ai-accelerator](https://github.com/HunterSpence/enterprise-ai-accelerator) —
What Accenture charges $50M for. Open source.*
