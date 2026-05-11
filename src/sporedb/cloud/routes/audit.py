"""Audit trail query API routes with tenant isolation.

All routes require JWT authentication and scope queries to the
authenticated tenant's audit entries.

Threat mitigations:
- T-8-20: Audit trail queries filtered by tenant_id from JWT.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sporedb.cloud.auth.deps import get_current_user
from sporedb.cloud.auth.middleware import TenantContext
from sporedb.cloud.db.models import AuditIndex

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AuditEntryResponse(BaseModel):
    """Serialized audit trail entry returned to the client."""

    id: str
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    user_id: str | None = None
    created_at: datetime
    # Crypto fields (from Plan 11-01)
    previous_entry_hash: str | None = None
    new_value_hash: str | None = None
    old_value_hash: str | None = None
    record_hash: str | None = None
    reason: str | None = None
    has_signature: bool = False
    verified: bool | None = None


# ---------------------------------------------------------------------------
# Database dependency
# ---------------------------------------------------------------------------


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session from the app-level factory."""
    async with request.app.state.db_session.get_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(entry: AuditIndex, verified: bool | None = None) -> AuditEntryResponse:
    """Convert an AuditIndex ORM object to an API response model."""
    return AuditEntryResponse(
        id=entry.id,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        user_id=entry.user_id,
        created_at=entry.created_at,
        previous_entry_hash=entry.previous_entry_hash,
        new_value_hash=entry.new_value_hash,
        old_value_hash=entry.old_value_hash,
        record_hash=entry.record_hash,
        reason=entry.reason,
        has_signature=bool(entry.signature),
        verified=verified,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/trail", response_model=list[AuditEntryResponse])
async def list_audit_entries(
    request: Request,
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
) -> list[AuditEntryResponse]:
    """List audit trail entries for the authenticated tenant.

    Supports pagination via ``limit`` and ``offset``, and optional
    filtering by ``action`` type.
    """
    stmt = (
        select(AuditIndex)
        .where(AuditIndex.tenant_id == ctx.tenant_id)
        .order_by(AuditIndex.created_at.desc())
    )

    if action is not None:
        stmt = stmt.where(AuditIndex.action == action)

    stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)
    entries = result.scalars().all()

    # Chain verification is opt-in via a dedicated /verify endpoint;
    # listing entries does not verify (avoids O(n) DoS on every page view).
    return [_to_response(e, verified=None) for e in entries]


@router.get("/trail/{entry_id}", response_model=AuditEntryResponse)
async def get_audit_entry(
    entry_id: str,
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> AuditEntryResponse:
    """Get a single audit trail entry by ID, scoped to the authenticated tenant."""
    stmt = (
        select(AuditIndex)
        .where(AuditIndex.id == entry_id)
        .where(AuditIndex.tenant_id == ctx.tenant_id)
    )
    result = await session.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    # Single-entry verification is not meaningful for hash chains;
    # set verified=None (chain verification requires full sequence).
    return _to_response(entry, verified=None)
