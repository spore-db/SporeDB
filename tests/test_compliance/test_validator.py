"""Tests for COMPL-04: Compliance validator and regulatory checklists."""

import pytest

from sporedb.compliance.audit import AuditAction, AuditEntry, AuditTrailWriter
from sporedb.compliance.checklist import (
    CHECKLIST_21CFR11,
    CHECKLIST_ANNEX11,
    get_checklist,
)
from sporedb.compliance.rbac import Role
from sporedb.compliance.signing import generate_keypair
from sporedb.compliance.user_store import UserStore
from sporedb.compliance.validator import (
    CheckStatus,
    ComplianceValidator,
)
from sporedb.storage.engine import StorageEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def populated_audit_trail(tmp_path):
    """Engine with 5 diverse audit entries for validation tests."""
    data_root = tmp_path / "validator_data"
    data_root.mkdir()
    engine = StorageEngine(data_root)

    key_dir = tmp_path / "keys"
    private_key, public_key = generate_keypair(key_dir)
    writer = AuditTrailWriter(engine, private_key)

    writer.append(
        AuditEntry(
            user_id="user-001",
            action=AuditAction.CREATE,
            entity_type="batch",
            entity_id="batch-001",
            new_value_hash="a" * 64,
            reason="Initial batch creation",
        )
    )
    writer.append(
        AuditEntry(
            user_id="user-001",
            action=AuditAction.UPDATE,
            entity_type="batch",
            entity_id="batch-001",
            old_value_hash="a" * 64,
            new_value_hash="b" * 64,
            reason="Updated metadata",
        )
    )
    writer.append(
        AuditEntry(
            user_id="user-002",
            action=AuditAction.CREATE,
            entity_type="telemetry",
            entity_id="tel-001",
            new_value_hash="c" * 64,
            reason="Telemetry upload",
        )
    )
    writer.append(
        AuditEntry(
            user_id="user-001",
            action=AuditAction.SIGN,
            entity_type="batch",
            entity_id="batch-001",
            old_value_hash="b" * 64,
            new_value_hash="b" * 64,
            reason="E-signature: approved by User 1",
        )
    )
    writer.append(
        AuditEntry(
            user_id="user-003",
            action=AuditAction.DELETE,
            entity_type="assay",
            entity_id="assay-001",
            old_value_hash="d" * 64,
            new_value_hash="",
            reason="Removed erroneous assay data",
        )
    )

    yield {"engine": engine, "public_key": public_key, "writer": writer}
    engine.close()


@pytest.fixture
def empty_engine(tmp_path):
    """Engine with no audit entries."""
    data_root = tmp_path / "empty_data"
    data_root.mkdir()
    engine = StorageEngine(data_root)
    yield engine
    engine.close()


# ---------------------------------------------------------------------------
# TestChecklistData
# ---------------------------------------------------------------------------


class TestChecklistData:
    def test_21cfr11_has_9_items(self):
        assert len(CHECKLIST_21CFR11) == 9

    def test_annex11_has_4_items(self):
        assert len(CHECKLIST_ANNEX11) == 4

    def test_all_items_have_required_fields(self):
        for item in get_checklist():
            assert item.item_id, f"Missing item_id: {item}"
            assert item.regulation, f"Missing regulation: {item.item_id}"
            assert item.section, f"Missing section: {item.item_id}"
            assert item.requirement, f"Missing requirement: {item.item_id}"
            assert item.verification_type, f"Missing verification_type: {item.item_id}"

    def test_get_checklist_combined(self):
        assert len(get_checklist()) == 13

    def test_get_checklist_filtered(self):
        assert len(get_checklist("21_CFR_Part_11")) == 9

    def test_get_checklist_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown regulation"):
            get_checklist("unknown")


# ---------------------------------------------------------------------------
# TestComplianceValidator
# ---------------------------------------------------------------------------


