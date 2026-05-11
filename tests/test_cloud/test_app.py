"""Tests for FastAPI application factory and health check.

Validates that the app factory produces a working FastAPI instance
with health and OpenAPI endpoints available.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAppFactory:
    """App factory and core endpoint tests."""

    async def test_create_app_returns_fastapi(self, test_app):
        """Verify create_app returns a FastAPI instance."""
        from fastapi import FastAPI

        assert isinstance(test_app, FastAPI)

    async def test_health_endpoint(self, client: AsyncClient):
        """GET /health returns 200 with status ok."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_openapi_schema(self, client: AsyncClient):
        """GET /openapi.json returns 200 with a valid schema."""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "paths" in schema
        assert "/health" in schema["paths"]
