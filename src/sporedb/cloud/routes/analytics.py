"""Phase detection and alignment analytics API routes.

Reuses existing SporeDB analytics modules (PhaseDetector, align) to
expose phase detection and cross-run alignment through the cloud API.

Threat mitigations:
- T-8-21: CPU-bound operations use sync handlers (threadpool execution).
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any
from uuid import UUID

import pandas as pd
import pyarrow.parquet as pq
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from sporedb.analytics.alignment import align
from sporedb.analytics.bocpd import BOCPDDetector
from sporedb.analytics.detector import PhaseDetector
from sporedb.analytics.metrics import compute_batch_metrics
from sporedb.analytics.models import BOCPDConfig, DetectionConfig, PhaseType
from sporedb.analytics.phase_store import _records_to_table
from sporedb.cloud.auth.deps import get_current_user
from sporedb.cloud.auth.middleware import TenantContext

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class DetectPhasesRequest(BaseModel):
    """Payload for phase detection on a single batch."""

    batch_id: str
    signal: str = "OD600"
    min_size: int = Field(default=10, ge=2, le=10000)


class PhaseAnnotationResponse(BaseModel):
    """A detected phase boundary in a batch run."""

    phase_type: str
    start_idx: int
    end_idx: int
    start_time: str | None = None
    end_time: str | None = None
    confidence: float | None = None


class AlignRequest(BaseModel):
    """Payload for cross-run alignment of multiple batches."""

    batch_ids: list[str]
    signal: str = "OD600"


class AlignResponse(BaseModel):
    """Aligned time-series data across multiple batches."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int


class MetricsRequest(BaseModel):
    """Payload for batch metrics computation."""

    batch_id: str
    signal: str = "OD600"
    min_size: int = 10


class MetricsResponse(BaseModel):
    """Computed batch metrics per phase."""

    batch_id: str
    metrics: list[dict[str, Any]]


class DetectPhasesOnlineRequest(BaseModel):
    """Payload for BOCPD online phase detection."""

    batch_id: str
    signal: str = "OD600"
    hazard_rate: float = 0.004  # 1/250
    threshold: float = 0.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_uuid(value: str) -> UUID:
    """Validate that a string is a valid UUID format."""
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400, detail=f"Invalid UUID format: {value}"
        ) from None


def _load_parquet_from_bytes(data: bytes) -> pd.DataFrame:
    """Load a Parquet file from raw bytes into a pandas DataFrame."""
    return pd.read_parquet(BytesIO(data))


# ---------------------------------------------------------------------------
# Endpoints (sync handlers for CPU-bound operations)
# ---------------------------------------------------------------------------


