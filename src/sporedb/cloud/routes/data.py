"""Data upload/download API routes for telemetry and assay Parquet files.

All routes require JWT authentication and scope S3 operations to the
authenticated tenant's prefix.

Threat mitigations:
- T-8-19: batch_id validated as UUID before S3 key construction.
- T-8-22: S3 key construction scoped to tenant prefix via S3Storage.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from uuid import UUID

import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather
import pyarrow.parquet as pq
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from sporedb.cloud.auth.deps import get_current_user, require_permission
from sporedb.cloud.auth.middleware import TenantContext
from sporedb.cloud.services.cloud_audit_service import CloudAuditService
from sporedb.compliance.rbac import Permission

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    """Response returned after a successful Parquet upload."""

    batch_id: str
    data_type: str
    size_bytes: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_uuid(value: str) -> UUID:
    """Validate that a string is a valid UUID format (T-8-19)."""
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400, detail=f"Invalid UUID format: {value}"
        ) from None


# ---------------------------------------------------------------------------
# Upload endpoints
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB limit


@router.post("/telemetry/{batch_id}", response_model=UploadResponse, status_code=201)
async def upload_telemetry(
    batch_id: str,
    file: UploadFile,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.WRITE)),  # noqa: B008
) -> UploadResponse:
    """Upload a telemetry Parquet file for a batch."""
    batch_uuid = _validate_uuid(batch_id)
    # Check Content-Length header for fast rejection
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            cl = int(content_length)
        except (ValueError, TypeError):
            cl = 0
        if cl > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    # Validate uploaded bytes are valid Parquet format
    try:
        pq.read_table(BytesIO(data))  # type: ignore[no-untyped-call]
    except Exception:
        raise HTTPException(
            status_code=400, detail="Invalid Parquet file format"
        ) from None

    s3_storage = request.app.state.s3_storage
    await s3_storage.put_parquet(ctx.tenant_id, batch_uuid, "telemetry", data)
    async with request.app.state.db_session.get_session() as audit_session:
        audit_svc = CloudAuditService(audit_session, request.app.state.jwt_private_key)
        data_hash = hashlib.sha256(data).hexdigest()
        await audit_svc.append(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            action="create",
            entity_type="telemetry",
            entity_id=batch_id,
            new_value_hash=data_hash,
        )
        await audit_session.commit()
    return UploadResponse(
        batch_id=batch_id,
        data_type="telemetry",
        size_bytes=len(data),
    )


@router.post("/assay/{batch_id}", response_model=UploadResponse, status_code=201)
async def upload_assay(
    batch_id: str,
    file: UploadFile,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.WRITE)),  # noqa: B008
) -> UploadResponse:
    """Upload an assay Parquet file for a batch."""
    batch_uuid = _validate_uuid(batch_id)
    # Check Content-Length header for fast rejection (T-13-25)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            cl = int(content_length)
        except (ValueError, TypeError):
            cl = 0
        if cl > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    # Validate uploaded bytes are valid Parquet format
    try:
        pq.read_table(BytesIO(data))  # type: ignore[no-untyped-call]
    except Exception:
        raise HTTPException(
            status_code=400, detail="Invalid Parquet file format"
        ) from None

    s3_storage = request.app.state.s3_storage
    await s3_storage.put_parquet(ctx.tenant_id, batch_uuid, "assay", data)
    async with request.app.state.db_session.get_session() as audit_session:
        audit_svc = CloudAuditService(audit_session, request.app.state.jwt_private_key)
        data_hash = hashlib.sha256(data).hexdigest()
        await audit_svc.append(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            action="create",
            entity_type="assay",
            entity_id=batch_id,
            new_value_hash=data_hash,
        )
        await audit_session.commit()
    return UploadResponse(
        batch_id=batch_id,
        data_type="assay",
        size_bytes=len(data),
    )


# ---------------------------------------------------------------------------
# Download endpoints
# ---------------------------------------------------------------------------


@router.get("/telemetry/{batch_id}")
async def download_telemetry(
    batch_id: str,
    request: Request,
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
) -> Response:
    """Download the telemetry Parquet file for a batch."""
    batch_uuid = _validate_uuid(batch_id)
    s3_storage = request.app.state.s3_storage
    try:
        data = await s3_storage.get_parquet(ctx.tenant_id, batch_uuid, "telemetry")
    except (KeyError, Exception) as exc:
        # ClientError or missing key
        raise HTTPException(status_code=404, detail="Telemetry data not found") from exc
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=telemetry_{batch_id}.parquet"
        },
    )


@router.get("/assay/{batch_id}")
async def download_assay(
    batch_id: str,
    request: Request,
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
) -> Response:
    """Download the assay Parquet file for a batch."""
    batch_uuid = _validate_uuid(batch_id)
    s3_storage = request.app.state.s3_storage
    try:
        data = await s3_storage.get_parquet(ctx.tenant_id, batch_uuid, "assay")
    except (KeyError, Exception) as exc:
        if "NoSuchKey" in str(exc) or isinstance(exc, KeyError):
            raise HTTPException(status_code=404, detail="Assay data not found") from exc
        raise HTTPException(status_code=404, detail="Assay data not found") from exc
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=assay_{batch_id}.parquet"
        },
    )


# ---------------------------------------------------------------------------
# Export endpoint (CSV / Arrow)
# ---------------------------------------------------------------------------

_ALLOWED_FORMATS = {"csv", "arrow"}


@router.get("/export/{batch_id}")
async def export_batch(
    batch_id: str,
    request: Request,
    format: str = "csv",
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
) -> Response:
    """Export batch telemetry data as CSV or Arrow IPC.

    Threat mitigations:
    - T-12-03: Requires JWT auth via get_current_user.
    - T-12-04: format parameter validated against allowlist.
    - T-12-05: S3 key scoped to ctx.tenant_id.
    """
    batch_uuid = _validate_uuid(batch_id)

    if format not in _ALLOWED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid format '{format}'. Must be one of: {sorted(_ALLOWED_FORMATS)}"
            ),
        )

    s3_storage = request.app.state.s3_storage
    try:
        data = await s3_storage.get_parquet(ctx.tenant_id, batch_uuid, "telemetry")
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"Telemetry data not found for batch {batch_id}",
        ) from None

    df = pd.read_parquet(BytesIO(data))

    if format == "csv":
        content = df.to_csv(index=False).encode("utf-8")
        media_type = "text/csv"
        ext = "csv"
    else:  # arrow
        buf = BytesIO()
        feather.write_feather(pa.Table.from_pandas(df), buf)  # type: ignore[no-untyped-call]
        content = buf.getvalue()
        media_type = "application/vnd.apache.arrow.file"
        ext = "arrow"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename=export_{batch_id}.{ext}"
        },
    )
