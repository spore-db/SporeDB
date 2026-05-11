"""Batch CRUD API routes with tenant isolation.

All routes require JWT authentication and derive the tenant scope
from the authenticated user's ``TenantContext``.

Threat mitigations:
- T-8-12: batch_id validated as UUID format in path params.
- T-8-13: All queries include tenant_id filter from JWT (not user input).
- T-8-14: require_permission enforces RBAC on write/delete operations.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from sporedb.cloud.auth.deps import get_current_user, require_permission
from sporedb.cloud.auth.middleware import TenantContext
from sporedb.cloud.db.models import CloudBatch
from sporedb.cloud.services.batch_service import BatchService
from sporedb.cloud.services.cloud_audit_service import CloudAuditService
from sporedb.compliance.rbac import Permission

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class BatchCreateRequest(BaseModel):
    """Payload for creating a new batch."""

    name: str = Field(..., min_length=1, max_length=255)
    lifecycle: str = "planned"
    metadata: dict[str, object] | None = None
    tags: list[str] | None = None


class BatchUpdateRequest(BaseModel):
    """Payload for updating an existing batch."""

    name: str | None = None
    lifecycle: str | None = None
    metadata: dict[str, object] | None = None
    tags: list[str] | None = None


class BatchResponse(BaseModel):
    """Serialized batch returned to the client."""

    id: str
    name: str
    lifecycle: str
    metadata: dict[str, object] | None = None
    tags: list[str] | None = None
    created_at: datetime
    updated_at: datetime | None = None


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


def _to_response(batch: CloudBatch) -> BatchResponse:
    """Convert a CloudBatch ORM object to an API response model."""
    metadata = None
    if batch.metadata_json:
        metadata = json.loads(batch.metadata_json)

    tags = None
    if batch.tags_json:
        tags = json.loads(batch.tags_json)

    return BatchResponse(
        id=batch.id,
        name=batch.name,
        lifecycle=batch.lifecycle,
        metadata=metadata,
        tags=tags,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
    )


def _get_audit_service(session: AsyncSession, request: Request) -> CloudAuditService:
    """Create a CloudAuditService instance for the current request."""
    return CloudAuditService(session, request.app.state.jwt_private_key)


def _validate_uuid(value: str) -> None:
    """Validate that a string is a valid UUID format (T-8-12)."""
    try:
        UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400, detail=f"Invalid UUID format: {value}"
        ) from None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/", response_model=BatchResponse, status_code=201)
async def create_batch(
    body: BatchCreateRequest,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.WRITE)),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> BatchResponse:
    """Create a new batch for the authenticated tenant."""
    svc = BatchService(session)
    batch = await svc.create_batch(
        tenant_id=ctx.tenant_id,
        name=body.name,
        lifecycle=body.lifecycle,
        metadata_json=json.dumps(body.metadata) if body.metadata else None,
        tags_json=json.dumps(body.tags) if body.tags else None,
    )
    audit_svc = _get_audit_service(session, request)
    new_hash = hashlib.sha256(
        f"{batch.id}:{batch.name}:{batch.lifecycle}".encode()
    ).hexdigest()
    await audit_svc.append(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="create",
        entity_type="batch",
        entity_id=batch.id,
        new_value_hash=new_hash,
    )
    await session.commit()
    return _to_response(batch)


@router.get("/", response_model=list[BatchResponse])
async def list_batches(
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[BatchResponse]:
    """List all batches for the authenticated tenant."""
    svc = BatchService(session)
    batches = await svc.list_batches(ctx.tenant_id)
    return [_to_response(b) for b in batches]


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(
    batch_id: str,
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> BatchResponse:
    """Get a single batch by ID, scoped to the authenticated tenant."""
    _validate_uuid(batch_id)
    svc = BatchService(session)
    batch = await svc.get_batch(ctx.tenant_id, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return _to_response(batch)


@router.put("/{batch_id}", response_model=BatchResponse)
async def update_batch(
    batch_id: str,
    body: BatchUpdateRequest,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.WRITE)),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> BatchResponse:
    """Update an existing batch, scoped to the authenticated tenant."""
    _validate_uuid(batch_id)
    svc = BatchService(session)

    update_kwargs: dict[str, str | None] = {}
    if body.name is not None:
        update_kwargs["name"] = body.name
    if body.lifecycle is not None:
        update_kwargs["lifecycle"] = body.lifecycle
    if body.metadata is not None:
        update_kwargs["metadata_json"] = json.dumps(body.metadata)
    if body.tags is not None:
        update_kwargs["tags_json"] = json.dumps(body.tags)

    batch = await svc.update_batch(ctx.tenant_id, batch_id, **update_kwargs)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    audit_svc = _get_audit_service(session, request)
    new_hash = hashlib.sha256(
        f"{batch.id}:{batch.name}:{batch.lifecycle}".encode()
    ).hexdigest()
    await audit_svc.append(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="update",
        entity_type="batch",
        entity_id=batch.id,
        new_value_hash=new_hash,
    )
    await session.commit()
    return _to_response(batch)


@router.delete("/{batch_id}")
async def delete_batch(
    batch_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.DELETE)),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    """Delete a batch, scoped to the authenticated tenant."""
    _validate_uuid(batch_id)
    svc = BatchService(session)
    deleted = await svc.delete_batch(ctx.tenant_id, batch_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Batch not found")
    audit_svc = _get_audit_service(session, request)
    await audit_svc.append(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="delete",
        entity_type="batch",
        entity_id=batch_id,
        new_value_hash=hashlib.sha256(batch_id.encode()).hexdigest(),
    )
    await session.commit()
    return {"status": "deleted", "id": batch_id}
