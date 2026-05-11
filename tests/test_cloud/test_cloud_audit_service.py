"""Tests for CloudAuditService -- signed, hash-chained audit entries."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from sporedb.cloud.db.models import AuditIndex, Tenant
from sporedb.cloud.services.cloud_audit_service import CloudAuditService


@pytest_asyncio.fixture
async def audit_service(test_db_session, ed25519_keypair, test_tenant_id):
    """Create a CloudAuditService and seed a tenant row."""
    private_key, _ = ed25519_keypair

    # Seed tenant so FK constraint is satisfied
    tenant = Tenant(
        id=test_tenant_id,
        name="Test Org",
        slug="test-org",
    )
    test_db_session.add(tenant)
    await test_db_session.flush()

    return CloudAuditService(session=test_db_session, private_key=private_key)


@pytest.mark.asyncio
async def test_append_creates_signed_entry(audit_service, test_tenant_id, test_user_id):
    """Append one entry -- verify signature and record_hash are populated."""
    row = await audit_service.append(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        action="create",
        entity_type="batch",
        entity_id="batch-001",
        new_value_hash="abc123",
    )

    assert isinstance(row, AuditIndex)
    assert row.signature is not None and len(row.signature) > 0
    assert row.record_hash is not None and len(row.record_hash) > 0
    assert row.previous_entry_hash == ""
    assert row.public_key_pem is not None and "PUBLIC KEY" in row.public_key_pem


@pytest.mark.asyncio
async def test_append_builds_hash_chain(audit_service, test_tenant_id, test_user_id):
    """Two sequential appends -- second entry chains to the first."""
    row1 = await audit_service.append(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        action="create",
        entity_type="batch",
        entity_id="batch-001",
        new_value_hash="hash1",
    )
    row2 = await audit_service.append(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        action="update",
        entity_type="batch",
        entity_id="batch-001",
        new_value_hash="hash2",
        old_value_hash="hash1",
    )

    assert row2.previous_entry_hash == row1.record_hash
    assert row2.previous_entry_hash != ""


@pytest.mark.asyncio
async def test_verify_chain_valid(audit_service, test_tenant_id, test_user_id):
    """Append 3 entries, verify_chain should report all valid."""
    for i in range(3):
        await audit_service.append(
            tenant_id=test_tenant_id,
            user_id=test_user_id,
            action="create",
            entity_type="batch",
            entity_id=f"batch-{i:03d}",
            new_value_hash=f"hash-{i}",
        )

    results = await audit_service.verify_chain(test_tenant_id)
    assert len(results) == 3
    assert all(valid for _, valid in results)


@pytest.mark.asyncio
async def test_verify_chain_detects_tampering(
    audit_service, test_tenant_id, test_user_id, test_db_session
):
    """Tamper with first entry's record_hash -- second entry should fail."""
    row1 = await audit_service.append(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        action="create",
        entity_type="batch",
        entity_id="batch-001",
        new_value_hash="hash1",
    )
    await audit_service.append(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        action="update",
        entity_type="batch",
        entity_id="batch-001",
        new_value_hash="hash2",
        old_value_hash="hash1",
    )

    # Tamper: change first entry's record_hash
    row1.record_hash = "tampered_hash_value"
    await test_db_session.flush()

    results = await audit_service.verify_chain(test_tenant_id)
    assert len(results) == 2
    # First entry should still be valid (its own hash doesn't depend on predecessor)
    assert results[0][1] is True
    # Second entry should fail -- its previous_entry_hash no longer matches
    # the (tampered) record_hash of the first entry
    assert results[1][1] is False


@pytest.mark.asyncio
async def test_append_acquires_advisory_lock(
    test_db_session, ed25519_keypair, test_tenant_id, test_user_id
):
    """Verify that the append method's source code includes advisory lock (CR-05).

    Also verify that the service always reads from DB (no cache) by
    checking the hash chain is correct after sequential appends using
    separate CloudAuditService instances (simulating different requests).
    """
    import inspect

    # 1. Verify source code contains advisory lock
    source = inspect.getsource(CloudAuditService.append)
    assert "advisory_lock" in source, (
        "CloudAuditService.append must acquire advisory lock"
    )

    # 2. Verify no in-memory cache is used
    assert "_last_hash_cache" not in source, (
        "CloudAuditService.append must not use in-memory hash cache"
    )

    # 3. Verify correctness: two separate service instances (simulating
    #    separate requests) produce a valid hash chain because they both
    #    read from DB instead of relying on an in-memory cache.
    private_key, _ = ed25519_keypair

    tenant = Tenant(id=test_tenant_id, name="Test Org", slug="test-org")
    test_db_session.add(tenant)
    await test_db_session.flush()

    # Patch out the advisory lock call for SQLite compatibility
    from sqlalchemy import TextClause

    original_execute = test_db_session.execute.__func__

    async def execute_skip_lock(self, *args, **kw):
        stmt = args[0] if args else None
        if isinstance(stmt, TextClause) and "pg_advisory_xact_lock" in stmt.text:
            return None
        return await original_execute(self, *args, **kw)

    with patch.object(type(test_db_session), "execute", execute_skip_lock):
        svc1 = CloudAuditService(session=test_db_session, private_key=private_key)
        row1 = await svc1.append(
            tenant_id=test_tenant_id,
            user_id=test_user_id,
            action="create",
            entity_type="batch",
            entity_id="batch-001",
            new_value_hash="hash1",
        )

        # Second service instance -- simulates a different request
        svc2 = CloudAuditService(session=test_db_session, private_key=private_key)
        row2 = await svc2.append(
            tenant_id=test_tenant_id,
            user_id=test_user_id,
            action="update",
            entity_type="batch",
            entity_id="batch-001",
            new_value_hash="hash2",
            old_value_hash="hash1",
        )

    # Without the cache, svc2 must have read the DB to find row1's hash
    assert row2.previous_entry_hash == row1.record_hash
    assert row2.previous_entry_hash != ""


@pytest.mark.asyncio
async def test_no_in_memory_hash_cache(ed25519_keypair):
    """Verify that CloudAuditService no longer uses an in-memory hash cache."""
    private_key, _ = ed25519_keypair
    mock_session = AsyncMock()
    service = CloudAuditService(session=mock_session, private_key=private_key)
    assert not hasattr(service, "_last_hash_cache"), (
        "CloudAuditService should not have _last_hash_cache attribute"
    )
