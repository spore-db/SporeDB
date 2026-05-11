"""Shared fixtures for cloud tier tests.

Provides reusable authentication fixtures (keypairs, tokens, tenant
context, auth headers) consumed by all ``test_cloud/`` test modules.
Also provides app-level fixtures for integration tests (test database,
mock S3, test FastAPI app, HTTP client).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sporedb.cloud.auth.jwt import create_access_token
from sporedb.cloud.auth.middleware import TenantContext
from sporedb.cloud.config import CloudSettings
from sporedb.cloud.db.models import AuditIndex, Base, CloudUser, Tenant
from sporedb.cloud.storage.s3 import S3Storage

# ---------------------------------------------------------------------------
# Auth fixtures (from Plan 02)
# ---------------------------------------------------------------------------


@pytest.fixture
def ed25519_keypair():
    """Generate a fresh Ed25519 keypair for test isolation."""
    private_key = Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


@pytest.fixture
def test_tenant_id() -> str:
    """Fixed tenant UUID for deterministic tests."""
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def test_user_id() -> str:
    """Fixed user UUID for deterministic tests."""
    return "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def test_access_token(ed25519_keypair, test_tenant_id, test_user_id) -> str:
    """Create an access token for the default test editor user."""
    private_key, _ = ed25519_keypair
    return create_access_token(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        email="editor@example.com",
        role="editor",
        private_key=private_key,
    )


@pytest.fixture
def test_tenant_context(test_tenant_id, test_user_id) -> TenantContext:
    """Pre-built TenantContext matching the default test user."""
    return TenantContext(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        email="editor@example.com",
        role="editor",
    )


@pytest.fixture
def auth_headers(test_access_token) -> dict[str, str]:
    """Authorization header dict for use with TestClient requests."""
    return {"Authorization": f"Bearer {test_access_token}"}


@pytest.fixture
def admin_access_token(ed25519_keypair, test_tenant_id) -> str:
    """Access token for an admin user (different user_id)."""
    private_key, _ = ed25519_keypair
    return create_access_token(
        tenant_id=test_tenant_id,
        user_id="00000000-0000-0000-0000-000000000099",
        email="admin@example.com",
        role="admin",
        private_key=private_key,
    )


# ---------------------------------------------------------------------------
# Database fixtures (Plan 03)
# ---------------------------------------------------------------------------


def _register_pg_compat_functions(dbapi_conn, _connection_record):
    """Register no-op PostgreSQL functions for SQLite test compatibility.

    pg_advisory_xact_lock is PostgreSQL-specific; register a no-op so
    that the audit service's advisory lock call succeeds in tests.
    """
    dbapi_conn.create_function("pg_advisory_xact_lock", 1, lambda _key: None)


@pytest_asyncio.fixture
async def test_db_engine(tmp_path):
    """Create an async SQLite engine with all tables for testing."""
    from sqlalchemy import event

    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    # Register pg_advisory_xact_lock as a no-op on each new connection
    event.listen(engine.sync_engine, "connect", _register_pg_compat_functions)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db_session(test_db_engine):
    """Yield an async session bound to the test database."""
    session_factory = async_sessionmaker(
        test_db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_s3():
    """Create a mock S3 client backed by an in-memory dict."""
    storage: dict[str, bytes] = {}
    client = MagicMock()

    def put_object(Bucket: str, Key: str, Body: bytes, **kw):  # noqa: N803
        storage[Key] = Body

    def get_object(Bucket: str, Key: str, **kw):  # noqa: N803
        if Key not in storage:
            raise client.exceptions.NoSuchKey(
                {"Error": {"Code": "NoSuchKey"}}, "GetObject"
            )
        body = MagicMock()
        body.read.return_value = storage[Key]
        return {"Body": body}

    def list_objects_v2(Bucket: str, Prefix: str = "", **kw):  # noqa: N803
        contents = [{"Key": k} for k in storage if k.startswith(Prefix)]
        return {"Contents": contents}

    client.put_object.side_effect = put_object
    client.get_object.side_effect = get_object
    client.list_objects_v2.side_effect = list_objects_v2
    return client


# ---------------------------------------------------------------------------
# App fixtures (Plan 03)
# ---------------------------------------------------------------------------


class _TestSessionFactory:
    """Minimal session factory that wraps a test engine for the app."""

    def __init__(self, engine):
        self._engine = engine
        self._session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session

    async def dispose(self):
        pass


@pytest.fixture
def test_app(ed25519_keypair, test_db_engine, mock_s3):
    """Create a FastAPI test app with test DB, mock S3, and test keys.

    Sets app.state directly (no lifespan) so that ASGITransport works
    without needing lifespan event support.
    """
    private_key, public_key = ed25519_keypair

    from sporedb.cloud.routes.auth import router as auth_router
    from sporedb.cloud.routes.batches import router as batches_router

    app = FastAPI(
        title="SporeDB Cloud Test",
        version="0.1.0-test",
    )

    # Wire state directly -- bypasses lifespan for test simplicity
    app.state.db_session = _TestSessionFactory(test_db_engine)
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

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(batches_router, prefix="/api/v1/batches", tags=["batches"])

    return app


@pytest_asyncio.fixture
async def client(test_app) -> AsyncIterator[AsyncClient]:
    """Async HTTP client connected to the test app via ASGI transport."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seeded_tenant(test_db_session, test_tenant_id, test_user_id):
    """Create a Tenant and CloudUser in the test database.

    Returns (tenant, user) tuple. The user's password is 'testpassword'.
    """
    from argon2 import PasswordHasher

    ph = PasswordHasher()

    tenant = Tenant(
        id=test_tenant_id,
        name="Test Org",
        slug="test-org",
        s3_prefix=f"tenants/{test_tenant_id}",
    )
    test_db_session.add(tenant)

    user = CloudUser(
        id=test_user_id,
        tenant_id=test_tenant_id,
        email="editor@example.com",
        name="Test Editor",
        role="editor",
        password_hash=ph.hash("testpassword"),
    )
    test_db_session.add(user)
    await test_db_session.commit()

    return tenant, user


