"""Ed25519 key management and digital signing for audit trail entries.

Provides key generation, loading, signing, and verification using
Ed25519 signatures from the ``cryptography`` library. Private keys
are stored with restrictive file permissions (0o600).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

if TYPE_CHECKING:
    from sporedb.compliance.audit import AuditEntry

_PRIVATE_KEY_FILE = "signing_key.pem"
_PUBLIC_KEY_FILE = "signing_key.pub"


def generate_keypair(key_dir: Path) -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Generate an Ed25519 keypair and persist to *key_dir*.

    The private key is saved as ``signing_key.pem`` with mode 0o600.
    The public key is saved as ``signing_key.pub``.

    Returns the (private_key, public_key) tuple.
    """
    key_dir.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Write private key with restricted permissions
    private_path = key_dir / _PRIVATE_KEY_FILE
    passphrase = os.environ.get("SPOREDB_SIGNING_KEY_PASSPHRASE", "").encode()
    encryption_algorithm = (
        serialization.BestAvailableEncryption(passphrase)
        if passphrase
        else serialization.NoEncryption()
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption_algorithm,
    )
    private_path.write_bytes(private_pem)
    private_path.chmod(0o600)

    # Write public key
    public_path = key_dir / _PUBLIC_KEY_FILE
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path.write_bytes(public_pem)

    return private_key, public_key


def load_private_key(key_dir: Path) -> Ed25519PrivateKey:
    """Load the Ed25519 private key from *key_dir*/signing_key.pem."""
    private_path = key_dir / _PRIVATE_KEY_FILE
    private_pem = private_path.read_bytes()
    passphrase = os.environ.get("SPOREDB_SIGNING_KEY_PASSPHRASE", "").encode() or None
    key = serialization.load_pem_private_key(private_pem, password=passphrase)
    if not isinstance(key, Ed25519PrivateKey):
        msg = f"Expected Ed25519PrivateKey, got {type(key).__name__}"
        raise TypeError(msg)
    return key


def load_public_key(key_dir: Path) -> Ed25519PublicKey:
    """Load the Ed25519 public key from *key_dir*/signing_key.pub."""
    public_path = key_dir / _PUBLIC_KEY_FILE
    public_pem = public_path.read_bytes()
    key = serialization.load_pem_public_key(public_pem)
    if not isinstance(key, Ed25519PublicKey):
        msg = f"Expected Ed25519PublicKey, got {type(key).__name__}"
        raise TypeError(msg)
    return key


def sign_entry(entry: AuditEntry, private_key: Ed25519PrivateKey) -> AuditEntry:
    """Sign *entry* in place using Ed25519 and return it.

    Signs ``entry.canonical_bytes()`` and stores the raw signature
    in ``entry.signature``.
    """
    signature = private_key.sign(entry.canonical_bytes())
    entry.signature = signature
    return entry


def verify_entry(entry: AuditEntry, public_key: Ed25519PublicKey) -> bool:
    """Verify *entry*'s Ed25519 signature.

    Returns ``True`` if valid, ``False`` if the signature does not match.
    """
    try:
        public_key.verify(entry.signature, entry.canonical_bytes())
        return True
    except InvalidSignature:
        return False
