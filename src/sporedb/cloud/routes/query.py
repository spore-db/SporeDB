"""DSL query execution API route.

Accepts bioprocess DSL query strings, parses and compiles them to
DuckDB SQL, and executes against tenant-scoped S3 Parquet data.

Threat mitigations:
- T-8-17: All queries go through DSL parser -> SQL compiler. No raw SQL.
- T-8-18: Query timeout enforced by QueryService (30 seconds).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from sporedb.cloud.auth.deps import get_current_user
from sporedb.cloud.auth.middleware import TenantContext

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """Payload for executing a DSL query."""

    query: str
    format: str = "json"  # "json" or "arrow"


class QueryResponse(BaseModel):
    """Tabular query result returned as JSON."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def execute_query(
    body: QueryRequest,
    request: Request,
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
) -> QueryResponse:
    """Execute a bioprocess DSL query against tenant data.

    Uses a sync handler (``def`` not ``async def``) because DuckDB
    execution is CPU-bound. FastAPI auto-runs sync handlers in a
    threadpool, preventing event loop blocking (RESEARCH.md Pitfall 1).
    """
    query_service = request.app.state.query_service

    try:
        results = query_service.execute_dsl(ctx.tenant_id, body.query)
    except ValueError as exc:
        # DSL parse errors
        raise HTTPException(
            status_code=400, detail=f"Query parse error: {exc}"
        ) from exc
    except RuntimeError as exc:
        # Log internal details server-side; return generic message to client
        logger = logging.getLogger(__name__)
        logger.error("Query execution error for tenant %s: %s", ctx.tenant_id, exc)
        raise HTTPException(status_code=500, detail="Query execution failed") from exc

    if not results:
        return QueryResponse(columns=[], rows=[], row_count=0)

    columns = list(results[0].keys())
    rows = [list(row.values()) for row in results]
    return QueryResponse(columns=columns, rows=rows, row_count=len(rows))


router.add_api_route(
    "/execute",
    execute_query,
    methods=["POST"],
    response_model=QueryResponse,
)
