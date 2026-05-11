"""Compliance validator for FDA 21 CFR Part 11 and EU Annex 11.

Reads the audit trail from Parquet and verifies hash chain integrity,
Ed25519 signatures, Merkle tree consistency, field completeness, and
access control structure. Produces a :class:`ComplianceReport` mapping
each check to a specific regulatory checklist item.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import BaseModel, Field
from uuid_utils import uuid7

from sporedb.compliance.audit import AuditAction, AuditEntry, _deserialize_entry
from sporedb.compliance.checklist import get_checklist
from sporedb.compliance.merkle import MerkleCheckpointer
from sporedb.compliance.signing import verify_entry
from sporedb.storage.engine import StorageEngine
from sporedb.storage.parquet_layout import ParquetLayout

try:
    import pyarrow.parquet as pq

    from sporedb.compliance.audit import _AUDIT_SCHEMA
except ImportError:  # pragma: no cover
    pq = None  # type: ignore[assignment]


class CheckStatus(StrEnum):
    """Result status for a single compliance check."""

    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NOT_APPLICABLE = "not_applicable"
    ERROR = "error"


class CheckResult(BaseModel):
    """Outcome of a single compliance checklist verification."""

    item_id: str
    status: CheckStatus
    evidence: str
    details: str = ""


class ComplianceReport(BaseModel):
    """Full compliance validation report."""

    report_id: str = Field(default_factory=lambda: str(uuid7()))
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    regulation: str
    total_entries_checked: int
    results: list[CheckResult]
    overall_status: CheckStatus
    summary: str


class ComplianceValidator:
    """Validates an audit trail against regulatory checklists.

    Parameters
    ----------
    engine:
        Storage engine whose data root contains the audit trail.
    public_key:
        Optional Ed25519 public key for signature verification.
        If ``None``, the validator extracts keys from each entry's
        ``public_key_pem`` field.
    """

    def __init__(
        self,
        engine: StorageEngine,
        public_key: Ed25519PublicKey | None = None,
    ) -> None:
        self._engine = engine
        self._layout = ParquetLayout(engine.data_root)
        self._public_key = public_key

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_entries(self) -> list[AuditEntry]:
        """Read audit entries directly from the Parquet trail file."""
        path = self._layout.audit_trail_file()
        if not path.exists():
            return []
        table = pq.read_table(path, schema=_AUDIT_SCHEMA)  # type: ignore[no-untyped-call]
        df = table.to_pandas()
        return [_deserialize_entry(row.to_dict()) for _, row in df.iterrows()]

    def _check_hash_chain(self, entries: list[AuditEntry]) -> CheckResult:
        if not entries:
            return CheckResult(
                item_id="hash_chain",
                status=CheckStatus.NOT_APPLICABLE,
                evidence="No audit entries to verify",
            )
        if entries[0].previous_entry_hash != "":
            return CheckResult(
                item_id="hash_chain",
                status=CheckStatus.FAIL,
                evidence="First entry has non-empty previous_entry_hash",
                details=f"Found: {entries[0].previous_entry_hash!r}",
            )
        for i in range(1, len(entries)):
            expected = entries[i - 1].compute_hash()
            if entries[i].previous_entry_hash != expected:
                return CheckResult(
                    item_id="hash_chain",
                    status=CheckStatus.FAIL,
                    evidence=f"Hash chain broken at entry {i}",
                    details=(
                        f"Expected previous_entry_hash={expected!r}, "
                        f"got {entries[i].previous_entry_hash!r}"
                    ),
                )
        return CheckResult(
            item_id="hash_chain",
            status=CheckStatus.PASS,
            evidence=f"SHA-256 hash chain intact across {len(entries)} entries",
        )

    def _check_signatures(self, entries: list[AuditEntry]) -> CheckResult:
        if not entries:
            return CheckResult(
                item_id="signature",
                status=CheckStatus.NOT_APPLICABLE,
                evidence="No audit entries to verify",
            )
        signed = [e for e in entries if e.signature and e.signature != b""]
        if not signed:
            return CheckResult(
                item_id="signature",
                status=CheckStatus.NOT_APPLICABLE,
                evidence="No signed entries found",
            )
        for idx, entry in enumerate(signed):
            try:
                if self._public_key:
                    pk = self._public_key
                elif entry.public_key_pem:
                    # WARNING: using embedded key from the entry itself.
                    # This only detects signature/content mismatch, NOT
                    # key substitution attacks. Provide an external public
                    # key for full tamper detection. (CR-05)
                    logging.getLogger(__name__).warning(
                        "No external public key provided; using embedded key "
                        "from entry %d. This does NOT protect against key "
                        "substitution attacks.",
                        idx,
                    )
                    pk = load_pem_public_key(entry.public_key_pem.encode())  # type: ignore[assignment]
                else:
                    return CheckResult(
                        item_id="signature",
                        status=CheckStatus.FAIL,
                        evidence="No trusted public key available for verification",
                    )
                if not verify_entry(entry, pk):
                    return CheckResult(
                        item_id="signature",
                        status=CheckStatus.FAIL,
                        evidence=f"Invalid signature on entry {idx}",
                    )
            except Exception as exc:
                return CheckResult(
                    item_id="signature",
                    status=CheckStatus.FAIL,
                    evidence=f"Signature verification error on entry {idx}",
                    details=str(exc),
                )
        return CheckResult(
            item_id="signature",
            status=CheckStatus.PASS,
            evidence=f"All {len(signed)} Ed25519 signatures verified",
        )

    def _check_merkle_consistency(self, entries: list[AuditEntry]) -> CheckResult:
        if not entries:
            return CheckResult(
                item_id="merkle",
                status=CheckStatus.NOT_APPLICABLE,
                evidence="No audit entries for Merkle tree",
            )
        try:
            mc = MerkleCheckpointer(self._engine)
            mc.build_from_entries(entries)
            if mc.get_size() != len(entries):
                return CheckResult(
                    item_id="merkle",
                    status=CheckStatus.FAIL,
                    evidence=(
                        f"Merkle tree size {mc.get_size()} != "
                        f"entry count {len(entries)}"
                    ),
                )
            return CheckResult(
                item_id="merkle",
                status=CheckStatus.PASS,
                evidence=(
                    f"Merkle tree consistent: {mc.get_size()} leaves "
                    f"match {len(entries)} entries"
                ),
            )
        except Exception as exc:
            return CheckResult(
                item_id="merkle",
                status=CheckStatus.ERROR,
                evidence="Merkle consistency check error",
                details=str(exc),
            )

    def _check_field_completeness(
        self,
        entries: list[AuditEntry],
        required_fields: list[str],
    ) -> CheckResult:
        if not entries:
            return CheckResult(
                item_id="field_completeness",
                status=CheckStatus.NOT_APPLICABLE,
                evidence="No audit entries to check",
            )
        missing: list[str] = []
        # Fields that are legitimately empty for certain actions
        action_exempt: dict[str, set[str]] = {
            "create": {"old_value_hash"},
            "delete": {"new_value_hash"},
        }
        for idx, entry in enumerate(entries):
            data = entry.model_dump()
            action_val = (
                entry.action.value
                if hasattr(entry.action, "value")
                else str(entry.action)
            )
            exempt = action_exempt.get(action_val, set())
            for field in required_fields:
                if field in exempt:
                    continue
                val = data.get(field)
                if val is None or val == "" or val == b"":
                    missing.append(f"entry {idx}: {field}")
        if missing:
            return CheckResult(
                item_id="field_completeness",
                status=CheckStatus.FAIL,
                evidence=f"Missing fields in {len(missing)} cases",
                details="; ".join(missing[:10]),
            )
        return CheckResult(
            item_id="field_completeness",
            status=CheckStatus.PASS,
            evidence=(
                f"All {len(required_fields)} required fields present "
                f"in {len(entries)} entries"
            ),
        )

    def _check_audit_entry_format(self, entries: list[AuditEntry]) -> CheckResult:
        if not entries:
            return CheckResult(
                item_id="audit_entry_format",
                status=CheckStatus.NOT_APPLICABLE,
                evidence="No audit entries to check",
            )
        issues: list[str] = []
        for idx, entry in enumerate(entries):
            try:
                UUID(str(entry.entry_id))
            except (ValueError, AttributeError):
                issues.append(f"entry {idx}: invalid UUID entry_id")
            if entry.timestamp.tzinfo is None:
                issues.append(f"entry {idx}: timestamp not timezone-aware")
            if not entry.user_id:
                issues.append(f"entry {idx}: empty user_id")
            if not isinstance(entry.action, AuditAction):
                issues.append(f"entry {idx}: invalid action type")
        if issues:
            return CheckResult(
                item_id="audit_entry_format",
                status=CheckStatus.FAIL,
                evidence=f"Format issues in {len(issues)} entries",
                details="; ".join(issues[:10]),
            )
        return CheckResult(
            item_id="audit_entry_format",
            status=CheckStatus.PASS,
            evidence=(
                f"All {len(entries)} entries have valid UUID, "
                f"UTC timestamp, user_id, action"
            ),
        )

    def _check_access_control(self) -> CheckResult:
        """Verify RBAC is configured with valid user roles."""
        try:
            from sporedb.compliance.user_store import UserStore

            user_store = UserStore(self._engine)
            users = user_store.list_users()
            if not users:
                return CheckResult(
                    item_id="access_control",
                    status=CheckStatus.WARNING,
                    evidence="No users found in user store. RBAC not configured.",
                )
            roles_found = {u.role.value for u in users}
            has_admin = "admin" in roles_found
            if not has_admin:
                return CheckResult(
                    item_id="access_control",
                    status=CheckStatus.WARNING,
                    evidence=f"No admin user found. Roles present: {roles_found}",
                )
            return CheckResult(
                item_id="access_control",
                status=CheckStatus.PASS,
                evidence=f"RBAC configured: {len(users)} users, roles: {roles_found}",
            )
        except Exception as exc:
            return CheckResult(
                item_id="access_control",
                status=CheckStatus.FAIL,
                evidence=f"Could not verify access control: {exc}",
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, regulation: str | None = None) -> ComplianceReport:
        """Run all checklist verifications and produce a report.

        Parameters
        ----------
        regulation:
            ``"21_CFR_Part_11"``, ``"EU_Annex_11"``, or ``None`` for
            combined. Passed to :func:`get_checklist`.
        """
        entries = self._read_entries()
        checklist = get_checklist(regulation)

        # Cache results by verification_type to avoid redundant checks
        cache: dict[str, CheckResult] = {}
        results: list[CheckResult] = []

        for item in checklist:
            vtype = item.verification_type
            cache_key = vtype
            if vtype == "field_completeness":
                cache_key = f"{vtype}:{','.join(item.required_fields)}"

            if cache_key not in cache:
                if vtype == "hash_chain":
                    cache[cache_key] = self._check_hash_chain(entries)
                elif vtype == "signature":
                    cache[cache_key] = self._check_signatures(entries)
                elif vtype == "merkle":
                    cache[cache_key] = self._check_merkle_consistency(entries)
                elif vtype == "field_completeness":
                    cache[cache_key] = self._check_field_completeness(
                        entries, item.required_fields
                    )
                elif vtype == "audit_entry_format":
                    cache[cache_key] = self._check_audit_entry_format(entries)
                elif vtype == "access_control":
                    cache[cache_key] = self._check_access_control()
                else:
                    cache[cache_key] = CheckResult(
                        item_id=item.item_id,
                        status=CheckStatus.ERROR,
                        evidence=f"Unknown verification type: {vtype}",
                    )

            base = cache[cache_key]
            results.append(
                CheckResult(
                    item_id=item.item_id,
                    status=base.status,
                    evidence=base.evidence,
                    details=base.details,
                )
            )

        passed = sum(1 for r in results if r.status == CheckStatus.PASS)
        failed = sum(1 for r in results if r.status == CheckStatus.FAIL)
        warnings = sum(1 for r in results if r.status == CheckStatus.WARNING)
        errors = sum(1 for r in results if r.status == CheckStatus.ERROR)
        na = sum(1 for r in results if r.status == CheckStatus.NOT_APPLICABLE)
        if failed > 0 or errors > 0:
            overall = CheckStatus.FAIL
        elif warnings > 0:
            overall = CheckStatus.WARNING
        else:
            overall = CheckStatus.PASS
        reg_label = regulation or "21_CFR_Part_11+EU_Annex_11"

        return ComplianceReport(
            regulation=reg_label,
            total_entries_checked=len(entries),
            results=results,
            overall_status=overall,
            summary=(
                f"Compliance validation {overall.value.upper()}: "
                f"{passed} checks passed, {failed} failed, "
                f"{na} not applicable out of {len(results)} "
                f"checklist items."
            ),
        )
