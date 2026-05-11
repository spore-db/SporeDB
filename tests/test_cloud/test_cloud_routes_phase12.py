"""Integration tests for Phase 12-02 cloud routes.

Covers: export, metrics, BOCPD, phase persistence.

Uses the shared test fixtures from conftest.py (mock S3, auth, test app)
with additional route registration for data and analytics routers.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from uuid import UUID

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.ipc
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sporedb.cloud.config import CloudSettings
from sporedb.cloud.storage.s3 import S3Storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_BATCH_ID = "00000000-0000-0000-0000-000000000b10"


def _make_telemetry_parquet(n_rows: int = 100) -> bytes:
    """Create synthetic telemetry Parquet bytes with lag + exponential growth pattern.

    Returns Parquet bytes with columns: ts, variable, value.
    """
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    timestamps = [base_time + pd.Timedelta(hours=i) for i in range(n_rows)]

    # Lag phase (first 30 rows): flat OD
    # Exponential phase (30-70): growing OD
    # Stationary (70-100): flat high OD
    values = []
    for i in range(n_rows):
        if i < 30:
            values.append(0.1 + np.random.normal(0, 0.01))
        elif i < 70:
            values.append(0.1 * np.exp(0.05 * (i - 30)) + np.random.normal(0, 0.02))
        else:
            values.append(0.1 * np.exp(0.05 * 40) + np.random.normal(0, 0.1))

    df = pd.DataFrame(
        {
            "ts": timestamps * 1,  # Just OD600 signal
            "variable": ["OD600"] * n_rows,
            "value": values,
        }
    )

    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def phase12_app(ed25519_keypair, test_db_engine, mock_s3):
    """FastAPI test app with data + analytics routers registered."""
    from sporedb.cloud.routes import analytics, data

    private_key, public_key = ed25519_keypair

    app = FastAPI(title="SporeDB Phase12 Test", version="0.1.0-test")

    class _SessionFactory:
        def __init__(self, engine):
            self._factory = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def get_session(self):
            async with self._factory() as session:
                yield session
                await session.commit()

        async def dispose(self):
            pass

    app.state.db_session = _SessionFactory(test_db_engine)
    app.state.s3 = mock_s3
    app.state.s3_storage = S3Storage(mock_s3, "test-bucket")
    app.state.jwt_private_key = private_key
    app.state.jwt_public_key = public_key
    app.state.settings = CloudSettings(
        database_url="sqlite+aiosqlite:///test.db",
        s3_access_key="test",
        s3_secret_key="test",
        jwt_secret_key_path="unused",
        jwt_public_key_path="unused",
    )

    app.include_router(data.router, prefix="/api/v1/data", tags=["data"])
    app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])

    return app


@pytest_asyncio.fixture
async def phase12_client(phase12_app):
    """Async HTTP client for phase12 tests."""
    transport = ASGITransport(app=phase12_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def seeded_telemetry(phase12_app, test_tenant_id):
    """Seed telemetry data into mock S3 for the test batch."""
    s3_storage = phase12_app.state.s3_storage
    batch_uuid = UUID(TEST_BATCH_ID)
    parquet_bytes = _make_telemetry_parquet()

    # Store directly in mock S3 using the key convention
    key = s3_storage.telemetry_key(str(test_tenant_id), batch_uuid)
    phase12_app.state.s3.put_object(Bucket="test-bucket", Key=key, Body=parquet_bytes)
    return parquet_bytes


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_csv(phase12_client, auth_headers, seeded_telemetry):
    """GET /data/export/{batch_id}?format=csv returns valid CSV."""
    resp = await phase12_client.get(
        f"/api/v1/data/export/{TEST_BATCH_ID}?format=csv",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert "text/csv" in resp.headers["content-type"]
    assert "Content-Disposition" in resp.headers

    # Parse CSV to verify structure
    csv_df = pd.read_csv(io.StringIO(resp.text))
    assert "ts" in csv_df.columns
    assert "variable" in csv_df.columns
    assert "value" in csv_df.columns
    assert len(csv_df) == 100


@pytest.mark.asyncio
async def test_export_arrow(phase12_client, auth_headers, seeded_telemetry):
    """GET /data/export/{batch_id}?format=arrow returns valid Arrow IPC."""
    resp = await phase12_client.get(
        f"/api/v1/data/export/{TEST_BATCH_ID}?format=arrow",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert "apache.arrow" in resp.headers["content-type"]

    # Read the Arrow IPC file
    reader = pa.ipc.open_file(io.BytesIO(resp.content))
    table = reader.read_all()
    assert table.num_rows == 100
    assert "ts" in table.column_names


@pytest.mark.asyncio
async def test_export_invalid_format(phase12_client, auth_headers, seeded_telemetry):
    """GET /data/export/{batch_id}?format=json returns 400."""
    resp = await phase12_client.get(
        f"/api/v1/data/export/{TEST_BATCH_ID}?format=json",
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Invalid format" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_metrics(phase12_client, auth_headers, seeded_telemetry):
    """POST /analytics/metrics returns metrics list."""
    resp = await phase12_client.post(
        "/api/v1/analytics/metrics",
        json={"batch_id": TEST_BATCH_ID},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "metrics" in data
    assert isinstance(data["metrics"], list)
    assert data["batch_id"] == TEST_BATCH_ID


@pytest.mark.asyncio
async def test_detect_phases_online(phase12_client, auth_headers, seeded_telemetry):
    """POST /analytics/detect-phases-online returns list (may be empty)."""
    resp = await phase12_client.post(
        "/api/v1/analytics/detect-phases-online",
        json={"batch_id": TEST_BATCH_ID},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_detect_phases_persists(
    phase12_client, auth_headers, seeded_telemetry, phase12_app, test_tenant_id
):
    """POST /analytics/detect-phases persists phase annotations to S3."""
    resp = await phase12_client.post(
        "/api/v1/analytics/detect-phases",
        json={"batch_id": TEST_BATCH_ID},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    annotations = resp.json()
    assert isinstance(annotations, list)

    # Verify phase data was persisted in mock S3
    if annotations:
        s3_storage = phase12_app.state.s3_storage
        batch_uuid = UUID(TEST_BATCH_ID)
        key = s3_storage.phases_key(str(test_tenant_id), batch_uuid)
        # Check it exists in mock S3 storage
        try:
            phase12_app.state.s3.get_object(Bucket="test-bucket", Key=key)
            phase_persisted = True
        except Exception:
            phase_persisted = False
        assert phase_persisted, "Phase annotations should be persisted to S3"
