"""Local JSON-backed user store with argon2id password hashing.

Provides persistent user management for SporeDB's RBAC system.
Passwords are hashed with argon2id (memory-hard KDF) and never stored
in plaintext, satisfying FDA 21 CFR Part 11 section 11.300 requirements
for controls over identification codes and passwords.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from sporedb.compliance.rbac import Role, User
from sporedb.storage.engine import StorageEngine
from sporedb.storage.parquet_layout import ParquetLayout


class UserStore:
    """CRUD operations for users backed by a local JSON file.

    Thread-safe via a threading.Lock. Passwords are hashed with argon2id
    before storage. Follows the same existence-check + ValueError pattern
    as BatchStore.
    """

    def __init__(self, engine: StorageEngine) -> None:
        self._engine = engine
        self._layout = ParquetLayout(engine.data_root)
        self._lock = threading.Lock()
        self._ph = PasswordHasher()

    def _store_path(self) -> Path:
        """Return the path to the user store JSON file."""
        return self._layout.user_store_file()

    def _read_store(self) -> dict[str, dict[str, Any]]:
        """Read the JSON file and return dict keyed by user_id.

        Returns empty dict if the file does not exist.
        """
        path = self._store_path()
        if not path.exists():
            return {}
        with open(path) as f:
            return json.load(f)  # type: ignore[no-any-return]

    def _write_store(self, data: dict[str, dict[str, Any]]) -> None:
        """Write the user dict to the JSON file atomically.

        Uses tempfile + rename to ensure the store file is never left in
        a partially-written state if the process crashes mid-write (HI-04).
        """
        path = self._store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, default=str)
            Path(tmp_name).rename(path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        path.chmod(0o600)

    @staticmethod
    def _validate_password(password: str) -> None:
        """Enforce password complexity per FDA 21 CFR Part 11 s11.300."""
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in password):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in password):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in password):
            raise ValueError("Password must contain at least one digit")

    def create_user(self, name: str, email: str, role: Role, password: str) -> User:
        """Create a new user with argon2id-hashed password.

        Raises ValueError if a user with the same email already exists
        or if the password fails complexity requirements.
        """
        self._validate_password(password)
        with self._lock:
            store = self._read_store()

            # Check email uniqueness
            for existing in store.values():
                if existing.get("email", "").lower() == email.lower():
                    msg = f"User with email {email} already exists"
                    raise ValueError(msg)

            password_hash = self._ph.hash(password)
            user = User(
                name=name,
                email=email,
                role=role,
                password_hash=password_hash,
            )

            store[user.user_id] = user.model_dump(mode="json")
            # password_hash is excluded by default; add it back for storage
            store[user.user_id]["password_hash"] = password_hash
            self._write_store(store)
            return user

    def get_user(self, user_id: str) -> User | None:
        """Retrieve a user by ID. Returns None if not found."""
        store = self._read_store()
        data = store.get(user_id)
        if data is None:
            return None
        return User.model_validate(data)

    def get_user_by_email(self, email: str) -> User | None:
        """Search for a user by email address. Returns None if not found."""
        store = self._read_store()
        for data in store.values():
            if data.get("email", "").lower() == email.lower():
                return User.model_validate(data)
        return None

    def list_users(self) -> list[User]:
        """Return all users in the store."""
        store = self._read_store()
        return [User.model_validate(data) for data in store.values()]

    def update_user(self, user_id: str, **kwargs: Any) -> User:
        """Update user fields (name, email, role, active).

        Does NOT allow password updates -- use change_password() instead.
        Raises ValueError if user not found.
        """
        allowed_fields = {"name", "email", "role", "active"}
        invalid = set(kwargs.keys()) - allowed_fields
        if invalid:
            msg = (
                f"Cannot update fields: {invalid}. "
                "Use change_password() for password changes."
            )
            raise ValueError(msg)

        with self._lock:
            store = self._read_store()
            if user_id not in store:
                msg = f"User {user_id} not found"
                raise ValueError(msg)

            # Enforce email uniqueness when email is being changed (WR-06)
            new_email = kwargs.get("email")
            if new_email is not None:
                for uid, existing in store.items():
                    if (
                        uid != user_id
                        and existing.get("email", "").lower() == new_email.lower()
                    ):
                        msg = f"User with email {new_email} already exists"
                        raise ValueError(msg)

            data = store[user_id]
            for key, value in kwargs.items():
                if isinstance(value, Role):
                    data[key] = value.value
                else:
                    data[key] = value

            store[user_id] = data
            self._write_store(store)
            return User.model_validate(data)

    def change_password(self, user_id: str, new_password: str) -> None:
        """Hash and store a new password for the user.

        Raises ValueError if user not found or password fails complexity requirements.
        """
        self._validate_password(new_password)
        with self._lock:
            store = self._read_store()
            if user_id not in store:
                msg = f"User {user_id} not found"
                raise ValueError(msg)

            store[user_id]["password_hash"] = self._ph.hash(new_password)
            self._write_store(store)

    def verify_password(self, user_id: str, password: str) -> bool:
        """Verify a password against the stored argon2id hash.

        Returns True if valid, False if invalid.
        Raises ValueError if user not found.
        """
        store = self._read_store()
        if user_id not in store:
            msg = f"User {user_id} not found"
            raise ValueError(msg)

        stored_hash = store[user_id].get("password_hash", "")
        if not stored_hash:
            return False

        try:
            return self._ph.verify(stored_hash, password)
        except VerifyMismatchError:
            return False

    def deactivate_user(self, user_id: str) -> User:
        """Deactivate a user (set active=False).

        Raises ValueError if user not found.
        """
        return self.update_user(user_id, active=False)
