"""FastAPI application factory for SporeDB cloud tier.

Creates the ASGI application with lifespan management, CORS middleware,
health check, and versioned API routers for auth and batch management.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import boto3
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from sporedb.cloud.config import CloudSettings
from sporedb.cloud.dashboard_deps import SlidingWindowRefreshMiddleware
from sporedb.cloud.db.session import AsyncSessionFactory
from sporedb.cloud.routes import analytics, audit, data, query
from sporedb.cloud.routes.auth import router as auth_router
from sporedb.cloud.routes.batches import router as batches_router
from sporedb.cloud.routes.dashboard import router as dashboard_router
from sporedb.cloud.routes.figures import router as figures_router
from sporedb.cloud.services.query_service import QueryService
from sporedb.cloud.storage.s3 import S3Storage


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle: startup and shutdown resources."""
    settings: CloudSettings = app.state.settings

    # Database
    db = AsyncSessionFactory(settings.database_url)
    app.state.db_session = db

    # S3-compatible object storage
    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    app.state.s3 = s3_client
    app.state.s3_storage = S3Storage(s3_client, settings.s3_bucket)

    # Ed25519 keys for JWT signing
    private_pem = Path(settings.jwt_secret_key_path).read_bytes()
    private_key = load_pem_private_key(private_pem, password=None)
    app.state.jwt_private_key = private_key

    public_pem = Path(settings.jwt_public_key_path).read_bytes()
    public_key = load_pem_public_key(public_pem)
    app.state.jwt_public_key = public_key

    # QueryService for DSL query execution against S3 Parquet
    app.state.query_service = QueryService(
        s3_config={
            "region": settings.s3_region,
            "key_id": settings.s3_access_key,
            "secret": settings.s3_secret_key,
            "endpoint": settings.s3_endpoint.replace("http://", "").replace(
                "https://", ""
            ),
            "bucket": settings.s3_bucket,
        }
    )

    yield

    # Shutdown
    await db.dispose()


def create_app(settings: CloudSettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    settings:
        Cloud tier configuration. If None, loads from environment
        variables with the ``SPOREDB_`` prefix.
    """
    if settings is None:
        settings = CloudSettings()

    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        lifespan=_lifespan,
    )

    # Store settings for lifespan and dependencies to access
    app.state.settings = settings

    # CORS — reject wildcard with credentials in non-debug mode
    if settings.cors_origins == ["*"]:
        if not settings.debug:
            raise ValueError(
                "CORS wildcard origin ('*') is not allowed in production. "
                "Set SPOREDB_CORS_ORIGINS to specific allowed origins."
            )
        # Debug mode: allow wildcard but WITHOUT credentials
        allow_creds = False
    else:
        allow_creds = True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=allow_creds,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Sliding window token refresh for dashboard cookie sessions
    app.add_middleware(SlidingWindowRefreshMiddleware)

    # CSRF protection for dashboard form submissions (double-submit cookie)
    from sporedb.cloud.dashboard_deps import CSRFMiddleware

    app.add_middleware(CSRFMiddleware)

    # Rate limiting on auth endpoints (T-13-07 / HI-07)
    from sporedb.cloud.routes.auth import limiter as auth_limiter

    app.state.limiter = auth_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # Health check
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # API routers
    app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(batches_router, prefix="/api/v1/batches", tags=["batches"])
    app.include_router(data.router, prefix="/api/v1/data", tags=["data"])
    app.include_router(query.router, prefix="/api/v1/query", tags=["query"])
    app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
    app.include_router(audit.router, prefix="/api/v1/audit", tags=["audit"])

    # Dashboard (server-rendered HTML routes)
    app.include_router(dashboard_router)  # Router already has /dash prefix

    # Dashboard figure endpoints (Plotly JSON for client-side rendering)
    app.include_router(figures_router)

    # Static files for dashboard assets
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount(
            "/dash/static",
            StaticFiles(directory=str(static_dir)),
            name="dashboard_static",
        )

    return app
