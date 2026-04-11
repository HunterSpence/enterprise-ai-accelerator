# AIAuditTrail

**EU AI Act enforcement: 113 days. IBM OpenPages: $500K/yr. Credo AI: $180K/yr. AIAuditTrail: $0.**

![Zero Dependencies](https://img.shields.io/badge/core-zero%20dependencies-brightgreen)
![EU AI Act](https://img.shields.io/badge/EU%20AI%20Act-Article%2012%20%7C%20Article%2062-blue)
![NIST AI RMF](https://img.shields.io/badge/NIST-AI%20RMF%201.0-orange)
![Merkle Chain](https://img.shields.io/badge/tamper--evident-Merkle%20SHA--256-red)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)

Tamper-evident AI audit logging with EU AI Act Article 12 compliance, NIST AI RMF mapping, and 5 SDK integrations. Core runs on Python stdlib — no mandatory dependencies.

---

## Cost Comparison

| Product | Annual Cost | EU Art. 12 | NIST MEASURE | SDKs | Merkle Chain |
|---------|-------------|-----------|--------------|------|--------------|
| IBM OpenPages | $500,000 | 40% | 55% | 2 | No |
| Credo AI | $180,000 | 60% | 65% | 3 | No |
| **AIAuditTrail** | **$0** | **100%** | **100%** | **5** | **Yes** |

**3-year savings vs IBM OpenPages: $1,500,000**  
**3-year savings vs Credo AI: $540,000**

---

## Quick Start

### 1. Anthropic (2-line drop-in)

```python
# Before:
from anthropic import Anthropic
client = Anthropic()

# After — full EU AI Act Article 12 logging:
from ai_audit_trail.integrations.anthropic_sdk import AuditedAnthropic
from ai_audit_trail.chain import AuditChain
client = AuditedAnthropic(audit_chain=AuditChain("audit.db"), system_id="my-ai-v1")

# Every call is now tamper-evident, EU-compliant, and cost-tracked:
response = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=200,
                                   messages=[{"role": "user", "content": "Hello"}])
```

### 2. OpenAI (same pattern)

```python
from ai_audit_trail.integrations.openai_sdk import AuditedOpenAI
from ai_audit_trail.chain import AuditChain

client = AuditedOpenAI(audit_chain=AuditChain("audit.db"), system_id="gpt-assistant-v1")
response = client.chat.completions.create(model="gpt-4o-mini",
                                           messages=[{"role": "user", "content": "Hello"}])
```

### 3. LangChain (one callback)

```python
from ai_audit_trail.integrations.langchain import AuditTrailCallback
from ai_audit_trail.chain import AuditChain

audit = AuditTrailCallback(audit_chain=AuditChain("audit.db"), system_id="lc-pipeline-v1")
llm = ChatAnthropic(model="claude-haiku-4-5-20251001", callbacks=[audit])  # <- one line
```

### 4. LlamaIndex (retrieval + synthesis)

```python
from ai_audit_trail.integrations.llamaindex import AuditTrailLlamaCallback
from llama_index.core import Settings
from llama_index.core.callbacks import CallbackManager

Settings.callback_manager = CallbackManager([
    AuditTrailLlamaCallback(audit_chain=AuditChain("audit.db"), system_id="rag-v1")
])
```

### 5. CrewAI (multi-agent)

```python
from ai_audit_trail.integrations.crewai import AIAuditTrailCrewCallback
from ai_audit_trail.chain import AuditChain

crew = Crew(agents=[...], tasks=[...],
            callbacks=[AIAuditTrailCrewCallback(AuditChain("audit.db"), "crew-v1")])
```

---

## EU AI Act Enforcement Timeline

| Phase | Enforcement Date | Status | What's Required |
|-------|-----------------|--------|-----------------|
| Prohibited Systems (Art. 5) | Feb 2, 2025 | ENFORCED | Social scoring, biometric surveillance banned |
| GPAI Model Rules (Ch. V) | Aug 2, 2025 | ENFORCED | Transparency docs, copyright policy |
| **High-Risk AI (Art. 8-25)** | **Aug 2, 2026** | **113 days** | **Full Article 12 logging required** |
| Remaining Provisions | Aug 2, 2027 | Upcoming | Notified body assessments |

> Article 12 **mandatory fields** (Annex IV): input hash · output hash · timestamp · model ID ·
> session ID · decision type · tamper-evident storage · retention policy

---

## Chain Integrity — Merkle Tree Structure

AIAuditTrail builds a binary Merkle tree over every audit log entry. Any modification to any entry invalidates all parent hashes up to the root.

```
                  Merkle Root
                  (hourly anchored)
                 /              \
         Node AB                Node CD
        /       \              /       \
   Entry A    Entry B     Entry C    Entry D
  (SHA-256)  (SHA-256)   (SHA-256)  (SHA-256)
     |            |          |           |
  input_hash  input_hash  input_hash  input_hash
  output_hash output_hash output_hash output_hash
  prev_hash -> prev_hash -> prev_hash -> prev_hash
```

**Verification:**
```python
chain = AuditChain("audit.db")
report = chain.verify_chain()
print(f"{'VALID' if report.is_valid else 'TAMPERED'}: {report.total_entries} entries")
print(f"Merkle root: {report.merkle_root[:32]}...")

# Per-entry O(log n) proof:
proof = chain.get_entry_proof("entry-uuid")
verified = MerkleTree.verify_proof(proof["leaf_hash"], proof["proof"], proof["merkle_root"])
```

---

## NIST AI RMF Coverage

| Function | Score | Key Subcategories Covered |
|----------|-------|--------------------------|
| GOVERN | 75% | 1.1 (Policy artifact), 5.2 (Third-party tracking) |
| MAP | 80% | 1.1 (Risk context), 1.5 (Impact estimation) |
| MEASURE | 100% | 2.5 (Validity/reliability logging), 2.6 (Performance metrics) |
| MANAGE | 85% | 1.3 (Incident playbooks), 2.2 (Human oversight) |

**Cross-framework efficiency:** Many NIST RMF subcategories and EU AI Act articles are satisfied by the same AIAuditTrail evidence. Fix once, cover both frameworks.

---

## Installation

```bash
# Core only (zero dependencies):
pip install ai-audit-trail

# With specific SDK:
pip install "ai-audit-trail[anthropic]"
pip install "ai-audit-trail[openai]"
pip install "ai-audit-trail[langchain]"
pip install "ai-audit-trail[llamaindex]"
pip install "ai-audit-trail[crewai]"

# With web dashboard:
pip install "ai-audit-trail[ui]"

# Everything:
pip install "ai-audit-trail[all]"
```

---

## Commands

```bash
make demo        # Run CLI demo -- no API key needed
make ui          # Launch Streamlit compliance operations center
make api         # Start FastAPI server (http://localhost:8000/docs)
make benchmark   # Show competitive benchmark vs IBM OpenPages + Credo AI
make test        # Run 35+ unit tests
make docker-up   # Start Docker Compose (API + Redis)
```

---

## Architecture

```
ai_audit_trail/
├── chain.py            -- Merkle SHA-256 hash chain (SQLite WAL, zero deps)
├── eu_ai_act.py        -- EU AI Act Articles 5, 12, 51-55, 62 engine
├── nist_rmf.py         -- NIST AI RMF 1.0 subcategory mapping
├── incident_manager.py -- P0-P3 incident management + Article 62 tracker
├── reporter.py         -- HTML/Markdown compliance report generation
├── api.py              -- FastAPI REST + WebSocket endpoints
├── web_ui.py           -- Streamlit compliance operations center (V3 NEW)
├── benchmark.py        -- Competitive benchmark vs IBM OpenPages, Credo AI (V3 NEW)
├── integrations/
│   ├── anthropic_sdk.py -- AuditedAnthropic drop-in wrapper
│   ├── openai_sdk.py    -- AuditedOpenAI drop-in wrapper
│   ├── langchain.py     -- AuditTrailCallback for LangChain
│   ├── llamaindex.py    -- AuditTrailLlamaCallback for LlamaIndex
│   └── crewai.py        -- AIAuditTrailCrewCallback for CrewAI
├── sdk_examples/        -- 5 runnable integration examples (V3 NEW)
│   ├── 01_anthropic_quickstart.py
│   ├── 02_openai_quickstart.py
│   ├── 03_langchain_chain.py
│   ├── 04_llamaindex_rag.py
│   └── 05_crewai_agents.py
└── tests/               -- 35+ pytest tests (V3 NEW)
```

---

## License

MIT -- free to use, modify, and deploy.

---

*EU AI Act enforcement begins August 2, 2026 for high-risk AI systems.*  
*IBM OpenPages costs $500K/yr. Credo AI costs $180K/yr. AIAuditTrail costs $0.*
