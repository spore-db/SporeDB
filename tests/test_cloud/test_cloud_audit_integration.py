"""Integration tests for cloud audit wiring.

Verifies that mutations produce signed hash-chained entries.

Tests the end-to-end flow: BatchService mutation -> CloudAuditService audit entry
creation -> verify_chain confirmation.  Uses an in-memory SQLite async database
with shared sessions to simulate the route-level integration without requiring
the full FastAPI app stack.
"""

from __future__ import annotations

import hashlib

import pytest
import pytest_asyncio

from sporedb.cloud.db.models import Tenant
from sporedb.cloud.services.batch_service import BatchService
from sporedb.cloud.services.cloud_audit_service import CloudAuditService


@pytest_asyncio.fixture
async def services(test_db_session, ed25519_keypair, test_tenant_id):
    """Create BatchService and CloudAuditService with a shared session.

    Seeds a tenant row for FK constraints.
    """
    private_key, _ = ed25519_keypair

    tenant = Tenant(
        id=test_tenant_id,
        name="Integration Test Org",
        slug="int-test-org",
    )
    test_db_session.add(tenant)
    await test_db_session.flush()

    batch_svc = BatchService(test_db_session)
    audit_svc = CloudAuditService(session=test_db_session, private_key=private_key)
    return batch_svc, audit_svc


@pytest.mark.asyncio
async def test_create_batch_writes_audit_entry(services, test_tenant_id, test_user_id):
    """Creating a batch and appending an audit entry produces a verifiable record."""
    batch_svc, audit_svc = services

    # Simulate what the route does: create batch, then audit
    batch = await batch_svc.create_batch(
        tenant_id=test_tenant_id,
        name="Integration Batch",
        lifecycle="planned",
    )
    new_hash = hashlib.sha256(
        f"{batch.id}:{batch.name}:{batch.lifecycle}".encode()
    ).hexdigest()
    row = await audit_svc.append(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        action="create",
        entity_type="batch",
        entity_id=batch.id,
        new_value_hash=new_hash,
    )

    assert row.action == "create"
    assert row.entity_type == "batch"
    assert row.entity_id == batch.id
    assert row.record_hash is not None and len(row.record_hash) > 0
    assert row.previous_entry_hash == ""  # First entry has empty prev hash

    # Verify chain
    results = await audit_svc.verify_chain(test_tenant_id)
    assert len(results) == 1
    assert results[0][1] is True


@pytest.mark.asyncio
async def test_multiple_mutations_form_hash_chain(
    services, test_tenant_id, test_user_id
):
    """Create, update, delete mutations form a valid 3-entry hash chain."""
    batch_svc, audit_svc = services

    # 1. Create batch
    batch = await batch_svc.create_batch(
        tenant_id=test_tenant_id,
        name="Chain Test Batch",
        lifecycle="planned",
    )
    create_hash = hashlib.sha256(
        f"{batch.id}:{batch.name}:{batch.lifecycle}".encode()
    ).hexdigest()
    entry1 = await audit_svc.append(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        action="create",
        entity_type="batch",
        entity_id=batch.id,
        new_value_hash=create_hash,
    )

    # 2. Update batch (simulate)
    update_hash = hashlib.sha256(f"{batch.id}:{batch.name}:active".encode()).hexdigest()
    entry2 = await audit_svc.append(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        action="update",
        entity_type="batch",
        entity_id=batch.id,
        new_value_hash=update_hash,
    )

    # 3. Delete batch (simulate)
    delete_hash = hashlib.sha256(batch.id.encode()).hexdigest()
    entry3 = await audit_svc.append(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        action="delete",
        entity_type="batch",
        entity_id=batch.id,
        new_value_hash=delete_hash,
    )

    # Verify chain linkage
    assert entry2.previous_entry_hash == entry1.record_hash
    assert entry3.previous_entry_hash == entry2.record_hash

    # Verify via verify_chain
    results = await audit_svc.verify_chain(test_tenant_id)
    assert len(results) == 3
    assert all(valid for _, valid in results), f"Chain verification failed: {results}"


@pytest.mark.asyncio
async def test_audit_api_returns_crypto_fields(services, test_tenant_id, test_user_id):
    """Audit entries contain all required crypto fields for API responses."""
    batch_svc, audit_svc = services

    batch = await batch_svc.create_batch(
        tenant_id=test_tenant_id,
        name="Crypto Fields Batch",
        lifecycle="active",
    )
    new_hash = hashlib.sha256(
        f"{batch.id}:{batch.name}:{batch.lifecycle}".encode()
    ).hexdigest()
    row = await audit_svc.append(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        action="create",
        entity_type="batch",
        entity_id=batch.id,
        new_value_hash=new_hash,
    )

    # Fields that the audit API response model expects
    assert row.record_hash is not None and len(row.record_hash) == 64  # SHA-256 hex
    assert row.previous_entry_hash is not None  # "" for first entry
    assert row.new_value_hash == new_hash
    assert row.signature is not None and len(row.signature) > 0  # has_signature=True
    assert row.public_key_pem is not None and "PUBLIC KEY" in row.public_key_pem

    # Verify chain confirms verified=True
    results = await audit_svc.verify_chain(test_tenant_id)
    assert len(results) == 1
    entry_id, verified = results[0]
    assert entry_id == row.id
    assert verified is True
