# Compliance Frameworks — Enterprise AI Accelerator

**Last updated:** April 2026

PolicyGuard scans against 9 compliance frameworks. This guide covers the control catalog for each, cross-framework mapping strategy, and how to select the right baseline for your organization.

---

## Framework Overview

| Framework | Standard Body | Enforcement Date | Scope | Controls in Catalog | Our Coverage |
|-----------|--------------|-----------------|-------|---------------------|--------------|
| CIS AWS Foundations v3.0 | Center for Internet Security | Always | Cloud infrastructure | 176 | Configurable |
| SOC 2 Type II + AICC | AICPA | Always | Cloud services | 50 | Configurable |
| HIPAA Security Rule | HHS | Always | Healthcare PHI | 42 | Configurable |
| EU AI Act | European Union | Aug 2026 (High-Risk) | AI systems in EU market | 13 articles | Configurable |
| NIST AI RMF 2.0 | NIST | Voluntary | AI systems globally | 73 subcategories | Configurable |
| ISO/IEC 42001:2023 | ISO | Always (self-cert) | AI management systems | 49 controls | Configurable |
| DORA | European Union | Jan 17, 2025 | EU financial entities | 39 controls | Configurable |
| FedRAMP Rev 5 | FedRAMP PMO / GSA | Always | US federal cloud | 248 controls (Moderate) | Configurable |
| PCI DSS 4.0 | PCI SSC | Mar 31, 2025 | Payment card processing | 83 sub-requirements | Configurable |

---

## NIST AI RMF 2.0 (NIST AI 100-1 + NIST AI 600-1)

**Scope:** Voluntary framework for AI risk management across any sector. July 2024 update adds the Generative AI Risk Profile (NIST AI 600-1).

**Control structure:** 4 Core Functions → 73 Subcategories (72 base + MG-4.3 added in 2.0)

| Function | Subcategory Count | Focus |
|----------|------------------|-------|
| GOVERN | 16 | Organizational culture, accountability, policies |
| MAP | 16 | Context, risk identification, stakeholder analysis |
| MEASURE | 18 | Testing, metrics, monitoring |
| MANAGE | 10+1(v2) | Prioritization, response, residual risk |

**NIST AI 600-1 Generative AI Risk Areas (12 total):**
- GAI-1: CBRN Information | GAI-2: Confabulation | GAI-3: Data Privacy
- GAI-4: Data Poisoning | GAI-5: Harmful Bias | GAI-6: Human-AI Configuration
- GAI-7: Information Integrity | GAI-8: Information Security | GAI-9: Intellectual Property
- GAI-10: Harmful Content | GAI-11: Societal Harms | GAI-12: Value Chain Risk

**Worked mapping example — GOVERN-1.1:**
```
GOVERN-1.1 (AI governance policy)
  → EU AI Act Article 9 (risk management system)
  → ISO 42001 Clause 5.2 (AI policy)
  → SOC 2 CC1.1 (commitment to integrity)
ONE policy document satisfies all three frameworks.
```

---

## ISO/IEC 42001:2023

**Scope:** AI management system standard. Certifiable (like ISO 27001 for AI). Applicable to any organization developing, providing, or using AI systems.

**Control structure:** 7 management clauses + 17 Annex A technical controls = 49 total

| Section | Controls | Focus |
|---------|----------|-------|
| Clauses 4-5 | 7 | Context, leadership, AI policy |
| Clause 6 | 6 | Risk planning, objectives |
| Clause 7 | 5 | Resources, competence, communication |
| Clause 8 | 8 | Operations, lifecycle, data management |
| Clauses 9-10 | 5 | Performance evaluation, improvement |
| Annex A | 17 | Technical controls (policies, data, monitoring) |

**EU AI Act cross-mapping highlight:**

| ISO 42001 | EU AI Act | Description |
|-----------|-----------|-------------|
| A.7.3 | Article 10 | Data quality |
| A.8.2 | Article 13 | Transparency |
| 8.7 | Article 62 | Incident management |
| 8.3 | Article 9 | Impact assessment |

---

## DORA — Digital Operational Resilience Act

**Scope:** EU financial entities (banks, investment firms, payment institutions, insurance undertakings) and their critical ICT third-party providers. In force from 17 January 2025.

**Control structure:** 39 controls across 6 chapters

| Chapter | Articles | Controls | Focus |
|---------|----------|----------|-------|
| II | 5-14 | 17 | ICT risk management |
| III | 15-23 | 6 | Incident management and reporting |
| IV | 24-27 | 4 | Operational resilience testing (incl. TLPT) |
| V | 28-44 | 7 | Third-party ICT risk |
| VI | 45-49 | 2 | Information sharing |
| VII | 50-56 | 3 | Oversight framework |

