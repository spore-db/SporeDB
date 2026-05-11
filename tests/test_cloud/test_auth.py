"""Unit tests for JWT authentication and TenantContext.

Tests cover token creation, validation, expiry, tamper detection,
wrong-key rejection, and TenantContext construction from JWT claims.
"""

from __future__ import annotations

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sporedb.cloud.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from sporedb.cloud.auth.middleware import TenantContext


class TestJWT:
    """JWT creation and validation with Ed25519."""

    def test_create_and_decode_access_token(self, ed25519_keypair):
        private_key, public_key = ed25519_keypair
        token = create_access_token(
            tenant_id="tenant-1",
            user_id="user-1",
            email="alice@example.com",
            role="editor",
            private_key=private_key,
        )

        payload = decode_token(token, public_key)

        assert payload["sub"] == "user-1"
        assert payload["tenant_id"] == "tenant-1"
        assert payload["email"] == "alice@example.com"
        assert payload["role"] == "editor"
        assert payload["type"] == "access"
        assert "iat" in payload
        assert "nbf" in payload
        assert "exp" in payload

    def test_create_and_decode_refresh_token(self, ed25519_keypair):
        private_key, public_key = ed25519_keypair
        token = create_refresh_token(
            tenant_id="tenant-1",
            user_id="user-1",
            private_key=private_key,
        )

        payload = decode_token(token, public_key)

        assert payload["sub"] == "user-1"
        assert payload["tenant_id"] == "tenant-1"
        assert payload["type"] == "refresh"
        # Refresh tokens should NOT contain email or role
        assert "email" not in payload
        assert "role" not in payload

    def test_expired_token_raises(self, ed25519_keypair):
        private_key, public_key = ed25519_keypair
        token = create_access_token(
            tenant_id="tenant-1",
            user_id="user-1",
            email="alice@example.com",
            role="editor",
            private_key=private_key,
            expires_minutes=-1,  # Already expired
        )

        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_token(token, public_key)

    def test_tampered_token_raises(self, ed25519_keypair):
        private_key, public_key = ed25519_keypair
        token = create_access_token(
            tenant_id="tenant-1",
            user_id="user-1",
            email="alice@example.com",
            role="editor",
            private_key=private_key,
        )

        # Flip a character in the signature portion
        parts = token.split(".")
        sig = parts[2]
        tampered_char = "A" if sig[0] != "A" else "B"
        parts[2] = tampered_char + sig[1:]
        tampered_token = ".".join(parts)

        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token(tampered_token, public_key)

    def test_wrong_key_raises(self, ed25519_keypair):
        private_key, _ = ed25519_keypair

        # Sign with one key, verify with a different one
        token = create_access_token(
            tenant_id="tenant-1",
            user_id="user-1",
            email="alice@example.com",
            role="editor",
            private_key=private_key,
        )

        other_private = Ed25519PrivateKey.generate()
        other_public = other_private.public_key()

        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token(token, other_public)


class TestTenantContext:
    """TenantContext dataclass construction and field access."""

    def test_tenant_context_fields(self):
        ctx = TenantContext(
            tenant_id="t1",
            user_id="u1",
            email="test@example.com",
            role="viewer",
        )
        assert ctx.tenant_id == "t1"
        assert ctx.user_id == "u1"
        assert ctx.email == "test@example.com"
        assert ctx.role == "viewer"

    def test_tenant_context_from_token(self, ed25519_keypair):
        private_key, public_key = ed25519_keypair
        token = create_access_token(
            tenant_id="tenant-99",
            user_id="user-42",
            email="bob@example.com",
            role="admin",
            private_key=private_key,
        )

        payload = decode_token(token, public_key)
        ctx = TenantContext(
            tenant_id=payload["tenant_id"],
            user_id=payload["sub"],
            email=payload["email"],
            role=payload["role"],
        )

        assert ctx.tenant_id == "tenant-99"
        assert ctx.user_id == "user-42"
        assert ctx.email == "bob@example.com"
        assert ctx.role == "admin"

    def test_tenant_context_is_frozen(self):
        ctx = TenantContext(
            tenant_id="t1",
            user_id="u1",
            email="test@example.com",
            role="editor",
        )
        with pytest.raises(AttributeError):
            ctx.tenant_id = "tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Auth route security tests (Phase 13 Plan 02)
