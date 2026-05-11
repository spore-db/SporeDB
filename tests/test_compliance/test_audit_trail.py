"""Tests for COMPL-01: audit trail, hash chain, and Ed25519 signing."""

from __future__ import annotations

import threading
from datetime import UTC
from uuid import UUID

import pyarrow.parquet as pq

from sporedb.compliance.audit import (
    _AUDIT_SCHEMA,
    AuditAction,
    AuditEntry,
)
from sporedb.compliance.signing import sign_entry, verify_entry
from sporedb.storage.parquet_layout import ParquetLayout

# ---------------------------------------------------------------------------
# AuditEntry model tests
# ---------------------------------------------------------------------------


class TestAuditEntryModel:
    def test_entry_has_uuid7_id(self, sample_audit_entry):
        assert isinstance(sample_audit_entry.entry_id, UUID)

    def test_entry_has_utc_timestamp(self, sample_audit_entry):
        assert sample_audit_entry.timestamp.tzinfo is not None
        assert sample_audit_entry.timestamp.tzinfo == UTC

    def test_canonical_bytes_deterministic(self):
        """Same logical content produces identical canonical bytes."""
        kwargs = dict(
            entry_id=UUID("019614a0-0000-7000-8000-000000000001"),
            user_id="user-001",
            action=AuditAction.CREATE,
            entity_type="batch",
            entity_id="batch-1",
            new_value_hash="b" * 64,
        )
        e1 = AuditEntry(**kwargs)
        e2 = AuditEntry(**kwargs)
        # Force same timestamp for determinism
        e2.timestamp = e1.timestamp
        assert e1.canonical_bytes() == e2.canonical_bytes()

    def test_canonical_bytes_excludes_signature(self, sample_audit_entry, private_key):
        before = sample_audit_entry.canonical_bytes()
        sign_entry(sample_audit_entry, private_key)
        after = sample_audit_entry.canonical_bytes()
        assert before == after

    def test_compute_hash_is_sha256_hex(self, sample_audit_entry):
        h = sample_audit_entry.compute_hash()
        assert len(h) == 64
        int(h, 16)  # raises if not valid hex


# ---------------------------------------------------------------------------
# AuditTrailWriter tests
# ---------------------------------------------------------------------------


class TestAuditTrailWriter:
    def _make_entry(self, suffix: int = 0) -> AuditEntry:
        return AuditEntry(
            user_id=f"user-{suffix}",
            action=AuditAction.CREATE,
            entity_type="batch",
            entity_id=f"batch-{suffix}",
            new_value_hash="c" * 64,
        )

    def test_append_returns_signed_entry(self, audit_writer):
        entry = self._make_entry()
        result = audit_writer.append(entry)
        assert result.signature != b""

    def test_append_sets_previous_hash(self, audit_writer):
        e1 = audit_writer.append(self._make_entry(1))
        e2 = audit_writer.append(self._make_entry(2))
        assert e2.previous_entry_hash == e1.compute_hash()

    def test_append_first_entry_empty_previous(self, audit_writer):
        entry = audit_writer.append(self._make_entry())
        assert entry.previous_entry_hash == ""

    def test_append_persists_to_parquet(self, audit_writer, audit_engine):
        audit_writer.append(self._make_entry())
        layout = ParquetLayout(audit_engine.data_root)
        assert layout.audit_trail_file().exists()

    def test_get_entries_returns_all(self, audit_writer):
        for i in range(3):
            audit_writer.append(self._make_entry(i))
        entries = audit_writer.get_entries()
        assert len(entries) == 3

    def test_get_entries_empty_when_no_file(self, audit_writer):
        assert audit_writer.get_entries() == []

    def test_verify_chain_intact(self, audit_writer):
        for i in range(5):
            audit_writer.append(self._make_entry(i))
        assert audit_writer.verify_chain() is True

    def test_verify_chain_detects_tamper(self, audit_writer, audit_engine):
        for i in range(3):
            audit_writer.append(self._make_entry(i))

        # Corrupt the second entry's previous_entry_hash on disk
        layout = ParquetLayout(audit_engine.data_root)
        path = layout.audit_trail_file()
        table = pq.read_table(path, schema=_AUDIT_SCHEMA)
        df = table.to_pandas()
        df.loc[1, "previous_entry_hash"] = "tampered_hash"

        import pyarrow as pa

        corrupted = pa.Table.from_pandas(df, schema=_AUDIT_SCHEMA)
        pq.write_table(corrupted, path, use_dictionary=False)

        assert audit_writer.verify_chain() is False

    def test_concurrent_appends_serialized(self, audit_writer):
        """10 threads append concurrently; chain must remain valid."""
        errors: list[Exception] = []

        def _append(idx: int) -> None:
            try:
                audit_writer.append(self._make_entry(idx))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_append, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent append: {errors}"
        assert len(audit_writer.get_entries()) == 10
        assert audit_writer.verify_chain() is True


# ---------------------------------------------------------------------------
# Signing / verification tests
# ---------------------------------------------------------------------------


class TestSigningVerification:
    def test_sign_and_verify_entry(self, sample_audit_entry, private_key, public_key):
        sign_entry(sample_audit_entry, private_key)
        assert verify_entry(sample_audit_entry, public_key) is True

    def test_verify_detects_modified_entry(
        self, sample_audit_entry, private_key, public_key
    ):
        sign_entry(sample_audit_entry, private_key)
        sample_audit_entry.entity_id = "modified-id"
        assert verify_entry(sample_audit_entry, public_key) is False

    def test_public_key_pem_stored_in_entry(self, audit_writer):
        entry = AuditEntry(
            user_id="user-pem",
            action=AuditAction.CREATE,
            entity_type="batch",
            entity_id="batch-pem",
            new_value_hash="d" * 64,
        )
        result = audit_writer.append(entry)
        assert result.public_key_pem.startswith("-----BEGIN PUBLIC KEY-----")
