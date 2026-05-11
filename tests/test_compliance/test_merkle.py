"""Tests for COMPL-01: Merkle tree checkpointing."""

from __future__ import annotations

from sporedb.compliance.audit import AuditAction, AuditEntry
from sporedb.compliance.merkle import MerkleCheckpointer


class TestMerkleCheckpointer:
    def _make_entry(self, idx: int) -> AuditEntry:
        return AuditEntry(
            user_id=f"user-{idx}",
            action=AuditAction.CREATE,
            entity_type="batch",
            entity_id=f"batch-{idx}",
            new_value_hash="e" * 64,
        )

    def test_add_entry_returns_index(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        idx = mc.add_entry("a" * 64)
        assert idx >= 1  # pymerkle uses 1-based indexing

    def test_root_changes_after_add(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        mc.add_entry("a" * 64)
        root1 = mc.get_root()
        mc.add_entry("b" * 64)
        root2 = mc.get_root()
        assert root1 != root2

    def test_inclusion_proof_valid(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        for i in range(5):
            mc.add_entry(f"{i}" * 64)
        leaf, root, proof = mc.prove_inclusion(1)
        assert mc.verify_inclusion(leaf, root, proof) is True

    def test_consistency_proof_valid(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        for i in range(3):
            mc.add_entry(f"{i}" * 64)
        old_root = mc.get_root()
        old_size = mc.get_size()

        # Add more entries
        for i in range(3, 5):
            mc.add_entry(f"{i}" * 64)
        new_size = mc.get_size()

        old_r, new_r, proof = mc.prove_consistency(old_size, old_root)
        assert (
            mc.verify_consistency(
                old_r, new_r, proof, old_size=old_size, new_size=new_size
            )
            is True
        )

    def test_build_from_entries(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        entries = [self._make_entry(i) for i in range(5)]
        mc.build_from_entries(entries)
        assert mc.get_size() == 5

    # ------------------------------------------------------------------
    # State persistence (MD-09)
    # ------------------------------------------------------------------

    def test_save_state_creates_file(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        mc.add_entry("a" * 64)
        state_path = mc._state_path()
        assert state_path.exists(), "save_state should create merkle_state.json"

    def test_save_state_content(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        mc.add_entry("a" * 64)
        mc.add_entry("b" * 64)
        import json

        state = json.loads(mc._state_path().read_text())
        assert state["size"] == 2
        assert state["root"] != ""

    def test_load_state_rebuilds_tree(self, audit_engine):
        entries = [self._make_entry(i) for i in range(5)]
        # Build and persist state with first checkpointer
        mc1 = MerkleCheckpointer(audit_engine)
        mc1.build_from_entries(entries)
        mc1.save_state()
        original_root = mc1.get_root()
        original_size = mc1.get_size()

        # Create a fresh checkpointer and load state
        mc2 = MerkleCheckpointer(audit_engine)
        assert mc2.get_size() == 0
        mc2.load_state(entries)
        assert mc2.get_size() == original_size
        assert mc2.get_root() == original_root

    def test_inclusion_proof_after_load_state(self, audit_engine):
        entries = [self._make_entry(i) for i in range(5)]
        mc1 = MerkleCheckpointer(audit_engine)
        mc1.build_from_entries(entries)
        mc1.save_state()

        # Rebuild from persisted state
        mc2 = MerkleCheckpointer(audit_engine)
        mc2.load_state(entries)

        # Inclusion proof should work on the rebuilt tree
        leaf, root, proof = mc2.prove_inclusion(1)
        assert mc2.verify_inclusion(leaf, root, proof) is True

    def test_load_state_noop_when_no_file(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        mc.load_state([])  # Should not raise
        assert mc.get_size() == 0