**Key DORA-unique requirements:**
- **DORA-17.1**: Major incident reports due within 4 hours (initial), 72 hours (intermediate), 1 month (final)
- **DORA-26.1**: Threat-Led Penetration Testing (TLPT) every 3 years for significant entities
- **DORA-30.1**: Mandatory contractual clauses for all ICT third-party providers

**Worked mapping example — Incident Reporting:**
```
DORA Article 17.1 (4h/72h/1-month reporting)
  → FEDRAMP IR-6 (US-CERT reporting within 1 hour)
  → PCI DSS 12.10.1 (incident response plan and testing)
  → SOC 2 CC7.3 / CC7.4 (incident response and recovery)
  → HIPAA 164.308(a)(6) (security incident procedures)
```

---

## FedRAMP Rev 5 Baselines

**Scope:** Cloud Service Providers (CSPs) serving US federal agencies. Rev 5 aligns to NIST SP 800-53 Rev 5 (September 2023).

**Baseline tiers:**

| Baseline | Use Case | Controls (approx.) |
|----------|----------|-------------------|
| Low | Non-sensitive federal data | 125 |
| Moderate | Most federal workloads | 323 |
| High | Law enforcement, financial, health | 421 |

**18 control families covered in catalog (248 controls):**
AC, AT, AU, CA, CM, CP, IA, IR, MA, MP, PE, PL, PS, RA, SA, SC, SI, SR

**Critical FedRAMP-specific requirements:**
- **CA-5**: Monthly POA&M submission to FedRAMP PMO
- **CA-7**: Continuous monitoring — monthly scans, monthly POA&M, annual assessment
- **RA-5**: Credentialed vulnerability scanning (critical findings remediated in 30 days)
- **IR-6**: US-CERT reporting within 1 hour for Priority 1/2 incidents
- **IA-2(1)/(2)/(12)**: MFA + PIV credential acceptance

**Mapping to PCI DSS 4.0:**

| FedRAMP | PCI DSS 4.0 | Shared requirement |
|---------|-------------|-------------------|
| AU-11 | 10.5.1 | Log retention (12 months) |
| IA-2(1) | 8.4.1 | MFA for privileged accounts |
| RA-5 | 11.3.1/11.3.2 | Quarterly vulnerability scans |
| CA-8 | 11.4.2/11.4.3 | Annual penetration testing |

---

## PCI DSS 4.0

**Scope:** Any organization that stores, processes, or transmits payment card data. Mandatory from 31 March 2025.

**Control structure:** 12 Requirements, 83 sub-requirements

| Req | Focus | Sub-reqs |
|-----|-------|---------|
| 1-2 | Network security and secure configuration | 22 |
| 3-4 | Account data protection | 15 |
| 5-6 | Vulnerability management | 17 |
| 7-8 | Access control | 17 |
| 9 | Physical security | 7 |
| 10-11 | Logging and testing | 19 |
| 12 | Policy and program | ~20 |

**New in v4.0 (18 requirements not in v3.2.1):**
- **1.5.1**: Personal device protection when connecting to CDE
- **8.4.2**: MFA for ALL CDE access (not just admin)
- **6.4.3**: Payment page script inventory and authorization
- **11.6.1**: Change/tamper detection for payment pages (anti-skimming)
- **12.3.1**: Documented targeted risk analysis for each PCI requirement

**Two implementation approaches:**
- **Defined Approach**: Follow the prescriptive requirements as stated (classic PCI DSS)
- **Customized Approach**: Meet the Stated Objective using alternative controls (documented justification required)

---

## Cross-Framework Traceability Matrix

The `policy_guard/frameworks/mapping.py` module provides `CONTROL_MAPPINGS` with canonical cross-framework linkages. As of this release: **60+ canonical entries with 180+ individual control links**.

### Usage

```python
from policy_guard.frameworks.mapping import get_equivalents, coverage_report

# Find all frameworks that map to FedRAMP AU-11
equiv = get_equivalents("FEDRAMP", "AU-11")
# Returns: {"CIS_AWS": ["CIS_AWS_3.1", "CIS_AWS_3.2"], "SOC2": ["SOC2_CC7.2"],
#           "PCI_DSS_40": ["PCI_DSS_40_10.5.1"], "DORA": ["DORA_10.2"], ...}

# Coverage analysis from a finding set
findings = [
    {"framework": "FEDRAMP", "control_id": "AU-11", "status": "FAIL"},
    {"framework": "PCI_DSS_40", "control_id": "10.5.1", "status": "PASS"},
]
report = coverage_report(findings)
# Returns per-framework coverage % and pass rates
```

### High-Value Cross-Framework Wins (one implementation, multiple frameworks satisfied)

