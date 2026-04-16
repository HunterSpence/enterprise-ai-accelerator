"""
compliance_citations/evidence.py
================================

Evidence-grounded compliance answers via the Anthropic Citations API.

The ``EvidenceLibrary`` holds a curated set of regulatory reference texts
(CIS Benchmark, SOC 2 TSC, HIPAA Security Rule, PCI-DSS, EU AI Act Annex IV,
NIST AI RMF, etc.) and exposes a single ``cite`` entry point:

    lib = EvidenceLibrary()
    lib.add_text_source(
        title="EU AI Act — Annex IV",
        text=ANNEX_IV_FULL_TEXT,
        citations_key="eu_ai_act_annex_iv",
    )
    result = await lib.cite(
        question="Does this decision need an Annex IV technical documentation record?",
        system="You are a compliance auditor.",
    )
    for finding in result.findings:
        print(finding.claim)
        for c in finding.citations:
            print("  -", c.cited_text, "in", c.document_title)

The module intentionally keeps the corpus in-memory rather than uploading to
the Files API at import time — the Files API upload path is available via
``upload_corpus()`` for teams running the managed version.

Reference text stubs are provided for the following frameworks:
  - CIS AWS Foundations Benchmark (existing)
  - SOC 2 Type II Trust Service Criteria (existing)
  - HIPAA Security Rule (existing)
  - EU AI Act (existing)
  - NIST AI RMF 1.0/2.0 (existing + updated)
  - ISO/IEC 42001:2023 (new)
  - DORA — Regulation (EU) 2022/2554 (new)
  - FedRAMP Rev 5 (new)
  - PCI DSS 4.0 (new)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core import AIClient, MODEL_OPUS_4_7


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Citation:
    cited_text: str
    document_title: str
    document_index: int
    start_char: int | None = None
    end_char: int | None = None


@dataclass
class CitedFinding:
    claim: str
    citations: list[Citation] = field(default_factory=list)


@dataclass
class CitationResult:
    question: str
    answer_text: str
    findings: list[CitedFinding]
    raw_response: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# EvidenceLibrary
# ---------------------------------------------------------------------------

class EvidenceLibrary:
    """In-memory collection of text sources that can be cited."""

    def __init__(self, ai: AIClient | None = None) -> None:
        self._ai = ai or AIClient(default_model=MODEL_OPUS_4_7)
        self._sources: list[dict[str, Any]] = []

    # ------------------------------------------------------------------

    def add_text_source(
        self,
        *,
        title: str,
        text: str,
        citations_key: str | None = None,
        media_type: str = "text/plain",
    ) -> None:
        """Register a plain-text source that will participate in citations."""
        self._sources.append({
            "type": "document",
            "title": title,
            "source": {
                "type": "text",
                "media_type": media_type,
                "data": text,
            },
            "citations": {"enabled": True},
            "context": citations_key or title,
        })

    def source_count(self) -> int:
        return len(self._sources)

    def clear(self) -> None:
        self._sources.clear()

    # ------------------------------------------------------------------

    async def cite(
        self,
        *,
        question: str,
        system: str = "You are a compliance auditor. Ground every statement in the supplied regulatory documents.",
        model: str | None = None,
        max_tokens: int = 2048,
    ) -> CitationResult:
        """Ask the model a question; the response is cite-grounded."""
        if not self._sources:
            raise RuntimeError("EvidenceLibrary is empty — add at least one source before calling cite().")

        raw = await self._ai.cite(
            system=system,
            question=question,
            documents=self._sources,
            model=model or MODEL_OPUS_4_7,
            max_tokens=max_tokens,
        )

        findings, answer_text = _parse_citations(raw, self._sources)
        return CitationResult(
            question=question,
            answer_text=answer_text,
            findings=findings,
            raw_response=raw,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Reference text stubs for new compliance frameworks
# These stubs are used by EvidenceLibrary to ground citation answers.
# In production, replace with full regulatory text or official excerpts.
# ---------------------------------------------------------------------------

ISO_42001_REFERENCE_TEXT = """
ISO/IEC 42001:2023 — Artificial Intelligence Management System (AIMS)

Clause 4.1 — Understanding the organization and its context:
The organization shall determine external and internal issues that are relevant to its purpose and that affect its ability to achieve the intended outcome(s) of its AI management system.

Clause 5.2 — AI policy:
Top management shall establish, implement, and maintain an AI policy that is appropriate to the purpose of the organization; includes objectives for AI or provides a framework for setting objectives; includes a commitment to satisfy applicable requirements; includes a commitment to continual improvement of the AI management system.

