"""Tenant and user management service.

Handles tenant CRUD, user registration, and password verification
using argon2id hashing consistent with the compliance module's
``user_store.py`` pattern.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from sporedb.cloud.db.models import CloudUser, Tenant

ph = PasswordHasher()


class TenantService:
    """Business logic for tenant and user management.

    Parameters
    ----------
    session:
        An async SQLAlchemy session for database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_tenant(self, name: str, slug: str) -> Tenant:
        """Create a new tenant with an auto-generated S3 prefix.

        Raises
        ------
        ValueError
            If a tenant with the given slug already exists.
        """
        # Check slug uniqueness
        result = await self._session.execute(select(Tenant).where(Tenant.slug == slug))
        if result.scalar_one_or_none() is not None:
            raise ValueError(f"Tenant with slug '{slug}' already exists")

        tenant_id = str(uuid7())
        tenant = Tenant(
            id=tenant_id,
            name=name,
            slug=slug,
            s3_prefix=f"tenants/{tenant_id}",
        )
        self._session.add(tenant)
        await self._session.flush()
        return tenant

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Retrieve a tenant by ID, or None if not found."""
        result = await self._session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        """Retrieve a tenant by slug, or None if not found."""
        result = await self._session.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    async def create_user(
        self,
        tenant_id: str,
        email: str,
        name: str,
        password: str,
        role: str = "editor",
    ) -> CloudUser:
        """Create a new user within a tenant.

        Password is hashed with argon2id before storage.

        Raises
        ------
        ValueError
            If a user with the given email already exists in the tenant.
        """
        # Check email uniqueness within tenant
        result = await self._session.execute(
            select(CloudUser).where(
                CloudUser.tenant_id == tenant_id,
                CloudUser.email == email,
            )
        )
        if result.scalar_one_or_none() is not None:
            raise ValueError(f"User with email '{email}' already exists in tenant")

        user = CloudUser(
            id=str(uuid7()),
            tenant_id=tenant_id,
            email=email,
            name=name,
            role=role,
            password_hash=ph.hash(password),
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_user_by_email(self, tenant_id: str, email: str) -> CloudUser | None:
        """Look up a user by email within a tenant."""
        result = await self._session.execute(
            select(CloudUser).where(
                CloudUser.tenant_id == tenant_id,
                CloudUser.email == email,
            )
        )
        return result.scalar_one_or_none()

    async def verify_password(self, stored_hash: str, password: str) -> bool:
        """Verify a password against an argon2id hash.

        Returns True if the password matches, False otherwise.
        Does not raise on mismatch (safe for login flows).
        """
        try:
            ph.verify(stored_hash, password)
            return True
        except VerifyMismatchError:
            return False
