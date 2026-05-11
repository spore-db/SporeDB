"""Tests for CSRF protection on dashboard POST endpoints.

Verifies double-submit cookie pattern: cookie + hidden form field must match.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sporedb.cloud.dashboard_deps import CSRFMiddleware


class TestCSRFMiddlewareExists:
    """CSRFMiddleware must be importable with correct interface."""

    def test_csrf_middleware_importable(self):
        """CSRFMiddleware should be importable from dashboard_deps."""
        assert CSRFMiddleware is not None

    def test_csrf_middleware_is_middleware_class(self):
        """CSRFMiddleware should be a class that can wrap an ASGI app."""
        import inspect

        assert inspect.isclass(CSRFMiddleware)


class TestCSRFMountedInApp:
    """Verify CSRFMiddleware is mounted in the real app."""

    def test_app_has_csrf_middleware(self):
        import inspect

        from sporedb.cloud.app import create_app

        source = inspect.getsource(create_app)
        assert "CSRFMiddleware" in source, "create_app must mount CSRFMiddleware"


class TestCSRFInTemplates:
    """Verify CSRF token is injected into template forms."""

    def test_login_form_has_csrf_field(self):
        """login.html must contain _csrf_token hidden input."""
        from pathlib import Path

        login_html = Path("src/sporedb/cloud/templates/pages/login.html").read_text()
        assert "_csrf_token" in login_html, (
            "login.html form must include _csrf_token hidden field"
        )

    def test_settings_form_has_csrf_field(self):
        """settings.html must contain _csrf_token hidden input."""
        from pathlib import Path

        settings_html = Path(
            "src/sporedb/cloud/templates/pages/settings.html"
        ).read_text()
        assert "_csrf_token" in settings_html, (
            "settings.html form must include _csrf_token hidden field"
        )


class TestCSRFProtection:
    """Test CSRF token validation on dashboard POST endpoints."""

    @pytest.fixture
    def csrf_app(self):
        """Create a minimal FastAPI app with CSRF middleware for testing."""
        from starlette.applications import Starlette
        from starlette.responses import HTMLResponse, JSONResponse
        from starlette.routing import Route

        async def get_form(request):
            token = getattr(request.state, "csrf_token", "")
            return HTMLResponse(
                f'<form><input name="_csrf_token" value="{token}"></form>'
            )

        async def post_form(request):
            return JSONResponse({"ok": True})

        async def api_endpoint(request):
            return JSONResponse({"ok": True})

        app = Starlette(
            routes=[
                Route("/dash/form", get_form, methods=["GET"]),
                Route("/dash/submit", post_form, methods=["POST"]),
                Route("/api/data", api_endpoint, methods=["POST"]),
            ]
        )
        app.add_middleware(CSRFMiddleware)
        return app

    @pytest.mark.asyncio
    async def test_get_sets_csrf_cookie(self, csrf_app):
        """GET to /dash/* should set a csrftoken cookie."""
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/dash/form")
            assert resp.status_code == 200, f"Body: {resp.text}"
            assert "csrftoken" in resp.cookies

    @pytest.mark.asyncio
    async def test_post_without_csrf_rejected(self, csrf_app):
        """POST to /dash/* without CSRF token should be rejected."""
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/dash/submit", data={"key": "value"})
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_post_with_valid_csrf_accepted(self, csrf_app):
        """POST with matching cookie + form token should succeed."""
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Get CSRF token via GET
            get_resp = await client.get("/dash/form")
            csrf_token = get_resp.cookies["csrftoken"]

            # POST with matching token
            resp = await client.post(
                "/dash/submit",
                data={"_csrf_token": csrf_token},
                cookies={"csrftoken": csrf_token},
            )
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_post_with_mismatched_csrf_rejected(self, csrf_app):
        """POST with mismatched cookie vs form token should be rejected."""
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            get_resp = await client.get("/dash/form")
            csrf_token = get_resp.cookies["csrftoken"]

            resp = await client.post(
                "/dash/submit",
                data={"_csrf_token": "wrong-token"},
                cookies={"csrftoken": csrf_token},
            )
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_api_routes_not_affected(self, csrf_app):
        """POST to /api/* should not require CSRF token."""
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/data", json={"key": "value"})
            assert resp.status_code == 200
