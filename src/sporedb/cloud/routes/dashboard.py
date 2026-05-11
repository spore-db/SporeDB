"""Dashboard HTML routes: login/logout flow and page stubs.

Serves server-rendered HTML via Jinja2 templates alongside the existing
JSON API routes.  Cookie-based JWT auth (not Bearer) for browser sessions.

Threat mitigations:
- T-10-02: SameSite=Lax cookie blocks cross-origin POST; cookie scoped to /dash.
- T-10-03: Jinja2 auto-escaping enabled by default.
- T-10-07: New token on login; cookie deleted on logout.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sporedb.cloud.auth.jwt import create_access_token
from sporedb.cloud.auth.middleware import TenantContext
from sporedb.cloud.dashboard_deps import get_dashboard_user, require_admin
from sporedb.cloud.db.models import AuditIndex, CloudUser, Tenant
from sporedb.cloud.services.batch_service import BatchService
from sporedb.cloud.services.cloud_audit_service import CloudAuditService
from sporedb.cloud.services.tenant_service import TenantService

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _ctx(request: Request, **kwargs: object) -> dict[str, object]:
    """Build template context with CSRF token."""
    return {
        "request": request,
        "csrf_token": getattr(request.state, "csrf_token", ""),
        **kwargs,
    }


def _parse_json(value: str | None) -> dict[str, object]:
    """Jinja2 filter: parse a JSON string into a dict, returning {} on failure."""
    if not value:
        return {}
    try:
        return json.loads(value)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        return {}


templates.env.filters["parse_json"] = _parse_json

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/dash", tags=["dashboard"])


def _safe_redirect(next_url: str) -> str:
    """Ensure redirect target is a safe relative path under /dash/.

    Blocks open redirects by rejecting absolute URLs, protocol-relative
    URLs, and paths outside the /dash/ prefix.

    Threat mitigation: T-13-05 (CR-03).
    """
    if not isinstance(next_url, str) or not next_url.startswith("/dash/"):
        return "/dash/batches"
    if next_url.startswith("//"):
        return "/dash/batches"
    return next_url


# ---------------------------------------------------------------------------
# Database dependency (same pattern as auth routes)
# ---------------------------------------------------------------------------


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session from the app-level factory."""
    async with request.app.state.db_session.get_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/dash/batches") -> Any:
    """Render login form. No auth required."""
    return templates.TemplateResponse(
        request=request,
        name="pages/login.html",
        context=_ctx(request, next=_safe_redirect(next)),
    )


@router.post("/login")
@limiter.limit("5/minute")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    tenant_slug: str = Form(...),
    next: str = Form(default="/dash/batches"),
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> Any:
    """Authenticate user and set httpOnly session cookie."""
    svc = TenantService(session)

    tenant = await svc.get_tenant_by_slug(tenant_slug)
    if tenant is None:
        return templates.TemplateResponse(
            request=request,
            name="pages/login.html",
            context=_ctx(request, error="Invalid credentials", next=next),
        )

    user = await svc.get_user_by_email(tenant.id, email)
    if user is None or not await svc.verify_password(user.password_hash, password):
        return templates.TemplateResponse(
            request=request,
            name="pages/login.html",
            context=_ctx(request, error="Invalid credentials", next=next),
        )

    settings = request.app.state.settings
    private_key = request.app.state.jwt_private_key

    access_token = create_access_token(
        tenant_id=tenant.id,
        user_id=user.id,
        email=user.email,
        role=user.role,
        private_key=private_key,
        expires_minutes=settings.jwt_access_token_expire_minutes,
    )

    response = RedirectResponse(url=_safe_redirect(next), status_code=303)
    response.set_cookie(
        key="sporedb_session",
        value=access_token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/dash",
    )
    return response


@router.get("/logout")
async def logout() -> Any:
    """Clear session cookie and redirect to login."""
    response = RedirectResponse(url="/dash/login", status_code=303)
    response.delete_cookie("sporedb_session", path="/dash")
    return response


# ---------------------------------------------------------------------------
# Page stubs (content filled by Plans 03-05)
# ---------------------------------------------------------------------------


