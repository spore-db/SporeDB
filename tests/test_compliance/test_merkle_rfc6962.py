"""Tests for RFC 6962 Merkle proof correctness.

These tests verify that inclusion and consistency proofs follow RFC 6962
Section 2.1 — O(log n) proof sizes, no raw leaf exposure, and static
verification without tree state.
"""

from __future__ import annotations

import math
import tempfile

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sporedb.compliance.merkle import (
    MerkleCheckpointer,
    _hash_leaf,
)
from sporedb.storage.engine import StorageEngine


class TestConsistencyProofFormat:
    """Consistency proofs must be O(log n) hash lists, not raw leaf dumps."""

    def test_consistency_proof_is_list_of_bytes(self, audit_engine):
        """Proof should be list[bytes], not dict with leaf arrays."""
        mc = MerkleCheckpointer(audit_engine)
        for i in range(5):
            mc.add_entry(f"{i}" * 64)
        old_root = mc.get_root()
        old_size = mc.get_size()

        for i in range(5, 10):
            mc.add_entry(f"{i}" * 64)

        _, _, proof = mc.prove_consistency(old_size, old_root)
        assert isinstance(proof, list), (
            f"Proof should be list[bytes], got {type(proof)}"
        )
        for item in proof:
            assert isinstance(item, bytes), (
                f"Proof items should be bytes, got {type(item)}"
            )

    def test_consistency_proof_size_is_logarithmic(self, audit_engine):
        """Proof should have O(log n) elements, not O(n)."""
        mc = MerkleCheckpointer(audit_engine)
        n = 100
        for i in range(n):
            mc.add_entry(f"{i}" * 64)
        old_root = mc.get_root()
        old_size = mc.get_size()

        for i in range(n, 2 * n):
            mc.add_entry(f"{i}" * 64)

        _, _, proof = mc.prove_consistency(old_size, old_root)
        # O(log n) — proof should be at most 2 * ceil(log2(n)) elements
        max_expected = 2 * math.ceil(math.log2(2 * n)) + 2
        assert len(proof) <= max_expected, (
            f"Proof has {len(proof)} elements for tree of size {2 * n}; "
            f"expected at most {max_expected} (O(log n))"
        )

    def test_consistency_proof_does_not_contain_leaf_hashes(self, audit_engine):
        """Proof must not leak raw leaf hashes — only interior path hashes."""
        mc = MerkleCheckpointer(audit_engine)
        leaves = []
        for i in range(10):
            entry_hash = f"{i}" * 64
            mc.add_entry(entry_hash)
            leaves.append(_hash_leaf(entry_hash.encode()))

        old_root = mc.get_root()
        old_size = mc.get_size()

        for i in range(10, 20):
            entry_hash = f"{i}" * 64
            mc.add_entry(entry_hash)
            leaves.append(_hash_leaf(entry_hash.encode()))

        _, _, proof = mc.prove_consistency(old_size, old_root)
        leaf_set = set(lh for lh in leaves)
        for p in proof:
            assert p not in leaf_set, (
                "Proof contains a raw leaf hash — should only have interior hashes"
            )


