"""Async database session management for SporeDB cloud tier."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class AsyncSessionFactory:
    """Factory for async SQLAlchemy sessions.

    Usage::

        factory = AsyncSessionFactory("postgresql+asyncpg://...")
        async with factory.get_session() as session:
            result = await session.execute(...)

    Or as an async context manager::

        async with AsyncSessionFactory("postgresql+asyncpg://...") as factory:
            async with factory.get_session() as session:
                ...
    """

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self._engine = create_async_engine(database_url, echo=echo)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """Yield an async session; rollback on error.

        Caller must commit explicitly.  Removing the automatic commit
        eliminates the double-commit issue (HI-03) where route handlers
        that already call ``await session.commit()`` would trigger a
        second, redundant commit from the context manager.
        """
        session = self._session_factory()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def dispose(self) -> None:
        """Dispose of the underlying engine and its connection pool."""
        await self._engine.dispose()

    async def __aenter__(self) -> AsyncSessionFactory:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.dispose()
