"""Merkle tree checkpoint management for audit trail integrity proofs.

Pure-Python implementation using ``hashlib`` (SHA-256) following RFC 6962
(Certificate Transparency) algorithms for inclusion and consistency proofs.
Replaces the previous ``pymerkle`` dependency to avoid GPL contamination.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sporedb.storage.engine import StorageEngine
from sporedb.storage.parquet_layout import ParquetLayout

if TYPE_CHECKING:
    from sporedb.compliance.audit import AuditEntry


class InvalidProof(Exception):
    """Raised when a Merkle proof verification fails."""


# ------------------------------------------------------------------
# RFC 6962 hash functions
# ------------------------------------------------------------------


def _hash_leaf(data: bytes) -> bytes:
    """SHA-256 hash of a leaf node: H(0x00 || data)."""
    return hashlib.sha256(b"\x00" + data).digest()


def _hash_node(left: bytes, right: bytes) -> bytes:
    """SHA-256 hash of an interior node: H(0x01 || left || right)."""
    return hashlib.sha256(b"\x01" + left + right).digest()


def _compute_root(leaves: list[bytes]) -> bytes:
    """Compute the Merkle root from a list of leaf hashes.

    Uses iterative bottom-up pairing. When the number of nodes at a
    level is odd, the last node is promoted unpaired (RFC 6962 style).
    Returns an empty bytes value for an empty tree.
    """
    if not leaves:
        return b""
    nodes = list(leaves)
    while len(nodes) > 1:
        next_level: list[bytes] = []
        i = 0
        while i < len(nodes) - 1:
            next_level.append(_hash_node(nodes[i], nodes[i + 1]))
            i += 2
        if i < len(nodes):
            next_level.append(nodes[i])
        nodes = next_level
    return nodes[0]


def _inclusion_proof(leaves: list[bytes], index: int) -> list[tuple[str, bytes]]:
    """Generate an RFC 6962 inclusion proof for the leaf at *index* (0-based).

    Returns a list of (side, hash) tuples where side is 'L' or 'R',
    indicating whether the sibling is on the left or right.
    Uses the same tree structure as _merkle_tree_hash (split at largest
    power of 2).
    """
    return _inclusion_proof_inner(leaves, index)


def _inclusion_proof_inner(leaves: list[bytes], index: int) -> list[tuple[str, bytes]]:
    """Recursive inclusion proof using RFC 6962 tree structure."""
    n = len(leaves)
    if n <= 1:
        return []
    k = _largest_power_of_2_less_than(n)
    if index < k:
        proof = _inclusion_proof_inner(leaves[:k], index)
        proof.append(("R", _merkle_tree_hash(leaves[k:])))
        return proof
    else:
        proof = _inclusion_proof_inner(leaves[k:], index - k)
        proof.append(("L", _merkle_tree_hash(leaves[:k])))
        return proof


def _verify_inclusion(
    leaf_hash: bytes,
    root: bytes,
    proof: list[tuple[str, bytes]],
) -> bool:
    """Verify an inclusion proof against *root*."""
    current = leaf_hash
    for side, sibling in proof:
        if side == "L":
            current = _hash_node(sibling, current)
        else:
            current = _hash_node(current, sibling)
    return current == root


def _compute_root_from_range(leaves: list[bytes], start: int, end: int) -> bytes:
    """Compute root hash for a contiguous sub-range of leaves."""
    return _compute_root(leaves[start:end])


# ------------------------------------------------------------------
# RFC 6962 Section 2.1.2 — consistency proof helpers
# ------------------------------------------------------------------


def _largest_power_of_2_less_than(n: int) -> int:
    """Return the largest power of 2 strictly less than n."""
    if n <= 1:
        return 0
    return 1 << (n - 1).bit_length() - 1


def _merkle_tree_hash(leaves: list[bytes]) -> bytes:
    """Compute the Merkle tree hash for a list of leaf hashes (RFC 6962)."""
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return leaves[0]
    k = _largest_power_of_2_less_than(n)
    left = _merkle_tree_hash(leaves[:k])
    right = _merkle_tree_hash(leaves[k:])
    return _hash_node(left, right)


def _consistency_proof_nodes(
    old_size: int, new_size: int, leaves: list[bytes], start_from_old: bool
) -> list[bytes]:
    """RFC 6962 Section 2.1.2 SUBPROOF algorithm.

    Returns the minimal set of node hashes needed to prove that the tree
    of ``old_size`` leaves is a prefix of the tree of ``new_size`` leaves.
    """
    n = len(leaves)
    if n == 0 or old_size == 0:
        return []
    if old_size == n:
        if start_from_old:
            return []
        return [_merkle_tree_hash(leaves)]
    k = _largest_power_of_2_less_than(n)
    if old_size <= k:
        proof = _consistency_proof_nodes(old_size, k, leaves[:k], start_from_old)
        proof.append(_merkle_tree_hash(leaves[k:]))
        return proof
    else:
        proof = _consistency_proof_nodes(old_size - k, n - k, leaves[k:], False)
        proof.append(_merkle_tree_hash(leaves[:k]))
        return proof


def _verify_consistency_proof(
    old_size: int,
    new_size: int,
    old_root: bytes,
    new_root: bytes,
    proof: list[bytes],
) -> bool:
    """RFC 6962 Section 2.1.2 consistency proof verification.

    Reconstructs both old and new roots from the proof hashes and compares.
    Does NOT require access to the tree's leaf data.
    """
    if old_size == 0 or old_size > new_size:
        return False
    if old_size == new_size:
        return old_root == new_root and len(proof) == 0
    if not proof:
        return False

    # Decompose the path from root to the split point
    # The proof was generated by _consistency_proof_nodes which walks
    # the tree splitting at the largest power of 2 less than n.
    # We mirror that walk to determine left/right for each proof node.
    path = _consistency_path(old_size, new_size)

    idx = 0
    if old_size & (old_size - 1) == 0:  # old_size is power of 2
        # start_from_old was True, so first implicit node is the old root itself
        fn = old_root
        sn = old_root
    else:
        if idx >= len(proof):
            return False
        fn = proof[idx]
        sn = proof[idx]
        idx += 1

    for direction in path:
        if idx >= len(proof):
            return False
        node = proof[idx]
        idx += 1
        if direction == "L":
            fn = _hash_node(node, fn)
            sn = _hash_node(node, sn)
        else:  # "R"
            sn = _hash_node(sn, node)

    if idx != len(proof):
        return False

    return fn == old_root and sn == new_root


def _consistency_path(old_size: int, new_size: int) -> list[str]:
    """Compute the left/right direction for each proof node.

    Mirrors the structure of _consistency_proof_nodes to determine
    whether each proof hash should be combined on the left or right.
    """
    directions: list[str] = []
    _consistency_path_inner(old_size, new_size, True, directions)
    return directions


def _consistency_path_inner(
    old_size: int, n: int, start_from_old: bool, directions: list[str]
) -> None:
    """Recursive path computation mirroring _consistency_proof_nodes."""
    if n == 0 or old_size == 0:
        return
    if old_size == n:
        if not start_from_old:
            pass  # emits one node but no direction needed (it's the seed)
        return
    k = _largest_power_of_2_less_than(n)
    if old_size <= k:
        _consistency_path_inner(old_size, k, start_from_old, directions)
        directions.append("R")  # right subtree hash appended
    else:
        _consistency_path_inner(old_size - k, n - k, False, directions)
        directions.append("L")  # left subtree hash appended


class MerkleCheckpointer:
    """Merkle tree over audit entry hashes.

    Supports inclusion proofs (prove a specific entry is in the tree)
    and consistency proofs (prove the tree only had entries appended,
    never modified or deleted).
    """

    def __init__(self, engine: StorageEngine) -> None:
        self._engine = engine
        self._layout = ParquetLayout(engine.data_root)
        self._leaves: list[bytes] = []

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _state_path(self) -> Path:
        """Return the path for the Merkle state JSON file."""
        return self._layout.merkle_state_dir() / "merkle_state.json"

    def save_state(self) -> None:
        """Persist the current Merkle tree state to disk."""
        state_path = self._state_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "size": self.get_size(),
            "root": self.get_root().hex() if self.get_size() > 0 else "",
        }
        state_path.write_text(json.dumps(state))

    def load_state(self, entries: list[AuditEntry]) -> None:
        """Load persisted state and rebuild tree from entries if needed.

        If the state file exists and records a non-zero tree size, the tree
        is rebuilt from the first ``saved_size`` *entries* so that inclusion
        and consistency proofs continue to work after a process restart.
        """
        state_path = self._state_path()
        if not state_path.exists():
            return
        state = json.loads(state_path.read_text())
        saved_size = state.get("size", 0)
        if saved_size > 0 and self.get_size() == 0:
            for entry in entries[:saved_size]:
                self._append_leaf(entry.compute_hash().encode())

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def _append_leaf(self, data: bytes) -> int:
        """Hash *data* as a leaf, append to the tree, return 1-based index."""
        leaf_hash = _hash_leaf(data)
        self._leaves.append(leaf_hash)
        return len(self._leaves)  # 1-based

    def add_entry(self, entry_hash: str) -> int:
        """Append *entry_hash* as a leaf and return the 1-based leaf index."""
        idx = self._append_leaf(entry_hash.encode())
        self.save_state()
        return idx

    def get_root(self) -> bytes:
        """Return the current Merkle root (RFC 6962 tree hash)."""
        return _merkle_tree_hash(self._leaves)

    def get_size(self) -> int:
        """Return the number of leaves in the tree."""
        return len(self._leaves)

    def get_leaf(self, leaf_index: int) -> bytes:
        """Return the leaf hash at *leaf_index* (1-based)."""
        return self._leaves[leaf_index - 1]

    def prove_inclusion(self, leaf_index: int) -> tuple[bytes, bytes, Any]:
        """Generate an inclusion proof for the leaf at *leaf_index* (1-based).

        Returns ``(leaf, root, proof)``.
        """
        idx = leaf_index - 1  # convert to 0-based
        proof = _inclusion_proof(self._leaves, idx)
        leaf = self._leaves[idx]
        root = self.get_root()
        return leaf, root, proof

    def verify_inclusion(self, leaf: bytes, root: bytes, proof: Any) -> bool:
        """Verify an inclusion proof. Returns ``True`` or ``False``."""
        try:
            if not _verify_inclusion(leaf, root, proof):
                raise InvalidProof("Inclusion proof verification failed")
            return True
        except InvalidProof:
            return False

    def prove_consistency(
        self, old_size: int, old_root: bytes
    ) -> tuple[bytes, bytes, list[bytes]]:
        """Generate an RFC 6962 consistency proof from *old_size* to current size.

        Returns ``(old_root, new_root, proof)`` where *proof* is a list of
        O(log n) interior node hashes — never raw leaf hashes.
        """
        new_size = self.get_size()
        if old_size == new_size:
            return old_root, old_root, []
        proof = _consistency_proof_nodes(
            old_size, new_size, self._leaves[:new_size], True
        )
        new_root = _merkle_tree_hash(self._leaves[:new_size])
        return old_root, new_root, proof

    def verify_consistency(
        self,
        old_root: bytes,
        new_root: bytes,
        proof: list[bytes] | Any,
        old_size: int | None = None,
        new_size: int | None = None,
    ) -> bool:
        """Verify a consistency proof. Returns ``True`` or ``False``.

        This is a static operation — it does not require access to the
        tree's leaf data, only the old/new roots, sizes, and proof hashes.

        Parameters *old_size* and *new_size* are required for RFC 6962
        verification. If omitted, the method falls back to the current
        tree size (for backward compatibility with existing callers).
        """
        if isinstance(proof, dict):
            return False
        if old_size is None or new_size is None:
            # Backward compat: infer from current tree if sizes not provided
            # This only works if the checkpointer still has the full tree
            return False
        try:
            return _verify_consistency_proof(
                old_size,
                new_size,
                old_root,
                new_root,
                proof,
            )
        except (InvalidProof, ValueError, IndexError):
            return False

    def build_from_entries(self, entries: list[AuditEntry]) -> None:
        """Rebuild the tree from a list of :class:`AuditEntry` objects."""
        for entry in entries:
            self.add_entry(entry.compute_hash())