class TestConsistencyProofVerification:
    """Consistency proofs must be verifiable and tamper-resistant."""

    def test_valid_consistency_proof_passes(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        for i in range(8):
            mc.add_entry(f"{i}" * 64)
        old_root = mc.get_root()
        old_size = mc.get_size()

        for i in range(8, 16):
            mc.add_entry(f"{i}" * 64)
        new_size = mc.get_size()

        old_r, new_r, proof = mc.prove_consistency(old_size, old_root)
        assert (
            mc.verify_consistency(
                old_r, new_r, proof, old_size=old_size, new_size=new_size
            )
            is True
        )

    def test_tampered_proof_rejected(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        for i in range(8):
            mc.add_entry(f"{i}" * 64)
        old_root = mc.get_root()
        old_size = mc.get_size()

        for i in range(8, 16):
            mc.add_entry(f"{i}" * 64)
        new_size = mc.get_size()

        old_r, new_r, proof = mc.prove_consistency(old_size, old_root)
        if proof:
            tampered = list(proof)
            tampered[0] = b"\x00" * 32
            assert (
                mc.verify_consistency(
                    old_r, new_r, tampered, old_size=old_size, new_size=new_size
                )
                is False
            )

    def test_wrong_old_root_rejected(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        for i in range(4):
            mc.add_entry(f"{i}" * 64)
        old_root = mc.get_root()
        old_size = mc.get_size()

        for i in range(4, 8):
            mc.add_entry(f"{i}" * 64)
        new_size = mc.get_size()

        _, new_r, proof = mc.prove_consistency(old_size, old_root)
        fake_root = b"\xff" * 32
        assert (
            mc.verify_consistency(
                fake_root, new_r, proof, old_size=old_size, new_size=new_size
            )
            is False
        )

    def test_wrong_new_root_rejected(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        for i in range(4):
            mc.add_entry(f"{i}" * 64)
        old_root = mc.get_root()
        old_size = mc.get_size()

        for i in range(4, 8):
            mc.add_entry(f"{i}" * 64)
        new_size = mc.get_size()

        old_r, _, proof = mc.prove_consistency(old_size, old_root)
        fake_root = b"\xff" * 32
        assert (
            mc.verify_consistency(
                old_r, fake_root, proof, old_size=old_size, new_size=new_size
            )
            is False
        )

    def test_consistency_verify_is_static(self, audit_engine):
        """verify_consistency should work without access to the tree's leaf array."""
        mc = MerkleCheckpointer(audit_engine)
        for i in range(8):
            mc.add_entry(f"{i}" * 64)
        old_root = mc.get_root()
        old_size = mc.get_size()

        for i in range(8, 12):
            mc.add_entry(f"{i}" * 64)
        new_root = mc.get_root()
        new_size = mc.get_size()

        _, _, proof = mc.prove_consistency(old_size, old_root)

        # Create a fresh checkpointer with NO leaves
        mc2 = MerkleCheckpointer(audit_engine)
        assert mc2.get_size() == 0
        # Should still be able to verify with just roots + proof + sizes
        assert (
            mc2.verify_consistency(
                old_root, new_root, proof, old_size=old_size, new_size=new_size
            )
            is True
        )


class TestInclusionProofFormat:
    """Inclusion proofs must be O(log n) and statically verifiable."""

    def test_inclusion_proof_size_is_logarithmic(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        n = 64
        for i in range(n):
            mc.add_entry(f"{i}" * 64)

        leaf, root, proof = mc.prove_inclusion(1)
        max_expected = math.ceil(math.log2(n)) + 1
        assert len(proof) <= max_expected, (
            f"Proof has {len(proof)} elements for tree of size {n}; "
            f"expected at most {max_expected}"
        )

    def test_inclusion_proof_valid_for_every_leaf(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        n = 16
        for i in range(n):
            mc.add_entry(f"{i}" * 64)

        for idx in range(1, n + 1):
            leaf, root, proof = mc.prove_inclusion(idx)
            assert mc.verify_inclusion(leaf, root, proof) is True, (
                f"Inclusion proof failed for leaf {idx}"
            )

    def test_tampered_inclusion_proof_rejected(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        for i in range(8):
            mc.add_entry(f"{i}" * 64)

        leaf, root, proof = mc.prove_inclusion(3)
        if proof:
            tampered = list(proof)
            tampered[0] = (tampered[0][0], b"\x00" * 32)
            assert mc.verify_inclusion(leaf, root, tampered) is False

    def test_wrong_leaf_rejected(self, audit_engine):
        mc = MerkleCheckpointer(audit_engine)
        for i in range(8):
            mc.add_entry(f"{i}" * 64)

        _, root, proof = mc.prove_inclusion(3)
        fake_leaf = b"\xff" * 32
        assert mc.verify_inclusion(fake_leaf, root, proof) is False


class TestConsistencyProofPropertyBased:
    """Property-based tests for consistency proofs."""

    @given(
        old_size=st.integers(min_value=1, max_value=50),
        extra=st.integers(min_value=1, max_value=50),
    )
    @settings(
        max_examples=50,
        deadline=10000,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_consistency_proof_roundtrips(self, tmp_path, old_size, extra):
        """For any tree prefix, consistency proof verifies."""
        with tempfile.TemporaryDirectory() as td:
            engine = StorageEngine(td)
            mc = MerkleCheckpointer(engine)
            for i in range(old_size):
                mc.add_entry(f"entry-{i}")
            old_root = mc.get_root()

            for i in range(old_size, old_size + extra):
                mc.add_entry(f"entry-{i}")
            new_size = mc.get_size()

            old_r, new_r, proof = mc.prove_consistency(old_size, old_root)
            assert (
                mc.verify_consistency(
                    old_r, new_r, proof, old_size=old_size, new_size=new_size
                )
                is True
            )
            engine.close()

    @given(tree_size=st.integers(min_value=1, max_value=50))
    @settings(
        max_examples=30,
        deadline=10000,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_inclusion_proof_roundtrips(self, tmp_path, tree_size):
        """For any tree, every leaf has a valid inclusion proof."""
        with tempfile.TemporaryDirectory() as td:
            engine = StorageEngine(td)
            mc = MerkleCheckpointer(engine)
            for i in range(tree_size):
                mc.add_entry(f"entry-{i}")

            for idx in range(1, tree_size + 1):
                leaf, root, proof = mc.prove_inclusion(idx)
                assert mc.verify_inclusion(leaf, root, proof) is True
            engine.close()
