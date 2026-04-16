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
