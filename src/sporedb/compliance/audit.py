"""Audit trail model and writer with SHA-256 hash chain.

Implements a tamper-evident audit log where each entry is linked to
its predecessor via a SHA-256 hash chain. Every entry is signed with
Ed25519 on append.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel, Field
from uuid_utils import uuid7

from sporedb.compliance.signing import sign_entry
from sporedb.storage.engine import StorageEngine
from sporedb.storage.parquet_layout import ParquetLayout


def _make_uuid7() -> UUID:
    """Generate a UUIDv7 and return as stdlib UUID for Pydantic compatibility."""
    return UUID(str(uuid7()))


class AuditAction(StrEnum):
    """Actions that can be recorded in the audit trail."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SIGN = "sign"


class AuditEntry(BaseModel):
    """A single tamper-evident audit record.

    Each entry carries a SHA-256 hash of its predecessor
    (``previous_entry_hash``) forming a chain, plus an Ed25519
    ``signature`` over its canonical representation.
    """

    entry_id: UUID = Field(default_factory=_make_uuid7)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    user_id: str
    action: AuditAction
    entity_type: str
    entity_id: str
    old_value_hash: str = ""
    new_value_hash: str
    previous_entry_hash: str = ""
    reason: str = ""
    signature: bytes = b""
    public_key_pem: str = ""

    model_config = {"arbitrary_types_allowed": True}

    def canonical_bytes(self) -> bytes:
        """Deterministic serialisation for signing / hashing.

        Excludes ``signature`` and ``public_key_pem`` so that signing
        does not create a circular dependency.
        """
        data = self.model_dump(exclude={"signature", "public_key_pem"})
        # Ensure JSON-safe types
        data["entry_id"] = str(data["entry_id"])
        data["timestamp"] = data["timestamp"].isoformat()
        data["action"] = (
            data["action"].value if isinstance(data["action"], Enum) else data["action"]
        )
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

    def compute_hash(self) -> str:
        """SHA-256 hex digest of the canonical representation."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Parquet schema (flat, following lineage_store pattern)
# ---------------------------------------------------------------------------

_AUDIT_SCHEMA = pa.schema(
    [
        ("entry_id", pa.string()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("user_id", pa.string()),
        ("action", pa.string()),
        ("entity_type", pa.string()),
        ("entity_id", pa.string()),
        ("old_value_hash", pa.string()),
        ("new_value_hash", pa.string()),
        ("previous_entry_hash", pa.string()),
        ("reason", pa.string()),
        ("signature", pa.binary()),
        ("public_key_pem", pa.string()),
    ]
)


def _serialize_entry(entry: AuditEntry) -> dict[str, Any]:
    """Serialize an AuditEntry to a flat dict for Parquet storage."""
    return {
        "entry_id": str(entry.entry_id),
        "timestamp": entry.timestamp,
        "user_id": entry.user_id,
        "action": entry.action.value,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "old_value_hash": entry.old_value_hash,
        "new_value_hash": entry.new_value_hash,
        "previous_entry_hash": entry.previous_entry_hash,
        "reason": entry.reason,
        "signature": entry.signature,
        "public_key_pem": entry.public_key_pem,
    }


def _deserialize_entry(row: dict[str, Any]) -> AuditEntry:
    """Deserialize a flat dict from Parquet back to an AuditEntry."""
    return AuditEntry(
        entry_id=UUID(row["entry_id"]),
        timestamp=row["timestamp"],
        user_id=row["user_id"],
        action=AuditAction(row["action"]),
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        old_value_hash=row.get("old_value_hash", ""),
        new_value_hash=row["new_value_hash"],
        previous_entry_hash=row.get("previous_entry_hash", ""),
        reason=row.get("reason", ""),
        signature=row.get("signature", b"") or b"",
        public_key_pem=row.get("public_key_pem", ""),
    )


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class AuditTrailWriter:
    """Thread-safe audit trail writer with Ed25519 signing and hash chain.

    Every ``append`` call:
    1. Links the entry to its predecessor via ``previous_entry_hash``.
    2. Signs the entry with the supplied Ed25519 private key.
    3. Persists the entry to a Parquet file.
    """

    def __init__(
        self,
        engine: StorageEngine,
        private_key: Ed25519PrivateKey,
    ) -> None:
        self._engine = engine
        self._layout = ParquetLayout(engine.data_root)
        self._private_key = private_key
        self._public_key_pem = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
        self._lock = threading.Lock()
        self._last_hash: str = ""

        # Resume hash chain from existing trail
        trail_file = self._layout.audit_trail_file()
        if trail_file.exists():
            entries = self.get_entries()
            if entries:
                self._last_hash = entries[-1].compute_hash()

    def append(self, entry: AuditEntry) -> AuditEntry:
        """Append a signed entry to the audit trail.

        Thread-safe: serialises concurrent callers via an internal lock.
        """
        with self._lock:
            entry.previous_entry_hash = self._last_hash
            entry.public_key_pem = self._public_key_pem
            sign_entry(entry, self._private_key)

            # Serialize and write to Parquet
            row = _serialize_entry(entry)
            arrays = []
            for field in _AUDIT_SCHEMA:
                arrays.append(pa.array([row[field.name]], type=field.type))
            new_table = pa.table(arrays, schema=_AUDIT_SCHEMA)

            path = self._layout.audit_trail_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                existing = pq.read_table(path, schema=_AUDIT_SCHEMA)  # type: ignore[no-untyped-call]
                combined = pa.concat_tables([existing, new_table])
            else:
                combined = new_table

            # Write to temp file then atomically rename (POSIX) to
            # prevent corruption if the process crashes mid-write.
            fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".parquet")
            os.close(fd)  # close fd; pq.write_table opens by path
            tmp_path = Path(tmp_name)
            try:
                pq.write_table(combined, tmp_path, use_dictionary=False)  # type: ignore[no-untyped-call]
                os.replace(str(tmp_path), str(path))  # atomic on both POSIX and Windows
            except BaseException:
                tmp_path.unlink(missing_ok=True)
                raise

            self._last_hash = entry.compute_hash()
            return entry

    def get_entries(self) -> list[AuditEntry]:
        """Read all audit entries from the Parquet trail file."""
        path = self._layout.audit_trail_file()
        if not path.exists():
            return []
        table = pq.read_table(path, schema=_AUDIT_SCHEMA)  # type: ignore[no-untyped-call]
        df = table.to_pandas()
        return [_deserialize_entry(row.to_dict()) for _, row in df.iterrows()]

    def verify_chain(self) -> bool:
        """Verify the SHA-256 hash chain is intact.

        Returns ``True`` if every entry's ``previous_entry_hash``
        matches ``compute_hash()`` of its predecessor.  The first
        entry must have an empty ``previous_entry_hash``.
        """
        entries = self.get_entries()
        if not entries:
            return True

        if entries[0].previous_entry_hash != "":
            return False

        for i in range(1, len(entries)):
            expected = entries[i - 1].compute_hash()
            if entries[i].previous_entry_hash != expected:
                return False
        return True
