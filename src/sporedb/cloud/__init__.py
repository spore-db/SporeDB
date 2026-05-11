"""SporeDB cloud tier: FastAPI-based hosted multi-tenant service."""

from __future__ import annotations

from sporedb.cloud.app import create_app

__all__ = ["create_app"]
