"""Tenant context resolved from JWT claims on every request."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Request-scoped identity resolved from a validated JWT.

    This lightweight dataclass carries the authenticated tenant and user
    identity through the request lifecycle.  It is constructed by the
    ``get_current_user`` FastAPI dependency and injected into route handlers.
    """

    tenant_id: str
    user_id: str
    email: str
    role: str
    active: bool = True
