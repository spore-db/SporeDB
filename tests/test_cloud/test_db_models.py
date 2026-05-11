"""Tests for SQLAlchemy cloud tier models using async SQLite backend.

Uses aiosqlite as the test database backend so no PostgreSQL is needed
in CI. All CRUD operations are tested against in-memory SQLite.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sporedb.cloud.db.models import AuditIndex, Base, CloudBatch, CloudUser, Tenant


@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite async engine, yield a session, then tear down."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        yield session

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


def _make_tenant(
    slug: str = "acme",
    name: str = "Acme Biotech",
    s3_prefix: str | None = None,
    **kwargs: object,
) -> Tenant:
    """Helper to create a Tenant with defaults."""
    if s3_prefix is None:
        s3_prefix = f"tenants/{slug}"
    return Tenant(slug=slug, name=name, s3_prefix=s3_prefix, **kwargs)


class TestTenantModel:
    """Tests for the Tenant model."""

    @pytest.mark.asyncio
    async def test_create_tenant(self, db_session: AsyncSession) -> None:
        tenant = _make_tenant()
        db_session.add(tenant)
        await db_session.commit()

        result = await db_session.execute(select(Tenant).where(Tenant.slug == "acme"))
        loaded = result.scalar_one()

        assert loaded.name == "Acme Biotech"
        assert loaded.slug == "acme"
        assert loaded.s3_prefix == "tenants/acme"
        assert loaded.id is not None
        assert len(loaded.id) == 36  # UUID string length

    @pytest.mark.asyncio
    async def test_tenant_slug_unique(self, db_session: AsyncSession) -> None:
        t1 = _make_tenant(slug="dup", s3_prefix="tenants/dup1")
        t2 = _make_tenant(slug="dup", s3_prefix="tenants/dup2")
        db_session.add(t1)
        await db_session.flush()
        db_session.add(t2)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_tenant_defaults(self, db_session: AsyncSession) -> None:
        tenant = _make_tenant(slug="defaults-test")
        db_session.add(tenant)
        await db_session.commit()

        result = await db_session.execute(
            select(Tenant).where(Tenant.slug == "defaults-test")
        )
        loaded = result.scalar_one()

        assert loaded.active is True
        assert loaded.created_at is not None


class TestCloudUserModel:
    """Tests for the CloudUser model."""

    @pytest.mark.asyncio
    async def test_create_user_with_tenant(self, db_session: AsyncSession) -> None:
        tenant = _make_tenant()
        db_session.add(tenant)
        await db_session.flush()

        user = CloudUser(
            tenant_id=tenant.id,
            email="alice@acme.com",
            name="Alice",
            password_hash="hashed_pw",
        )
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(
            select(CloudUser).where(CloudUser.email == "alice@acme.com")
        )
        loaded = result.scalar_one()

        assert loaded.tenant_id == tenant.id
        assert loaded.name == "Alice"
        assert loaded.password_hash == "hashed_pw"

    @pytest.mark.asyncio
    async def test_user_email_unique_per_tenant(self, db_session: AsyncSession) -> None:
        tenant = _make_tenant()
        db_session.add(tenant)
        await db_session.flush()

        u1 = CloudUser(
            tenant_id=tenant.id,
            email="dup@acme.com",
            name="User1",
            password_hash="hash1",
        )
        u2 = CloudUser(
            tenant_id=tenant.id,
            email="dup@acme.com",
            name="User2",
            password_hash="hash2",
        )
        db_session.add(u1)
        await db_session.flush()
        db_session.add(u2)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_user_email_allowed_across_tenants(
        self, db_session: AsyncSession
    ) -> None:
        t1 = _make_tenant(slug="tenant-a", s3_prefix="tenants/a")
        t2 = _make_tenant(slug="tenant-b", name="Tenant B", s3_prefix="tenants/b")
        db_session.add_all([t1, t2])
        await db_session.flush()

        u1 = CloudUser(
            tenant_id=t1.id,
            email="shared@example.com",
            name="User1",
            password_hash="hash1",
        )
        u2 = CloudUser(
            tenant_id=t2.id,
            email="shared@example.com",
            name="User2",
            password_hash="hash2",
        )
        db_session.add_all([u1, u2])
        await db_session.commit()

        result = await db_session.execute(
            select(CloudUser).where(CloudUser.email == "shared@example.com")
        )
        users = result.scalars().all()
        assert len(users) == 2

    @pytest.mark.asyncio
    async def test_user_role_default(self, db_session: AsyncSession) -> None:
        tenant = _make_tenant(slug="role-test")
        db_session.add(tenant)
        await db_session.flush()

        user = CloudUser(
            tenant_id=tenant.id,
            email="bob@acme.com",
            name="Bob",
            password_hash="hash",
        )
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(
            select(CloudUser).where(CloudUser.email == "bob@acme.com")
        )
        loaded = result.scalar_one()
        assert loaded.role == "editor"


class TestCloudBatchModel:
    """Tests for the CloudBatch model."""

    @pytest.mark.asyncio
    async def test_create_batch(self, db_session: AsyncSession) -> None:
        tenant = _make_tenant(slug="batch-test")
        db_session.add(tenant)
        await db_session.flush()

        batch = CloudBatch(
            tenant_id=tenant.id,
            name="Fermentation Run 001",
        )
        db_session.add(batch)
        await db_session.commit()

        result = await db_session.execute(
            select(CloudBatch).where(CloudBatch.name == "Fermentation Run 001")
        )
        loaded = result.scalar_one()

        assert loaded.tenant_id == tenant.id
        assert loaded.id is not None
        assert loaded.created_at is not None

    @pytest.mark.asyncio
    async def test_batch_lifecycle_default(self, db_session: AsyncSession) -> None:
        tenant = _make_tenant(slug="lc-test")
        db_session.add(tenant)
        await db_session.flush()

        batch = CloudBatch(tenant_id=tenant.id, name="Run 002")
        db_session.add(batch)
        await db_session.commit()

        result = await db_session.execute(
            select(CloudBatch).where(CloudBatch.name == "Run 002")
        )
        loaded = result.scalar_one()
        assert loaded.lifecycle == "planned"

    @pytest.mark.asyncio
    async def test_batch_metadata_json(self, db_session: AsyncSession) -> None:
        tenant = _make_tenant(slug="meta-test")
        db_session.add(tenant)
        await db_session.flush()

        import json

        metadata = {"organism": "E. coli", "temperature": 37.0}
        batch = CloudBatch(
            tenant_id=tenant.id,
            name="Run 003",
            metadata_json=json.dumps(metadata),
        )
        db_session.add(batch)
        await db_session.commit()

        result = await db_session.execute(
            select(CloudBatch).where(CloudBatch.name == "Run 003")
        )
        loaded = result.scalar_one()
        parsed = json.loads(loaded.metadata_json)
        assert parsed["organism"] == "E. coli"
        assert parsed["temperature"] == 37.0


class TestAuditIndexModel:
    """Tests for the AuditIndex model."""

    @pytest.mark.asyncio
    async def test_create_audit_entry(self, db_session: AsyncSession) -> None:
        tenant = _make_tenant(slug="audit-test")
        db_session.add(tenant)
        await db_session.flush()

        entry = AuditIndex(
            tenant_id=tenant.id,
            action="create_batch",
            entity_type="batch",
            entity_id="some-batch-id",
            user_id="some-user-id",
        )
        db_session.add(entry)
        await db_session.commit()

        result = await db_session.execute(
            select(AuditIndex).where(AuditIndex.action == "create_batch")
        )
        loaded = result.scalar_one()

        assert loaded.tenant_id == tenant.id
        assert loaded.entity_type == "batch"
        assert loaded.entity_id == "some-batch-id"
        assert loaded.user_id == "some-user-id"
        assert loaded.created_at is not None

    @pytest.mark.asyncio
    async def test_audit_tenant_scoping(self, db_session: AsyncSession) -> None:
        t1 = _make_tenant(slug="scope-a", s3_prefix="tenants/scope-a")
        t2 = _make_tenant(slug="scope-b", name="Tenant B", s3_prefix="tenants/scope-b")
        db_session.add_all([t1, t2])
        await db_session.flush()

        # Add entries for both tenants
        e1 = AuditIndex(tenant_id=t1.id, action="login")
        e2 = AuditIndex(tenant_id=t1.id, action="create_batch")
        e3 = AuditIndex(tenant_id=t2.id, action="login")
        db_session.add_all([e1, e2, e3])
        await db_session.commit()

        # Query only tenant 1
        result = await db_session.execute(
            select(AuditIndex).where(AuditIndex.tenant_id == t1.id)
        )
        t1_entries = result.scalars().all()
        assert len(t1_entries) == 2

        # Query only tenant 2
        result = await db_session.execute(
            select(AuditIndex).where(AuditIndex.tenant_id == t2.id)
        )
        t2_entries = result.scalars().all()
        assert len(t2_entries) == 1
