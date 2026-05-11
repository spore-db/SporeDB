"""Electronic signatures per FDA 21 CFR Part 11.

Implements electronic signatures satisfying:
- 11.50: Signature includes printed name, date/time, and meaning
- 11.70: Signature cryptographically linked to signed record via JWT+Ed25519
- 11.100: Each signature uniquely tied to signer identity
- 11.200: Signing requires re-authentication (password verification)

Signatures are JWT tokens signed with Ed25519 (EdDSA algorithm) that bind
the signer identity, meaning, and timestamp to a specific record version
identified by its SHA-256 hash.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, Field
from uuid_utils import uuid7

from sporedb.compliance.audit import AuditAction, AuditEntry, AuditTrailWriter
from sporedb.compliance.rbac import Permission, check_permission
from sporedb.compliance.user_store import UserStore


class SignatureMeaning(StrEnum):
    """The meaning conveyed by an electronic signature per FDA 11.50."""

    APPROVED = "approved"
    REVIEWED = "reviewed"
    VERIFIED = "verified"
    RELEASED = "released"
    REJECTED = "rejected"


class ElectronicSignature(BaseModel):
    """An electronic signature binding signer identity to a record.

    Captures signer name, ID, meaning, and timestamp per FDA 11.50,
    with a JWT token providing cryptographic non-repudiation per 11.70.
    """

    signature_id: str = Field(default_factory=lambda: str(uuid7()))
    signer_name: str
    signer_id: str
    meaning: SignatureMeaning
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    record_type: str
    record_id: str
    record_hash: str
    signature_token: str = ""


def create_signature_jwt(
    signature: ElectronicSignature,
    private_key: Ed25519PrivateKey,
) -> str:
    """Create a JWT binding the electronic signature to the signed record.

    The JWT payload includes signer identity, meaning, timestamp, and
    record hash. Signed with Ed25519 (EdDSA algorithm) for non-repudiation.
    """
    # Derive kid from PUBLIC key, not private key (CR-01)
    pub_pem_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    iat = int(signature.timestamp.timestamp())
    kid = hashlib.sha256(pub_pem_bytes).hexdigest()[:16]
    payload = {
        "sub": signature.signer_id,
        "name": signature.signer_name,
        "meaning": signature.meaning.value,
        "iat": iat,
        "nbf": iat,
        "exp": iat
        + (
            365 * 24 * 3600
        ),  # 1-year validity; re-sign records before expiry for long-term retention
        "sig_id": signature.signature_id,
        "record_type": signature.record_type,
        "record_id": signature.record_id,
        "record_hash": signature.record_hash,
    }
    return jwt.encode(payload, pem_bytes, algorithm="EdDSA", headers={"kid": kid})


def verify_signature_jwt(
    token: str,
    public_key: Ed25519PublicKey,
) -> dict[str, object]:
    """Verify a signature JWT and return the decoded payload.

    Raises jwt.exceptions.InvalidSignatureError if the token was
    signed with a different key. Other jwt.exceptions may be raised
    for malformed or expired tokens.
    """
    pem_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return jwt.decode(token, pem_bytes, algorithms=["EdDSA"])


def sign_record(
    user_id: str,
    password: str,
    meaning: SignatureMeaning,
    record_type: str,
    record_id: str,
    record_hash: str,
    user_store: UserStore,
    audit_writer: AuditTrailWriter,
    private_key: Ed25519PrivateKey,
) -> ElectronicSignature:
    """Apply an electronic signature to a record with re-authentication.

    Workflow per FDA 21 CFR Part 11:
    1. Fetch user and verify active status
    2. Re-authenticate signer (11.200) via password verification
    3. Check SIGN permission (11.10(d))
    4. Create signature with identity, meaning, timestamp (11.50)
    5. Bind to record via JWT+Ed25519 (11.70)
    6. Record signing action in audit trail

    Raises:
        PermissionError: If user is deactivated, password is wrong,
            or user lacks SIGN permission.
        ValueError: If user_id is not found.
    """
    # Step 1: Get user first to make auth + permission check atomic
    user = user_store.get_user(user_id)
    if user is None:
        msg = f"User {user_id} not found"
        raise ValueError(msg)

    # Check active status before password verification
    if not user.active:
        msg = f"User {user_id} is deactivated"
        raise PermissionError(msg)

    # Step 2: Re-authenticate (FDA 11.200)
    if not user_store.verify_password(user_id, password):
        msg = "Re-authentication failed: invalid password"
        raise PermissionError(msg)

    # Step 3: Check SIGN permission (uses already-fetched user object)
    check_permission(user, Permission.SIGN)

    # Step 4: Create signature
    sig = ElectronicSignature(
        signer_name=user.name,
        signer_id=user.user_id,
        meaning=meaning,
        record_type=record_type,
        record_id=record_id,
        record_hash=record_hash,
    )

    # Step 5: Create JWT
    token = create_signature_jwt(sig, private_key)
    sig.signature_token = token

    # Step 6: Audit trail entry
    entry = AuditEntry(
        user_id=user_id,
        action=AuditAction.SIGN,
        entity_type=record_type,
        entity_id=record_id,
        old_value_hash=record_hash,
        new_value_hash=record_hash,
        reason=f"E-signature: {meaning.value} by {user.name}",
    )
    audit_writer.append(entry)

    # Step 7: Return
    return sig
