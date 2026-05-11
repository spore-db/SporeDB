"""Tests for JWT token revocation via jti tracking.

Verifies that refresh tokens carry jti claims, are tracked in DB,
support one-time use, and can be revoked.
"""

from __future__ import annotations

from datetime import UTC

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sporedb.cloud.auth.jwt import create_refresh_token, decode_token


class TestRefreshTokenJti:
    """Refresh tokens must carry a unique jti claim."""

    def test_refresh_token_has_jti_claim(self):
        """Every refresh token must include a unique jti (JWT ID)."""
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        token = create_refresh_token(
            tenant_id="t-1", user_id="u-1", private_key=private_key
        )
        payload = decode_token(token, public_key)
        assert "jti" in payload, "Refresh token must include jti claim"
        assert isinstance(payload["jti"], str)
        assert len(payload["jti"]) > 0

    def test_each_refresh_token_has_unique_jti(self):
        """Two refresh tokens must have different jti values."""
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        token1 = create_refresh_token(
            tenant_id="t-1", user_id="u-1", private_key=private_key
        )
        token2 = create_refresh_token(
            tenant_id="t-1", user_id="u-1", private_key=private_key
        )
        jti1 = decode_token(token1, public_key)["jti"]
        jti2 = decode_token(token2, public_key)["jti"]
        assert jti1 != jti2, "Each refresh token must have a unique jti"


class TestRefreshTokenModel:
    """DB model for tracking refresh tokens must exist."""

    def test_refresh_token_model_exists(self):
        """RefreshToken SQLAlchemy model must be importable."""
        from sporedb.cloud.db.models import RefreshToken

        assert hasattr(RefreshToken, "jti")
        assert hasattr(RefreshToken, "user_id")
        assert hasattr(RefreshToken, "tenant_id")
        assert hasattr(RefreshToken, "revoked_at")
        assert hasattr(RefreshToken, "replaced_by")
        assert hasattr(RefreshToken, "family_id")
        assert hasattr(RefreshToken, "expires_at")


class TestRefreshEndpointJti:
    """Integration tests: /login records jti, /refresh validates and rotates."""

    @pytest.mark.asyncio
    async def test_login_records_jti_in_db(
        self, client, seeded_tenant, test_db_session
    ):
        """Login should insert a RefreshToken row with the token's jti."""
        from sqlalchemy import select

        from sporedb.cloud.db.models import RefreshToken

        resp = await client.post(
            "/api/v1/auth/login",
            params={"tenant_slug": "test-org"},
            json={"email": "editor@example.com", "password": "testpassword"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "refresh_token" in data

        # Decode to get jti
        refresh_payload = decode_token(
            data["refresh_token"],
            client._transport.app.state.jwt_public_key,  # type: ignore[attr-defined]
        )

        # Check DB has a row with this jti
        result = await test_db_session.execute(
            select(RefreshToken).where(RefreshToken.jti == refresh_payload["jti"])
        )
        row = result.scalar_one_or_none()
        assert row is not None, "Login must record refresh token jti in DB"
        assert row.revoked_at is None

    @pytest.mark.asyncio
    async def test_refresh_with_revoked_jti_rejected(
        self, client, seeded_tenant, test_db_session
    ):
        """Using a revoked refresh token should return 401."""
        from datetime import datetime

        from sqlalchemy import select

        from sporedb.cloud.db.models import RefreshToken

        # Login to get a refresh token
        resp = await client.post(
            "/api/v1/auth/login",
            params={"tenant_slug": "test-org"},
            json={"email": "editor@example.com", "password": "testpassword"},
        )
        assert resp.status_code == 200
        refresh_token_str = resp.json()["refresh_token"]

        # Decode to get jti, then revoke it in DB
        refresh_payload = decode_token(
            refresh_token_str,
            client._transport.app.state.jwt_public_key,  # type: ignore[attr-defined]
        )
        result = await test_db_session.execute(
            select(RefreshToken).where(RefreshToken.jti == refresh_payload["jti"])
        )
        row = result.scalar_one_or_none()
        assert row is not None
        row.revoked_at = datetime.now(UTC)
        await test_db_session.commit()

        # Try to refresh — should be rejected
        resp2 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token_str},
        )
        assert resp2.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_rotates_jti(self, client, seeded_tenant, test_db_session):
        """Successful refresh should revoke old jti and record new one."""
        from sqlalchemy import select

        from sporedb.cloud.db.models import RefreshToken

        # Login
        resp = await client.post(
            "/api/v1/auth/login",
            params={"tenant_slug": "test-org"},
            json={"email": "editor@example.com", "password": "testpassword"},
        )
        old_refresh = resp.json()["refresh_token"]
        old_payload = decode_token(
            old_refresh,
            client._transport.app.state.jwt_public_key,  # type: ignore[attr-defined]
        )

        # Refresh
        resp2 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp2.status_code == 200
        new_refresh = resp2.json()["refresh_token"]
        new_payload = decode_token(
            new_refresh,
            client._transport.app.state.jwt_public_key,  # type: ignore[attr-defined]
        )

        # Old jti should be revoked
        result = await test_db_session.execute(
            select(RefreshToken).where(RefreshToken.jti == old_payload["jti"])
        )
        old_row = result.scalar_one_or_none()
        assert old_row is not None
        assert old_row.revoked_at is not None
        assert old_row.replaced_by == new_payload["jti"]

        # New jti should exist and not be revoked
        result2 = await test_db_session.execute(
            select(RefreshToken).where(RefreshToken.jti == new_payload["jti"])
        )
        new_row = result2.scalar_one_or_none()
        assert new_row is not None
        assert new_row.revoked_at is None
