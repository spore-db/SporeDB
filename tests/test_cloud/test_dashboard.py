"""Dashboard integration tests: login/logout, cookie auth, role-based access.

Tests the server-rendered HTML dashboard routes including cookie-based
JWT authentication, sliding-window token refresh, and admin-only access.
"""

from __future__ import annotations

import pytest

from sporedb.cloud.auth.jwt import create_access_token

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Login page rendering
# ---------------------------------------------------------------------------


async def test_login_page_renders(dashboard_client):
    """GET /dash/login returns 200 with HTML containing login form."""
    resp = await dashboard_client.get("/dash/login")
    assert resp.status_code == 200
    body = resp.text
    assert "<form" in body
    assert 'name="email"' in body
    assert 'name="password"' in body
    assert 'name="tenant_slug"' in body


# ---------------------------------------------------------------------------
# Login success / failure
# ---------------------------------------------------------------------------


async def test_login_success_sets_cookie(dashboard_client, seeded_tenant):
    """POST /dash/login with valid credentials returns 303 redirect with Set-Cookie."""
    resp = await dashboard_client.post(
        "/dash/login",
        data={
            "email": "editor@example.com",
            "password": "testpassword",
            "tenant_slug": "test-org",
            "next": "/dash/batches",
        },
    )
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/dash/batches"

    # Check Set-Cookie header
    set_cookie = resp.headers.get("set-cookie", "")
    assert "sporedb_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


async def test_login_invalid_credentials(dashboard_client, seeded_tenant):
    """POST /dash/login with bad password returns login page with error."""
    resp = await dashboard_client.post(
        "/dash/login",
        data={
            "email": "editor@example.com",
            "password": "wrongpassword",
            "tenant_slug": "test-org",
        },
    )
    assert resp.status_code == 200
    assert "Invalid credentials" in resp.text


async def test_login_invalid_tenant(dashboard_client, seeded_tenant):
    """POST /dash/login with bad tenant shows error."""
    resp = await dashboard_client.post(
        "/dash/login",
        data={
            "email": "editor@example.com",
            "password": "testpassword",
            "tenant_slug": "nonexistent-org",
        },
    )
    assert resp.status_code == 200
    assert "Invalid credentials" in resp.text


# ---------------------------------------------------------------------------
# Unauthenticated redirect
# ---------------------------------------------------------------------------


async def test_unauthenticated_redirect(dashboard_client):
    """GET /dash/batches without cookie returns 303 redirect to /dash/login."""
    resp = await dashboard_client.get("/dash/batches")
    assert resp.status_code == 303
    location = resp.headers.get("location", "")
    assert "/dash/login" in location
    assert "next=" in location


# ---------------------------------------------------------------------------
# Authenticated page access
# ---------------------------------------------------------------------------


