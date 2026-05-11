"""Tenant-scoped S3-compatible object storage for SporeDB cloud tier.

Mirrors the Hive-style path conventions from
:class:`sporedb.storage.parquet_layout.ParquetLayout` but scoped under
``tenants/{tenant_id}/`` prefixes for multi-tenant isolation.

All async methods use :func:`asyncio.to_thread` because boto3 is
synchronous (RESEARCH.md Pitfall 4).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any
from uuid import UUID

# Pre-compiled pattern for UUID validation
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _validate_id(value: str, name: str) -> None:
    """Validate that a value looks like a UUID and has no path traversal."""
    if ".." in value or "/" in value:
        raise ValueError(f"{name} contains path traversal characters: {value!r}")
    if not _UUID_RE.match(value):
        raise ValueError(f"{name} is not a valid UUID: {value!r}")


class S3Storage:
    """Tenant-scoped S3-compatible object storage.

    Constructs S3 keys under ``tenants/{tenant_id}/...`` to enforce
    multi-tenant data isolation at the storage layer.

    Parameters
    ----------
    s3_client:
        A boto3 S3 client (or ``None`` for path-construction-only usage).
    bucket:
        The S3 bucket name.
    """

    def __init__(self, s3_client: Any, bucket: str) -> None:
        self._client = s3_client
        self._bucket = bucket

    # ------------------------------------------------------------------
    # Key construction
    # ------------------------------------------------------------------

    def _key(self, tenant_id: str, *parts: str) -> str:
        """Build a tenant-scoped S3 key."""
        _validate_id(tenant_id, "tenant_id")
        for part in parts:
            if ".." in part:
                raise ValueError(
                    f"Key part contains path traversal characters: {part!r}"
                )
        return f"tenants/{tenant_id}/{'/'.join(parts)}"

    def telemetry_key(self, tenant_id: str, batch_id: UUID) -> str:
        """S3 key for telemetry Parquet, mirroring ParquetLayout."""
        _validate_id(str(batch_id), "batch_id")
        return self._key(tenant_id, "telemetry", f"batch_id={batch_id}", "data.parquet")

    def assay_key(self, tenant_id: str, batch_id: UUID) -> str:
        """S3 key for assay Parquet, mirroring ParquetLayout."""
        _validate_id(str(batch_id), "batch_id")
        return self._key(tenant_id, "assay", f"batch_id={batch_id}", "data.parquet")

    def audit_trail_key(self, tenant_id: str) -> str:
        """S3 key for audit trail Parquet."""
        return self._key(tenant_id, "audit", "trail.parquet")

    def phases_key(self, tenant_id: str, batch_id: UUID) -> str:
        """S3 key for phase annotations Parquet."""
        _validate_id(str(batch_id), "batch_id")
        return self._key(tenant_id, "phases", f"batch_id={batch_id}", "data.parquet")

    def s3_url(self, tenant_id: str, *parts: str) -> str:
        """Full ``s3://`` URL for DuckDB httpfs queries."""
        return f"s3://{self._bucket}/{self._key(tenant_id, *parts)}"

    # ------------------------------------------------------------------
    # CRUD operations (async via asyncio.to_thread for boto3)
    # ------------------------------------------------------------------

    async def put_object(self, tenant_id: str, key_suffix: str, data: bytes) -> None:
        """Put an object under the tenant prefix."""
        key = self._key(tenant_id, key_suffix)
        await asyncio.to_thread(
            self._client.put_object, Bucket=self._bucket, Key=key, Body=data
        )

    async def get_object(self, tenant_id: str, key_suffix: str) -> bytes:
        """Get an object from the tenant prefix."""
        key = self._key(tenant_id, key_suffix)
        response = await asyncio.to_thread(
            self._client.get_object, Bucket=self._bucket, Key=key
        )
        body = response["Body"]
        return await asyncio.to_thread(body.read)

    async def delete_object(self, tenant_id: str, key_suffix: str) -> None:
        """Delete an object from the tenant prefix."""
        key = self._key(tenant_id, key_suffix)
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self._bucket, Key=key
        )

    async def list_objects(self, tenant_id: str, prefix: str = "") -> list[str]:
        """List object keys under the tenant prefix."""
        full_prefix = (
            self._key(tenant_id, prefix) if prefix else self._key(tenant_id, "")
        )
        response = await asyncio.to_thread(
            self._client.list_objects_v2,
            Bucket=self._bucket,
            Prefix=full_prefix,
        )
        contents = response.get("Contents", [])
        return [obj["Key"] for obj in contents]

    async def put_parquet(
        self,
        tenant_id: str,
        batch_id: UUID,
        data_type: str,
        data: bytes,
    ) -> str:
        """Convenience: put Parquet data using path helpers.

        Parameters
        ----------
        data_type:
            One of ``"telemetry"``, ``"assay"``, or ``"audit"``.

        Returns
        -------
        str
            The full S3 key where the data was stored.
        """
        if data_type == "telemetry":
            key = self.telemetry_key(tenant_id, batch_id)
        elif data_type == "assay":
            key = self.assay_key(tenant_id, batch_id)
        elif data_type == "audit":
            key = self.audit_trail_key(tenant_id)
        elif data_type == "phases":
            key = self.phases_key(tenant_id, batch_id)
        else:
            raise ValueError(f"Unknown data_type: {data_type!r}")

        await asyncio.to_thread(
            self._client.put_object, Bucket=self._bucket, Key=key, Body=data
        )
        return key

    async def get_parquet(
        self,
        tenant_id: str,
        batch_id: UUID,
        data_type: str,
    ) -> bytes:
        """Convenience: get Parquet data using path helpers."""
        if data_type == "telemetry":
            key = self.telemetry_key(tenant_id, batch_id)
        elif data_type == "assay":
            key = self.assay_key(tenant_id, batch_id)
        elif data_type == "audit":
            key = self.audit_trail_key(tenant_id)
        elif data_type == "phases":
            key = self.phases_key(tenant_id, batch_id)
        else:
            raise ValueError(f"Unknown data_type: {data_type!r}")

        response = await asyncio.to_thread(
            self._client.get_object, Bucket=self._bucket, Key=key
        )
        body = response["Body"]
        return await asyncio.to_thread(body.read)
