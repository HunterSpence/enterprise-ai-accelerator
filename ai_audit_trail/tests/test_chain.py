"""
test_chain.py — Unit tests for the SHA-256 Merkle hash chain ledger.

Tests:
- SHA-256 hash computation and verification
- Tamper detection catches single-entry field modification
- Merkle proof validates correctly
- Chain export / import round-trip (JSONL)
- Thread safety (concurrent appends)
- chain.count(), chain.query() filtering
- Genesis hash for empty chain
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid

import pytest

from ai_audit_trail.chain import (
    AuditChain,
    DecisionType,
    LogEntry,
    MerkleTree,
    RiskTier,
    _GENESIS_HASH,
    _hash_pair,
    _hash_text,
)


# ---------------------------------------------------------------------------
# Hash functions
# ---------------------------------------------------------------------------

class TestHashFunctions:
    def test_hash_text_is_sha256(self):
        """_hash_text returns a valid 64-hex SHA-256 digest."""
        text = "hello world"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert _hash_text(text) == expected

    def test_hash_text_is_deterministic(self):
        result1 = _hash_text("deterministic input")
        result2 = _hash_text("deterministic input")
        assert result1 == result2

    def test_hash_text_different_inputs_different_outputs(self):
        assert _hash_text("input A") != _hash_text("input B")

    def test_hash_pair_is_sha256_of_concatenation(self):
        left = "a" * 64
        right = "b" * 64
        expected = hashlib.sha256((left + right).encode("utf-8")).hexdigest()
        assert _hash_pair(left, right) == expected

    def test_genesis_hash_is_64_zeros(self):
        assert _GENESIS_HASH == "0" * 64
        assert len(_GENESIS_HASH) == 64


# ---------------------------------------------------------------------------
# LogEntry hash computation
# ---------------------------------------------------------------------------

class TestLogEntryHash:
    def test_entry_hash_is_64_hex(self, populated_chain: AuditChain):
        entry = populated_chain.query(limit=1)[0]
        assert len(entry.entry_hash) == 64
        assert all(c in "0123456789abcdef" for c in entry.entry_hash)

    def test_entry_verify_passes_for_unmodified_entry(self, populated_chain: AuditChain):
        entry = populated_chain.query(limit=1)[0]
        assert entry.verify() is True

    def test_entry_hash_excludes_plaintext_fields(self, empty_chain: AuditChain):
        """Removing plaintext should not change the entry_hash."""
        empty_chain.store_plaintext = True
        entry = empty_chain.append(
            session_id="s1",
            model="claude-haiku-4-5",
            input_text="Test input",
            output_text="Test output",
            input_tokens=10,
            output_tokens=20,
            latency_ms=100.0,
        )
        # Hash must still be computable without plaintext
        import dataclasses
        stripped = dataclasses.replace(entry, input_plaintext=None, output_plaintext=None)
        assert stripped.entry_hash == entry.entry_hash

    def test_modifying_entry_field_invalidates_verify(self):
        """Directly modifying a field breaks entry.verify()."""
        entry = LogEntry(
            entry_id=str(uuid.uuid4()),
            timestamp="2026-01-01T00:00:00+00:00",
            system_id="test-system",
            session_id="session-1",
            model="claude-sonnet-4-6",
            input_hash=_hash_text("original input"),
            output_hash=_hash_text("original output"),
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=0,
            cost_usd=0.001,
            latency_ms=300.0,
            decision_type="GENERATION",
            risk_tier="LIMITED",
            metadata={},
            prev_hash=_GENESIS_HASH,
        )
        assert entry.verify() is True

        # Tamper: change a field without recomputing hash
        import dataclasses
        tampered = dataclasses.replace(entry, input_tokens=9999)
        assert tampered.verify() is False

    def test_entry_chain_linkage(self, empty_chain: AuditChain):
        """Each entry's prev_hash equals the prior entry's entry_hash."""
        e1 = empty_chain.append(
            session_id="s1", model="m1", input_text="a", output_text="b",
            input_tokens=1, output_tokens=1, latency_ms=1.0,
        )
        e2 = empty_chain.append(
            session_id="s1", model="m1", input_text="c", output_text="d",
            input_tokens=1, output_tokens=1, latency_ms=1.0,
        )
        e3 = empty_chain.append(
            session_id="s1", model="m1", input_text="e", output_text="f",
            input_tokens=1, output_tokens=1, latency_ms=1.0,
        )
        assert e1.prev_hash == _GENESIS_HASH
        assert e2.prev_hash == e1.entry_hash
        assert e3.prev_hash == e2.entry_hash


# ---------------------------------------------------------------------------
# MerkleTree
# ---------------------------------------------------------------------------

class TestMerkleTree:
    def test_empty_tree_root_is_genesis(self):
        tree = MerkleTree([])
        assert tree.root == _GENESIS_HASH

    def test_single_leaf_root_equals_leaf(self):
        leaf = "a" * 64
        tree = MerkleTree([leaf])
        assert tree.root == leaf

    def test_two_leaves(self):
        a = "a" * 64
        b = "b" * 64
        tree = MerkleTree([a, b])
        expected = _hash_pair(a, b)
        assert tree.root == expected

    def test_root_changes_when_leaf_changes(self):
        leaves = ["a" * 64, "b" * 64, "c" * 64]
        tree1 = MerkleTree(leaves)
        leaves2 = ["a" * 64, "X" * 64, "c" * 64]  # tamper leaf 1
        tree2 = MerkleTree(leaves2)
        assert tree1.root != tree2.root

    def test_proof_verifies_correctly(self):
        leaves = [_hash_text(f"entry-{i}") for i in range(8)]
        tree = MerkleTree(leaves)
        for idx in range(len(leaves)):
            proof = tree.get_proof(idx)
            assert MerkleTree.verify_proof(leaves[idx], proof, tree.root) is True

    def test_proof_fails_for_wrong_leaf(self):
        leaves = [_hash_text(f"entry-{i}") for i in range(4)]
        tree = MerkleTree(leaves)
        proof = tree.get_proof(0)
        wrong_leaf = _hash_text("wrong leaf")
        assert MerkleTree.verify_proof(wrong_leaf, proof, tree.root) is False

    def test_proof_fails_for_wrong_root(self):
        leaves = [_hash_text(f"entry-{i}") for i in range(4)]
        tree = MerkleTree(leaves)
        proof = tree.get_proof(0)
        wrong_root = "f" * 64
        assert MerkleTree.verify_proof(leaves[0], proof, wrong_root) is False

    def test_odd_number_of_leaves(self):
        """Odd leaf count should not raise — last leaf is duplicated."""
        leaves = [_hash_text(f"entry-{i}") for i in range(5)]
        tree = MerkleTree(leaves)
        assert len(tree.root) == 64  # valid hash

    def test_get_entry_proof_round_trip(self, populated_chain: AuditChain):
        """Entry proof from chain can be verified against chain's Merkle root."""
        entries = populated_chain.query(limit=3)
        for entry in entries:
            proof_data = populated_chain.get_entry_proof(entry.entry_id)
            assert proof_data is not None
            verified = MerkleTree.verify_proof(
                proof_data["leaf_hash"],
                proof_data["proof"],
                proof_data["merkle_root"],
            )
            assert verified is True


