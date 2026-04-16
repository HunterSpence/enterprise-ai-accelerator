"""
policy_guard/frameworks/mapping.py
===================================
Cross-framework traceability matrix.

Provides:
  CONTROL_MAPPINGS  — dict[str, dict[str, list[str]]]
      Keys are canonical control IDs (e.g. "CIS_AWS_2.1.2").
      Values are dicts mapping framework names to equivalent control IDs.

  get_equivalents(framework, control) -> dict[str, list[str]]
      Given a framework + control ID, return all equivalents in other frameworks.

  coverage_report(findings) -> dict
      Given a list of finding dicts (each with 'framework' and 'control_id'),
      return per-framework coverage percentage and gap counts.

Framework name constants used throughout:
  - "CIS_AWS"       — CIS AWS Foundations Benchmark
  - "SOC2"          — SOC 2 Type II (Trust Service Criteria)
  - "HIPAA"         — HIPAA Security Rule
  - "EU_AI_ACT"     — EU AI Act (Regulation EU 2024/1689)
  - "NIST_AI_RMF"   — NIST AI RMF (NIST AI 100-1 + 600-1 Gen AI Profile)
  - "ISO_42001"     — ISO/IEC 42001:2023
  - "DORA"          — Regulation (EU) 2022/2554
  - "FEDRAMP"       — FedRAMP Rev 5 (NIST SP 800-53 Rev 5 baselines)
  - "PCI_DSS_40"    — PCI DSS 4.0

Control ID format conventions:
  CIS_AWS       → "CIS_AWS_<section>"          e.g. "CIS_AWS_2.1.2"
  SOC2          → "SOC2_<criterion>"            e.g. "SOC2_CC6.7"
  HIPAA         → "HIPAA_<section>"             e.g. "HIPAA_164.312(a)(2)(iv)"
  EU_AI_ACT     → "EU_AI_ACT_Art<N>"            e.g. "EU_AI_ACT_Art10"
  NIST_AI_RMF   → "NIST_AI_RMF_<FUNC>-<N.N>"   e.g. "NIST_AI_RMF_GOVERN-1.1"
  ISO_42001     → "ISO_42001_<clause>"           e.g. "ISO_42001_A.7.3"
  DORA          → "DORA_<article>"               e.g. "DORA_9.1"
  FEDRAMP       → "FEDRAMP_<family>-<N>"         e.g. "FEDRAMP_AU-11"
  PCI_DSS_40    → "PCI_DSS_40_<req>"             e.g. "PCI_DSS_40_10.5.1"
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Control totals per framework (used for coverage_report denominator)
# ---------------------------------------------------------------------------

FRAMEWORK_CONTROL_TOTALS: dict[str, int] = {
    "CIS_AWS": 176,          # CIS AWS Foundations Benchmark v3.0
    "SOC2": 50,              # 38 CC + 12 AICC
    "HIPAA": 42,             # Security Rule addressable + required safeguards
    "EU_AI_ACT": 13,         # High-risk AI obligations (articles)
    "NIST_AI_RMF": 72,       # Full subcategory count (GOVERN/MAP/MEASURE/MANAGE)
    "ISO_42001": 49,         # Clauses 4-10 + Annex A
    "DORA": 39,              # Controls catalogued across chapters II-VII
    "FEDRAMP": 248,          # Controls catalogued across 18 families
    "PCI_DSS_40": 83,        # Sub-requirements across 12 principal requirements
}


# ---------------------------------------------------------------------------
# Cross-framework traceability matrix
# ---------------------------------------------------------------------------
# Format: CONTROL_MAPPINGS[canonical_id] = {framework: [equivalent_ids...]}
# Canonical ID uses the framework prefix of the control being described.
# Only the most authoritative mappings are listed; not every permutation.

CONTROL_MAPPINGS: dict[str, dict[str, list[str]]] = {

    # --- Encryption at rest ---
    "CIS_AWS_2.1.2": {
        "SOC2":       ["SOC2_CC6.7"],
        "HIPAA":      ["HIPAA_164.312(a)(2)(iv)"],
        "FEDRAMP":    ["FEDRAMP_SC-28"],
        "PCI_DSS_40": ["PCI_DSS_40_3.5.1"],
    },
    "CIS_AWS_2.2.1": {
        "SOC2":       ["SOC2_CC6.7"],
        "HIPAA":      ["HIPAA_164.312(a)(2)(iv)"],
        "FEDRAMP":    ["FEDRAMP_SC-28"],
        "PCI_DSS_40": ["PCI_DSS_40_3.5.1"],
    },

    # --- Encryption in transit ---
    "PCI_DSS_40_4.2.1": {
        "CIS_AWS":    ["CIS_AWS_2.1"],
        "SOC2":       ["SOC2_CC6.7"],
        "HIPAA":      ["HIPAA_164.312(e)(2)(ii)"],
        "FEDRAMP":    ["FEDRAMP_SC-8"],
        "DORA":       ["DORA_9.1"],
    },

    # --- MFA / Authentication ---
    "FEDRAMP_IA-2(1)": {
        "CIS_AWS":    ["CIS_AWS_1.10"],
        "SOC2":       ["SOC2_CC6.1"],
        "HIPAA":      ["HIPAA_164.312(d)"],
        "PCI_DSS_40": ["PCI_DSS_40_8.4.1", "PCI_DSS_40_8.4.2"],
        "DORA":       ["DORA_9.1"],
    },

    # --- Access control / Least privilege ---
    "FEDRAMP_AC-6": {
        "CIS_AWS":    ["CIS_AWS_1.16"],
        "SOC2":       ["SOC2_CC6.3"],
        "HIPAA":      ["HIPAA_164.312(a)(1)"],
        "PCI_DSS_40": ["PCI_DSS_40_7.2.2"],
        "DORA":       ["DORA_9.1"],
    },
    "PCI_DSS_40_7.2.2": {
        "CIS_AWS":    ["CIS_AWS_1.16"],
        "SOC2":       ["SOC2_CC6.3"],
        "HIPAA":      ["HIPAA_164.312(a)(1)"],
        "FEDRAMP":    ["FEDRAMP_AC-6"],
        "NIST_AI_RMF": ["NIST_AI_RMF_GOVERN-1.2"],
    },

    # --- Audit logging ---
    "FEDRAMP_AU-11": {
        "CIS_AWS":    ["CIS_AWS_3.1", "CIS_AWS_3.2"],
        "SOC2":       ["SOC2_CC7.2"],
        "PCI_DSS_40": ["PCI_DSS_40_10.5.1"],
        "DORA":       ["DORA_10.2"],
        "HIPAA":      ["HIPAA_164.312(b)"],
    },
    "PCI_DSS_40_10.5.1": {
        "CIS_AWS":    ["CIS_AWS_3.1"],
        "SOC2":       ["SOC2_CC7.2"],
        "FEDRAMP":    ["FEDRAMP_AU-11"],
        "DORA":       ["DORA_10.2"],
        "HIPAA":      ["HIPAA_164.312(b)"],
    },
    "DORA_10.2": {
        "CIS_AWS":    ["CIS_AWS_3.1"],
        "SOC2":       ["SOC2_CC7.2"],
        "FEDRAMP":    ["FEDRAMP_AU-11", "FEDRAMP_AU-12"],
        "PCI_DSS_40": ["PCI_DSS_40_10.5.1"],
    },

    # --- Vulnerability management ---
    "FEDRAMP_RA-5": {
        "CIS_AWS":    ["CIS_AWS_2.6"],
        "SOC2":       ["SOC2_CC7.1"],
        "PCI_DSS_40": ["PCI_DSS_40_11.3.1", "PCI_DSS_40_11.3.2"],
        "DORA":       ["DORA_25.1"],
    },
    "PCI_DSS_40_11.3.1": {
        "CIS_AWS":    ["CIS_AWS_2.6"],
        "SOC2":       ["SOC2_CC7.1"],
        "FEDRAMP":    ["FEDRAMP_RA-5"],
        "DORA":       ["DORA_25.1"],
    },
    "DORA_25.1": {
        "FEDRAMP":    ["FEDRAMP_CA-8", "FEDRAMP_RA-5"],
        "PCI_DSS_40": ["PCI_DSS_40_11.4.2", "PCI_DSS_40_11.4.3"],
        "SOC2":       ["SOC2_CC7.1"],
    },

    # --- Incident response ---
    "FEDRAMP_IR-6": {
        "SOC2":       ["SOC2_CC7.3", "SOC2_CC7.4"],
        "HIPAA":      ["HIPAA_164.308(a)(6)"],
        "PCI_DSS_40": ["PCI_DSS_40_12.10.1"],
        "DORA":       ["DORA_17.1"],
        "EU_AI_ACT":  ["EU_AI_ACT_Art62"],
    },
    "DORA_17.1": {
        "FEDRAMP":    ["FEDRAMP_IR-6", "FEDRAMP_IR-8"],
        "SOC2":       ["SOC2_CC7.3", "SOC2_CC7.4"],
        "PCI_DSS_40": ["PCI_DSS_40_12.10.1"],
        "HIPAA":      ["HIPAA_164.308(a)(6)"],
    },
    "PCI_DSS_40_12.10.1": {
        "FEDRAMP":    ["FEDRAMP_IR-8"],
        "SOC2":       ["SOC2_CC7.3"],
        "DORA":       ["DORA_15.1", "DORA_17.1"],
        "HIPAA":      ["HIPAA_164.308(a)(6)"],
    },

    # --- Business continuity / Backup ---
    "FEDRAMP_CP-9": {
        "SOC2":       ["SOC2_A1.2"],
        "HIPAA":      ["HIPAA_164.310(a)(2)(iv)"],
        "PCI_DSS_40": ["PCI_DSS_40_12.1.1"],
        "DORA":       ["DORA_11.3"],
    },
    "DORA_11.3": {
        "FEDRAMP":    ["FEDRAMP_CP-9"],
        "SOC2":       ["SOC2_A1.2"],
        "HIPAA":      ["HIPAA_164.310(a)(2)(iv)"],
        "PCI_DSS_40": ["PCI_DSS_40_12.1.1"],
    },

    # --- Third-party / Supply chain risk ---
    "DORA_28.1": {
        "FEDRAMP":    ["FEDRAMP_SA-9", "FEDRAMP_SR-2"],
        "SOC2":       ["SOC2_CC9.2"],
        "PCI_DSS_40": ["PCI_DSS_40_12.8.1"],
        "ISO_42001":  ["ISO_42001_A.10.2"],
        "NIST_AI_RMF": ["NIST_AI_RMF_GOVERN-6.1"],
    },
    "PCI_DSS_40_12.8.1": {
        "FEDRAMP":    ["FEDRAMP_SA-9"],
        "SOC2":       ["SOC2_CC9.2"],
        "DORA":       ["DORA_28.1"],
        "ISO_42001":  ["ISO_42001_A.10.2"],
    },
    "FEDRAMP_SA-9": {
        "SOC2":       ["SOC2_CC9.2"],
        "PCI_DSS_40": ["PCI_DSS_40_12.8.1", "PCI_DSS_40_12.8.2"],
        "DORA":       ["DORA_28.1", "DORA_30.1"],
        "ISO_42001":  ["ISO_42001_A.10.2"],
        "NIST_AI_RMF": ["NIST_AI_RMF_GOVERN-6.1"],
    },

    # --- AI governance / Policies ---
    "NIST_AI_RMF_GOVERN-1.1": {
        "EU_AI_ACT":  ["EU_AI_ACT_Art9"],
        "ISO_42001":  ["ISO_42001_5.2", "ISO_42001_A.2.2"],
        "SOC2":       ["SOC2_CC1.1"],
    },
    "ISO_42001_5.2": {
        "NIST_AI_RMF": ["NIST_AI_RMF_GOVERN-1.1"],
        "EU_AI_ACT":  ["EU_AI_ACT_Art9"],
        "SOC2":       ["SOC2_CC1.1"],
    },
    "EU_AI_ACT_Art9": {
        "NIST_AI_RMF": ["NIST_AI_RMF_GOVERN-1.1", "NIST_AI_RMF_GOVERN-1.3"],
        "ISO_42001":  ["ISO_42001_6.1", "ISO_42001_6.1.2"],
        "SOC2":       ["SOC2_CC3.1"],
    },

    # --- AI transparency / Explainability ---
    "NIST_AI_RMF_MEASURE-2.9": {
        "EU_AI_ACT":  ["EU_AI_ACT_Art13"],
        "ISO_42001":  ["ISO_42001_A.8.2"],
        "SOC2":       ["SOC2_CC6.1"],
    },
    "EU_AI_ACT_Art13": {
        "NIST_AI_RMF": ["NIST_AI_RMF_MEASURE-2.9", "NIST_AI_RMF_MEASURE-2.10"],
        "ISO_42001":  ["ISO_42001_A.8.2", "ISO_42001_A.5.2"],
    },

    # --- AI bias / Fairness ---
    "NIST_AI_RMF_MEASURE-2.3": {
        "EU_AI_ACT":  ["EU_AI_ACT_Art10"],
        "ISO_42001":  ["ISO_42001_A.7.3"],
        "SOC2":       ["SOC2_CC6.1"],
    },
    "ISO_42001_A.7.3": {
        "NIST_AI_RMF": ["NIST_AI_RMF_MEASURE-2.3"],
        "EU_AI_ACT":  ["EU_AI_ACT_Art10"],
    },
    "EU_AI_ACT_Art10": {
        "NIST_AI_RMF": ["NIST_AI_RMF_MEASURE-2.3", "NIST_AI_RMF_MAP-3.3"],
        "ISO_42001":  ["ISO_42001_A.7.3", "ISO_42001_8.5"],
    },

    # --- AI incident management ---
    "EU_AI_ACT_Art62": {
        "NIST_AI_RMF": ["NIST_AI_RMF_MANAGE-1.2"],
        "ISO_42001":  ["ISO_42001_8.7", "ISO_42001_A.9.4"],
        "FEDRAMP":    ["FEDRAMP_IR-6"],
        "DORA":       ["DORA_17.1"],
    },
    "ISO_42001_8.7": {
        "NIST_AI_RMF": ["NIST_AI_RMF_MANAGE-1.2"],
        "EU_AI_ACT":  ["EU_AI_ACT_Art62"],
        "FEDRAMP":    ["FEDRAMP_IR-4", "FEDRAMP_IR-8"],
        "DORA":       ["DORA_15.1"],
    },

    # --- AI post-deployment monitoring ---
    "NIST_AI_RMF_MANAGE-2.4": {
        "EU_AI_ACT":  ["EU_AI_ACT_Art72"],
        "ISO_42001":  ["ISO_42001_9.1", "ISO_42001_A.9.1"],
    },
    "EU_AI_ACT_Art72": {
        "NIST_AI_RMF": ["NIST_AI_RMF_MANAGE-2.4"],
        "ISO_42001":  ["ISO_42001_9.1"],
    },

    # --- Privacy ---
    "NIST_AI_RMF_MEASURE-2.6": {
        "EU_AI_ACT":  ["EU_AI_ACT_Art10"],
        "ISO_42001":  ["ISO_42001_A.7.4"],
        "HIPAA":      ["HIPAA_164.308(a)(1)"],
    },
    "ISO_42001_A.7.4": {
        "NIST_AI_RMF": ["NIST_AI_RMF_MEASURE-2.6"],
        "HIPAA":      ["HIPAA_164.308(a)(1)"],
        "EU_AI_ACT":  ["EU_AI_ACT_Art10"],
    },

    # --- Key management ---
    "FEDRAMP_SC-12": {
        "CIS_AWS":    ["CIS_AWS_3.7"],
        "SOC2":       ["SOC2_CC6.7"],
        "PCI_DSS_40": ["PCI_DSS_40_3.6.1", "PCI_DSS_40_3.7.1"],
        "HIPAA":      ["HIPAA_164.312(a)(2)(iv)"],
    },
    "PCI_DSS_40_3.7.1": {
        "FEDRAMP":    ["FEDRAMP_SC-12"],
        "CIS_AWS":    ["CIS_AWS_3.7"],
        "SOC2":       ["SOC2_CC6.7"],
    },

    # --- Configuration management ---
    "FEDRAMP_CM-6": {
        "CIS_AWS":    ["CIS_AWS_1.1"],
        "SOC2":       ["SOC2_CC8.1"],
        "PCI_DSS_40": ["PCI_DSS_40_2.2.1"],
        "DORA":       ["DORA_9.2"],
    },
    "PCI_DSS_40_2.2.1": {
        "CIS_AWS":    ["CIS_AWS_1.1"],
        "FEDRAMP":    ["FEDRAMP_CM-6"],
        "SOC2":       ["SOC2_CC8.1"],
    },

    # --- Risk assessment ---
    "FEDRAMP_RA-3": {
        "ISO_42001":  ["ISO_42001_6.1.2"],
        "NIST_AI_RMF": ["NIST_AI_RMF_MAP-4.1"],
        "DORA":       ["DORA_6.1"],
        "PCI_DSS_40": ["PCI_DSS_40_12.3.1"],
    },
    "ISO_42001_6.1.2": {
        "NIST_AI_RMF": ["NIST_AI_RMF_MAP-2.3"],
        "EU_AI_ACT":  ["EU_AI_ACT_Art9"],
        "FEDRAMP":    ["FEDRAMP_RA-3"],
        "DORA":       ["DORA_6.1"],
    },

    # --- Penetration testing ---
    "FEDRAMP_CA-8": {
        "SOC2":       ["SOC2_CC7.1"],
        "PCI_DSS_40": ["PCI_DSS_40_11.4.2", "PCI_DSS_40_11.4.3"],
        "DORA":       ["DORA_26.1"],
    },
    "DORA_26.1": {
        "FEDRAMP":    ["FEDRAMP_CA-8"],
        "PCI_DSS_40": ["PCI_DSS_40_11.4.2"],
        "SOC2":       ["SOC2_CC7.1"],
    },

    # --- Physical security ---
    "FEDRAMP_PE-3": {
        "SOC2":       ["SOC2_CC6.4"],
        "HIPAA":      ["HIPAA_164.310(a)(1)"],
        "PCI_DSS_40": ["PCI_DSS_40_9.2.1"],
    },
    "PCI_DSS_40_9.2.1": {
        "FEDRAMP":    ["FEDRAMP_PE-3"],
        "SOC2":       ["SOC2_CC6.4"],
        "HIPAA":      ["HIPAA_164.310(a)(1)"],
    },
}


# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------

def get_equivalents(framework: str, control: str) -> dict[str, list[str]]:
    """
    Given a framework name and control ID, return equivalent controls in other frameworks.

    Example:
        get_equivalents("FEDRAMP", "AU-11")
        # Returns: {"CIS_AWS": ["CIS_AWS_3.1", "CIS_AWS_3.2"], "SOC2": [...], ...}

    The function constructs the canonical key and looks up both directions.
    """
    # Normalize: build canonical key
    canonical = f"{framework}_{control}"

    result: dict[str, list[str]] = {}

    # Direct lookup
    if canonical in CONTROL_MAPPINGS:
        result = dict(CONTROL_MAPPINGS[canonical])

    # Reverse lookup: find any entry that maps back to this control
    for key, mappings in CONTROL_MAPPINGS.items():
        if key == canonical:
            continue
        source_fw = _extract_framework(key)
        if source_fw and framework in mappings:
            if control in mappings[framework] or canonical in [f"{framework}_{c}" for c in mappings.get(framework, [])]:
                # This key maps to our control — add the key's framework as a reverse entry
                key_control = key[len(source_fw) + 1:]  # strip "FW_" prefix
                if source_fw not in result:
                    result[source_fw] = []
                if key_control not in result[source_fw]:
                    result[source_fw].append(key_control)

    return result


def _extract_framework(canonical_id: str) -> str | None:
    """Extract the framework prefix from a canonical control ID."""
    for fw in FRAMEWORK_CONTROL_TOTALS:
        if canonical_id.startswith(f"{fw}_"):
            return fw
    return None


def coverage_report(findings: list[dict]) -> dict:
    """
    Given a list of finding dicts, return per-framework coverage analysis.

    Each finding dict must have at minimum:
        {"framework": str, "control_id": str, "status": str}  (status: "PASS" | "FAIL")

    Returns:
        {
            "FEDRAMP": {
                "total_controls": 248,
                "evaluated": 15,
                "passing": 10,
                "failing": 5,
                "coverage_pct": 6.0,      # evaluated / total_controls * 100
                "pass_rate_pct": 66.7,     # passing / evaluated * 100
            },
            ...
        }
    """
    per_fw: dict[str, dict[str, Any]] = {}

    for fw, total in FRAMEWORK_CONTROL_TOTALS.items():
        per_fw[fw] = {
            "total_controls": total,
            "evaluated": 0,
            "passing": 0,
            "failing": 0,
            "coverage_pct": 0.0,
            "pass_rate_pct": 0.0,
        }

    for f in findings:
        fw = f.get("framework", "")
        status = f.get("status", "FAIL")
        if fw not in per_fw:
            per_fw[fw] = {
                "total_controls": 0,
                "evaluated": 0,
                "passing": 0,
                "failing": 0,
                "coverage_pct": 0.0,
                "pass_rate_pct": 0.0,
            }
        per_fw[fw]["evaluated"] += 1
        if status == "PASS":
            per_fw[fw]["passing"] += 1
        else:
            per_fw[fw]["failing"] += 1

    # Compute percentages
    for fw, data in per_fw.items():
        total = data["total_controls"]
        evaluated = data["evaluated"]
        passing = data["passing"]
        data["coverage_pct"] = round(evaluated / total * 100, 1) if total > 0 else 0.0
        data["pass_rate_pct"] = round(passing / evaluated * 100, 1) if evaluated > 0 else 0.0

    return per_fw


def mapping_matrix_size() -> int:
    """Return the total number of cross-framework mapping entries in CONTROL_MAPPINGS."""
    return sum(len(targets) for mappings in CONTROL_MAPPINGS.values() for targets in mappings.values())