# ---------------------------------------------------------------------------
# Dashboard fixtures (Plan 10-01)
# ---------------------------------------------------------------------------


@pytest.fixture
def dashboard_app(ed25519_keypair, test_db_engine, mock_s3):
    """Create a FastAPI test app with dashboard routes, templates, and static files.

    Extends the base test_app pattern to include the dashboard router
    and static file mount for integration testing of HTML routes.
    """
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    from sporedb.cloud.dashboard_deps import SlidingWindowRefreshMiddleware
    from sporedb.cloud.routes.auth import router as auth_router
    from sporedb.cloud.routes.batches import router as batches_router
    from sporedb.cloud.routes.dashboard import router as dashboard_router

    private_key, public_key = ed25519_keypair

    app = FastAPI(
        title="SporeDB Cloud Test",
        version="0.1.0-test",
    )

    app.state.db_session = _TestSessionFactory(test_db_engine)
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
        debug=True,  # Disable Secure flag on cookies for test
    )

    app.add_middleware(SlidingWindowRefreshMiddleware)

    # Disable rate limiting in tests by patching module-level limiters
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from sporedb.cloud.routes.auth import limiter as auth_limiter
    from sporedb.cloud.routes.dashboard import limiter as dash_limiter

    auth_limiter.enabled = False
    dash_limiter.enabled = False
    app.state.limiter = auth_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(batches_router, prefix="/api/v1/batches", tags=["batches"])
    app.include_router(dashboard_router)

    static_dir = (
        Path(__file__).parent.parent.parent / "src" / "sporedb" / "cloud" / "static"
    )
    if static_dir.exists():
        app.mount(
            "/dash/static",
            StaticFiles(directory=str(static_dir)),
            name="dashboard_static",
        )

    return app


@pytest_asyncio.fixture
async def dashboard_client(dashboard_app) -> AsyncIterator[AsyncClient]:
    """Async HTTP client for dashboard integration tests."""
    transport = ASGITransport(app=dashboard_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        follow_redirects=False,
    ) as ac:
        yield ac


@pytest.fixture
def viewer_access_token(ed25519_keypair, test_tenant_id) -> str:
    """Access token for a viewer user (read-only role)."""
    private_key, _ = ed25519_keypair
    return create_access_token(
        tenant_id=test_tenant_id,
        user_id="00000000-0000-0000-0000-000000000088",
        email="viewer@example.com",
        role="viewer",
        private_key=private_key,
    )


@pytest_asyncio.fixture
async def seeded_batches(test_db_engine, test_tenant_id):
    """Create test batches in the database for batch list/detail tests.

    Returns list of (id, name) tuples for assertions.
    """
    import json

    from sporedb.cloud.db.models import CloudBatch

    session_factory = async_sessionmaker(
        test_db_engine, class_=AsyncSession, expire_on_commit=False
    )
    batch_data = [
        {
            "id": "00000000-0000-0000-0000-000000000b01",
            "tenant_id": test_tenant_id,
            "name": "Fermentation Run Alpha",
            "lifecycle": "active",
            "metadata_json": json.dumps(
                {"strain": "R. toruloides", "operator": "Dr. Smith"}
            ),
            "tags_json": json.dumps(["pilot", "glucose"]),
        },
        {
            "id": "00000000-0000-0000-0000-000000000b02",
            "tenant_id": test_tenant_id,
            "name": "Fermentation Run Beta",
            "lifecycle": "completed",
            "metadata_json": json.dumps(
                {"strain": "S. cerevisiae", "operator": "Dr. Jones"}
            ),
            "tags_json": None,
        },
        {
            "id": "00000000-0000-0000-0000-000000000b03",
            "tenant_id": test_tenant_id,
            "name": "Scale-up Test 001",
            "lifecycle": "planned",
            "metadata_json": None,
            "tags_json": None,
        },
    ]
    async with session_factory() as session:
        for bd in batch_data:
            session.add(CloudBatch(**bd))
        await session.commit()

    return [(b["id"], b["name"]) for b in batch_data]


@pytest_asyncio.fixture
async def seeded_audit_entries(test_db_session, test_tenant_id, test_user_id):
    """Seed audit entries in the test database for audit page tests.

    Creates 3 entries with different actions for filter testing.
    """
    from datetime import datetime

    entries = [
        AuditIndex(
            id="00000000-0000-0000-0000-000000000a01",
            tenant_id=test_tenant_id,
            action="create",
            entity_type="batch",
            entity_id="batch-001",
            user_id=test_user_id,
            created_at=datetime(2026, 4, 28, 10, 0, 0, tzinfo=UTC),
        ),
        AuditIndex(
            id="00000000-0000-0000-0000-000000000a02",
            tenant_id=test_tenant_id,
            action="update",
            entity_type="batch",
            entity_id="batch-001",
            user_id=test_user_id,
            created_at=datetime(2026, 4, 28, 11, 0, 0, tzinfo=UTC),
        ),
        AuditIndex(
            id="00000000-0000-0000-0000-000000000a03",
            tenant_id=test_tenant_id,
            action="sign",
            entity_type="batch",
            entity_id="batch-001",
            user_id=test_user_id,
            created_at=datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC),
        ),
    ]
    for entry in entries:
        test_db_session.add(entry)
    await test_db_session.commit()
    return entries
