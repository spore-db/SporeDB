"""Role-based access control for FDA 21 CFR Part 11 compliance.

Implements access controls per 11.10(d) (limiting system access to authorized
individuals) and 11.10(g) (authority checks on operations).

Roles: viewer (read-only), editor (read/write/sign), admin (full access).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field
from uuid_utils import uuid7


class Role(StrEnum):
    """User roles for RBAC. Maps to FDA 21 CFR Part 11 access levels."""

    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"


class Permission(StrEnum):
    """Granular permissions gated by role assignment."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SIGN = "sign"
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {Permission.READ},
    Role.EDITOR: {Permission.READ, Permission.WRITE, Permission.SIGN},
    Role.ADMIN: {
        Permission.READ,
        Permission.WRITE,
        Permission.DELETE,
        Permission.SIGN,
        Permission.MANAGE_USERS,
        Permission.MANAGE_ROLES,
    },
}


class User(BaseModel):
    """A SporeDB user with role-based access control.

    The password_hash field stores an argon2id hash set by UserStore.
    It is excluded from default serialization to prevent accidental exposure.
    """

    user_id: str = Field(default_factory=lambda: str(uuid7()))
    name: str
    email: str
    role: Role
    active: bool = True
    password_hash: str = Field(
        default="",
        # Excluded from model_dump() only; populated during model_validate()
        exclude=True,
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def check_permission(user: User, required: Permission) -> None:
    """Verify that a user has the required permission.

    Raises PermissionError if the user is deactivated or lacks the permission.
    Returns None on success (no exception = authorized).
    """
    if not user.active:
        msg = f"User {user.user_id} is deactivated"
        raise PermissionError(msg)

    granted = ROLE_PERMISSIONS.get(user.role, set())
    if required not in granted:
        msg = (
            f"User {user.user_id} ({user.role.value}) lacks {required.value} permission"
        )
        raise PermissionError(msg)


def has_permission(user: User, required: Permission) -> bool:
    """Check if a user has the required permission (non-raising variant).

    Returns True if user is active and has the required permission,
    False otherwise.
    """
    if not user.active:
        return False
    return required in ROLE_PERMISSIONS.get(user.role, set())
