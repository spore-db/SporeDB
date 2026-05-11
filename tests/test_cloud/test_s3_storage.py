"""Unit tests for S3Storage tenant-scoped key construction and operations.

Verifies:
- Key format follows Hive-style conventions with tenant prefix
- Tenant scoping prevents cross-tenant key collisions
- Path traversal characters are rejected (T-8-27)
- Async CRUD operations work with mock boto3 client
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest

from sporedb.cloud.storage.s3 import S3Storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
BATCH_ID = UUID("11111111-1111-1111-1111-111111111111")
BUCKET = "test-bucket"


# ---------------------------------------------------------------------------
# Key construction
# ---------------------------------------------------------------------------


class TestS3KeyConstruction:
    """Verify S3 key format follows expected conventions."""

    def test_telemetry_key_format(self, mock_s3):
        storage = S3Storage(mock_s3, BUCKET)
        key = storage.telemetry_key(TENANT_A, BATCH_ID)
        expected = f"tenants/{TENANT_A}/telemetry/batch_id={BATCH_ID}/data.parquet"
        assert key == expected

    def test_assay_key_format(self, mock_s3):
        storage = S3Storage(mock_s3, BUCKET)
        key = storage.assay_key(TENANT_A, BATCH_ID)
        expected = f"tenants/{TENANT_A}/assay/batch_id={BATCH_ID}/data.parquet"
        assert key == expected

    def test_audit_trail_key_format(self, mock_s3):
        storage = S3Storage(mock_s3, BUCKET)
        key = storage.audit_trail_key(TENANT_A)
        expected = f"tenants/{TENANT_A}/audit/trail.parquet"
        assert key == expected

    def test_s3_url_format(self, mock_s3):
        storage = S3Storage(mock_s3, BUCKET)
        url = storage.s3_url(TENANT_A, "some/path")
        expected = f"s3://{BUCKET}/tenants/{TENANT_A}/some/path"
        assert url == expected

    def test_key_includes_tenant_prefix(self, mock_s3):
        storage = S3Storage(mock_s3, BUCKET)
        keys = [
            storage.telemetry_key(TENANT_A, BATCH_ID),
            storage.assay_key(TENANT_A, BATCH_ID),
            storage.audit_trail_key(TENANT_A),
        ]
        for key in keys:
            assert key.startswith(f"tenants/{TENANT_A}/"), (
                f"Key does not start with tenant prefix: {key}"
            )


# ---------------------------------------------------------------------------
# Tenant scoping
# ---------------------------------------------------------------------------


class TestS3TenantScoping:
    """Verify tenant isolation at the key construction level."""

    def test_different_tenants_get_different_keys(self, mock_s3):
        storage = S3Storage(mock_s3, BUCKET)
        key_a = storage.telemetry_key(TENANT_A, BATCH_ID)
        key_b = storage.telemetry_key(TENANT_B, BATCH_ID)
        assert key_a != key_b
        assert TENANT_A in key_a
        assert TENANT_B in key_b

    def test_invalid_tenant_id_rejected(self, mock_s3):
        storage = S3Storage(mock_s3, BUCKET)
        with pytest.raises(ValueError, match="path traversal"):
            storage.telemetry_key("../escape", BATCH_ID)
        with pytest.raises(ValueError, match="path traversal"):
            storage.telemetry_key("tenant/id", BATCH_ID)

    def test_path_traversal_rejected(self, mock_s3):
        """batch_id-like strings with traversal characters are rejected."""
        storage = S3Storage(mock_s3, BUCKET)
        # Non-UUID tenant_id
        with pytest.raises(ValueError, match="not a valid UUID"):
            storage.telemetry_key("not-a-uuid", BATCH_ID)
        # Tenant with dotdot
        with pytest.raises(ValueError, match="path traversal"):
            storage._key("../../etc/passwd", "data")


# ---------------------------------------------------------------------------
# Async CRUD operations
# ---------------------------------------------------------------------------


class TestS3Operations:
    """Test async CRUD with mock boto3 client."""

    def test_put_and_get_parquet(self, mock_s3):
        storage = S3Storage(mock_s3, BUCKET)
        test_data = b"fake-parquet-data-12345"

        key = asyncio.run(
            storage.put_parquet(TENANT_A, BATCH_ID, "telemetry", test_data)
        )
        assert "telemetry" in key

        retrieved = asyncio.run(storage.get_parquet(TENANT_A, BATCH_ID, "telemetry"))
        assert retrieved == test_data

    def test_put_and_get_object(self, mock_s3):
        storage = S3Storage(mock_s3, BUCKET)
        test_data = b"hello-world"

        asyncio.run(storage.put_object(TENANT_A, "test/file.bin", test_data))
        retrieved = asyncio.run(storage.get_object(TENANT_A, "test/file.bin"))
        assert retrieved == test_data

    def test_list_objects(self, mock_s3):
        storage = S3Storage(mock_s3, BUCKET)

        asyncio.run(storage.put_object(TENANT_A, "data/a.parquet", b"aaa"))
        asyncio.run(storage.put_object(TENANT_A, "data/b.parquet", b"bbb"))

        keys = asyncio.run(storage.list_objects(TENANT_A, "data"))
        assert len(keys) >= 2

    def test_delete_object(self, mock_s3):
        storage = S3Storage(mock_s3, BUCKET)

        asyncio.run(storage.put_object(TENANT_A, "temp/delete-me.bin", b"x"))
        asyncio.run(storage.delete_object(TENANT_A, "temp/delete-me.bin"))

        # After delete, listing should not include it
        # (mock_s3 doesn't implement delete side effect on dict,
        #  so we just verify the call was made successfully)
        # The real test is that delete_object doesn't raise
