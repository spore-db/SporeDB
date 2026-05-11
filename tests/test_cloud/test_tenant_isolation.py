"""Tenant isolation integration tests -- proves PLAT-04 compliance.

Critical test file that verifies multi-tenant data isolation:
- Tenant A's data is completely invisible to Tenant B
- Cross-tenant CRUD operations return 404 (not 403, to prevent ID enumeration -- T-8-25)
- Tenant identity is always derived from JWT, never from request body (T-8-26)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from sporedb.cloud.auth.jwt import create_access_token

# ---------------------------------------------------------------------------
# Fixtures for two-tenant scenario
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_a_id() -> str:
    return "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture
def tenant_b_id() -> str:
    return "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.fixture
def tenant_a_headers(ed25519_keypair, tenant_a_id) -> dict[str, str]:
    """JWT auth headers for Tenant A (editor role)."""
    private_key, _ = ed25519_keypair
    token = create_access_token(
        tenant_id=tenant_a_id,
        user_id="00000000-0000-0000-0000-aaaaaaaaaaaa",
        email="user_a@example.com",
        role="editor",
        private_key=private_key,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_b_headers(ed25519_keypair, tenant_b_id) -> dict[str, str]:
    """JWT auth headers for Tenant B (editor role)."""
    private_key, _ = ed25519_keypair
    token = create_access_token(
        tenant_id=tenant_b_id,
        user_id="00000000-0000-0000-0000-bbbbbbbbbbbb",
        email="user_b@example.com",
        role="editor",
        private_key=private_key,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_a_admin_headers(ed25519_keypair, tenant_a_id) -> dict[str, str]:
    """JWT auth headers for Tenant A admin (needed for delete ops)."""
    private_key, _ = ed25519_keypair
    token = create_access_token(
        tenant_id=tenant_a_id,
        user_id="00000000-0000-0000-0000-aaaaaaaaaa99",
        email="admin_a@example.com",
        role="admin",
        private_key=private_key,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_b_admin_headers(ed25519_keypair, tenant_b_id) -> dict[str, str]:
    """JWT auth headers for Tenant B admin (needed for delete ops)."""
    private_key, _ = ed25519_keypair
    token = create_access_token(
        tenant_id=tenant_b_id,
        user_id="00000000-0000-0000-0000-bbbbbbbbbb99",
        email="admin_b@example.com",
        role="admin",
        private_key=private_key,
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tenant data isolation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTenantDataIsolation:
    """Prove that tenant data is completely isolated across CRUD operations."""

    async def test_tenant_a_batches_invisible_to_tenant_b(
        self,
        client: AsyncClient,
        tenant_a_headers,
        tenant_b_headers,
    ):
        """Batches created by Tenant A are not visible to Tenant B."""
        # Tenant A creates 3 batches
        for i in range(3):
            resp = await client.post(
                "/api/v1/batches/",
                json={"name": f"Tenant A Batch {i}"},
                headers=tenant_a_headers,
            )
            assert resp.status_code == 201

        # Tenant B lists batches -- should see 0
        list_resp = await client.get("/api/v1/batches/", headers=tenant_b_headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 0

        # Tenant A lists batches -- should see 3
        list_resp_a = await client.get("/api/v1/batches/", headers=tenant_a_headers)
        assert list_resp_a.status_code == 200
        assert len(list_resp_a.json()) == 3

    async def test_tenant_b_cannot_get_tenant_a_batch_by_id(
        self,
        client: AsyncClient,
        tenant_a_headers,
        tenant_b_headers,
    ):
        """Tenant B gets 404 (not 403) when accessing Tenant A's batch by ID."""
        # Tenant A creates a batch
        create_resp = await client.post(
            "/api/v1/batches/",
            json={"name": "Secret Batch"},
            headers=tenant_a_headers,
        )
        assert create_resp.status_code == 201
        batch_id = create_resp.json()["id"]

        # Tenant B tries to get it -- must get 404 (T-8-25: prevents ID enumeration)
        get_resp = await client.get(
            f"/api/v1/batches/{batch_id}", headers=tenant_b_headers
        )
        assert get_resp.status_code == 404

    async def test_tenant_b_cannot_delete_tenant_a_batch(
        self,
        client: AsyncClient,
        tenant_a_headers,
        tenant_a_admin_headers,
        tenant_b_admin_headers,
    ):
        """Tenant B cannot delete Tenant A's batch; batch remains intact."""
        # Tenant A creates a batch
        create_resp = await client.post(
            "/api/v1/batches/",
            json={"name": "Protected Batch"},
            headers=tenant_a_headers,
        )
        assert create_resp.status_code == 201
        batch_id = create_resp.json()["id"]

        # Tenant B (admin) tries to delete -- must get 404
        del_resp = await client.delete(
            f"/api/v1/batches/{batch_id}", headers=tenant_b_admin_headers
        )
        assert del_resp.status_code == 404

        # Verify batch still exists for Tenant A
        get_resp = await client.get(
            f"/api/v1/batches/{batch_id}", headers=tenant_a_headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Protected Batch"

    async def test_tenant_b_cannot_update_tenant_a_batch(
        self,
        client: AsyncClient,
        tenant_a_headers,
        tenant_b_headers,
    ):
        """Tenant B cannot modify Tenant A's batch; original data preserved."""
        # Tenant A creates a batch
        create_resp = await client.post(
            "/api/v1/batches/",
            json={"name": "Original"},
            headers=tenant_a_headers,
        )
        assert create_resp.status_code == 201
        batch_id = create_resp.json()["id"]

        # Tenant B tries to update -- must get 404
        put_resp = await client.put(
            f"/api/v1/batches/{batch_id}",
            json={"name": "Hacked"},
            headers=tenant_b_headers,
        )
        assert put_resp.status_code == 404

        # Verify Tenant A's batch is unchanged
        get_resp = await client.get(
            f"/api/v1/batches/{batch_id}", headers=tenant_a_headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Original"

    async def test_tenant_id_from_jwt_not_request_body(
        self,
        client: AsyncClient,
        tenant_a_headers,
        tenant_b_headers,
        tenant_a_id,
        tenant_b_id,
    ):
        """Tenant ID in request body is ignored; JWT tenant is used (T-8-26).

        Even if the request body includes a tenant_id field pointing to
        Tenant B, the batch is created under Tenant A (from JWT).
        """
        # Tenant A creates a batch with tenant_b_id in body
        resp = await client.post(
            "/api/v1/batches/",
            json={
                "name": "JWT Test Batch",
                "metadata": {"tenant_id": tenant_b_id},
            },
            headers=tenant_a_headers,
        )
        assert resp.status_code == 201
        batch_id = resp.json()["id"]

        # Batch should be visible to Tenant A
        get_a = await client.get(
            f"/api/v1/batches/{batch_id}", headers=tenant_a_headers
        )
        assert get_a.status_code == 200

        # Batch should NOT be visible to Tenant B
        get_b = await client.get(
            f"/api/v1/batches/{batch_id}", headers=tenant_b_headers
        )
        assert get_b.status_code == 404

    async def test_cross_tenant_batch_count_independence(
        self,
        client: AsyncClient,
        tenant_a_headers,
        tenant_b_headers,
    ):
        """Each tenant's batch count is independent of the other."""
        # Tenant A creates 2 batches
        for i in range(2):
            await client.post(
                "/api/v1/batches/",
                json={"name": f"A-{i}"},
                headers=tenant_a_headers,
            )

        # Tenant B creates 1 batch
        await client.post(
            "/api/v1/batches/",
            json={"name": "B-0"},
            headers=tenant_b_headers,
        )

        # Verify counts
        a_list = await client.get("/api/v1/batches/", headers=tenant_a_headers)
        b_list = await client.get("/api/v1/batches/", headers=tenant_b_headers)
        assert len(a_list.json()) == 2
        assert len(b_list.json()) == 1