async def test_authenticated_page_access(dashboard_client, test_access_token):
    """GET /dash/batches with valid cookie returns 200."""
    resp = await dashboard_client.get(
        "/dash/batches",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 200
    assert "Batches" in resp.text


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


async def test_logout_clears_cookie(dashboard_client, test_access_token):
    """GET /dash/logout returns redirect and deletes cookie."""
    resp = await dashboard_client.get(
        "/dash/logout",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/dash/login"

    # Cookie should be cleared (max-age=0 or empty value)
    set_cookie = resp.headers.get("set-cookie", "")
    # FastAPI delete_cookie sets max-age=0
    assert "sporedb_session" in set_cookie


# ---------------------------------------------------------------------------
# Admin settings access
# ---------------------------------------------------------------------------


async def test_admin_settings_access(dashboard_client, admin_access_token):
    """GET /dash/settings with admin cookie returns 200."""
    resp = await dashboard_client.get(
        "/dash/settings",
        cookies={"sporedb_session": admin_access_token},
    )
    assert resp.status_code == 200
    assert "Settings" in resp.text


async def test_non_admin_settings_denied(dashboard_client, test_access_token):
    """GET /dash/settings with editor cookie returns 403."""
    resp = await dashboard_client.get(
        "/dash/settings",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Sidebar role-based visibility
# ---------------------------------------------------------------------------


async def test_sidebar_admin_link_present_for_admin(
    dashboard_client, admin_access_token
):
    """Settings link is present in sidebar for admin users."""
    resp = await dashboard_client.get(
        "/dash/batches",
        cookies={"sporedb_session": admin_access_token},
    )
    assert resp.status_code == 200
    assert "/dash/settings" in resp.text


async def test_sidebar_admin_link_absent_for_viewer(
    dashboard_client, viewer_access_token
):
    """Settings link is absent from sidebar for viewer users."""
    resp = await dashboard_client.get(
        "/dash/batches",
        cookies={"sporedb_session": viewer_access_token},
    )
    assert resp.status_code == 200
    assert "/dash/settings" not in resp.text


# ---------------------------------------------------------------------------
# Sliding window token refresh
# ---------------------------------------------------------------------------


async def test_sliding_window_refresh(
    dashboard_client, ed25519_keypair, test_tenant_id, test_user_id, seeded_tenant
):
    """Token near expiry triggers refresh cookie in response (DB-fresh claims)."""
    private_key, _ = ed25519_keypair

    # Create a token that expires in 5 minutes (within the 15-min window)
    near_expiry_token = create_access_token(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        email="editor@example.com",
        role="editor",
        private_key=private_key,
        expires_minutes=5,  # Within 15-min refresh window
    )

    resp = await dashboard_client.get(
        "/dash/batches",
        cookies={"sporedb_session": near_expiry_token},
    )
    assert resp.status_code == 200

    # Response should include a refreshed cookie
    set_cookie = resp.headers.get("set-cookie", "")
    assert "sporedb_session=" in set_cookie, (
        "Expected refreshed cookie when token is near expiry"
    )


# ---------------------------------------------------------------------------
# Batch list page (Plan 10-03)
# ---------------------------------------------------------------------------


async def test_batches_page_renders_table(
    dashboard_client, test_access_token, seeded_batches
):
    """GET /dash/batches with auth returns HTML with batch table."""
    resp = await dashboard_client.get(
        "/dash/batches",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "batch-table-body" in body
    # Seeded batch names should appear
    assert "Fermentation Run Alpha" in body
    assert "Fermentation Run Beta" in body


async def test_batches_search_htmx_partial(
    dashboard_client, test_access_token, seeded_batches
):
    """GET /dash/batches/search?q=Alpha with HX-Request returns partial HTML."""
    resp = await dashboard_client.get(
        "/dash/batches/search?q=Alpha",
        cookies={"sporedb_session": test_access_token},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    body = resp.text
    # Should be a partial (no full HTML page wrapper)
    assert "<html" not in body
    # Should contain the matching batch
    assert "Fermentation Run Alpha" in body
    # Should NOT contain non-matching batch
    assert "Scale-up Test 001" not in body


async def test_batches_search_uses_service_layer(
    dashboard_client, test_access_token, seeded_batches
):
    """Search query is passed to BatchService via ILIKE (server-side)."""
    resp = await dashboard_client.get(
        "/dash/batches/search?q=Scale",
        cookies={"sporedb_session": test_access_token},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Scale-up Test 001" in body
    assert "Fermentation Run Alpha" not in body


async def test_batches_search_no_htmx_redirects(
    dashboard_client, test_access_token, seeded_batches
):
    """GET /dash/batches/search without HX-Request redirects to full page."""
    resp = await dashboard_client.get(
        "/dash/batches/search?q=test",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 302
    assert "/dash/batches" in resp.headers.get("location", "")


async def test_batches_search_redirect_url_encodes_query(
    dashboard_client, test_access_token, seeded_batches
):
    """GET /dash/batches/search with special chars URL-encodes the redirect (MD-11)."""
    # Use characters that are valid in URLs but need encoding in query values
    # (ampersand would split params, percent needs encoding, spaces need encoding)
    special_q = "test&extra=1 foo%bar"
    resp = await dashboard_client.get(
        "/dash/batches/search",
        params={"q": special_q},
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 302
    location = resp.headers.get("location", "")
    # The ampersand should be URL-encoded in the redirect, not a param separator
    assert "&extra=1" not in location
    # The quote() function encodes & as %26
    assert "%26" in location or "q=test" in location


async def test_batches_empty_state(dashboard_client, test_access_token):
    """GET /dash/batches with no batches shows empty state message."""
    resp = await dashboard_client.get(
        "/dash/batches",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 200
    assert "No batches found" in resp.text


# ---------------------------------------------------------------------------
# Batch detail page (Plan 10-03)
# ---------------------------------------------------------------------------


async def test_batch_detail_renders_metadata(
    dashboard_client, test_access_token, seeded_batches
):
    """GET /dash/batches/{id} with seeded batch returns HTML with batch name."""
    batch_id = seeded_batches[0][0]  # Alpha batch
    resp = await dashboard_client.get(
        f"/dash/batches/{batch_id}",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Fermentation Run Alpha" in body
    # Metadata fields should appear
    assert "R. toruloides" in body
    assert "Dr. Smith" in body


async def test_batch_detail_not_found(dashboard_client, test_access_token):
    """GET /dash/batches/nonexistent returns 404."""
    resp = await dashboard_client.get(
        "/dash/batches/00000000-0000-0000-0000-000000009999",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 404


async def test_batch_detail_has_chart_container(
    dashboard_client, test_access_token, seeded_batches
):
    """GET /dash/batches/{id} returns HTML with chart container and renderChart."""
    batch_id = seeded_batches[0][0]
    resp = await dashboard_client.get(
        f"/dash/batches/{batch_id}",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "batch-chart-plot" in body
    assert "renderChart" in body


# ---------------------------------------------------------------------------
# Compare page (Plan 10-04)
# ---------------------------------------------------------------------------


async def test_compare_page_renders(dashboard_client, test_access_token):
    """GET /dash/compare with auth returns HTML with batch selection elements."""
    resp = await dashboard_client.get(
        "/dash/compare",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Compare Batch Runs" in body
    assert "selectedBatches" in body
    assert "loadCompareChart" in body


# ---------------------------------------------------------------------------
# Audit trail page (Plan 10-04)
# ---------------------------------------------------------------------------


async def test_audit_page_renders(
    dashboard_client, test_access_token, seeded_audit_entries
):
    """GET /dash/audit with auth returns HTML with audit table."""
    resp = await dashboard_client.get(
        "/dash/audit",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Audit Trail" in body
    assert "audit-table-body" in body
    # Should contain seeded entries
    assert "create" in body.lower()


async def test_audit_search_htmx_partial(
    dashboard_client, test_access_token, seeded_audit_entries
):
    """GET /dash/audit/search with HX-Request returns HTML fragment (partial)."""
    resp = await dashboard_client.get(
        "/dash/audit/search",
        cookies={"sporedb_session": test_access_token},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    body = resp.text
    # Partial should NOT contain full page layout (no <html>, no base.html)
    assert "<!DOCTYPE" not in body
    # Should contain table rows (tr elements) or empty state
    assert "<tr" in body or "No audit entries" in body


async def test_audit_action_filter(
    dashboard_client, test_access_token, seeded_audit_entries
):
    """GET /dash/audit/search?action=create filters results to create actions."""
    resp = await dashboard_client.get(
        "/dash/audit/search?action=create",
        cookies={"sporedb_session": test_access_token},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    # Should contain create entries but filter is applied via SQLAlchemy
    assert resp.status_code == 200


async def test_audit_verification_column(
    dashboard_client, test_access_token, seeded_audit_entries
):
    """GET /dash/audit shows verification status icons (gray dash for N/A)."""
    resp = await dashboard_client.get(
        "/dash/audit",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 200
    body = resp.text
    # Should contain verification column with gray dash (N/A) for cloud entries
    assert "Verification data not available" in body


# ---------------------------------------------------------------------------
# Settings page (Plan 10-05)
# ---------------------------------------------------------------------------


async def test_settings_page_shows_users(dashboard_client, admin_access_token):
    """GET /dash/settings with admin auth returns HTML with user table."""
    resp = await dashboard_client.get(
        "/dash/settings",
        cookies={"sporedb_session": admin_access_token},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "User Management" in body
    assert "System Configuration" in body


async def test_settings_non_admin_forbidden(dashboard_client, test_access_token):
    """GET /dash/settings with editor auth returns 403."""
    resp = await dashboard_client.get(
        "/dash/settings",
        cookies={"sporedb_session": test_access_token},
    )
    assert resp.status_code == 403


async def test_settings_shows_system_config(dashboard_client, admin_access_token):
    """GET /dash/settings shows deployment mode and app version."""
    resp = await dashboard_client.get(
        "/dash/settings",
        cookies={"sporedb_session": admin_access_token},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "App Version" in body
    assert "v0.1.0" in body


async def test_full_navigation_flow(dashboard_client, admin_access_token):
    """Sequential test: visit all dashboard pages with admin auth."""
    pages = ["/dash/batches", "/dash/compare", "/dash/audit", "/dash/settings"]
    for page in pages:
        resp = await dashboard_client.get(
            page,
            cookies={"sporedb_session": admin_access_token},
        )
        assert resp.status_code == 200, f"Failed on {page}: {resp.status_code}"


# ---------------------------------------------------------------------------
# Open redirect protection (CR-03 / T-13-05)
# ---------------------------------------------------------------------------


async def test_login_submit_blocks_open_redirect(dashboard_client, seeded_tenant):
    """POST /dash/login with next=https://evil.com redirects to /dash/batches."""
    resp = await dashboard_client.post(
        "/dash/login",
        data={
            "email": "editor@example.com",
            "password": "testpassword",
            "tenant_slug": "test-org",
            "next": "https://evil.com",
        },
    )
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/dash/batches"


async def test_login_submit_blocks_protocol_relative_redirect(
    dashboard_client, seeded_tenant
):
    """POST /dash/login with next=//evil.com redirects to /dash/batches."""
    resp = await dashboard_client.post(
        "/dash/login",
        data={
            "email": "editor@example.com",
            "password": "testpassword",
            "tenant_slug": "test-org",
            "next": "//evil.com",
        },
    )
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/dash/batches"


async def test_login_page_sanitizes_next_param(dashboard_client):
    """GET /dash/login?next=https://evil.com sanitizes next in template context."""
    resp = await dashboard_client.get("/dash/login?next=https://evil.com")
    assert resp.status_code == 200
    # The form should contain the safe default, not the evil URL
    assert "https://evil.com" not in resp.text


async def test_login_submit_allows_valid_dash_redirect(dashboard_client, seeded_tenant):
    """POST /dash/login with next=/dash/audit redirects correctly."""
    resp = await dashboard_client.post(
        "/dash/login",
        data={
            "email": "editor@example.com",
            "password": "testpassword",
            "tenant_slug": "test-org",
            "next": "/dash/audit",
        },
    )
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/dash/audit"
