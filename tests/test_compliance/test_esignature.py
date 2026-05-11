"""Tests for COMPL-02: Electronic signatures per FDA 21 CFR Part 11."""

import pytest

from sporedb.compliance.audit import AuditAction, AuditTrailWriter
from sporedb.compliance.esignature import (
    ElectronicSignature,
    SignatureMeaning,
    create_signature_jwt,
    sign_record,
    verify_signature_jwt,
)
from sporedb.compliance.rbac import Role
from sporedb.compliance.signing import generate_keypair
from sporedb.compliance.user_store import UserStore
from sporedb.storage.engine import StorageEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def esig_setup(tmp_path):
    """Full e-signature test rig: engine, user store, audit writer, keys."""
    data_root = tmp_path / "esig_data"
    data_root.mkdir()
    engine = StorageEngine(data_root)

    user_store = UserStore(engine)
    user = user_store.create_user(
        name="Jane Scientist",
        email="jane@lab.org",
        role=Role.EDITOR,
        password="SecurePass123!",
    )

    key_dir = tmp_path / "keys"
    private_key, public_key = generate_keypair(key_dir)
    audit_writer = AuditTrailWriter(engine, private_key)

    yield {
        "engine": engine,
        "user": user,
        "user_store": user_store,
        "audit_writer": audit_writer,
        "private_key": private_key,
        "public_key": public_key,
    }
    engine.close()


# ---------------------------------------------------------------------------
# TestElectronicSignatureModel
# ---------------------------------------------------------------------------


class TestElectronicSignatureModel:
    def test_signature_has_uuid_id(self):
        sig = ElectronicSignature(
            signer_name="Test",
            signer_id="u1",
            meaning=SignatureMeaning.APPROVED,
            record_type="batch",
            record_id="b1",
            record_hash="a" * 64,
        )
        assert sig.signature_id
        assert isinstance(sig.signature_id, str)
        assert len(sig.signature_id) > 0

    def test_signature_has_utc_timestamp(self):
        sig = ElectronicSignature(
            signer_name="Test",
            signer_id="u1",
            meaning=SignatureMeaning.REVIEWED,
            record_type="batch",
            record_id="b1",
            record_hash="b" * 64,
        )
        assert sig.timestamp.tzinfo is not None

    def test_meaning_enum_values(self):
        values = {m.value for m in SignatureMeaning}
        assert values == {"approved", "reviewed", "verified", "released", "rejected"}


# ---------------------------------------------------------------------------
# TestSignatureJWT
# ---------------------------------------------------------------------------


class TestSignatureJWT:
    def test_create_and_verify_jwt(self, private_key, public_key):
        sig = ElectronicSignature(
            signer_name="Alice",
            signer_id="user-alice",
            meaning=SignatureMeaning.APPROVED,
            record_type="batch",
            record_id="batch-001",
            record_hash="c" * 64,
        )
        token = create_signature_jwt(sig, private_key)
        payload = verify_signature_jwt(token, public_key)
        assert payload["sub"] == "user-alice"
        assert payload["name"] == "Alice"
        assert payload["meaning"] == "approved"
        assert payload["record_id"] == "batch-001"
        assert payload["record_hash"] == "c" * 64

    def test_jwt_contains_all_required_fields(self, private_key, public_key):
        sig = ElectronicSignature(
            signer_name="Bob",
            signer_id="user-bob",
            meaning=SignatureMeaning.VERIFIED,
            record_type="telemetry",
            record_id="tel-002",
            record_hash="d" * 64,
        )
        token = create_signature_jwt(sig, private_key)
        payload = verify_signature_jwt(token, public_key)
        required = {
            "sub",
            "name",
            "meaning",
            "iat",
            "record_type",
            "record_id",
            "record_hash",
        }
        assert required.issubset(payload.keys())

    def test_jwt_invalid_with_wrong_key(self, private_key, tmp_path):
        sig = ElectronicSignature(
            signer_name="Eve",
            signer_id="user-eve",
            meaning=SignatureMeaning.RELEASED,
            record_type="batch",
            record_id="batch-003",
            record_hash="e" * 64,
        )
        token = create_signature_jwt(sig, private_key)

        # Generate a different keypair
        other_dir = tmp_path / "other_keys"
        _, other_public = generate_keypair(other_dir)

        import jwt as pyjwt

        with pytest.raises(pyjwt.exceptions.InvalidSignatureError):
            verify_signature_jwt(token, other_public)

    def test_jwt_binds_to_record_hash(self, private_key, public_key):
        record_hash = "f" * 64
        sig = ElectronicSignature(
            signer_name="Carol",
            signer_id="user-carol",
            meaning=SignatureMeaning.APPROVED,
            record_type="assay",
            record_id="assay-004",
            record_hash=record_hash,
        )
        token = create_signature_jwt(sig, private_key)
        payload = verify_signature_jwt(token, public_key)
        assert payload["record_hash"] == record_hash


