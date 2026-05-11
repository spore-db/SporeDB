"""Cloud authentication: JWT tokens, tenant resolution, FastAPI dependencies."""

from __future__ import annotations

from sporedb.cloud.auth.deps import get_current_user, require_permission
from sporedb.cloud.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from sporedb.cloud.auth.middleware import TenantContext

__all__ = [
    "TenantContext",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_current_user",
    "require_permission",
]
