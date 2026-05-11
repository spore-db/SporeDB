"""Plotly figure JSON endpoints for the SporeDB web dashboard.

Returns Plotly figure specs as JSON for client-side rendering with Plotly.js.
Endpoints are consumed by dashboard pages via ``fetch()`` calls in the browser.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from uuid import UUID

import jwt
import pandas as pd
import plotly.graph_objects as go
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import APIKeyCookie

from sporedb.cloud.auth.jwt import decode_token
from sporedb.cloud.auth.middleware import TenantContext
from sporedb.viz._colors import _D3_PALETTE, get_batch_colors

router = APIRouter(prefix="/dash/api", tags=["dashboard-figures"])

cookie_scheme = APIKeyCookie(name="sporedb_session", auto_error=False)


async def get_figure_user(
    request: Request,
    token: str | None = Depends(cookie_scheme),
) -> TenantContext:
    """Extract user from cookie JWT for figure API endpoints.

    Returns JSON 401 on missing/invalid cookie (not a redirect) because
    these endpoints are called by JavaScript ``fetch()``, not browser navigation.
    """
    if token is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    public_key = getattr(request.app.state, "jwt_public_key", None)
    if public_key is None:
        raise HTTPException(status_code=500, detail="JWT public key not configured")

    try:
        payload = decode_token(token, public_key)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token") from None

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    return TenantContext(
        tenant_id=payload["tenant_id"],
        user_id=payload["sub"],
        email=payload["email"],
        role=payload["role"],
    )


@router.get("/batches/{batch_id}/figure")
async def batch_figure(
    request: Request,
    batch_id: str,
    signal: str = Query(default="OD600"),
    ctx: TenantContext = Depends(get_figure_user),  # noqa: B008
) -> dict[str, Any]:
    """Return Plotly figure JSON for a single batch time-series.

    Parameters
    ----------
    batch_id:
        UUID of the batch to visualize.
    signal:
        Variable column to plot (default ``OD600``).
    """
    # Validate batch_id format (T-10-11 mitigation)
    try:
        bid = UUID(batch_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid batch_id format") from None

    s3_storage = request.app.state.s3_storage
    try:
        data = await s3_storage.get_parquet(ctx.tenant_id, bid, "telemetry")
    except Exception:
        raise HTTPException(
            status_code=404, detail="Batch telemetry data not found"
        ) from None

    df = pd.read_parquet(BytesIO(data))

    if signal not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"Signal '{signal}' not found in batch data",
        )

    # Determine time column
    time_col = "timestamp"
    if time_col not in df.columns:
        # Fall back to first datetime column or index
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                time_col = col
                break

    fig = go.Figure()
    fig.add_scatter(
        x=df[time_col].tolist() if time_col in df.columns else list(range(len(df))),
        y=df[signal].tolist(),
        name=signal,
        mode="lines",
        line=dict(color=_D3_PALETTE[0]),
    )
    fig.update_layout(
        template="plotly_white",
        hovermode="x unified",
        height=400,
        margin=dict(l=40, r=20, t=30, b=40),
        xaxis_title="Time",
        yaxis_title=signal,
    )

    # Best-effort: add phase boundary markers if phase detection data exists
    try:
        phase_data = await s3_storage.get_parquet(ctx.tenant_id, bid, "phases")
        phase_df = pd.read_parquet(BytesIO(phase_data))
        if "start_time" in phase_df.columns and "label" in phase_df.columns:
            for _, row in phase_df.iterrows():
                fig.add_vline(
                    x=row["start_time"],
                    line_dash="dash",
                    line_color="gray",
                    annotation_text=str(row["label"]),
                    annotation_position="top left",
                )
    except Exception:
        pass  # No phase data available — render chart without markers

    return json.loads(fig.to_json())  # type: ignore[no-any-return]


@router.get("/compare/figure")
async def compare_figure(
    request: Request,
    batch_ids: list[str] = Query(...),  # noqa: B008
    signal: str = Query(default="OD600"),
    ctx: TenantContext = Depends(get_figure_user),  # noqa: B008
) -> dict[str, Any]:
    """Return Plotly figure JSON for multi-run comparison overlay.

    Parameters
    ----------
    batch_ids:
        List of 2-10 batch UUIDs to compare.
    signal:
        Variable column to plot (default ``OD600``).
    """
    # Validate batch count (T-10-10 mitigation)
    if len(batch_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 batch_ids required for comparison",
        )
    if len(batch_ids) > 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 batch_ids allowed for comparison",
        )

    # Validate batch_id formats (T-10-11 mitigation)
    validated_ids: list[UUID] = []
    for bid_str in batch_ids:
        try:
            validated_ids.append(UUID(bid_str))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid batch_id format: {bid_str}",
            ) from None

    s3_storage = request.app.state.s3_storage
    colors = get_batch_colors(batch_ids)

    fig = go.Figure()
    for bid_str, bid in zip(batch_ids, validated_ids, strict=True):
        try:
            data = await s3_storage.get_parquet(ctx.tenant_id, bid, "telemetry")
        except Exception:
            # Skip batches with missing data
            continue

        df = pd.read_parquet(BytesIO(data))

        if signal not in df.columns:
            continue

        # Determine time column
        time_col = "timestamp"
        if time_col not in df.columns:
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    time_col = col
                    break

        fig.add_scatter(
            x=df[time_col].tolist() if time_col in df.columns else list(range(len(df))),
            y=df[signal].tolist(),
            name=bid_str,
            mode="lines",
            line=dict(color=colors[bid_str]),
        )

    fig.update_layout(
        template="plotly_white",
        hovermode="x unified",
        height=400,
        margin=dict(l=40, r=20, t=30, b=40),
        xaxis_title="Time",
        yaxis_title=signal,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    return json.loads(fig.to_json())  # type: ignore[no-any-return]