Clause 6.1.2 — AI risk assessment:
The organization shall define and apply an AI risk assessment process that: establishes and maintains criteria for AI risk including the risk acceptance criteria; ensures that repeated AI risk assessments produce consistent, valid, and comparable results; identifies AI risks; analyzes the AI risks; evaluates the AI risks.

Annex A.7.3 — Data quality:
The organization shall implement controls for data quality throughout the AI system lifecycle. This includes ensuring data used for training, validation, and testing is appropriate, representative, and of sufficient quality to support the intended purpose of the AI system.

Annex A.8.2 — AI system transparency:
The organization shall implement controls to ensure AI systems operate transparently and that affected persons and stakeholders can be informed about the AI system in a manner appropriate to the context.

Clause 8.5 — Data management for AI:
The organization shall plan, implement, and control processes for data management throughout the AI system lifecycle. This covers data acquisition, data quality, data governance, and data privacy.
"""

DORA_REFERENCE_TEXT = """
Regulation (EU) 2022/2554 — Digital Operational Resilience Act (DORA)
Date of application: 17 January 2025

Article 5(1) — ICT risk management framework — Management body responsibility:
Financial entities shall have an internal governance and control framework that ensures an effective and prudent management of ICT risk, in accordance with Article 6, in order to achieve a high level of digital operational resilience. The management body of the financial entity shall define, approve, oversee and be responsible for the implementation of all arrangements related to the ICT risk management framework referred to in Article 6(1).

Article 10(1) — Detection:
Financial entities shall have in place mechanisms to promptly detect anomalous activities, including ICT network performance issues and ICT-related incidents, and to identify potential material single points of failure.

Article 11(1) — Business continuity:
As part of the ICT risk management framework referred to in Article 6(1) and based on the identification analysis referred to in Article 8, financial entities shall put in place a comprehensive ICT business continuity policy, which may be adopted as a dedicated specific policy, forming an integral part of the overall business continuity policy of the financial entity.

Article 17(1) — Reporting of major ICT-related incidents to competent authorities:
Financial entities shall report major ICT-related incidents to the relevant competent authority as referred to in Article 46 in accordance with paragraph 4 of this Article.

Article 26(1) — Advanced threat-led penetration testing (TLPT):
Financial entities that are identified in accordance with paragraph 8 shall carry out at least every 3 years advanced testing by means of TLPT. Based on the risk profile of the financial entity and taking into account operational circumstances, the relevant competent authority may, where applicable, request the financial entity to carry out TLPT more frequently.

Article 28(1) — Third-party ICT risk strategy:
Financial entities shall manage ICT third-party risk as an integral component of ICT risk within their ICT risk management framework referred to in Article 6(1), and in accordance with the following principles: (a) financial entities that have in place contractual arrangements for the use of ICT services to run their business operations shall at all times remain fully responsible for compliance with, and the discharge of, all obligations under this Regulation and applicable financial services law.
"""

FEDRAMP_REV5_REFERENCE_TEXT = """
FedRAMP Rev 5 Security Controls Baseline — aligned to NIST SP 800-53 Rev 5 (2023)

CA-5 — Plan of Action and Milestones (POA&M):
Develop a plan of action and milestones for the system to document the planned remediation actions to correct weaknesses or deficiencies noted during the assessment of the controls and to reduce or eliminate known vulnerabilities in the system; and update existing plan of action and milestones monthly based on the findings from control assessments, independent audits or reviews, continuous monitoring activities, and reporting.

CA-7 — Continuous Monitoring:
Develop a system-level continuous monitoring strategy and implement continuous monitoring in accordance with the organization-level continuous monitoring strategy. FedRAMP requires monthly vulnerability scanning, annual penetration testing, monthly POA&M submissions, and annual control assessments.

AU-11 — Audit Record Retention:
Retain audit records for 90 days online and one year total to provide support for after-the-fact investigations of security incidents and to meet regulatory and organizational information retention requirements. FedRAMP requires at least 90 days of audit records available for immediate analysis.

IA-2(1) — Multi-Factor Authentication for Privileged Accounts:
Implement multi-factor authentication for access to privileged accounts. FedRAMP requires MFA for all privileged and non-privileged accounts accessing federal information systems.

IR-6 — Incident Reporting:
Require personnel to report suspected incidents to the organizational incident response capability within US-CERT defined timeframes. FedRAMP requires reporting of incidents to US-CERT within one hour of discovery for Priority 1/2 incidents.

RA-5 — Vulnerability Monitoring and Scanning:
Monitor and scan for vulnerabilities in the system and hosted applications monthly and when new vulnerabilities potentially affecting the system are identified and reported. FedRAMP requires credentialed scans and remediation of critical findings within 30 days.
"""

PCI_DSS_40_REFERENCE_TEXT = """
PCI DSS v4.0 — Payment Card Industry Data Security Standard
Mandatory compliance date: 31 March 2025

