"""Tests for cloud/auth/deps.py authentication dependencies.

Covers lines 33, 52-55, 59, 69-70:
- _get_public_key raises HTTP 500 when jwt_public_key not set on app.state (line 33)
- get_current_user raises HTTP 401 for ExpiredSignatureError (lines 52-53)
- get_current_user raises HTTP 401 for InvalidTokenError (lines 54-55)
- get_current_user raises HTTP 401 for wrong token type (line 59)
- require_permission raises HTTP 403 for insufficient permissions (lines 69-70)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from sporedb.cloud.auth.deps import (
    _get_public_key,
    get_current_user,
    require_permission,
)
from sporedb.cloud.auth.jwt import create_access_token
from sporedb.compliance.rbac import Permission

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app_without_public_key():
    """FastAPI app with no jwt_public_key in state."""
    app = FastAPI()

    @app.get("/test")
    async def test_route(request: Request):  # noqa: F821

        return {"key": str(_get_public_key(request))}

    return app


# ---------------------------------------------------------------------------
# _get_public_key tests
# ---------------------------------------------------------------------------


class TestGetPublicKey:
    def test_raises_500_when_no_public_key(self) -> None:
        from fastapi import HTTPException

        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # Empty state, no jwt_public_key attr

        with pytest.raises(HTTPException) as exc_info:
            _get_public_key(request)

        assert exc_info.value.status_code == 500
        assert "not configured" in exc_info.value.detail

    def test_returns_key_when_present(self, ed25519_keypair) -> None:
        _, public_key = ed25519_keypair
        request = MagicMock()
        request.app.state.jwt_public_key = public_key

        result = _get_public_key(request)
        assert result is public_key


# ---------------------------------------------------------------------------
# get_current_user tests
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_raises_401_for_expired_token(self, ed25519_keypair) -> None:
        """Expired token triggers HTTP 401 with 'Token expired' detail."""
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        private_key, public_key = ed25519_keypair
        expired_token = create_access_token(
            tenant_id="t1",
            user_id="u1",
            email="a@b.com",
            role="editor",
            private_key=private_key,
            expires_minutes=-5,
        )

        request = MagicMock()
        request.app.state.jwt_public_key = public_key
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=expired_token
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=request, credentials=credentials)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_raises_401_for_invalid_token(self, ed25519_keypair) -> None:
        """Tampered/invalid token triggers HTTP 401 with 'Invalid token' detail."""
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        _, public_key = ed25519_keypair
        request = MagicMock()
        request.app.state.jwt_public_key = public_key
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="not.a.valid.jwt.token"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=request, credentials=credentials)

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_raises_401_for_refresh_token_used_as_access(
        self, ed25519_keypair
    ) -> None:
        """Refresh tokens must not be accepted as access tokens."""
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        private_key, public_key = ed25519_keypair
        refresh_token = create_access_token(
            tenant_id="t1",
            user_id="u1",
            email="a@b.com",
            role="editor",
            private_key=private_key,
        )

        # Patch decode_token to return a payload with type="refresh"
        from sporedb.cloud.auth import deps

        request = MagicMock()
        request.app.state.jwt_public_key = public_key
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=refresh_token
        )

        refresh_payload = {
            "sub": "u1",
            "tenant_id": "t1",
            "email": "a@b.com",
            "role": "editor",
            "type": "refresh",  # wrong type
        }
        with (
            patch.object(deps, "decode_token", return_value=refresh_payload),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(request=request, credentials=credentials)

        assert exc_info.value.status_code == 401
        assert "token type" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_raises_401_for_malformed_claims(self, ed25519_keypair) -> None:
        """Missing required claims (tenant_id, sub, etc.) triggers HTTP 401."""
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        private_key, public_key = ed25519_keypair
        token = create_access_token(
            tenant_id="t1",
            user_id="u1",
            email="a@b.com",
            role="editor",
            private_key=private_key,
        )

        from sporedb.cloud.auth import deps

        request = MagicMock()
        request.app.state.jwt_public_key = public_key
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        # Return payload missing required claims
        missing_claims = {"type": "access"}  # missing sub, tenant_id, email, role
        with (
            patch.object(deps, "decode_token", return_value=missing_claims),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(request=request, credentials=credentials)

        assert exc_info.value.status_code == 401
        assert "malformed" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# require_permission tests
# ---------------------------------------------------------------------------


class TestRequirePermission:
    @pytest.mark.asyncio
    async def test_raises_403_for_insufficient_permission(
        self, ed25519_keypair
    ) -> None:
        """Viewer role cannot perform DELETE operations -> HTTP 403."""
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        private_key, public_key = ed25519_keypair
        viewer_token = create_access_token(
            tenant_id="t1",
            user_id="u1",
            email="viewer@example.com",
            role="viewer",
            private_key=private_key,
        )

        request = MagicMock()
        request.app.state.jwt_public_key = public_key
        _ = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=viewer_token
        )  # created but not used; we inject ctx directly

        # Build the permission checker
        checker = require_permission(Permission.DELETE)

        # get_current_user is a dependency - call manually
        from sporedb.cloud.auth.middleware import TenantContext

        ctx = TenantContext(
            tenant_id="t1",
            user_id="u1",
            email="viewer@example.com",
            role="viewer",
        )

        with pytest.raises(HTTPException) as exc_info:
            await checker(ctx=ctx)

        assert exc_info.value.status_code == 403
        assert "permission" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_passes_for_sufficient_permission(self) -> None:
        """Admin role can perform DELETE operations -> returns ctx."""
        from sporedb.cloud.auth.middleware import TenantContext

        ctx = TenantContext(
            tenant_id="t1",
            user_id="u1",
            email="admin@example.com",
            role="admin",
        )

        checker = require_permission(Permission.DELETE)
        result = await checker(ctx=ctx)
        assert result is ctx
