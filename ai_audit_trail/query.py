"""
query.py — Audit log querying, aggregation, and export.

Provides a high-level QueryEngine over an AuditChain with filtering,
aggregation stats, CSV/JSON export, and per-entry explanation.
"""

from __future__ import annotations

import csv
import io
import json
import statistics
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

from ai_audit_trail.chain import AuditChain, DecisionType, LogEntry, RiskTier


class QueryEngine:
    """
    High-level query interface for an AuditChain.

    Usage::

        qe = QueryEngine(chain)

        # Get all HIGH-risk entries in a date range
        entries = qe.filter(
            risk_tier=RiskTier.HIGH,
            since="2026-01-01T00:00:00+00:00",
        )

        # Aggregate stats
        stats = qe.aggregate_stats()

        # Export as CSV
        csv_text = qe.export_csv(entries)

        # Explain a specific entry
        info = qe.explain(entry_id="some-uuid")
    """

    def __init__(self, chain: AuditChain) -> None:
        self.chain = chain

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter(
        self,
        session_id: Optional[str] = None,
        decision_type: Optional[DecisionType | str] = None,
        risk_tier: Optional[RiskTier | str] = None,
        model: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[LogEntry]:
        """
        Filter audit entries. All parameters are optional AND conditions.

        Parameters
        ----------
        session_id: filter to a specific conversation session
        decision_type: RECOMMENDATION | CLASSIFICATION | GENERATION | AUTONOMOUS_ACTION
        risk_tier: MINIMAL | LIMITED | HIGH | UNACCEPTABLE
        model: exact model name match
        since: ISO 8601 UTC start timestamp (inclusive)
        until: ISO 8601 UTC end timestamp (inclusive)
        limit: maximum number of entries to return
        """
        if isinstance(decision_type, DecisionType):
            decision_type = decision_type.value
        if isinstance(risk_tier, RiskTier):
            risk_tier = risk_tier.value

        return self.chain.query(
            session_id=session_id,
            decision_type=decision_type,
            risk_tier=risk_tier,
            model=model,
            since=since,
            until=until,
            limit=limit,
        )

    def get_by_session(self, session_id: str) -> list[LogEntry]:
        """Return all entries for a given session, ordered chronologically."""
        return self.filter(session_id=session_id)

    def get_high_risk(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> list[LogEntry]:
        """Return all HIGH-risk tier entries in optional date range."""
        return self.filter(
            risk_tier=RiskTier.HIGH,
            since=since,
            until=until,
        )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def aggregate_stats(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Compute aggregate statistics over the audit log.

        Returns a dict with:
        - total_decisions: int
        - by_risk_tier: {tier: count}
        - by_decision_type: {type: count}
        - by_model: {model: count}
        - avg_latency_ms: float
        - median_latency_ms: float
        - p95_latency_ms: float
        - total_input_tokens: int
        - total_output_tokens: int
        - unique_sessions: int
        - date_range: {first, last}
        """
        entries = self.filter(since=since, until=until)

        if not entries:
            return {
                "total_decisions": 0,
                "by_risk_tier": {},
                "by_decision_type": {},
                "by_model": {},
                "avg_latency_ms": 0.0,
                "median_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "unique_sessions": 0,
                "date_range": {"first": None, "last": None},
            }

        by_risk: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_model: dict[str, int] = {}
        sessions: set[str] = set()
        latencies: list[float] = []
        total_in = 0
        total_out = 0

        for e in entries:
            by_risk[e.risk_tier] = by_risk.get(e.risk_tier, 0) + 1
            by_type[e.decision_type] = by_type.get(e.decision_type, 0) + 1
            by_model[e.model] = by_model.get(e.model, 0) + 1
            sessions.add(e.session_id)
            latencies.append(e.latency_ms)
            total_in += e.input_tokens
            total_out += e.output_tokens

        latencies_sorted = sorted(latencies)
        p95_idx = int(len(latencies_sorted) * 0.95)

        return {
            "total_decisions": len(entries),
            "by_risk_tier": by_risk,
            "by_decision_type": by_type,
            "by_model": by_model,
            "avg_latency_ms": round(statistics.mean(latencies), 2),
            "median_latency_ms": round(statistics.median(latencies), 2),
            "p95_latency_ms": round(
                latencies_sorted[min(p95_idx, len(latencies_sorted) - 1)], 2
            ),
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "unique_sessions": len(sessions),
            "date_range": {
                "first": entries[0].timestamp,
                "last": entries[-1].timestamp,
            },
        }

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_json(
        self,
        entries: Optional[list[LogEntry]] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        include_stats: bool = True,
    ) -> str:
        """
        Export entries as JSON string.

        If entries is None, exports all entries (filtered by since/until).
        """
        if entries is None:
            entries = self.filter(since=since, until=until)

        data: dict[str, Any] = {
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_entries": len(entries),
            "entries": [asdict(e) for e in entries],
        }
        if include_stats:
            data["stats"] = self.aggregate_stats(since=since, until=until)

        return json.dumps(data, indent=2, default=str)

    def export_csv(
        self,
        entries: Optional[list[LogEntry]] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> str:
        """Export entries as CSV string."""
        if entries is None:
            entries = self.filter(since=since, until=until)

        output = io.StringIO()
        fieldnames = [
            "entry_id", "timestamp", "session_id", "model",
            "input_hash", "output_hash", "input_tokens", "output_tokens",
            "latency_ms", "decision_type", "risk_tier", "metadata",
            "prev_hash", "entry_hash",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for e in entries:
            d = asdict(e)
            d["metadata"] = json.dumps(d["metadata"])
            # Only include the fields we want (drop plaintext)
            writer.writerow({k: d.get(k, "") for k in fieldnames})

        return output.getvalue()

    # ------------------------------------------------------------------
    # Entry explanation
    # ------------------------------------------------------------------

    def explain(self, entry_id: str) -> dict[str, Any]:
        """
        Look up a single entry and return a human-readable explanation
        of what was logged, without revealing plaintext (unless it was
        stored in dev mode).

        Returns a dict suitable for display or JSON serialization.
        """
        entry = self.chain.get_entry(entry_id)
        if not entry:
            return {"error": f"No entry found with id: {entry_id}"}

        # Verify this specific entry's hash
        hash_valid = entry.verify()

        explanation: dict[str, Any] = {
            "entry_id": entry.entry_id,
            "timestamp": entry.timestamp,
            "session_id": entry.session_id,
            "model": entry.model,
            "decision_type": entry.decision_type,
            "risk_tier": entry.risk_tier,
            "latency_ms": round(entry.latency_ms, 1),
            "token_usage": {
                "input_tokens": entry.input_tokens,
                "output_tokens": entry.output_tokens,
                "total": entry.input_tokens + entry.output_tokens,
            },
            "hash_chain": {
                "entry_hash": entry.entry_hash,
                "prev_hash": entry.prev_hash,
                "integrity": "VALID" if hash_valid else "TAMPERED",
            },
            "input_fingerprint": entry.input_hash[:16] + "…",
            "output_fingerprint": entry.output_hash[:16] + "…",
            "metadata": entry.metadata,
        }

        # Include plaintext if available (dev mode only)
        if entry.input_plaintext:
            explanation["input_text"] = entry.input_plaintext
        if entry.output_plaintext:
            explanation["output_text"] = entry.output_plaintext

        if not hash_valid:
            explanation["warning"] = (
                "INTEGRITY VIOLATION: This entry's hash does not match its content. "
                "The entry may have been tampered with. Do not trust this decision record."
            )

        return explanation

    # ------------------------------------------------------------------
    # Session replay
    # ------------------------------------------------------------------

    def session_timeline(self, session_id: str) -> list[dict[str, Any]]:
        """
        Return a chronological timeline of all entries in a session,
        with per-entry hash integrity status.
        """
        entries = self.get_by_session(session_id)
        timeline = []
        for i, e in enumerate(entries):
            timeline.append({
                "index": i + 1,
                "entry_id": e.entry_id,
                "timestamp": e.timestamp,
                "model": e.model,
                "decision_type": e.decision_type,
                "risk_tier": e.risk_tier,
                "latency_ms": round(e.latency_ms, 1),
                "tokens": e.input_tokens + e.output_tokens,
                "hash_valid": e.verify(),
            })
        return timeline
