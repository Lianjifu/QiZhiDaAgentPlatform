"""Unit of Work.

`UnitOfWork` bundles a session with its tenant scope, so a multi-aggregate
transaction can commit or roll back as one unit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
