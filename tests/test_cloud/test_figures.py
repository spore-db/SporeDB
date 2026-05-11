"""Integration tests for Plotly figure JSON endpoints.

Tests the /dash/api/batches/{id}/figure and /dash/api/compare/figure
endpoints including auth, error handling, and Plotly JSON structure.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from sporedb.cloud.auth.jwt import create_access_token
from sporedb.cloud.config import CloudSettings
from sporedb.cloud.routes.figures import router as figures_router
from sporedb.cloud.storage.s3 import S3Storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_TENANT_ID = "00000000-0000-0000-0000-000000000001"
TEST_USER_ID = "00000000-0000-0000-0000-000000000002"
TEST_BATCH_ID = "00000000-0000-0000-0000-000000000010"
TEST_BATCH_ID_2 = "00000000-0000-0000-0000-000000000011"


def _make_parquet_bytes(
    signals: list[str] | None = None,
    rows: int = 10,
) -> bytes:
    """Build a small Parquet file with timestamp + signal columns."""
    if signals is None:
        signals = ["OD600", "pH"]
    now = datetime.now(UTC)
    data = {"timestamp": [now + timedelta(minutes=i) for i in range(rows)]}
    for sig in signals:
        data[sig] = [float(i) * 0.1 for i in range(rows)]
    df = pd.DataFrame(data)
    table = pa.Table.from_pandas(df)
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures (self-contained -- parallel with Plan 01)
# ---------------------------------------------------------------------------


@pytest.fixture
def ed25519_keypair():
    private_key = Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


@pytest.fixture
def access_token(ed25519_keypair) -> str:
    private_key, _ = ed25519_keypair
    return create_access_token(
        tenant_id=TEST_TENANT_ID,
        user_id=TEST_USER_ID,
        email="editor@example.com",
        role="editor",
        private_key=private_key,
    )


@pytest.fixture
def mock_s3_client():
    """In-memory S3 mock pre-loaded with test parquet data."""
    storage: dict[str, bytes] = {}
    client = MagicMock()

    def put_object(Bucket: str, Key: str, Body: bytes, **kw):  # noqa: N803
        storage[Key] = Body

    def get_object(Bucket: str, Key: str, **kw):  # noqa: N803
        if Key not in storage:
            error = {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}
            exc = Exception("NoSuchKey")
            exc.response = error  # type: ignore[attr-defined]
            raise exc
        body = MagicMock()
        body.read.return_value = storage[Key]
        return {"Body": body}

    client.put_object.side_effect = put_object
    client.get_object.side_effect = get_object
    client._storage = storage
    return client


@pytest.fixture
def figures_app(ed25519_keypair, mock_s3_client) -> FastAPI:
    """Minimal FastAPI app with only the figures router."""
    private_key, public_key = ed25519_keypair

    app = FastAPI(title="Figures Test")
    app.state.jwt_private_key = private_key
    app.state.jwt_public_key = public_key
    app.state.s3_storage = S3Storage(mock_s3_client, "test-bucket")
    app.state.settings = CloudSettings(
        database_url="sqlite+aiosqlite:///test.db",
        s3_access_key="test",
        s3_secret_key="test",
        jwt_secret_key_path="unused",
        jwt_public_key_path="unused",
    )
    app.include_router(figures_router)
    return app


@pytest_asyncio.fixture
async def figures_client(figures_app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=figures_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_figure_unauthenticated(figures_client: AsyncClient):
    """GET without auth cookie returns 401 JSON."""
    resp = await figures_client.get(f"/dash/api/batches/{TEST_BATCH_ID}/figure")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication required"


@pytest.mark.asyncio
async def test_batch_figure_endpoint(
    figures_client: AsyncClient,
    figures_app: FastAPI,
    access_token: str,
):
    """GET with auth returns 200 with Plotly JSON structure."""
    # Seed S3 with test parquet
    s3_storage: S3Storage = figures_app.state.s3_storage
    parquet_bytes = _make_parquet_bytes()
    await s3_storage.put_parquet(
        TEST_TENANT_ID,
        __import__("uuid").UUID(TEST_BATCH_ID),
        "telemetry",
        parquet_bytes,
    )

    resp = await figures_client.get(
        f"/dash/api/batches/{TEST_BATCH_ID}/figure",
        cookies={"sporedb_session": access_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "layout" in body
    assert isinstance(body["data"], list)
    assert isinstance(body["layout"], dict)


@pytest.mark.asyncio
async def test_batch_figure_missing_signal(
    figures_client: AsyncClient,
    figures_app: FastAPI,
    access_token: str,
):
    """GET with non-existent signal returns 400."""
    s3_storage: S3Storage = figures_app.state.s3_storage
    parquet_bytes = _make_parquet_bytes(signals=["OD600"])
    await s3_storage.put_parquet(
        TEST_TENANT_ID,
        __import__("uuid").UUID(TEST_BATCH_ID),
        "telemetry",
        parquet_bytes,
    )

    resp = await figures_client.get(
        f"/dash/api/batches/{TEST_BATCH_ID}/figure?signal=nonexistent",
        cookies={"sporedb_session": access_token},
    )
    assert resp.status_code == 400
    assert "nonexistent" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_batch_figure_not_found(
    figures_client: AsyncClient,
    access_token: str,
):
    """GET for non-existent batch returns 404."""
    resp = await figures_client.get(
        f"/dash/api/batches/{TEST_BATCH_ID}/figure",
        cookies={"sporedb_session": access_token},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_compare_figure_endpoint(
    figures_client: AsyncClient,
    figures_app: FastAPI,
    access_token: str,
):
    """GET compare with 2 batches returns 200 with multiple traces."""
    import uuid as _uuid

    s3_storage: S3Storage = figures_app.state.s3_storage
    parquet_bytes = _make_parquet_bytes()
    await s3_storage.put_parquet(
        TEST_TENANT_ID, _uuid.UUID(TEST_BATCH_ID), "telemetry", parquet_bytes
    )
    await s3_storage.put_parquet(
        TEST_TENANT_ID, _uuid.UUID(TEST_BATCH_ID_2), "telemetry", parquet_bytes
    )

    resp = await figures_client.get(
        f"/dash/api/compare/figure?batch_ids={TEST_BATCH_ID}&batch_ids={TEST_BATCH_ID_2}",
        cookies={"sporedb_session": access_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "layout" in body
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 2  # one trace per batch


@pytest.mark.asyncio
async def test_compare_figure_too_many_batches(
    figures_client: AsyncClient,
    access_token: str,
):
    """>10 batch_ids returns 400."""
    ids = [f"00000000-0000-0000-0000-0000000000{i:02d}" for i in range(11)]
    params = "&".join(f"batch_ids={bid}" for bid in ids)
    resp = await figures_client.get(
        f"/dash/api/compare/figure?{params}",
        cookies={"sporedb_session": access_token},
    )
    assert resp.status_code == 400
    assert "10" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_compare_figure_too_few_batches(
    figures_client: AsyncClient,
    access_token: str,
):
    """<2 batch_ids returns 400."""
    resp = await figures_client.get(
        f"/dash/api/compare/figure?batch_ids={TEST_BATCH_ID}",
        cookies={"sporedb_session": access_token},
    )
    assert resp.status_code == 400
    assert "2" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_figure_response_has_plotly_structure(
    figures_client: AsyncClient,
    figures_app: FastAPI,
    access_token: str,
):
    """Verify Plotly JSON has expected structure: data is list, layout is dict."""
    import uuid as _uuid

    s3_storage: S3Storage = figures_app.state.s3_storage
    parquet_bytes = _make_parquet_bytes()
    await s3_storage.put_parquet(
        TEST_TENANT_ID, _uuid.UUID(TEST_BATCH_ID), "telemetry", parquet_bytes
    )

    resp = await figures_client.get(
        f"/dash/api/batches/{TEST_BATCH_ID}/figure",
        cookies={"sporedb_session": access_token},
    )
    assert resp.status_code == 200
    body = resp.json()

    # Plotly structure validation
    assert isinstance(body["data"], list)
    assert len(body["data"]) > 0
    trace = body["data"][0]
    assert "x" in trace
    assert "y" in trace
    assert isinstance(body["layout"], dict)
    assert body["layout"].get("template", {}).get("layout", {}) is not None