# ---------------------------------------------------------------------------
# AuditChain.verify_chain — tamper detection
# ---------------------------------------------------------------------------

class TestTamperDetection:
    def test_valid_chain_passes_verify(self, populated_chain: AuditChain):
        report = populated_chain.verify_chain()
        assert report.is_valid is True
        assert len(report.tampered_entries) == 0
        assert report.confidence == "HIGH"

    def test_empty_chain_passes_verify(self, empty_chain: AuditChain):
        report = empty_chain.verify_chain()
        assert report.is_valid is True
        assert report.total_entries == 0

    def test_tamper_detection_catches_field_modification(self, empty_chain: AuditChain):
        """Modifying a stored field must be detected by verify_chain()."""
        for i in range(3):
            empty_chain.append(
                session_id="s1", model="m", input_text=f"in{i}", output_text=f"out{i}",
                input_tokens=10, output_tokens=10, latency_ms=100.0,
            )
        entry = empty_chain.query(limit=1)[0]

        # Directly tamper a field, bypassing hash update
        empty_chain._tamper_entry_for_demo(entry.entry_id, "input_tokens", 99999)

        report = empty_chain.verify_chain()
        assert report.is_valid is False
        assert len(report.tampered_entries) >= 1
        tampered_ids = [t["entry_id"] for t in report.tampered_entries]
        assert entry.entry_id in tampered_ids

    def test_tamper_detection_returns_tampered_entry_details(self, empty_chain: AuditChain):
        """TamperReport.tampered_entries has entry_id, timestamp, tamper_types."""
        empty_chain.append(
            session_id="s1", model="m", input_text="in", output_text="out",
            input_tokens=10, output_tokens=10, latency_ms=100.0,
        )
        entry = empty_chain.query(limit=1)[0]
        empty_chain._tamper_entry_for_demo(entry.entry_id, "output_tokens", 77777)

        report = empty_chain.verify_chain()
        assert not report.is_valid
        t = report.tampered_entries[0]
        assert "entry_id" in t
        assert "timestamp" in t
        assert "tamper_types" in t
        assert "HASH_MISMATCH" in t["tamper_types"]

    def test_tamper_report_confidence_low_when_many_entries_tampered(self, populated_chain: AuditChain):
        entries = populated_chain.query(limit=5)
        for e in entries:
            populated_chain._tamper_entry_for_demo(e.entry_id, "input_tokens", 1)
        report = populated_chain.verify_chain()
        assert report.confidence in ("LOW", "MEDIUM")


