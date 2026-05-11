"""JWT creation and validation for cloud authentication.

Uses Ed25519 (EdDSA algorithm) for token signing, consistent with the
compliance module's electronic-signature approach but scoped to cloud
session management (access + refresh tokens).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def create_access_token(
    tenant_id: str,
    user_id: str,
    email: str,
    role: str,
    private_key: Ed25519PrivateKey,
    expires_minutes: int = 15,
    active: bool = True,
) -> str:
    """Create a short-lived access token with tenant and user claims.

    Parameters
    ----------
    tenant_id:
        The tenant (organisation) this user belongs to.
    user_id:
        Unique user identifier (``sub`` claim).
    email:
        User email address.
    role:
        RBAC role name (viewer / editor / admin).
    private_key:
        Ed25519 private key used to sign the token.
    expires_minutes:
        Token lifetime in minutes.  Defaults to 15.

    Returns
    -------
    str
        Encoded JWT string.
    """
    now = datetime.now(UTC)
    pem_bytes = _private_key_pem(private_key)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "role": role,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "type": "access",
        "active": active,
        "iss": "sporedb-cloud",
        "aud": "sporedb-cloud",
    }
    return jwt.encode(payload, pem_bytes, algorithm="EdDSA")


def create_refresh_token(
    tenant_id: str,
    user_id: str,
    private_key: Ed25519PrivateKey,
    expires_days: int = 7,
    jti: str | None = None,
) -> str:
    """Create a long-lived refresh token for session extension.

    The refresh token carries minimal claims (no email/role) and is
    exchanged for a new access token at the ``/auth/refresh`` endpoint.

    Parameters
    ----------
    jti:
        JWT ID for token revocation tracking. If None, a UUIDv7 is generated.
    """
    from uuid_utils import uuid7

    now = datetime.now(UTC)
    pem_bytes = _private_key_pem(private_key)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "jti": jti or str(uuid7()),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(days=expires_days),
        "type": "refresh",
        "iss": "sporedb-cloud",
        "aud": "sporedb-cloud",
    }
    return jwt.encode(payload, pem_bytes, algorithm="EdDSA")


def decode_token(token: str, public_key: Ed25519PublicKey) -> dict[str, Any]:
    """Decode and validate a JWT signed with the corresponding Ed25519 key.

    Raises
    ------
    jwt.ExpiredSignatureError
        If the token has expired.
    jwt.InvalidTokenError
        If the token is malformed, tampered with, or signed with a
        different key.
    """
    pem_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return jwt.decode(
        token,
        pem_bytes,
        algorithms=["EdDSA"],
        issuer="sporedb-cloud",
        audience="sporedb-cloud",
    )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _private_key_pem(private_key: Ed25519PrivateKey) -> bytes:
    """Serialize an Ed25519 private key to PEM bytes."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
