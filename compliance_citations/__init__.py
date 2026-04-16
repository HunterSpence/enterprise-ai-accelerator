"""
compliance_citations — Evidence-cited compliance findings via Citations API
===========================================================================

When PolicyGuard flags a violation, the auditor always wants to know which
line in which regulation framework justified the flag. The Citations API
makes that traceable: every claim in the output is automatically linked
back to the source document and character range.

This module wraps:
  - Anthropic Files API (upload CIS Benchmark PDFs, HIPAA reference docs,
    SOC 2 trust services criteria, EU AI Act Annex IV, NIST AI RMF)
  - Anthropic Citations feature (``citations: {"enabled": true}`` on each
    document block) so the model's response returns grounded citations

Pair this with ai_audit_trail.decorators.ai_decision to persist the raw
citation spans into the Merkle chain — then every PolicyGuard finding has
an auditor-friendly Annex IV evidence record.
"""

from compliance_citations.evidence import (
    EvidenceLibrary,
    CitationResult,
    CitedFinding,
)

__all__ = ["EvidenceLibrary", "CitationResult", "CitedFinding"]