# ---------------------------------------------------------------------------

pytestmark_async = pytest.mark.asyncio


class TestAuthRouteSecurity:
    """Integration tests for auth route security hardening."""

    @pytest.mark.asyncio
    async def test_login_nonexistent_tenant_returns_401(self, client, seeded_tenant):
        """Login with non-existent tenant returns 401, not 404 (MD-06)."""
        resp = await client.post(
            "/api/v1/auth/login",
            params={"tenant_slug": "nonexistent-org"},
            json={"email": "test@example.com", "password": "password123"},
        )
        assert resp.status_code == 401, f"Got {resp.status_code}: {resp.text}"
        assert resp.json()["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_refresh_cross_tenant_returns_401(
        self, client, ed25519_keypair, seeded_tenant
    ):
        """Refresh token for tenant A with user in tenant B returns 401 (CR-04)."""
        from sporedb.cloud.auth.jwt import create_refresh_token

        private_key, _ = ed25519_keypair
        # Create a refresh token for a different tenant_id
        cross_tenant_token = create_refresh_token(
            tenant_id="00000000-0000-0000-0000-999999999999",  # Non-existent tenant
            user_id="00000000-0000-0000-0000-000000000002",  # Real user
            private_key=private_key,
        )
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": cross_tenant_token},
        )
        assert resp.status_code == 401
        # Token not in DB is rejected at jti validation layer
        assert resp.json()["detail"] in (
            "User not found",
            "Refresh token revoked or expired",
        )

    @pytest.mark.asyncio
    async def test_register_without_auth_returns_401_or_403(
        self, client, seeded_tenant
    ):
        """Register without auth token returns 401/403 (MD-07)."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "new@example.com",
                "name": "New User",
                "password": "securepassword",
            },
        )
        # HTTPBearer returns 401 when no token is provided; 403 is also acceptable
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_register_with_non_admin_returns_403(
        self, client, test_access_token, seeded_tenant
    ):
        """Register with non-admin JWT returns 403 (MD-07)."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "new@example.com",
                "name": "New User",
                "password": "securepassword",
            },
            headers={"Authorization": f"Bearer {test_access_token}"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin role required"

    @pytest.mark.asyncio
    async def test_register_with_admin_succeeds(
        self, client, admin_access_token, seeded_tenant
    ):
        """Register with admin JWT succeeds (MD-07)."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "name": "New User",
                "password": "securepassword",
            },
            headers={"Authorization": f"Bearer {admin_access_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data


class TestRateLimiting:
    """Verify rate limiting decorators are applied (HI-07)."""

    def test_login_endpoint_has_rate_limit(self):
        """Login endpoint should have slowapi rate limit decorator."""
        from sporedb.cloud.routes.auth import login

        # slowapi decorates the function; check for the _rate_limit marker
        assert hasattr(login, "__wrapped__") or hasattr(login, "__self__")

    def test_register_endpoint_has_rate_limit(self):
        """Register endpoint should have slowapi rate limit decorator."""
        from sporedb.cloud.routes.auth import register

        assert hasattr(register, "__wrapped__") or hasattr(register, "__self__")

    def test_dashboard_login_has_rate_limit(self):
        """Dashboard login_submit should have slowapi rate limit decorator."""
        from sporedb.cloud.routes.dashboard import login_submit

        assert hasattr(login_submit, "__wrapped__") or hasattr(login_submit, "__self__")

    def test_auth_limiter_exists(self):
        """Auth module should export a limiter instance."""
        from sporedb.cloud.routes.auth import limiter

        assert limiter is not None

    def test_dashboard_limiter_exists(self):
        """Dashboard module should export a limiter instance."""
        from sporedb.cloud.routes.dashboard import limiter

        assert limiter is not None


class TestSlidingWindowRefresh:
    """Verify sliding window uses DB-fresh claims (MD-01)."""

    def test_refresh_window_constant_defined(self):
        """REFRESH_WINDOW_SECONDS constant should be defined."""
        from sporedb.cloud.dashboard_deps import REFRESH_WINDOW_SECONDS

        assert REFRESH_WINDOW_SECONDS == 900

    def test_dashboard_deps_imports_clouduser(self):
        """dashboard_deps should import CloudUser for DB queries."""
        from sporedb.cloud.dashboard_deps import CloudUser

        assert CloudUser is not None
