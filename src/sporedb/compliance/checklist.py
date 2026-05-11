"""FDA 21 CFR Part 11 and EU Annex 11 regulatory checklist definitions.

Static data following the ``vocabulary.py`` pattern: each checklist item
maps a regulatory requirement to a verification type that the
:class:`~sporedb.compliance.validator.ComplianceValidator` can execute
programmatically.
"""

from __future__ import annotations

import copy

from pydantic import BaseModel


class ChecklistItem(BaseModel):
    """A single regulatory checklist requirement.

    Each item maps a regulatory section to a programmatic verification
    type so the compliance validator can automatically check it.
    """

    item_id: str
    """Unique identifier, e.g. ``"CFR11-10e"`` or ``"AX11-9"``."""

    regulation: str
    """Regulation name: ``"21_CFR_Part_11"`` or ``"EU_Annex_11"``."""

    section: str
    """Regulatory section reference, e.g. ``"11.10(e)"``."""

    requirement: str
    """Human-readable requirement text."""

    verification_type: str
    """One of: ``hash_chain``, ``signature``, ``merkle``,
    ``field_completeness``, ``access_control``, ``audit_entry_format``."""

    required_fields: list[str] = []
    """AuditEntry fields that must be non-empty for this check."""

    description: str
    """What the validator checks for this item."""


# ---------------------------------------------------------------------------
# FDA 21 CFR Part 11
# ---------------------------------------------------------------------------

CHECKLIST_21CFR11: list[ChecklistItem] = [
    ChecklistItem(
        item_id="CFR11-10d",
        regulation="21_CFR_Part_11",
        section="11.10(d)",
        requirement="Limit system access to authorized individuals",
        verification_type="access_control",
        description=("RBAC enforces viewer/editor/admin roles on all operations"),
    ),
    ChecklistItem(
        item_id="CFR11-10e",
        regulation="21_CFR_Part_11",
        section="11.10(e)",
        requirement="Secure, computer-generated, time-stamped audit trail",
        verification_type="audit_entry_format",
        required_fields=[
            "entry_id",
            "timestamp",
            "user_id",
            "action",
            "entity_type",
            "entity_id",
        ],
        description=(
            "Every audit entry has UUIDv7 ID, UTC timestamp, user ID, action type"
        ),
    ),
    ChecklistItem(
        item_id="CFR11-10f",
        regulation="21_CFR_Part_11",
        section="11.10(f)",
        requirement="Operational system checks for sequencing",
        verification_type="hash_chain",
        description=(
            "SHA-256 hash chain enforces entry ordering; each entry "
            "references previous entry hash"
        ),
    ),
    ChecklistItem(
        item_id="CFR11-10g",
        regulation="21_CFR_Part_11",
        section="11.10(g)",
        requirement="Authority checks",
        verification_type="access_control",
        description=("Permission checks before write operations via RBAC"),
    ),
    ChecklistItem(
        item_id="CFR11-10k",
        regulation="21_CFR_Part_11",
        section="11.10(k)",
        requirement="Audit trail for record changes",
        verification_type="field_completeness",
        required_fields=[
            "old_value_hash",
            "new_value_hash",
            "user_id",
            "timestamp",
            "reason",
        ],
        description=(
            "Audit entries capture old/new value hashes, user, timestamp, "
            "and reason for change"
        ),
    ),
    ChecklistItem(
        item_id="CFR11-50",
        regulation="21_CFR_Part_11",
        section="11.50",
        requirement="Signature manifestation: name, date/time, meaning",
        verification_type="signature",
        description=(
            "Electronic signatures include signer name, timestamp, and "
            "meaning (approved/reviewed/verified/released/rejected)"
        ),
    ),
    ChecklistItem(
        item_id="CFR11-70",
        regulation="21_CFR_Part_11",
        section="11.70",
        requirement="Signatures linked to records",
        verification_type="signature",
        description=(
            "JWT cryptographically binds signature to record hash; "
            "signature cannot be excised"
        ),
    ),
    ChecklistItem(
        item_id="CFR11-100",
        regulation="21_CFR_Part_11",
        section="11.100",
        requirement="Unique to one individual",
        verification_type="access_control",
        description=("User model enforces unique user_id; no shared accounts"),
    ),
    ChecklistItem(
        item_id="CFR11-200",
        regulation="21_CFR_Part_11",
        section="11.200",
        requirement="Two identification components at signing",
        verification_type="signature",
        description=(
            "sign_record requires password re-entry for verification at signing time"
        ),
    ),
]

# ---------------------------------------------------------------------------
# EU Annex 11
# ---------------------------------------------------------------------------

CHECKLIST_ANNEX11: list[ChecklistItem] = [
    ChecklistItem(
        item_id="AX11-9",
        regulation="EU_Annex_11",
        section="Clause 9",
        requirement="Audit trail based on risk assessment",
        verification_type="audit_entry_format",
        description=(
            "All GMP-relevant changes logged (write operations on batch data)"
        ),
    ),
    ChecklistItem(
        item_id="AX11-12.1",
        regulation="EU_Annex_11",
        section="Clause 12.1",
        requirement="Security measures for data and changes",
        verification_type="hash_chain",
        description=("Ed25519 signatures, SHA-256 hash chain integrity, RBAC"),
    ),
    ChecklistItem(
        item_id="AX11-12.4",
        regulation="EU_Annex_11",
        section="Clause 12.4",
        requirement="Audit trail available in intelligible form",
        verification_type="field_completeness",
        description=(
            "Compliance report outputs human-readable results with pass/fail per item"
        ),
    ),
    ChecklistItem(
        item_id="AX11-14",
        regulation="EU_Annex_11",
        section="Clause 14",
        requirement=("Electronic signatures with same impact as handwritten"),
        verification_type="signature",
        description=(
            "ElectronicSignature with identity + meaning + timestamp "
            "+ cryptographic binding"
        ),
    ),
]


def get_checklist(regulation: str | None = None) -> list[ChecklistItem]:
    """Return regulatory checklist items.

    Parameters
    ----------
    regulation:
        ``"21_CFR_Part_11"`` for FDA items only,
        ``"EU_Annex_11"`` for EU items only,
        or ``None`` for the combined list.

    Raises
    ------
    ValueError
        If *regulation* is not a recognised value.
    """
    if regulation is None:
        return copy.deepcopy(CHECKLIST_21CFR11) + copy.deepcopy(CHECKLIST_ANNEX11)
    if regulation == "21_CFR_Part_11":
        return copy.deepcopy(CHECKLIST_21CFR11)
    if regulation == "EU_Annex_11":
        return copy.deepcopy(CHECKLIST_ANNEX11)
    msg = f"Unknown regulation: {regulation}"
    raise ValueError(msg)
