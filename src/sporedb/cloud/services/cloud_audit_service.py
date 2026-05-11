"""Cloud audit service with Ed25519 signing and SHA-256 hash chain.

Provides an async counterpart to the local AuditTrailWriter, persisting
signed, hash-chained audit entries to PostgreSQL via SQLAlchemy async
sessions.  Each entry is linked to its predecessor by including the
previous entry's SHA-256 hash, forming a tamper-evident chain.
"""

from __future__ import annotations

from datetime import UTC

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sporedb.cloud.db.models import AuditIndex
from sporedb.compliance.audit import AuditAction, AuditEntry
from sporedb.compliance.signing import sign_entry


class CloudAuditService:
    """Async audit trail writer for the cloud tier.

    Creates signed, hash-chained audit entries in the ``audit_index``
    table.  Mirrors the local :class:`AuditTrailWriter` behaviour but
    operates on an async SQLAlchemy session backed by PostgreSQL.
    """

    def __init__(
        self,
        session: AsyncSession,
        private_key: Ed25519PrivateKey,
    ) -> None:
        self._session = session
        self._private_key = private_key
        self._public_key_pem = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )

    async def _load_last_hash(self, tenant_id: str) -> str:
        """Load the hash of the most recent audit entry for *tenant_id*.

        Queries ``audit_index`` ordered by ``created_at DESC``, limit 1.
        Returns the ``record_hash`` if found, otherwise an empty string.
        """
        stmt = (
            select(AuditIndex.record_hash)
            .where(AuditIndex.tenant_id == tenant_id)
            .order_by(AuditIndex.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return row if row else ""

    async def append(
        self,
        tenant_id: str,
        user_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        new_value_hash: str,
        old_value_hash: str = "",
        reason: str = "",
    ) -> AuditIndex:
        """Create a signed, hash-chained audit entry.

        Steps
        -----
        1. Acquire per-tenant advisory lock to serialise concurrent appends.
        2. Load the latest hash from DB (always fresh, under lock).
        3. Build an :class:`AuditEntry` from the compliance module.
        4. Sign and hash the entry with Ed25519.
        5. Persist as an :class:`AuditIndex` row.

        Returns the newly created ``AuditIndex`` row.
        """
        # 1. Acquire advisory lock to serialise concurrent appends for this
        #    tenant, preventing hash-chain races (CR-05).  The lock is held
        #    until the surrounding transaction commits or rolls back.
        from sporedb.cloud.db.locking import advisory_lock

        await advisory_lock(self._session, tenant_id, "audit")

        # Always read from DB under lock -- no in-memory cache.
        previous_hash = await self._load_last_hash(tenant_id)

        # 2. Build compliance-layer AuditEntry
        entry = AuditEntry(
            user_id=user_id,
            action=AuditAction(action),
            entity_type=entity_type,
            entity_id=entity_id,
            new_value_hash=new_value_hash,
            old_value_hash=old_value_hash,
            reason=reason,
            previous_entry_hash=previous_hash,
        )

        # 3. Attach public key and sign
        entry.public_key_pem = self._public_key_pem
        sign_entry(entry, self._private_key)

        # 4. Compute record hash
        record_hash = entry.compute_hash()

        # 5. Persist to audit_index
        # Use entry.timestamp as created_at so that verify_chain can
        # reconstruct identical canonical bytes and recompute the hash.
        row = AuditIndex(
            id=str(entry.entry_id),
            tenant_id=tenant_id,
            action=entry.action.value,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            user_id=entry.user_id,
            created_at=entry.timestamp,
            old_value_hash=entry.old_value_hash,
            new_value_hash=entry.new_value_hash,
            previous_entry_hash=entry.previous_entry_hash,
            reason=entry.reason,
            signature=entry.signature,
            public_key_pem=entry.public_key_pem,
            record_hash=record_hash,
        )
        self._session.add(row)
        await self._session.flush()

        return row

    async def verify_chain(self, tenant_id: str) -> list[tuple[str, bool]]:
        """Verify the hash chain for *tenant_id*.

        Returns a list of ``(entry_id, is_valid)`` tuples.  For each
        entry the method reconstructs an :class:`AuditEntry`, computes
        its hash, and checks that ``previous_entry_hash`` matches the
        predecessor's ``record_hash``.
        """
        stmt = (
            select(AuditIndex)
            .where(AuditIndex.tenant_id == tenant_id)
            .order_by(AuditIndex.created_at.asc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return []

        results: list[tuple[str, bool]] = []
        prev_hash = ""

        for row in rows:
            # Reconstruct AuditEntry to reuse compute_hash()
            # Ensure timezone-aware timestamp (SQLite may strip tzinfo)
            ts = row.created_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            # Check chain linkage: this entry's previous_entry_hash
            # must match the predecessor's stored record_hash.
            chain_ok = (row.previous_entry_hash or "") == prev_hash

            results.append((row.id, chain_ok))

            # Track the stored record_hash for next entry's chain check.
            # If this hash was tampered, the next entry's chain_ok will
            # fail because its previous_entry_hash won't match.
            prev_hash = row.record_hash or ""

        return results
