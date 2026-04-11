"""
conftest.py — Shared pytest fixtures for AIAuditTrail test suite.

Provides:
- in-memory SQLite AuditChain (fast, no disk I/O)
- Pre-populated chain with mock log entries across multiple systems
- Mock log entry factory
- IncidentManager fixture
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generator

import pytest

from ai_audit_trail.chain import AuditChain, DecisionType, LogEntry, RiskTier
from ai_audit_trail.incident_manager import IncidentManager, IncidentSeverity


# ---------------------------------------------------------------------------
# Chain fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_chain() -> Generator[AuditChain, None, None]:
    """An in-memory AuditChain with zero entries."""
    chain = AuditChain(":memory:")
    yield chain
    chain.close()


@pytest.fixture
def populated_chain() -> Generator[AuditChain, None, None]:
    """
    An in-memory AuditChain pre-populated with 20 entries across
    two systems and multiple risk tiers / decision types.
    """
    chain = AuditChain(":memory:", store_plaintext=True)
    systems = ["loan-approval-v2", "fraud-detection-v3"]
    models = ["claude-sonnet-4-6", "claude-haiku-4-5", "gpt-4o"]
    tiers = [RiskTier.HIGH, RiskTier.HIGH, RiskTier.LIMITED, RiskTier.MINIMAL]
    dtypes = list(DecisionType)

    for i in range(20):
        chain.append(
            session_id=f"session-{i % 5}",
            model=models[i % len(models)],
            input_text=f"Input prompt number {i}",
            output_text=f"Model response number {i}",
            input_tokens=100 + i * 10,
            output_tokens=50 + i * 5,
            latency_ms=float(200 + i * 50),
            decision_type=dtypes[i % len(dtypes)],
            risk_tier=tiers[i % len(tiers)],
            system_id=systems[i % len(systems)],
            cost_usd=round(0.001 * (i + 1), 6),
            metadata={"index": i, "batch": i // 5},
        )

    yield chain
    chain.close()


@pytest.fixture
def high_risk_chain() -> Generator[AuditChain, None, None]:
    """Chain with only HIGH-risk CLASSIFICATION entries (bias detection tests)."""
    chain = AuditChain(":memory:")
    # 30 entries, all HIGH-risk CLASSIFICATION, limited output diversity
    for i in range(30):
        chain.append(
            session_id=f"hr-session-{i}",
            model="claude-sonnet-4-6",
            input_text=f"Applicant profile {i}",
            output_text="APPROVED" if i % 5 != 0 else "DENIED",  # low diversity
            input_tokens=120,
            output_tokens=10,
            latency_ms=300.0,
            decision_type=DecisionType.CLASSIFICATION,
            risk_tier=RiskTier.HIGH,
            system_id="loan-approval-v2",
            cost_usd=0.00025,
        )
    yield chain
    chain.close()


# ---------------------------------------------------------------------------
# Entry factory
# ---------------------------------------------------------------------------

def make_entry(
    system_id: str = "test-system",
    model: str = "claude-sonnet-4-6",
    input_text: str = "test input",
    output_text: str = "test output",
    input_tokens: int = 100,
    output_tokens: int = 50,
    latency_ms: float = 300.0,
    decision_type: DecisionType = DecisionType.GENERATION,
    risk_tier: RiskTier = RiskTier.LIMITED,
    cost_usd: float = 0.001,
) -> dict:
    """Return kwargs dict for AuditChain.append()."""
    return {
        "session_id": str(uuid.uuid4())[:8],
        "model": model,
        "input_text": input_text,
        "output_text": output_text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
        "decision_type": decision_type,
        "risk_tier": risk_tier,
        "system_id": system_id,
        "cost_usd": cost_usd,
        "metadata": {},
    }


@pytest.fixture
def entry_factory():
    """Return the make_entry factory function."""
    return make_entry


# ---------------------------------------------------------------------------
# IncidentManager fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def incident_manager() -> IncidentManager:
    """A fresh in-memory IncidentManager."""
    return IncidentManager()


@pytest.fixture
def p0_incident(incident_manager: IncidentManager):
    """A pre-created P0-SAFETY incident."""
    return incident_manager.create_incident(
        system_id="loan-approval-v2",
        system_name="Loan Approval AI",
        severity=IncidentSeverity.P0_SAFETY,
        title="Safety incident: harmful output detected",
        description="Output contained harmful loan denial reasoning targeting protected class",
        evidence_entry_ids=["entry-001", "entry-002"],
        affected_persons_estimate=150,
        detected_by="automated",
    )


@pytest.fixture
def p0_discrimination_incident(incident_manager: IncidentManager):
    """A pre-created P0-DISCRIMINATION incident."""
    return incident_manager.create_incident(
        system_id="hr-screening-v1",
        system_name="HR Screening AI",
        severity=IncidentSeverity.P0_DISCRIMINATION,
        title="Disparate impact: gender bias detected",
        description="Approval rate 0.42 for female applicants vs 0.78 for male applicants",
        evidence_entry_ids=["entry-010", "entry-011", "entry-012"],
        affected_persons_estimate=342,
        detected_by="automated",
    )