async def detect_phases(
    body: DetectPhasesRequest,
    request: Request,
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
) -> list[PhaseAnnotationResponse]:
    """Detect phases in a batch's telemetry data.

    Downloads telemetry Parquet from S3, runs PELT-based phase detection,
    and returns detected phase boundaries.
    """
    import asyncio

    batch_uuid = _validate_uuid(body.batch_id)
    s3_storage = request.app.state.s3_storage

    # Download telemetry Parquet from S3 (async)
    try:
        data = await s3_storage.get_parquet(ctx.tenant_id, batch_uuid, "telemetry")
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"Telemetry data not found for batch {body.batch_id}",
        ) from None

    # CPU-bound phase detection in threadpool
    config = DetectionConfig(
        signal_variable=body.signal,
        min_size=body.min_size,
    )
    detector = PhaseDetector(config)

    def _run_detection() -> list[Any]:
        df = _load_parquet_from_bytes(data)
        return detector.detect(df, batch_uuid)

    try:
        annotations = await asyncio.to_thread(_run_detection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Persist phase annotations to S3
    if annotations:
        try:
            table = _records_to_table(annotations)
            buf = BytesIO()
            pq.write_table(table, buf)  # type: ignore[no-untyped-call]
            phase_bytes = buf.getvalue()
            await s3_storage.put_parquet(
                ctx.tenant_id, batch_uuid, "phases", phase_bytes
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "Failed to persist phase annotations for batch %s",
                body.batch_id,
                exc_info=True,
            )

    # Convert to response format
    results: list[PhaseAnnotationResponse] = []
    for ann in annotations:
        results.append(
            PhaseAnnotationResponse(
                phase_type=ann.phase_type.value,
                start_idx=0,  # Index not tracked in PhaseAnnotation
                end_idx=0,
                start_time=ann.start_ts.isoformat() if ann.start_ts else None,
                end_time=ann.end_ts.isoformat() if ann.end_ts else None,
                confidence=ann.confidence,
            )
        )
    return results


async def align_batches(
    body: AlignRequest,
    request: Request,
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
) -> AlignResponse:
    """Align multiple batch runs by phase boundary.

    Downloads telemetry for each batch, detects phases, then aligns
    by the exponential phase start time.
    """

    if len(body.batch_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 batch_ids required for alignment",
        )

    s3_storage = request.app.state.s3_storage
    batches: dict[str, pd.DataFrame] = {}
    phase_annotations: dict[str, list[Any]] = {}

    config = DetectionConfig(signal_variable=body.signal)
    detector = PhaseDetector(config)

    for bid in body.batch_ids:
        batch_uuid = _validate_uuid(bid)

        # Download telemetry (async)
        try:
            data = await s3_storage.get_parquet(ctx.tenant_id, batch_uuid, "telemetry")
        except Exception:
            raise HTTPException(
                status_code=404,
                detail=f"Telemetry data not found for batch {bid}",
            ) from None

        df = _load_parquet_from_bytes(data)
        batches[bid] = df

        # Detect phases for alignment anchor
        try:
            annotations = detector.detect(df, batch_uuid)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Phase detection failed for batch {bid}: {exc}",
            ) from exc
        phase_annotations[bid] = annotations

    # Align all batches
    try:
        aligned_df = align(
            batches=batches,
            phase_annotations=phase_annotations,
            anchor_phase=PhaseType.EXPONENTIAL,
            variables=[body.signal],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Alignment failed: {exc}") from exc

    if aligned_df.empty:
        return AlignResponse(columns=[], rows=[], row_count=0)

    # Reset index so elapsed_hours becomes a column
    aligned_df = aligned_df.reset_index()
    columns = list(aligned_df.columns)
    rows = aligned_df.values.tolist()

    return AlignResponse(columns=columns, rows=rows, row_count=len(rows))


async def compute_metrics(
    body: MetricsRequest,
    request: Request,
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
) -> MetricsResponse:
    """Compute kinetic metrics for each detected phase of a batch.

    Downloads telemetry, runs phase detection, then computes metrics
    (growth rate, productivity, yields) for each phase.
    """
    import asyncio

    batch_uuid = _validate_uuid(body.batch_id)
    s3_storage = request.app.state.s3_storage

    try:
        data = await s3_storage.get_parquet(ctx.tenant_id, batch_uuid, "telemetry")
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"Telemetry data not found for batch {body.batch_id}",
        ) from None

    config = DetectionConfig(
        signal_variable=body.signal,
        min_size=body.min_size,
    )
    detector = PhaseDetector(config)

    def _run_metrics() -> list[dict[str, Any]]:
        df = _load_parquet_from_bytes(data)
        annotations = detector.detect(df, batch_uuid)
        metrics_list = compute_batch_metrics(df, annotations, batch_uuid)
        result = []
        for m in metrics_list:
            d = m.model_dump()
            # Convert UUID and enum fields to strings for JSON serialization
            d["batch_id"] = str(d["batch_id"])
            d["phase_type"] = (
                d["phase_type"].value
                if hasattr(d["phase_type"], "value")
                else str(d["phase_type"])
            )
            result.append(d)
        return result

    try:
        metrics = await asyncio.to_thread(_run_metrics)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MetricsResponse(batch_id=body.batch_id, metrics=metrics)


async def detect_phases_online(
    body: DetectPhasesOnlineRequest,
    request: Request,
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
) -> list[PhaseAnnotationResponse]:
    """Run BOCPD online phase detection on a batch's telemetry data.

    Uses Bayesian Online Changepoint Detection for real-time-style
    phase boundary identification.
    """
    import asyncio

    batch_uuid = _validate_uuid(body.batch_id)
    s3_storage = request.app.state.s3_storage

    try:
        data = await s3_storage.get_parquet(ctx.tenant_id, batch_uuid, "telemetry")
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"Telemetry data not found for batch {body.batch_id}",
        ) from None

    bocpd_config = BOCPDConfig(
        signal_variable=body.signal,
        hazard_rate=body.hazard_rate,
        threshold=body.threshold,
    )
    detector = BOCPDDetector(bocpd_config)

    def _run_bocpd() -> list[Any]:
        df = _load_parquet_from_bytes(data)
        return detector.detect_batch(df, batch_uuid)

    try:
        annotations = await asyncio.to_thread(_run_bocpd)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    results: list[PhaseAnnotationResponse] = []
    for ann in annotations:
        results.append(
            PhaseAnnotationResponse(
                phase_type=ann.phase_type.value,
                start_idx=0,
                end_idx=0,
                start_time=ann.start_ts.isoformat() if ann.start_ts else None,
                end_time=ann.end_ts.isoformat() if ann.end_ts else None,
                confidence=ann.confidence,
            )
        )
    return results


# Register routes
router.add_api_route(
    "/detect-phases",
    detect_phases,
    methods=["POST"],
    response_model=list[PhaseAnnotationResponse],
)

router.add_api_route(
    "/align",
    align_batches,
    methods=["POST"],
    response_model=AlignResponse,
)

router.add_api_route(
    "/metrics",
    compute_metrics,
    methods=["POST"],
    response_model=MetricsResponse,
)

router.add_api_route(
    "/detect-phases-online",
    detect_phases_online,
    methods=["POST"],
    response_model=list[PhaseAnnotationResponse],
)
