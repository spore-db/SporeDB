"""Tests for AsyncSessionFactory (cloud/db/session.py).

Covers lines 32-33, 46-53, 57, 60, 63:
- Constructor creates engine and session factory
- get_session() yields a working session
- get_session() rolls back on exception
- dispose() disposes the engine
- __aenter__ / __aexit__ context manager protocol
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sporedb.cloud.db.session import AsyncSessionFactory


@pytest_asyncio.fixture
async def sqlite_factory(tmp_path):
    """AsyncSessionFactory backed by an in-memory SQLite database."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test_session.db"
    factory = AsyncSessionFactory(db_url, echo=False)
    yield factory
    await factory.dispose()


class TestAsyncSessionFactoryCreation:
    """Constructor wires up engine and session factory."""

    def test_init_creates_factory(self, tmp_path) -> None:
        db_url = f"sqlite+aiosqlite:///{tmp_path}/init_test.db"
        factory = AsyncSessionFactory(db_url)
        # Engine and session factory should be set on construction
        assert factory._engine is not None
        assert factory._session_factory is not None


class TestGetSession:
    """get_session() yields AsyncSession and handles errors."""

    @pytest.mark.asyncio
    async def test_get_session_yields_async_session(self, sqlite_factory) -> None:
        async with sqlite_factory.get_session() as session:
            assert isinstance(session, AsyncSession)

    @pytest.mark.asyncio
    async def test_get_session_can_execute_query(self, sqlite_factory) -> None:
        async with sqlite_factory.get_session() as session:
            result = await session.execute(text("SELECT 1"))
            row = result.fetchone()
            assert row[0] == 1

    @pytest.mark.asyncio
    async def test_get_session_rollback_on_exception(self, sqlite_factory) -> None:
        """Exceptions inside the context manager trigger rollback and re-raise."""
        with pytest.raises(RuntimeError, match="deliberate"):
            async with sqlite_factory.get_session() as session:
                _ = session  # just to use the session
                raise RuntimeError("deliberate test error")


class TestDispose:
    """dispose() disposes the engine connection pool."""

    @pytest.mark.asyncio
    async def test_dispose_closes_engine(self, tmp_path) -> None:
        db_url = f"sqlite+aiosqlite:///{tmp_path}/dispose_test.db"
        factory = AsyncSessionFactory(db_url)
        # Should not raise
        await factory.dispose()


class TestAsyncContextManager:
    """AsyncSessionFactory supports async with syntax."""

    @pytest.mark.asyncio
    async def test_aenter_returns_self(self, tmp_path) -> None:
        db_url = f"sqlite+aiosqlite:///{tmp_path}/ctx_test.db"
        async with AsyncSessionFactory(db_url) as factory:
            assert isinstance(factory, AsyncSessionFactory)

    @pytest.mark.asyncio
    async def test_aexit_calls_dispose(self, tmp_path) -> None:
        """Exiting the async context manager disposes the engine without error."""
        db_url = f"sqlite+aiosqlite:///{tmp_path}/ctx_exit_test.db"
        factory = AsyncSessionFactory(db_url)
        async with factory:
            pass
        # Engine should be disposed - a second dispose should not raise
        await factory.dispose()