@router.get("/batches", response_class=HTMLResponse)
async def batches_page(
    request: Request,
    q: str = Query(default=""),
    ctx: TenantContext = Depends(get_dashboard_user),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> Any:
    """Batch list page with server-side search via BatchService."""
    svc = BatchService(session)
    batches = await svc.list_batches(ctx.tenant_id, search=q if q else None)
    # Paginate: 20 per page, default page 1
    page = 1
    per_page = 20
    has_next = len(batches) > per_page
    paginated = batches[:per_page]
    return templates.TemplateResponse(
        request=request,
        name="pages/batches.html",
        context=_ctx(
            request, user=ctx, batches=paginated, query=q, page=page, has_next=has_next
        ),
    )


@router.get("/batches/search", response_class=HTMLResponse)
async def batches_search(
    request: Request,
    q: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    ctx: TenantContext = Depends(get_dashboard_user),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> Any:
    """HTMX partial endpoint for batch search/filter.

    Returns only the table body partial when called via HTMX (HX-Request
    header present). Redirects to the full batches page otherwise.

    Threat mitigations:
    - T-10-15: SQLAlchemy ILIKE with parameterized query (no raw SQL).
    - T-10-12: Jinja2 auto-escaping handles search query in templates.
    """
    # If not an HTMX request, redirect to full page
    if "HX-Request" not in request.headers:
        return RedirectResponse(url=f"/dash/batches?q={quote(q)}", status_code=302)

    svc = BatchService(session)
    all_batches = await svc.list_batches(ctx.tenant_id, search=q if q else None)
    per_page = 20
    offset = (page - 1) * per_page
    paginated = all_batches[offset : offset + per_page]
    has_next = len(all_batches) > offset + per_page

    return templates.TemplateResponse(
        request=request,
        name="partials/_batch_table.html",
        context=_ctx(request, batches=paginated, page=page, query=q, has_next=has_next),
    )


@router.get("/batches/{batch_id}", response_class=HTMLResponse)
async def batch_detail_page(
    request: Request,
    batch_id: str,
    ctx: TenantContext = Depends(get_dashboard_user),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> Any:
    """Single batch detail page with metadata card and chart container."""
    svc = BatchService(session)
    batch = await svc.get_batch(ctx.tenant_id, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return templates.TemplateResponse(
        request=request,
        name="pages/batch_detail.html",
        context=_ctx(request, user=ctx, batch=batch),
    )


@router.get("/compare", response_class=HTMLResponse)
async def compare_page(
    request: Request,
    ctx: TenantContext = Depends(get_dashboard_user),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> Any:
    """Multi-run comparison page with batch selection and overlay chart."""
    svc = BatchService(session)
    batches = await svc.list_batches(ctx.tenant_id)
    return templates.TemplateResponse(
        request=request,
        name="pages/compare.html",
        context=_ctx(request, user=ctx, batches=batches),
    )


AUDIT_PAGE_SIZE = 20


async def _query_audit_entries(
    session: AsyncSession,
    tenant_id: str,
    page: int = 1,
    action_filter: str | None = None,
) -> tuple[list[AuditIndex], bool]:
    """Query audit entries for a tenant with optional action filter.

    Returns (entries, has_next) tuple. Pagination uses LIMIT/OFFSET
    (T-10-18 mitigation: capped at AUDIT_PAGE_SIZE per request).
    """
    offset = (page - 1) * AUDIT_PAGE_SIZE

    stmt = select(AuditIndex).where(AuditIndex.tenant_id == tenant_id)
    if action_filter:
        # T-10-17: parameterized query via SQLAlchemy, no raw SQL
        stmt = stmt.where(AuditIndex.action == action_filter)
    stmt = stmt.order_by(AuditIndex.created_at.desc())

    # Fetch one extra row to determine if there is a next page
    stmt = stmt.offset(offset).limit(AUDIT_PAGE_SIZE + 1)
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    has_next = len(rows) > AUDIT_PAGE_SIZE
    entries = rows[:AUDIT_PAGE_SIZE]
    return entries, has_next


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(
    request: Request,
    page: int = Query(default=1, ge=1),
    action_filter: str | None = Query(default=None, alias="action"),
    ctx: TenantContext = Depends(get_dashboard_user),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> Any:
    """Audit trail page with pagination and action filter.

    Threat mitigations:
    - T-10-16: All queries filtered by tenant_id from JWT.
    - T-10-17: SQLAlchemy parameterized queries for action filter.
    - T-10-18: Pagination limited to 20 per page.
    """
    entries, has_next = await _query_audit_entries(
        session, ctx.tenant_id, page, action_filter
    )
    # Real hash chain verification via CloudAuditService
    audit_svc = CloudAuditService(session, request.app.state.jwt_private_key)
    chain_results = await audit_svc.verify_chain(ctx.tenant_id)
    verified_map = dict(chain_results)
    verification_status: dict[str, bool | None] = {
        e.id: verified_map.get(e.id) for e in entries
    }

    return templates.TemplateResponse(
        request=request,
        name="pages/audit.html",
        context=_ctx(
            request,
            user=ctx,
            entries=entries,
            page=page,
            action_filter=action_filter or "",
            has_next=has_next,
            verification_status=verification_status,
        ),
    )


@router.get("/audit/search", response_class=HTMLResponse)
async def audit_search(
    request: Request,
    page: int = Query(default=1, ge=1),
    action: str = Query(default=""),
    ctx: TenantContext = Depends(get_dashboard_user),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> Any:
    """HTMX partial endpoint for audit table filtering and pagination.

    Returns the _audit_table.html partial when HX-Request header is present,
    otherwise redirects to the full audit page.
    """
    action_filter = action if action else None
    entries, has_next = await _query_audit_entries(
        session, ctx.tenant_id, page, action_filter
    )
    # Real hash chain verification via CloudAuditService
    audit_svc = CloudAuditService(session, request.app.state.jwt_private_key)
    chain_results = await audit_svc.verify_chain(ctx.tenant_id)
    verified_map = dict(chain_results)
    verification_status: dict[str, bool | None] = {
        e.id: verified_map.get(e.id) for e in entries
    }

    is_htmx = request.headers.get("HX-Request") == "true"
    template_name = "partials/_audit_table.html" if is_htmx else "pages/audit.html"

    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context=_ctx(
            request,
            user=ctx,
            entries=entries,
            page=page,
            action_filter=action or "",
            has_next=has_next,
            verification_status=verification_status,
        ),
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    ctx: TenantContext = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> Any:
    """Admin settings page with user management and system config.

    Threat mitigations:
    - T-10-18: require_admin enforces server-side admin check.
    - T-10-20: User list scoped to tenant_id from JWT.
    """
    # Fetch users for this tenant
    result = await session.execute(
        select(CloudUser).where(CloudUser.tenant_id == ctx.tenant_id)
    )
    users = list(result.scalars().all())

    # Fetch tenant info
    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == ctx.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()

    settings = request.app.state.settings
    # HI-06: expose only non-secret fields to template
    safe_settings = {
        "mode": getattr(settings, "mode", "cloud"),
        "app_title": settings.app_title,
        "app_version": settings.app_version,
        "debug": settings.debug,
    }

    return templates.TemplateResponse(
        request=request,
        name="pages/settings.html",
        context=_ctx(
            request, user=ctx, users=users, tenant=tenant, settings=safe_settings
        ),
    )


@router.post("/settings/users/{user_id}/role")
async def update_user_role(
    request: Request,
    user_id: str,
    role: str = Form(...),
    ctx: TenantContext = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> Any:
    """Update a user's role. Admin only.

    Threat mitigations:
    - T-10-18: require_admin enforces admin check.
    - T-10-19: Prevent self-role-change to avoid lockout.
    """
    if role not in ("viewer", "editor", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")

    if user_id == ctx.user_id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    result = await session.execute(
        select(CloudUser).where(
            CloudUser.id == user_id,
            CloudUser.tenant_id == ctx.tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = role
    await session.commit()

    # HTMX: return updated row or redirect
    if "HX-Request" in request.headers:
        if role == "admin":
            cls = "bg-red-100 text-red-700"
        elif role == "editor":
            cls = "bg-blue-100 text-blue-700"
        else:
            cls = "bg-gray-100 text-gray-700"
        return HTMLResponse(
            f'<span class="px-2 py-1 text-xs rounded-full {cls}">{role}</span>'
        )
    return RedirectResponse(url="/dash/settings", status_code=303)
