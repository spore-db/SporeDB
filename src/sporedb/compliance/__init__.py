"""SporeDB compliance layer.

Covers: audit trail, signing, RBAC, e-signatures, and validation.
"""

from sporedb.compliance.audit import AuditAction, AuditEntry, AuditTrailWriter
from sporedb.compliance.checklist import (
    CHECKLIST_21CFR11,
    CHECKLIST_ANNEX11,
    ChecklistItem,
    get_checklist,
)
from sporedb.compliance.esignature import (
    ElectronicSignature,
    SignatureMeaning,
    create_signature_jwt,
    sign_record,
    verify_signature_jwt,
)
from sporedb.compliance.merkle import MerkleCheckpointer
from sporedb.compliance.rbac import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    User,
    check_permission,
    has_permission,
)
from sporedb.compliance.signing import (
    generate_keypair,
    load_private_key,
    load_public_key,
    sign_entry,
    verify_entry,
)
from sporedb.compliance.user_store import UserStore
from sporedb.compliance.validator import (
    CheckResult,
    CheckStatus,
    ComplianceReport,
    ComplianceValidator,
)

__all__ = [
    "AuditAction",
    "AuditEntry",
    "AuditTrailWriter",
    "CHECKLIST_21CFR11",
    "CHECKLIST_ANNEX11",
    "CheckResult",
    "CheckStatus",
    "ChecklistItem",
    "ComplianceReport",
    "ComplianceValidator",
    "ElectronicSignature",
    "MerkleCheckpointer",
    "Permission",
    "ROLE_PERMISSIONS",
    "Role",
    "SignatureMeaning",
    "User",
    "UserStore",
    "check_permission",
    "create_signature_jwt",
    "generate_keypair",
    "get_checklist",
    "has_permission",
    "load_private_key",
    "load_public_key",
    "sign_entry",
    "sign_record",
    "verify_entry",
    "verify_signature_jwt",
]