| Implementation | Frameworks Satisfied |
|----------------|---------------------|
| TLS 1.2+ everywhere | PCI DSS 4.2.1, FEDRAMP SC-8, DORA 9.1, HIPAA 164.312(e)(2)(ii) |
| Annual pen test | FEDRAMP CA-8, PCI DSS 11.4.2/11.4.3, DORA 26.1, SOC 2 CC7.1 |
| AI governance policy | NIST AI RMF GOVERN-1.1, EU AI Act Art. 9, ISO 42001 5.2, SOC 2 CC1.1 |
| Log retention 12 months | FedRAMP AU-11, PCI DSS 10.5.1, DORA 10.2, HIPAA 164.312(b) |
| MFA for all privileged | FedRAMP IA-2(1), PCI DSS 8.4.1, DORA 9.1, SOC 2 CC6.1 |
| Third-party risk program | DORA 28.1, FedRAMP SA-9, PCI DSS 12.8.1, ISO 42001 A.10.2 |

---

## How to Pick a Baseline

Use this decision tree to determine which frameworks are mandatory vs. recommended:

```
Are you a US federal contractor or CSP serving federal agencies?
  YES → FedRAMP Rev 5 is REQUIRED (pick Low/Moderate/High per data sensitivity)
  NO  → continue

Do you process payment card data?
  YES → PCI DSS 4.0 is REQUIRED
  NO  → continue

Are you an EU financial entity (bank, insurer, investment firm)?
  YES → DORA is REQUIRED (in force Jan 2025)
  NO  → continue

Does your organization develop, provide, or deploy AI systems?
  YES → Consider:
    - EU AI Act (REQUIRED if AI system in EU market, high-risk category)
    - NIST AI RMF 2.0 (RECOMMENDED — voluntary but aligns with EU AI Act)
    - ISO/IEC 42001:2023 (RECOMMENDED if you want certifiable AI governance)

Are you a healthcare organization handling PHI?
  YES → HIPAA is REQUIRED

Do you need to demonstrate cloud security to enterprise customers?
  YES → SOC 2 Type II (RECOMMENDED) + CIS AWS (RECOMMENDED for AWS workloads)

Baseline recommendation for an AI-native enterprise cloud company:
  NIST AI RMF 2.0 + ISO 42001 + CIS AWS + SOC 2 (covers the widest surface)
```

---

## Sample Multi-Framework Audit Report Excerpt

```
PolicyGuard Compliance Report — Scan ID: A1B2C3D4
Timestamp: 2026-04-17 01:00 UTC | Duration: 3.2s

Framework Compliance Scores:
┌─────────────────────────┬───────┬──────────┬──────────┬───────┐
│ Framework               │ Score │ Findings │ Critical │ High  │
├─────────────────────────┼───────┼──────────┼──────────┼───────┤
│ CIS AWS Foundations     │  71%  │   51     │    3     │  18   │
│ EU AI Act               │  38%  │    8     │    4     │   3   │
│ NIST AI RMF 2.0         │  12%  │   64     │    0     │  29   │
│ SOC 2 Type II           │  46%  │   27     │    2     │  11   │
│ HIPAA                   │  55%  │   19     │    1     │   7   │
│ ISO/IEC 42001:2023      │   8%  │   45     │    6     │  21   │
│ DORA (EU) 2022/2554     │  10%  │   35     │   12     │  14   │
│ FedRAMP Rev 5 (Moderate)│  14%  │  278     │   21     │  89   │
│ PCI DSS 4.0             │  20%  │   66     │   18     │  24   │
├─────────────────────────┼───────┼──────────┼──────────┼───────┤
│ Overall (weighted)      │  25%  │  593     │   67     │ 216   │
└─────────────────────────┴───────┴──────────┴──────────┴───────┘

Risk Rating: HIGH RISK

Top Cross-Framework Priorities (implement once, close multiple):
1. Log retention policy (12 months) → closes FedRAMP AU-11, PCI 10.5.1, DORA 10.2
2. MFA for all accounts → closes FedRAMP IA-2(1), PCI 8.4.2, DORA 9.1, SOC 2 CC6.1
3. AI governance policy → closes NIST GOVERN-1.1, EU AI Act Art.9, ISO 42001 5.2
4. Third-party risk program → closes DORA 28.1, FedRAMP SA-9, PCI 12.8.1
5. Annual penetration testing → closes FedRAMP CA-8, PCI 11.4.2, DORA 26.1
```

---

## File Reference

| Purpose | File |
|---------|------|
| NIST AI RMF 2.0 scanner | `policy_guard/frameworks/nist_ai_rmf.py` |
| ISO 42001 scanner | `policy_guard/frameworks/iso_42001.py` |
| DORA scanner | `policy_guard/frameworks/dora.py` |
| FedRAMP Rev 5 scanner | `policy_guard/frameworks/fedramp_rev5.py` |
| PCI DSS 4.0 scanner | `policy_guard/frameworks/pci_dss_40.py` |
| Cross-framework mapping | `policy_guard/frameworks/mapping.py` |
| Orchestrator (all 9 frameworks) | `policy_guard/scanner.py` |
| Citation evidence library | `compliance_citations/evidence.py` |
| Expanded framework tests | `tests/test_frameworks_expanded.py` |
