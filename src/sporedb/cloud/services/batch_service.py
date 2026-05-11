"""Batch management service with mandatory tenant isolation.

Every query includes a ``tenant_id`` filter to enforce multi-tenant
data separation at the service layer.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from sporedb.cloud.db.models import CloudBatch


class BatchService:
    """Business logic for batch CRUD with tenant-scoped queries.

    Parameters
    ----------
    session:
        An async SQLAlchemy session for database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_batch(
        self,
        tenant_id: str,
        name: str,
        lifecycle: str = "planned",
        metadata_json: str | None = None,
        tags_json: str | None = None,
    ) -> CloudBatch:
        """Create a new batch owned by the given tenant."""
        batch = CloudBatch(
            id=str(uuid7()),
            tenant_id=tenant_id,
            name=name,
            lifecycle=lifecycle,
            metadata_json=metadata_json,
            tags_json=tags_json,
        )
        self._session.add(batch)
        await self._session.flush()
        return batch

    async def get_batch(self, tenant_id: str, batch_id: str) -> CloudBatch | None:
        """Get a single batch, scoped to the tenant.

        Returns None if not found or if the batch belongs to another tenant.
        """
        result = await self._session.execute(
            select(CloudBatch).where(
                CloudBatch.tenant_id == tenant_id,
                CloudBatch.id == batch_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_batches(
        self, tenant_id: str, search: str | None = None
    ) -> list[CloudBatch]:
        """List batches for the given tenant, optionally filtered by name.

        Parameters
        ----------
        tenant_id:
            Tenant scope for multi-tenant isolation.
        search:
            Optional search term. When provided, applies a SQL ILIKE
            filter on the batch name (server-side, not in-memory).
        """
        stmt = select(CloudBatch).where(CloudBatch.tenant_id == tenant_id)
        if search:
            # HI-02: Escape LIKE wildcards to prevent pattern injection.
            # Escape backslash first to prevent double-escaping.
            escaped = (
                search.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
            )
            stmt = stmt.where(CloudBatch.name.ilike(f"%{escaped}%", escape="\\"))
        stmt = stmt.order_by(CloudBatch.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_batch(
        self, tenant_id: str, batch_id: str, **kwargs: str | None
    ) -> CloudBatch | None:
        """Update batch fields, scoped to the tenant.

        Returns the updated batch, or None if not found.
        """
        batch = await self.get_batch(tenant_id, batch_id)
        if batch is None:
            return None

        for field, value in kwargs.items():
            if value is not None and hasattr(batch, field):
                setattr(batch, field, value)

        batch.updated_at = datetime.now(UTC)
        await self._session.flush()
        return batch

    async def delete_batch(self, tenant_id: str, batch_id: str) -> bool:
        """Delete a batch, scoped to the tenant.

        Returns True if a batch was deleted, False if not found.
        """
        result = await self._session.execute(
            delete(CloudBatch).where(
                CloudBatch.tenant_id == tenant_id,
                CloudBatch.id == batch_id,
            )
        )
        return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]
