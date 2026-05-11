"""PostgreSQL advisory locks for cloud-tier concurrent access control.

Uses transaction-scoped advisory locks (``pg_advisory_xact_lock``) that
are automatically released on commit/rollback.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def advisory_lock(session: AsyncSession, *key_parts: str) -> None:
    """Acquire a transaction-scoped PostgreSQL advisory lock.

    The lock key is derived from the string parts via MD5 hash,
    ensuring deterministic behavior across workers (unlike Python's
    ``hash()`` which is randomized per process).

    Parameters
    ----------
    session:
        Active async SQLAlchemy session (must be in a transaction).
    *key_parts:
        Strings combined to form the lock key (e.g., tenant_id, "batch", batch_id).
    """
    key = ":".join(key_parts)
    lock_id = int(hashlib.md5(key.encode()).hexdigest()[:8], 16) & 0x7FFFFFFF
    await session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock_id})
