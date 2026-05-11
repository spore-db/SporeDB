"""Integration tests for batch CRUD API with tenant isolation.

Tests cover create, list, get, delete operations through the HTTP API,
as well as unauthenticated access rejection and cross-tenant isolation.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sporedb.cloud.auth.jwt import create_access_token
from sporedb.cloud.services.batch_service import BatchService


@pytest.mark.asyncio
class TestBatchCRUD:
    """Batch CRUD operations through the API."""

    async def test_create_batch(self, client: AsyncClient, auth_headers):
        """POST /api/v1/batches creates a batch and returns it."""
        response = await client.post(
            "/api/v1/batches/",
            json={"name": "Fermentation Run 1", "lifecycle": "planned"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Fermentation Run 1"
        assert data["lifecycle"] == "planned"
        assert "id" in data
        assert "created_at" in data

    async def test_list_batches(self, client: AsyncClient, auth_headers):
        """GET /api/v1/batches returns all batches for the tenant."""
        # Create two batches
        await client.post(
            "/api/v1/batches/",
            json={"name": "Batch A"},
            headers=auth_headers,
        )
        await client.post(
            "/api/v1/batches/",
            json={"name": "Batch B"},
            headers=auth_headers,
        )

        response = await client.get("/api/v1/batches/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        names = {b["name"] for b in data}
        assert "Batch A" in names
        assert "Batch B" in names

    async def test_get_batch(self, client: AsyncClient, auth_headers):
        """GET /api/v1/batches/{id} returns the specific batch."""
        create_resp = await client.post(
            "/api/v1/batches/",
            json={"name": "Lookup Batch"},
            headers=auth_headers,
        )
        batch_id = create_resp.json()["id"]

        response = await client.get(f"/api/v1/batches/{batch_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "Lookup Batch"
        assert response.json()["id"] == batch_id

    async def test_get_batch_not_found(self, client: AsyncClient, auth_headers):
        """GET with a random UUID returns 404."""
        fake_id = "00000000-0000-0000-0000-999999999999"
        response = await client.get(f"/api/v1/batches/{fake_id}", headers=auth_headers)
        assert response.status_code == 404

    async def test_delete_batch(self, client: AsyncClient, auth_headers):
        """DELETE removes the batch; subsequent GET returns 404.

        Note: delete requires DELETE permission (admin role).
        """
        # Create with editor token
        create_resp = await client.post(
            "/api/v1/batches/",
            json={"name": "To Delete"},
            headers=auth_headers,
        )
        batch_id = create_resp.json()["id"]

        # Delete requires admin -- use admin token
        # For this test, the editor token lacks DELETE permission,
        # so we test that admin can delete.
        # The auth_headers fixture uses an editor role which has WRITE but not DELETE.
        # We need admin headers for delete.
        response = await client.delete(
            f"/api/v1/batches/{batch_id}", headers=auth_headers
        )
        # Editor should get 403 for delete (lacks DELETE permission)
        assert response.status_code == 403

    async def test_delete_batch_as_admin(
        self, client: AsyncClient, ed25519_keypair, test_tenant_id
    ):
        """Admin can delete a batch successfully."""
        private_key, _ = ed25519_keypair
        admin_token = create_access_token(
            tenant_id=test_tenant_id,
            user_id="00000000-0000-0000-0000-000000000099",
            email="admin@example.com",
            role="admin",
            private_key=private_key,
        )
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Create batch
        create_resp = await client.post(
            "/api/v1/batches/",
            json={"name": "Admin Delete Test"},
            headers=admin_headers,
        )
        assert create_resp.status_code == 201
        batch_id = create_resp.json()["id"]

        # Delete as admin
        del_resp = await client.delete(
            f"/api/v1/batches/{batch_id}", headers=admin_headers
        )
        assert del_resp.status_code == 200

        # Verify gone
        get_resp = await client.get(
            f"/api/v1/batches/{batch_id}", headers=admin_headers
        )
        assert get_resp.status_code == 404

    async def test_unauthenticated_request(self, client: AsyncClient):
        """GET /api/v1/batches without auth returns 401 or 403."""
        response = await client.get("/api/v1/batches/")
        assert response.status_code in (401, 403)


@pytest.mark.asyncio
class TestTenantIsolation:
    """Cross-tenant data isolation tests."""

    async def test_tenant_a_cannot_see_tenant_b_batches(
        self, client: AsyncClient, ed25519_keypair
    ):
        """Batches created by tenant A are invisible to tenant B."""
        private_key, _ = ed25519_keypair

        tenant_a_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        tenant_b_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        token_a = create_access_token(
            tenant_id=tenant_a_id,
            user_id="00000000-0000-0000-0000-aaaaaaaaaaaa",
            email="user_a@example.com",
            role="editor",
            private_key=private_key,
        )
        token_b = create_access_token(
            tenant_id=tenant_b_id,
            user_id="00000000-0000-0000-0000-bbbbbbbbbbbb",
            email="user_b@example.com",
            role="editor",
            private_key=private_key,
        )

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant A creates a batch
        create_resp = await client.post(
            "/api/v1/batches/",
            json={"name": "Tenant A Secret Batch"},
            headers=headers_a,
        )
        assert create_resp.status_code == 201
        batch_id = create_resp.json()["id"]

        # Tenant B lists batches -- should NOT see tenant A's batch
        list_resp = await client.get("/api/v1/batches/", headers=headers_b)
        assert list_resp.status_code == 200
        b_batches = list_resp.json()
        b_ids = {b["id"] for b in b_batches}
        assert batch_id not in b_ids

        # Tenant B tries to get tenant A's batch directly -- should get 404
        get_resp = await client.get(f"/api/v1/batches/{batch_id}", headers=headers_b)
        assert get_resp.status_code == 404


@pytest.mark.asyncio
class TestILIKEWildcardEscape:
    """HI-02: ILIKE search must escape wildcard metacharacters."""

    async def test_search_with_percent_does_not_wildcard(
        self, test_db_session: AsyncSession
    ):
        """Search term containing '%' is treated as a literal '%'."""
        tenant_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        svc = BatchService(test_db_session)

        # Create batches with distinct names
        await svc.create_batch(tenant_id, "Normal Batch")
        await svc.create_batch(tenant_id, "100% Yield Batch")

        # Search for literal "%" -- should only match the batch with "%"
        results = await svc.list_batches(tenant_id, search="%")
        names = [b.name for b in results]
        assert "100% Yield Batch" in names
        # "Normal Batch" must NOT match a literal "%" search
        assert "Normal Batch" not in names

    async def test_search_with_underscore_does_not_wildcard(
        self, test_db_session: AsyncSession
    ):
        """Search term containing '_' is treated as a literal '_'."""
        tenant_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        svc = BatchService(test_db_session)

        await svc.create_batch(tenant_id, "batch_alpha")
        await svc.create_batch(tenant_id, "batch2alpha")

        # Search for literal "_" -- should match "batch_alpha" but not "batch2alpha"
        results = await svc.list_batches(tenant_id, search="_")
        names = [b.name for b in results]
        assert "batch_alpha" in names
        assert "batch2alpha" not in names

    async def test_normal_search_still_works(self, test_db_session: AsyncSession):
        """Plain text search without metacharacters still works."""
        tenant_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        svc = BatchService(test_db_session)

        await svc.create_batch(tenant_id, "Fermentation Run 1")
        await svc.create_batch(tenant_id, "Scale-up Test")

        results = await svc.list_batches(tenant_id, search="Fermentation")
        names = [b.name for b in results]
        assert "Fermentation Run 1" in names
        assert "Scale-up Test" not in names
