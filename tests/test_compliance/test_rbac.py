"""Tests for RBAC models, permission guard, and JSON user store.

Covers COMPL-03: Role-based access control with viewer/editor/admin roles
and argon2id password hashing per FDA 21 CFR Part 11 sections 11.10(d)
and 11.10(g).
"""

from __future__ import annotations

import pytest

from sporedb.compliance.rbac import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    User,
    check_permission,
    has_permission,
)
from sporedb.compliance.user_store import UserStore
from sporedb.storage.engine import StorageEngine


@pytest.fixture
def user_store(data_root):
    """UserStore backed by a temporary data directory."""
    engine = StorageEngine(data_root)
    try:
        yield UserStore(engine)
    finally:
        engine.close()


def _make_user(role: Role, active: bool = True) -> User:
    """Helper to create a User with a given role."""
    return User(name="Test", email="test@example.com", role=role, active=active)


class TestRolePermissions:
    """Test that role-permission mappings enforce correct access."""

    def test_viewer_can_read(self):
        user = _make_user(Role.VIEWER)
        check_permission(user, Permission.READ)  # should not raise

    def test_viewer_cannot_write(self):
        user = _make_user(Role.VIEWER)
        with pytest.raises(PermissionError):
            check_permission(user, Permission.WRITE)

    def test_viewer_cannot_delete(self):
        user = _make_user(Role.VIEWER)
        with pytest.raises(PermissionError):
            check_permission(user, Permission.DELETE)

    def test_viewer_cannot_sign(self):
        user = _make_user(Role.VIEWER)
        with pytest.raises(PermissionError):
            check_permission(user, Permission.SIGN)

    def test_editor_can_read_write_sign(self):
        user = _make_user(Role.EDITOR)
        check_permission(user, Permission.READ)
        check_permission(user, Permission.WRITE)
        check_permission(user, Permission.SIGN)

    def test_editor_cannot_delete(self):
        user = _make_user(Role.EDITOR)
        with pytest.raises(PermissionError):
            check_permission(user, Permission.DELETE)

    def test_editor_cannot_manage_users(self):
        user = _make_user(Role.EDITOR)
        with pytest.raises(PermissionError):
            check_permission(user, Permission.MANAGE_USERS)

    def test_admin_has_all_permissions(self):
        user = _make_user(Role.ADMIN)
        for perm in Permission:
            check_permission(user, perm)  # should not raise for any

    def test_deactivated_user_blocked(self):
        user = _make_user(Role.ADMIN, active=False)
        with pytest.raises(PermissionError, match="deactivated"):
            check_permission(user, Permission.READ)

    def test_has_permission_returns_bool(self):
        viewer = _make_user(Role.VIEWER)
        assert has_permission(viewer, Permission.READ) is True
        assert has_permission(viewer, Permission.WRITE) is False

    def test_has_permission_deactivated_returns_false(self):
        user = _make_user(Role.ADMIN, active=False)
        assert has_permission(user, Permission.READ) is False

    def test_role_permissions_coverage(self):
        """Every role should have at least READ permission."""
        for role in Role:
            assert Permission.READ in ROLE_PERMISSIONS[role]


