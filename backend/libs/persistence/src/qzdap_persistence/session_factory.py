"""Async session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.ext.asyncio import (
    create_async_engine as _sa_create_async_engine,
)


def create_engine(
    database_url: str,
    *,
    pool_size: int = 20,
    max_overflow: int = 10,
    pool_recycle: int = 3600,
    echo: bool = False,
) -> AsyncEngine:
    return _sa_create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        echo=echo,
        future=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class SessionFactory:
    """Async session factory with a `session()` async context manager."""

    def __init__(
        self,
        engine: AsyncEngine,
        factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.engine = engine
        self._factory = factory or create_session_factory(engine)

    @property
    def maker(self) -> async_sessionmaker[AsyncSession]:
        return self._factory

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._factory() as s:
            yield s

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def healthcheck(self) -> bool:
        from sqlalchemy import text

        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001
            return False
        return True


# Make the symbols available at module level
async_session_factory = SessionFactory


def __getattr__(name: str) -> Any:
    if name in {"AsyncEngine", "AsyncSession"}:
        return globals()[name]
    raise AttributeError(name)
