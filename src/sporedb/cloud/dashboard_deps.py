"""Cookie-based authentication dependencies for dashboard routes.

Provides ``get_dashboard_user`` which extracts the authenticated user
from an httpOnly session cookie (rather than a Bearer header used by
the JSON API).  Includes sliding-window token refresh so sessions
stay alive while the user is active.

Threat mitigations:
- T-10-01: httpOnly + Secure + SameSite=Lax cookie; Ed25519 JWT verification.
- T-10-04: httpOnly prevents JS access; Secure flag enforced in production.
- T-10-07: New token issued on each login; cookie deleted on logout.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyCookie
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from sporedb.cloud.auth.jwt import create_access_token, decode_token
from sporedb.cloud.auth.middleware import TenantContext
from sporedb.cloud.db.models import CloudUser

REFRESH_WINDOW_SECONDS = 900  # 15 minutes

cookie_scheme = APIKeyCookie(name="sporedb_session", auto_error=False)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection for dashboard routes.

    On GET to /dash/*: generates a random token, sets it as a cookie,
    and stores it in request.state.csrf_token for template injection.

    On POST to /dash/*: compares cookie csrftoken vs form _csrf_token.
    Rejects with 403 on mismatch.

    API routes (/api/*) are unaffected — they use Bearer auth.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if not request.url.path.startswith("/dash/"):
            return await call_next(request)

        if request.method == "GET":
            token = secrets.token_hex(32)
            request.state.csrf_token = token
            response = await call_next(request)
            response.set_cookie(
                "csrftoken",
                token,
                samesite="lax",
                path="/dash/",
                httponly=False,
            )
            return response

        if request.method == "POST":
            cookie_token = request.cookies.get("csrftoken")
            form = await request.form()
            form_token = form.get("_csrf_token")
            if not cookie_token or cookie_token != form_token:
                from starlette.responses import JSONResponse

                return JSONResponse(
                    {"detail": "CSRF validation failed"}, status_code=403
                )

        return await call_next(request)


class SlidingWindowRefreshMiddleware(BaseHTTPMiddleware):
    """Middleware that applies sliding-window token refresh cookies.

    After ``get_dashboard_user`` stores refresh cookie details on
    ``request.state._refresh_cookie``, this middleware applies them
    to the actual response. This is necessary because TemplateResponse
    bypasses FastAPI's dependency Response header merging.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        refresh = getattr(request.state, "_refresh_cookie", None)
        if refresh is not None:
            response.set_cookie(**refresh)
        return response


async def get_dashboard_user(
    request: Request,
    token: str | None = Depends(cookie_scheme),
) -> TenantContext:
    """Extract and validate tenant context from the session cookie.

    If the token is missing or invalid, raises an HTTP 303 redirect to
    the login page with a ``?next=`` parameter preserving the original
    request URL.

    Implements sliding-window token refresh: when the token will expire
    within 15 minutes (900 seconds), stores refresh cookie details on
    ``request.state`` for the ``SlidingWindowRefreshMiddleware`` to apply.
    """
    next_path = request.url.path
    # Validate redirect target to prevent open redirect (CR-04)
    if not next_path.startswith("/dash/") or "://" in next_path or "//" in next_path:
        next_path = "/dash/"
    login_url = f"/dash/login?next={next_path}"

    if token is None:
        raise HTTPException(
            status_code=303,
            headers={"Location": login_url},
        )

    public_key = request.app.state.jwt_public_key

    try:
        payload = decode_token(token, public_key)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=303,
            headers={"Location": login_url},
        ) from None
    except pyjwt.InvalidTokenError:
        raise HTTPException(
            status_code=303,
            headers={"Location": login_url},
        ) from None

    # Reject non-access tokens (e.g. refresh tokens)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=303,
            headers={"Location": login_url},
        )

    # Sliding window token refresh: if token expires within REFRESH_WINDOW_SECONDS,
    # query DB for current role/email (T-13-10 / MD-01) and issue a fresh token.
    exp_ts = payload["exp"]
    now_ts = datetime.now(UTC).timestamp()
    remaining = exp_ts - now_ts

    if remaining <= REFRESH_WINDOW_SECONDS:
        # Query DB for current user data instead of using stale JWT claims
        async with request.app.state.db_session.get_session() as refresh_session:
            result = await refresh_session.execute(
                select(CloudUser).where(
                    CloudUser.id == payload["sub"],
                    CloudUser.tenant_id == payload["tenant_id"],
                )
            )
            current_user = result.scalar_one_or_none()

        if current_user is not None and current_user.active:
            # User still active; refresh with current DB values
            settings = request.app.state.settings
            private_key = request.app.state.jwt_private_key
            new_token = create_access_token(
                tenant_id=payload["tenant_id"],
                user_id=payload["sub"],
                email=current_user.email,
                role=current_user.role,
                private_key=private_key,
                expires_minutes=settings.jwt_access_token_expire_minutes,
            )
            request.state._refresh_cookie = {
                "key": "sporedb_session",
                "value": new_token,
                "httponly": True,
                "secure": not settings.debug,
                "samesite": "lax",
                "max_age": settings.jwt_access_token_expire_minutes * 60,
                "path": "/dash",
            }
        # If current_user is None, user was deleted/deactivated; let token expire

    return TenantContext(
        tenant_id=payload["tenant_id"],
        user_id=payload["sub"],
        email=payload["email"],
        role=payload["role"],
        active=payload.get("active", True),
    )


async def require_admin(
    ctx: TenantContext = Depends(get_dashboard_user),  # noqa: B008
) -> TenantContext:
    """Enforce admin role for dashboard routes.

    Threat mitigation T-10-05: Server-side role check, not just UI hiding.
    """
    if ctx.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return ctx
