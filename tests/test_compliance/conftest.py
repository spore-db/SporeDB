"""Shared fixtures for compliance tests."""

import pytest

from sporedb.compliance.audit import AuditAction, AuditEntry, AuditTrailWriter
from sporedb.compliance.signing import generate_keypair
from sporedb.storage.engine import StorageEngine


@pytest.fixture
def key_dir(tmp_path):
    return tmp_path / "keys"


@pytest.fixture
def signing_keypair(key_dir):
    return generate_keypair(key_dir)


@pytest.fixture
def private_key(signing_keypair):
    return signing_keypair[0]


@pytest.fixture
def public_key(signing_keypair):
    return signing_keypair[1]


@pytest.fixture
def audit_data_root(tmp_path):
    root = tmp_path / "sporedb_audit_data"
    root.mkdir()
    return root


@pytest.fixture
def audit_engine(audit_data_root):
    with StorageEngine(audit_data_root) as engine:
        yield engine


@pytest.fixture
def audit_writer(audit_engine, private_key):
    return AuditTrailWriter(audit_engine, private_key)


@pytest.fixture
def sample_audit_entry():
    return AuditEntry(
        user_id="user-001",
        action=AuditAction.CREATE,
        entity_type="batch",
        entity_id="batch-abc-123",
        new_value_hash="a" * 64,
    )
