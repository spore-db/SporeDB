"""Authentication routes: login, register, and token refresh.

Threat mitigations:
- T-8-11: Generic "invalid credentials" error prevents email enumeration.
- T-8-16: Registration creates audit trail entry.
- T-13-07: Rate limiting on login (5/min) and register (3/min) via slowapi.
- T-13-08: Generic 401 for tenant-not-found prevents enumeration.
- T-13-09: Registration requires admin JWT.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from sporedb.cloud.auth.deps import get_current_user
from sporedb.cloud.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from sporedb.cloud.auth.middleware import TenantContext
from sporedb.cloud.db.models import RefreshToken
from sporedb.cloud.services.tenant_service import TenantService

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Credentials for user login."""

    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    password: str


class RegisterRequest(BaseModel):
    """New user registration payload."""

    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    """JWT token pair returned on successful authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token exchange payload."""

    refresh_token: str


# ---------------------------------------------------------------------------
# Database dependency
# ---------------------------------------------------------------------------


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session from the app-level factory."""
    async with request.app.state.db_session.get_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    body: LoginRequest,
    tenant_slug: str,
    request: Request,
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> TokenResponse:
    """Authenticate a user and return JWT tokens.

    Uses generic error message to prevent email enumeration (T-8-11).
    """
    svc = TenantService(session)
    tenant = await svc.get_tenant_by_slug(tenant_slug)
    if tenant is None:
        # Return generic error to prevent tenant enumeration (T-13-08 / MD-06)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = await svc.get_user_by_email(tenant.id, body.email)
    if user is None or not await svc.verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.active:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    private_key = request.app.state.jwt_private_key
    settings = request.app.state.settings

    access_token = create_access_token(
        tenant_id=tenant.id,
        user_id=user.id,
        email=user.email,
        role=user.role,
        private_key=private_key,
        expires_minutes=settings.jwt_access_token_expire_minutes,
    )
    refresh_token = create_refresh_token(
        tenant_id=tenant.id,
        user_id=user.id,
        private_key=private_key,
        expires_days=settings.jwt_refresh_token_expire_days,
    )

    # Record refresh token jti in DB for revocation tracking
    refresh_payload = decode_token(refresh_token, request.app.state.jwt_public_key)
    refresh_row = RefreshToken(
        id=str(uuid7()),
        tenant_id=tenant.id,
        user_id=user.id,
        jti=refresh_payload["jti"],
        family_id=str(uuid7()),
        expires_at=datetime.fromtimestamp(refresh_payload["exp"], tz=UTC),
    )
    session.add(refresh_row)
    await session.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("3/minute")
async def register(
    body: RegisterRequest,
    request: Request,
    ctx: TenantContext = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> TokenResponse:
    """Register a new user within the caller's tenant.

    Requires an authenticated admin JWT (T-13-09 / MD-07).
    The new user is created in the admin's tenant.
    """
    if ctx.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")

    svc = TenantService(session)

    try:
        user = await svc.create_user(
            tenant_id=ctx.tenant_id,
            email=body.email,
            name=body.name,
            password=body.password,
        )
    except ValueError:
        raise HTTPException(
            status_code=409, detail="Email already registered"
        ) from None

    await session.commit()

    private_key = request.app.state.jwt_private_key
    settings = request.app.state.settings

    access_token = create_access_token(
        tenant_id=ctx.tenant_id,
        user_id=user.id,
        email=user.email,
        role=user.role,
        private_key=private_key,
        expires_minutes=settings.jwt_access_token_expire_minutes,
    )
    refresh_token = create_refresh_token(
        tenant_id=ctx.tenant_id,
        user_id=user.id,
        private_key=private_key,
        expires_days=settings.jwt_refresh_token_expire_days,
    )

    # Record refresh token jti in DB for revocation tracking
    refresh_payload = decode_token(refresh_token, request.app.state.jwt_public_key)
    refresh_row = RefreshToken(
        id=str(uuid7()),
        tenant_id=ctx.tenant_id,
        user_id=user.id,
        jti=refresh_payload["jti"],
        family_id=str(uuid7()),
        expires_at=datetime.fromtimestamp(refresh_payload["exp"], tz=UTC),
    )
    session.add(refresh_row)
    await session.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(
    body: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> TokenResponse:
    """Exchange a refresh token for a new access/refresh token pair."""
    public_key = request.app.state.jwt_public_key
    private_key = request.app.state.jwt_private_key
    settings = request.app.state.settings

    try:
        payload = decode_token(body.refresh_token, public_key)
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Validate jti exists and is not revoked
    old_jti = payload.get("jti")
    if not old_jti:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.jti == old_jti,
            RefreshToken.revoked_at.is_(None),
        )
    )
    token_row = result.scalar_one_or_none()
    if token_row is None:
        raise HTTPException(status_code=401, detail="Refresh token revoked or expired")

    # Look up the user to get current email/role for the new access token
    tenant_id = payload["tenant_id"]
    user_id = payload["sub"]

    from sporedb.cloud.db.models import CloudUser

    user_result = await session.execute(
        select(CloudUser).where(
            CloudUser.id == user_id,
            CloudUser.tenant_id == tenant_id,
        )
    )
    user_row = user_result.scalar_one_or_none()
    if user_row is None or not user_row.active:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token(
        tenant_id=tenant_id,
        user_id=user_id,
        email=user_row.email,
        role=user_row.role,
        private_key=private_key,
        expires_minutes=settings.jwt_access_token_expire_minutes,
    )
    new_refresh = create_refresh_token(
        tenant_id=tenant_id,
        user_id=user_id,
        private_key=private_key,
        expires_days=settings.jwt_refresh_token_expire_days,
    )

    # Rotate: mark old token as replaced, insert new token
    new_refresh_payload = decode_token(new_refresh, public_key)
    token_row.revoked_at = datetime.now(UTC)
    token_row.replaced_by = new_refresh_payload["jti"]

    new_token_row = RefreshToken(
        id=str(uuid7()),
        tenant_id=tenant_id,
        user_id=user_id,
        jti=new_refresh_payload["jti"],
        family_id=token_row.family_id,
        expires_at=datetime.fromtimestamp(new_refresh_payload["exp"], tz=UTC),
    )
    session.add(new_token_row)
    await session.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
    )