# ---------------------------------------------------------------------------
# TestSignRecord (integration)
# ---------------------------------------------------------------------------


class TestSignRecord:
    def test_sign_record_success(self, esig_setup):
        s = esig_setup
        result = sign_record(
            user_id=s["user"].user_id,
            password="SecurePass123!",
            meaning=SignatureMeaning.APPROVED,
            record_type="batch",
            record_id="batch-100",
            record_hash="a1" * 32,
            user_store=s["user_store"],
            audit_writer=s["audit_writer"],
            private_key=s["private_key"],
        )
        assert result.signature_token
        assert result.signer_name == "Jane Scientist"
        assert result.meaning == SignatureMeaning.APPROVED

    def test_sign_record_creates_audit_entry(self, esig_setup):
        s = esig_setup
        sign_record(
            user_id=s["user"].user_id,
            password="SecurePass123!",
            meaning=SignatureMeaning.REVIEWED,
            record_type="batch",
            record_id="batch-200",
            record_hash="b2" * 32,
            user_store=s["user_store"],
            audit_writer=s["audit_writer"],
            private_key=s["private_key"],
        )
        entries = s["audit_writer"].get_entries()
        assert len(entries) >= 1
        last = entries[-1]
        assert last.action == AuditAction.SIGN
        assert last.entity_id == "batch-200"

    def test_sign_record_requires_reauth(self, esig_setup):
        s = esig_setup
        with pytest.raises(PermissionError, match="Re-authentication failed"):
            sign_record(
                user_id=s["user"].user_id,
                password="WrongPass999",
                meaning=SignatureMeaning.APPROVED,
                record_type="batch",
                record_id="batch-300",
                record_hash="c3" * 32,
                user_store=s["user_store"],
                audit_writer=s["audit_writer"],
                private_key=s["private_key"],
            )

    def test_sign_record_requires_sign_permission(self, esig_setup):
        s = esig_setup
        # Create a viewer (no SIGN permission)
        viewer = s["user_store"].create_user(
            name="View Only",
            email="viewer@lab.org",
            role=Role.VIEWER,
            password="ViewerPass123!",
        )
        with pytest.raises(PermissionError):
            sign_record(
                user_id=viewer.user_id,
                password="ViewerPass123!",
                meaning=SignatureMeaning.APPROVED,
                record_type="batch",
                record_id="batch-400",
                record_hash="d4" * 32,
                user_store=s["user_store"],
                audit_writer=s["audit_writer"],
                private_key=s["private_key"],
            )

    def test_sign_record_jwt_verifiable(self, esig_setup):
        s = esig_setup
        result = sign_record(
            user_id=s["user"].user_id,
            password="SecurePass123!",
            meaning=SignatureMeaning.VERIFIED,
            record_type="batch",
            record_id="batch-500",
            record_hash="e5" * 32,
            user_store=s["user_store"],
            audit_writer=s["audit_writer"],
            private_key=s["private_key"],
        )
        payload = verify_signature_jwt(result.signature_token, s["public_key"])
        assert payload["record_hash"] == "e5" * 32

    def test_sign_record_deactivated_user_blocked(self, esig_setup):
        s = esig_setup
        s["user_store"].deactivate_user(s["user"].user_id)
        with pytest.raises(PermissionError):
            sign_record(
                user_id=s["user"].user_id,
                password="SecurePass123!",
                meaning=SignatureMeaning.APPROVED,
                record_type="batch",
                record_id="batch-600",
                record_hash="f6" * 32,
                user_store=s["user_store"],
                audit_writer=s["audit_writer"],
                private_key=s["private_key"],
            )
