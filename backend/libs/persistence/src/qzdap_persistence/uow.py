"""Unit of Work.

`unit_of_work` is the canonical pattern for committing a multi-aggregate
transaction. It binds the session to a tenant scope (via `bind_tenant_to_session`)
and yields it to the caller's `async with` block.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from qzdap_persistence.tenant_guard import bind_tenant_to_session, reset_tenant_to_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork:
    def __init__(self, session: AsyncSession, tenant_id: object | None) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self._committed = False

    async def commit(self) -> None:
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        await self.session.rollback()


@asynccontextmanager
async def unit_of_work(
    session: AsyncSession,
    tenant_id: object | None = None,
) -> AsyncIterator[UnitOfWork]:
    token = bind_tenant_to_session(tenant_id)  # type: ignore[arg-type]
    uow = UnitOfWork(session, tenant_id)
    try:
        yield uow
    except Exception:
        await uow.rollback()
        raise
    finally:
        reset_tenant_to_session(token)
        if not uow._committed:
            await uow.rollback()
