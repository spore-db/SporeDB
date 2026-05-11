"""FastAPI dependencies for authentication and permission checks.

Provides injectable dependencies that extract authenticated user context
from JWT bearer tokens and enforce RBAC permissions on route handlers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sporedb.cloud.auth.jwt import decode_token
from sporedb.cloud.auth.middleware import TenantContext
from sporedb.compliance.rbac import Permission, Role, User, check_permission

security = HTTPBearer()


def _get_public_key(request: Request) -> Ed25519PublicKey:
    """Retrieve the JWT public key from application state.

    The key must be set during app startup via::

        app.state.jwt_public_key = public_key
    """
    key: Ed25519PublicKey | None = getattr(request.app.state, "jwt_public_key", None)
    if key is None:
        raise HTTPException(
            status_code=500,
            detail="JWT public key not configured",
        )
    return key


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),  # noqa: B008
) -> TenantContext:
    """Extract and validate tenant context from the Authorization header.

    Returns a ``TenantContext`` on success.  Raises HTTP 401 for expired
    or invalid tokens.
    """
    public_key = _get_public_key(request)
    try:
        payload = decode_token(credentials.credentials, public_key)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token") from None

    # Reject refresh tokens used as access tokens
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    try:
        return TenantContext(
            tenant_id=payload["tenant_id"],
            user_id=payload["sub"],
            email=payload["email"],
            role=payload["role"],
            active=payload.get("active", True),
        )
    except KeyError:
        raise HTTPException(status_code=401, detail="Malformed token claims") from None


def require_permission(required: Permission) -> Callable[..., Any]:
    """Return a FastAPI dependency that enforces a specific RBAC permission.

    Usage::

        @router.delete("/batches/{batch_id}",
                       dependencies=[Depends(require_permission(Permission.DELETE))])
        async def delete_batch(...): ...
    """

    async def _check(
        ctx: TenantContext = Depends(get_current_user),  # noqa: B008
    ) -> TenantContext:
        user = User(
            user_id=ctx.user_id,
            name=ctx.email,  # Use email as display name in permission checks
            email=ctx.email,
            role=Role(ctx.role),
            active=ctx.active,
        )
        try:
            check_permission(user, required)
        except PermissionError:
            raise HTTPException(
                status_code=403, detail="Insufficient permissions"
            ) from None
        return ctx

    return _check