# ---------------------------------------------------------------------------
# Chain export / import round-trip
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_jsonl_is_valid_json_lines(self, populated_chain: AuditChain):
        jsonl = populated_chain.export_jsonl()
        lines = [l for l in jsonl.split("\n") if l.strip()]
        assert len(lines) == populated_chain.count()
        for line in lines:
            obj = json.loads(line)
            assert "entry_id" in obj
            assert "entry_hash" in obj

    def test_export_jsonl_round_trip(self, populated_chain: AuditChain):
        """Exported entries can be parsed back to LogEntry objects."""
        jsonl = populated_chain.export_jsonl()
        lines = jsonl.split("\n")
        original_entries = populated_chain.query()
        for i, (line, orig) in enumerate(zip(lines, original_entries)):
            if not line.strip():
                continue
            data = json.loads(line)
            restored = LogEntry.from_dict(data)
            assert restored.entry_hash == orig.entry_hash
            assert restored.verify() is True

    def test_export_jsonl_filter_by_system(self, populated_chain: AuditChain):
        jsonl = populated_chain.export_jsonl(system_id="loan-approval-v2")
        lines = [l for l in jsonl.split("\n") if l.strip()]
        for line in lines:
            obj = json.loads(line)
            assert obj["system_id"] == "loan-approval-v2"


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_appends_all_recorded(self, empty_chain: AuditChain):
        """50 concurrent appends should all be stored without data loss."""
        errors = []

        def append_entry(idx: int) -> None:
            try:
                empty_chain.append(
                    session_id=f"thread-{idx}",
                    model="test-model",
                    input_text=f"concurrent input {idx}",
                    output_text=f"concurrent output {idx}",
                    input_tokens=10,
                    output_tokens=10,
                    latency_ms=50.0,
                )
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=append_entry, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors in concurrent appends: {errors}"
        assert empty_chain.count() == 50

    def test_concurrent_appends_chain_remains_valid(self, empty_chain: AuditChain):
        """After concurrent appends, chain integrity must hold."""
        threads = [
            threading.Thread(
                target=empty_chain.append,
                kwargs={
                    "session_id": f"t{i}", "model": "m", "input_text": f"in{i}",
                    "output_text": f"out{i}", "input_tokens": 5, "output_tokens": 5,
                    "latency_ms": 10.0,
                },
            )
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        report = empty_chain.verify_chain()
        assert report.is_valid is True
