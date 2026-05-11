"""Tests for the DSL query execution API route.

Covers cloud/routes/query.py lines 61-81:
- Successful query returning results
- Empty results returning empty QueryResponse
- ValueError (DSL parse error) returns HTTP 400
- RuntimeError (internal error) returns HTTP 500
- Result shape (columns, rows, row_count)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from sporedb.cloud.routes.query import QueryRequest, QueryResponse, router

# ---------------------------------------------------------------------------
# App fixture specific to query route (needs query_service in app.state)
# ---------------------------------------------------------------------------


@pytest.fixture
def query_app(ed25519_keypair):
    """FastAPI test app wired with query router and a mock query_service."""
    _, public_key = ed25519_keypair

    app = FastAPI(title="SporeDB Query Test")
    app.state.jwt_public_key = public_key
    app.state.query_service = MagicMock()

    app.include_router(router, prefix="/api/v1/query")

    return app


@pytest_asyncio.fixture
async def query_client(query_app) -> AsyncClient:
    transport = ASGITransport(app=query_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers_for_query(ed25519_keypair, test_tenant_id, test_user_id):
    """Auth headers signed with the test keypair."""
    from sporedb.cloud.auth.jwt import create_access_token

    private_key, _ = ed25519_keypair
    token = create_access_token(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        email="editor@example.com",
        role="editor",
        private_key=private_key,
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestQueryRouteSuccess:
    """Successful DSL query execution returns correct QueryResponse."""

    @pytest.mark.asyncio
    async def test_returns_200_with_results(
        self, query_app, query_client, auth_headers_for_query
    ):
        """Successful query with rows returns 200 and correct JSON structure."""
        query_app.state.query_service.execute_dsl.return_value = [
            {"batch_id": "abc-123", "ts": "2026-01-01T00:00:00", "value": 1.5},
            {"batch_id": "abc-123", "ts": "2026-01-01T01:00:00", "value": 2.0},
        ]

        resp = await query_client.post(
            "/api/v1/query/execute",
            json={"query": "select(batch_id='abc-123')"},
            headers=auth_headers_for_query,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["columns"] == ["batch_id", "ts", "value"]
        assert body["row_count"] == 2
        assert len(body["rows"]) == 2
        assert body["rows"][0] == ["abc-123", "2026-01-01T00:00:00", 1.5]

    @pytest.mark.asyncio
    async def test_returns_empty_response_when_no_results(
        self, query_app, query_client, auth_headers_for_query
    ):
        """Empty result list returns QueryResponse with empty columns/rows."""
        query_app.state.query_service.execute_dsl.return_value = []

        resp = await query_client.post(
            "/api/v1/query/execute",
            json={"query": "select(batch_id='nonexistent')"},
            headers=auth_headers_for_query,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["columns"] == []
        assert body["rows"] == []
        assert body["row_count"] == 0


class TestQueryRouteErrors:
    """Error conditions in DSL query execution."""

    @pytest.mark.asyncio
    async def test_value_error_returns_400(
        self, query_app, query_client, auth_headers_for_query
    ):
        """DSL parse error (ValueError) maps to HTTP 400."""
        query_app.state.query_service.execute_dsl.side_effect = ValueError(
            "Unexpected token at position 5"
        )

        resp = await query_client.post(
            "/api/v1/query/execute",
            json={"query": "bad dsl query !!!"},
            headers=auth_headers_for_query,
        )

        assert resp.status_code == 400
        assert "Query parse error" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_runtime_error_returns_500(
        self, query_app, query_client, auth_headers_for_query
    ):
        """Internal execution error (RuntimeError) maps to HTTP 500."""
        query_app.state.query_service.execute_dsl.side_effect = RuntimeError(
            "DuckDB connection lost"
        )

        resp = await query_client.post(
            "/api/v1/query/execute",
            json={"query": "select(batch_id='abc')"},
            headers=auth_headers_for_query,
        )

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Query execution failed"

    @pytest.mark.asyncio
    async def test_unauthorized_without_token(self, query_client):
        """Request without Authorization header returns 403 (no bearer scheme)."""
        resp = await query_client.post(
            "/api/v1/query/execute",
            json={"query": "select(batch_id='abc')"},
        )
        assert resp.status_code in (401, 403, 422)


class TestQueryResponseModel:
    """QueryResponse Pydantic model behaves correctly."""

    def test_query_response_fields(self) -> None:
        qr = QueryResponse(
            columns=["a", "b"],
            rows=[[1, 2], [3, 4]],
            row_count=2,
        )
        assert qr.columns == ["a", "b"]
        assert qr.row_count == 2

    def test_query_request_defaults(self) -> None:
        qr = QueryRequest(query="select()")
        assert qr.format == "json"

    def test_query_request_custom_format(self) -> None:
        qr = QueryRequest(query="select()", format="arrow")
        assert qr.format == "arrow"
