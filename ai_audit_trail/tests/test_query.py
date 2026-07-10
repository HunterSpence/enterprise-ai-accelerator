"""
test_query.py — Tests for QueryEngine, notably the P0-02 cross-tenant fix.

Regression coverage for: GET /audit-logs used to filter the COUNT by
system_id but return ROWS from every system, and ignored offset entirely.
QueryEngine.filter() now threads system_id and offset through to
AuditChain.query() so both are actually honored.
"""

from __future__ import annotations

from ai_audit_trail.chain import AuditChain
from ai_audit_trail.query import QueryEngine


def test_filter_system_id_excludes_other_tenants(empty_chain: AuditChain):
    """Regression for P0-02: querying system A must return ZERO system-B rows."""
    for i in range(5):
        empty_chain.append(
            session_id=f"a{i}", model="m", input_text="in", output_text="out",
            input_tokens=10, output_tokens=10, latency_ms=100.0,
            system_id="tenant-a",
        )
    for i in range(5):
        empty_chain.append(
            session_id=f"b{i}", model="m", input_text="in", output_text="out",
            input_tokens=10, output_tokens=10, latency_ms=100.0,
            system_id="tenant-b",
        )

    qe = QueryEngine(empty_chain)
    tenant_a_rows = qe.filter(system_id="tenant-a", limit=100)

    assert len(tenant_a_rows) == 5
    assert all(e.system_id == "tenant-a" for e in tenant_a_rows)
    assert not any(e.system_id == "tenant-b" for e in tenant_a_rows)


def test_filter_offset_returns_a_different_page(empty_chain: AuditChain):
    """Regression for P0-02: offset was previously silently dropped."""
    for i in range(10):
        empty_chain.append(
            session_id=f"s{i}", model="m", input_text=f"in{i}", output_text=f"out{i}",
            input_tokens=10, output_tokens=10, latency_ms=100.0,
            system_id="tenant-a",
        )

    qe = QueryEngine(empty_chain)
    page1 = qe.filter(system_id="tenant-a", limit=5, offset=0)
    page2 = qe.filter(system_id="tenant-a", limit=5, offset=5)

    assert len(page1) == 5
    assert len(page2) == 5
    page1_ids = {e.entry_id for e in page1}
    page2_ids = {e.entry_id for e in page2}
    assert page1_ids.isdisjoint(page2_ids)