Requirement 1 — Install and maintain network security controls:
Network security controls (NSCs) are network-based security solutions that control network traffic between two or more logical or physical network segments (also referred to as subnets) based on pre-defined policies or rules. Organizations must implement and maintain NSCs between all networks and document all services, protocols, and ports allowed.

Requirement 3.2.1 — Sensitive authentication data (SAD) not stored after authorization:
SAD is not retained after authorization, even if encrypted. All sensitive authentication data received is rendered unrecoverable upon completion of the authorization process. This applies to full track data, card verification codes, and PINs.

Requirement 4.2.1 — Strong cryptography for PAN transmission:
Strong cryptography is used to safeguard PAN during transmission over open, public networks. PCI DSS requires a minimum of TLS 1.2 for all transmissions of cardholder data. SSL and early TLS (1.0 and 1.1) are not permitted.

Requirement 8.4.2 — MFA for all access to CDE (new in v4.0):
Multi-factor authentication (MFA) is implemented for all access into the cardholder data environment (CDE). This is a new requirement in PCI DSS v4.0, expanding the MFA requirement from administrative access only (v3.2.1) to all user access.

Requirement 10.5.1 — Audit log retention:
Retain audit log history for at least 12 months, with at least the most recent three months available for immediate analysis. This supports forensic investigations and regulatory requirements.

Requirement 11.6.1 — Change and tamper detection for payment pages (new in v4.0):
A change- and tamper-detection mechanism is deployed as follows: to alert personnel to unauthorized modification (including indicators of compromise, changes, additions, and deletions) to the HTTP headers and the contents of payment pages as received by the consumer browser; the mechanism is configured to evaluate the received HTTP header and payment page; the entity is alerted to changes. This is a new requirement in PCI DSS v4.0 targeting e-commerce skimming attacks.

Requirement 12.3.1 — Risk assessment process (new in v4.0, Defined Approach):
Each targeted risk analysis required by PCI DSS is documented to include: identification of the assets being protected; identification of the threat(s) that the requirement is protecting against; resulting analysis that results in the likelihood or probability of the threat being realized; and the impact resulting from the risk materializing.
"""


def load_expanded_framework_stubs(library: EvidenceLibrary) -> None:
    """
    Register reference text stubs for ISO 42001, DORA, FedRAMP Rev 5, and PCI DSS 4.0
    into the given EvidenceLibrary instance.

    Call this before ``cite()`` when you want the Citations API to ground answers
    in the new compliance frameworks.

    Example:
        lib = EvidenceLibrary()
        load_expanded_framework_stubs(lib)
        result = await lib.cite(question="What does DORA require for incident reporting?")
    """
    library.add_text_source(
        title="ISO/IEC 42001:2023 — AI Management System",
        text=ISO_42001_REFERENCE_TEXT,
        citations_key="iso_42001",
    )
    library.add_text_source(
        title="DORA — Regulation (EU) 2022/2554",
        text=DORA_REFERENCE_TEXT,
        citations_key="dora",
    )
    library.add_text_source(
        title="FedRAMP Rev 5 Security Controls Baseline",
        text=FEDRAMP_REV5_REFERENCE_TEXT,
        citations_key="fedramp_rev5",
    )
    library.add_text_source(
        title="PCI DSS v4.0 — Payment Card Industry Data Security Standard",
        text=PCI_DSS_40_REFERENCE_TEXT,
        citations_key="pci_dss_40",
    )


def _parse_citations(
    response: dict[str, Any],
    sources: list[dict[str, Any]],
) -> tuple[list[CitedFinding], str]:
    """Walk Anthropic's response content blocks and extract cite-bearing text."""
    findings: list[CitedFinding] = []
    answer_parts: list[str] = []

    content_blocks = response.get("content", []) or []
    for block in content_blocks:
        btype = block.get("type")
        if btype != "text":
            continue

        text = block.get("text", "") or ""
        answer_parts.append(text)

        citations_raw = block.get("citations") or []
        if not citations_raw:
            # No citations on this block — record as a no-citation finding.
            if text.strip():
                findings.append(CitedFinding(claim=text.strip(), citations=[]))
            continue

        cites: list[Citation] = []
        for c in citations_raw:
            idx = c.get("document_index", 0)
            title = sources[idx]["title"] if 0 <= idx < len(sources) else c.get("document_title", "unknown")
            cites.append(Citation(
                cited_text=c.get("cited_text", ""),
                document_title=title,
                document_index=idx,
                start_char=c.get("start_char_index"),
                end_char=c.get("end_char_index"),
            ))
        findings.append(CitedFinding(claim=text.strip(), citations=cites))

    return findings, "".join(answer_parts).strip()