class TestUserStore:
    """Test JSON-backed user store with argon2id password hashing."""

    def test_create_user(self, user_store):
        user = user_store.create_user(
            name="Alice", email="alice@lab.com", role=Role.VIEWER, password="Pass123!"
        )
        assert user.name == "Alice"
        assert user.email == "alice@lab.com"
        assert user.role == Role.VIEWER
        assert user.active is True
        assert user.user_id  # non-empty

    def test_create_user_persists_to_json(self, user_store):
        user_store.create_user(
            name="Bob", email="bob@lab.com", role=Role.EDITOR, password="Pass123!"
        )
        store_path = user_store._store_path()
        assert store_path.exists()

    def test_get_user_by_id(self, user_store):
        created = user_store.create_user(
            name="Carol", email="carol@lab.com", role=Role.ADMIN, password="Pass123!"
        )
        found = user_store.get_user(created.user_id)
        assert found is not None
        assert found.user_id == created.user_id
        assert found.name == "Carol"

    def test_get_user_by_email(self, user_store):
        user_store.create_user(
            name="Dave", email="dave@lab.com", role=Role.VIEWER, password="Pass123!"
        )
        found = user_store.get_user_by_email("dave@lab.com")
        assert found is not None
        assert found.name == "Dave"

    def test_get_user_not_found(self, user_store):
        assert user_store.get_user("nonexistent") is None

    def test_list_users(self, user_store):
        user_store.create_user(
            name="U1", email="u1@lab.com", role=Role.VIEWER, password="Pass123!"
        )
        user_store.create_user(
            name="U2", email="u2@lab.com", role=Role.EDITOR, password="Pass123!"
        )
        user_store.create_user(
            name="U3", email="u3@lab.com", role=Role.ADMIN, password="Pass123!"
        )
        users = user_store.list_users()
        assert len(users) == 3

    def test_duplicate_email_rejected(self, user_store):
        user_store.create_user(
            name="Eve", email="eve@lab.com", role=Role.VIEWER, password="Pass123!"
        )
        with pytest.raises(ValueError, match="already exists"):
            user_store.create_user(
                name="Eve2", email="eve@lab.com", role=Role.EDITOR, password="Other123!"
            )

    def test_verify_password_correct(self, user_store):
        user = user_store.create_user(
            name="Frank",
            email="frank@lab.com",
            role=Role.VIEWER,
            password="TestPass123!",
        )
        assert user_store.verify_password(user.user_id, "TestPass123!") is True

    def test_verify_password_incorrect(self, user_store):
        user = user_store.create_user(
            name="Grace",
            email="grace@lab.com",
            role=Role.VIEWER,
            password="TestPass123!",
        )
        assert user_store.verify_password(user.user_id, "WrongPass!") is False

    def test_change_password(self, user_store):
        user = user_store.create_user(
            name="Heidi",
            email="heidi@lab.com",
            role=Role.VIEWER,
            password="OldPass123!",
        )
        user_store.change_password(user.user_id, "NewPass456!")
        assert user_store.verify_password(user.user_id, "NewPass456!") is True
        assert user_store.verify_password(user.user_id, "OldPass123!") is False

    def test_deactivate_user(self, user_store):
        user = user_store.create_user(
            name="Ivan", email="ivan@lab.com", role=Role.EDITOR, password="Pass123!"
        )
        deactivated = user_store.deactivate_user(user.user_id)
        assert deactivated.active is False

    def test_update_user_role(self, user_store):
        user = user_store.create_user(
            name="Judy", email="judy@lab.com", role=Role.VIEWER, password="Pass123!"
        )
        updated = user_store.update_user(user.user_id, role=Role.ADMIN)
        assert updated.role == Role.ADMIN
        # Verify persistence
        reloaded = user_store.get_user(user.user_id)
        assert reloaded is not None
        assert reloaded.role == Role.ADMIN

    def test_update_user_not_found(self, user_store):
        with pytest.raises(ValueError, match="not found"):
            user_store.update_user("nonexistent", name="Ghost")

    def test_change_password_not_found(self, user_store):
        with pytest.raises(ValueError, match="not found"):
            user_store.change_password("nonexistent", "NewPass1!")

    def test_verify_password_not_found(self, user_store):
        with pytest.raises(ValueError, match="not found"):
            user_store.verify_password("nonexistent", "Pass!")


class TestUserStoreAtomicWrite:
    """Tests for atomic file write behavior (HI-04)."""

    def test_write_uses_atomic_tempfile(self, user_store):
        """Verify _write_store uses tempfile + rename pattern."""
        import inspect

        source = inspect.getsource(user_store._write_store)
        assert "tempfile.mkstemp" in source
        assert ".rename(" in source

    def test_store_unchanged_on_write_failure(self, user_store):
        """If JSON write fails mid-write, the original store is preserved."""
        from unittest.mock import patch

        # Create a user first
        user_store.create_user("Alice", "alice@example.com", Role.EDITOR, "P@ss1234")

        # Now attempt to create another user but make os.fdopen fail
        with (
            patch(
                "sporedb.compliance.user_store.os.fdopen",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError, match="disk full"),
        ):
            user_store.create_user("Bob", "bob@example.com", Role.VIEWER, "P@ss2345")

        # Original store should be intact
        users = user_store.list_users()
        assert len(users) == 1
        assert users[0].name == "Alice"

    def test_file_permissions_600(self, user_store):
        """After write, file should have 0o600 permissions."""
        import stat

        user_store.create_user("Alice", "alice@example.com", Role.EDITOR, "P@ss1234")
        path = user_store._store_path()
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600