class TestComplianceValidator:
    def test_validate_intact_trail_passes(self, populated_audit_trail):
        s = populated_audit_trail
        validator = ComplianceValidator(s["engine"], s["public_key"])
        report = validator.validate()
        # WARNING is acceptable -- trail is intact but access_control may warn
        assert report.overall_status in (CheckStatus.PASS, CheckStatus.WARNING)

    def test_validate_empty_trail(self, empty_engine):
        validator = ComplianceValidator(empty_engine)
        report = validator.validate()
        # With no entries, checks are NOT_APPLICABLE; access control warns
        assert report.overall_status in (CheckStatus.PASS, CheckStatus.WARNING)
        na_count = sum(
            1 for r in report.results if r.status == CheckStatus.NOT_APPLICABLE
        )
        assert na_count > 0

    def test_hash_chain_check_passes(self, populated_audit_trail):
        s = populated_audit_trail
        validator = ComplianceValidator(s["engine"], s["public_key"])
        report = validator.validate("21_CFR_Part_11")
        cfr10f = next(r for r in report.results if r.item_id == "CFR11-10f")
        assert cfr10f.status == CheckStatus.PASS

    def test_hash_chain_check_fails_on_tamper(self, populated_audit_trail):
        s = populated_audit_trail
        # Tamper: rewrite Parquet with corrupted previous_entry_hash
        import pyarrow.parquet as pq

        from sporedb.storage.parquet_layout import ParquetLayout

        layout = ParquetLayout(s["engine"].data_root)
        path = layout.audit_trail_file()
        table = pq.read_table(path)
        df = table.to_pandas()
        # Corrupt the second entry's previous_entry_hash
        df.at[1, "previous_entry_hash"] = "corrupted_hash_value"

        import pyarrow as pa

        new_table = pa.Table.from_pandas(df, schema=table.schema)
        pq.write_table(new_table, path)

        validator = ComplianceValidator(s["engine"], s["public_key"])
        report = validator.validate("21_CFR_Part_11")
        cfr10f = next(r for r in report.results if r.item_id == "CFR11-10f")
        assert cfr10f.status == CheckStatus.FAIL

    def test_signature_check_passes(self, populated_audit_trail):
        s = populated_audit_trail
        validator = ComplianceValidator(s["engine"], s["public_key"])
        report = validator.validate("21_CFR_Part_11")
        cfr50 = next(r for r in report.results if r.item_id == "CFR11-50")
        assert cfr50.status == CheckStatus.PASS

    def test_field_completeness_passes(self, populated_audit_trail):
        s = populated_audit_trail
        validator = ComplianceValidator(s["engine"], s["public_key"])
        report = validator.validate("21_CFR_Part_11")
        cfr10e = next(r for r in report.results if r.item_id == "CFR11-10e")
        assert cfr10e.status == CheckStatus.PASS

    def test_report_has_all_checklist_items(self, populated_audit_trail):
        s = populated_audit_trail
        validator = ComplianceValidator(s["engine"], s["public_key"])
        report = validator.validate()
        assert len(report.results) == len(get_checklist())

    def test_report_summary_human_readable(self, populated_audit_trail):
        s = populated_audit_trail
        validator = ComplianceValidator(s["engine"], s["public_key"])
        report = validator.validate()
        assert "Compliance validation" in report.summary

    def test_validate_21cfr_only(self, populated_audit_trail):
        s = populated_audit_trail
        validator = ComplianceValidator(s["engine"], s["public_key"])
        report = validator.validate(regulation="21_CFR_Part_11")
        assert len(report.results) == 9

    def test_validate_annex11_only(self, populated_audit_trail):
        s = populated_audit_trail
        validator = ComplianceValidator(s["engine"], s["public_key"])
        report = validator.validate(regulation="EU_Annex_11")
        assert len(report.results) == 4


# ---------------------------------------------------------------------------
# TestAccessControlCheck (MD-10)
# ---------------------------------------------------------------------------


class TestAccessControlCheck:
    def test_no_users_returns_warning(self, empty_engine):
        validator = ComplianceValidator(empty_engine)
        result = validator._check_access_control()
        assert result.status == CheckStatus.WARNING
        assert "No users found" in result.evidence

    def test_users_without_admin_returns_warning(self, tmp_path):
        data_root = tmp_path / "rbac_data"
        data_root.mkdir()
        engine = StorageEngine(data_root)
        try:
            us = UserStore(engine)
            us.create_user("viewer1", "v@test.com", Role.VIEWER, "Pass123!")
            validator = ComplianceValidator(engine)
            result = validator._check_access_control()
            assert result.status == CheckStatus.WARNING
            assert "No admin user found" in result.evidence
        finally:
            engine.close()

    def test_admin_user_returns_pass(self, tmp_path):
        data_root = tmp_path / "rbac_admin_data"
        data_root.mkdir()
        engine = StorageEngine(data_root)
        try:
            us = UserStore(engine)
            us.create_user("admin1", "a@test.com", Role.ADMIN, "Pass123!")
            validator = ComplianceValidator(engine)
            result = validator._check_access_control()
            assert result.status == CheckStatus.PASS
            assert "RBAC configured" in result.evidence
        finally:
            engine.close()
