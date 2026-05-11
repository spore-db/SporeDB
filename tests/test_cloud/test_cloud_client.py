"""Integration tests for CloudClient via the FastAPI test app.

Tests the full stack: HTTP client -> FastAPI routes -> BatchService -> DB.
Uses the ``test_app`` and ``client`` fixtures from conftest.py with
httpx.AsyncClient connected via ASGI transport.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from sporedb.cloud.auth.jwt import create_access_token


@pytest.mark.asyncio
class TestCloudClient:
    """End-to-end API tests exercising the batch CRUD contract."""

    async def test_create_and_list_batches(self, client: AsyncClient, auth_headers):
        """Create batches via API and list them back."""
        # Create two batches
        resp1 = await client.post(
            "/api/v1/batches/",
            json={"name": "Cloud Batch 1", "lifecycle": "planned"},
            headers=auth_headers,
        )
        assert resp1.status_code == 201
        data1 = resp1.json()
        assert data1["name"] == "Cloud Batch 1"

        resp2 = await client.post(
            "/api/v1/batches/",
            json={"name": "Cloud Batch 2", "lifecycle": "inoculated"},
            headers=auth_headers,
        )
        assert resp2.status_code == 201

        # List batches
        list_resp = await client.get("/api/v1/batches/", headers=auth_headers)
        assert list_resp.status_code == 200
        batches = list_resp.json()
        names = {b["name"] for b in batches}
        assert "Cloud Batch 1" in names
        assert "Cloud Batch 2" in names

    async def test_get_batch_by_id(self, client: AsyncClient, auth_headers):
        """Create a batch and retrieve it by ID."""
        create_resp = await client.post(
            "/api/v1/batches/",
            json={"name": "Lookup Test"},
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        batch_id = create_resp.json()["id"]

        get_resp = await client.get(f"/api/v1/batches/{batch_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Lookup Test"
        assert get_resp.json()["id"] == batch_id

    async def test_delete_batch(
        self, client: AsyncClient, ed25519_keypair, test_tenant_id
    ):
        """Create, delete (as admin), and verify batch is gone."""
        private_key, _ = ed25519_keypair
        admin_token = create_access_token(
            tenant_id=test_tenant_id,
            user_id="00000000-0000-0000-0000-000000000099",
            email="admin@example.com",
            role="admin",
            private_key=private_key,
        )
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Create
        create_resp = await client.post(
            "/api/v1/batches/",
            json={"name": "Delete Me"},
            headers=admin_headers,
        )
        assert create_resp.status_code == 201
        batch_id = create_resp.json()["id"]

        # Delete
        del_resp = await client.delete(
            f"/api/v1/batches/{batch_id}", headers=admin_headers
        )
        assert del_resp.status_code == 200

        # Verify gone
        get_resp = await client.get(
            f"/api/v1/batches/{batch_id}", headers=admin_headers
        )
        assert get_resp.status_code == 404

    async def test_unauthenticated_rejected(self, client: AsyncClient):
        """Requests without auth token are rejected."""
        resp = await client.get("/api/v1/batches/")
        assert resp.status_code in (401, 403)

    async def test_create_batch_with_metadata(self, client: AsyncClient, auth_headers):
        """Batch metadata is stored and returned correctly."""
        resp = await client.post(
            "/api/v1/batches/",
            json={
                "name": "Metadata Test",
                "metadata": {"strain": "CHO-K1", "scale_liters": 50.0},
                "tags": ["pilot", "gmp"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["metadata"]["strain"] == "CHO-K1"
        assert data["tags"] == ["pilot", "gmp"]

    async def test_get_nonexistent_batch_returns_404(
        self, client: AsyncClient, auth_headers
    ):
        """GET with a random UUID returns 404."""
        fake_id = "00000000-0000-0000-0000-999999999999"
        resp = await client.get(f"/api/v1/batches/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404
