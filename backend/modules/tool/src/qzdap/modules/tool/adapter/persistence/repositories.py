"""SQLAlchemy repository implementations of the application ports.

PK-only lookups additionally verify `tenant_id` against the value bound
via `bind_tenant_to_session` — defense in depth on top of the auto-filter
installed by `qzdap_persistence.tenant_guard.install_tenant_loader`.
"""

from __future__ import annotations

from uuid import UUID

from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.tool.adapter.persistence.mappers import (
    tool_call_domain_to_orm,
    tool_call_orm_to_domain,
    tool_domain_to_orm,
    tool_orm_to_domain,
)
from qzdap.modules.tool.adapter.persistence.models import ToolCallORM, ToolORM
from qzdap.modules.tool.application.ports import ToolCallRepository, ToolRepository
from qzdap.modules.tool.domain import Tool, ToolCall


def _cross_tenant(o: object) -> bool:
    bound = current_tenant_id()
    if bound is None:
        return False
    return getattr(o, "tenant_id", None) != bound


class SqlToolRepository(ToolRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, tool: Tool) -> None:
        self._s.add(tool_domain_to_orm(tool))

    async def update(self, tool: Tool) -> None:
        o = await self._s.get(ToolORM, tool.id)
        if o is None or _cross_tenant(o):
            return
        o.name = tool.name
        o.description = tool.description
        o.protocol = tool.protocol.value
        o.spec = dict(tool.spec)
        from qzdap.modules.tool.adapter.persistence.mappers import (
            _auth_config_to_dict,
            _spec_operations_to_list,
        )

        o.spec_operations = _spec_operations_to_list(tool.spec_operations)
        o.auth_config = _auth_config_to_dict(tool.auth_config)
        o.rate_limit_per_minute = tool.rate_limit_per_minute
        o.enabled = tool.enabled
        o.version = tool.version
        o.updated_at = tool.updated_at

    async def delete(self, tool_id: UUID) -> None:
        o = await self._s.get(ToolORM, tool_id)
        if o is None or _cross_tenant(o):
            return
        await self._s.delete(o)

    async def get(self, tool_id: UUID) -> Tool | None:
        o = await self._s.get(ToolORM, tool_id)
        if o is None or _cross_tenant(o):
            return None
        return tool_orm_to_domain(o)

    async def get_by_name(self, *, tenant_id: UUID, name: str) -> Tool | None:
        q = select(ToolORM).where(ToolORM.name == name)
        rows = (await self._s.execute(q)).scalars().all()
        for o in rows:
            if o.tenant_id == tenant_id:
                return tool_orm_to_domain(o)
        return None

    async def list(
        self,
        *,
        tenant_id: UUID,
        enabled: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Tool]:
        q = (
            select(ToolORM)
            .order_by(ToolORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if enabled is not None:
            q = q.where(ToolORM.enabled == enabled)
        rows = (await self._s.execute(q)).scalars().all()
        return [tool_orm_to_domain(o) for o in rows if o.tenant_id == tenant_id]


class SqlToolCallRepository(ToolCallRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, call: ToolCall) -> None:
        # Upsert by id: running → succeeded/failed rows share a PK; replace.
        o = await self._s.get(ToolCallORM, call.id)
        if o is None:
            self._s.add(tool_call_domain_to_orm(call))
            return
        o.tool_name = call.tool_name
        o.arguments = dict(call.arguments)
        o.result = dict(call.result) if call.result is not None else None
        o.error_code = call.error_code
        o.status = call.status.value
        o.finished_at = call.finished_at
        o.latency_ms = call.latency_ms

    async def get(self, call_id: UUID) -> ToolCall | None:
        o = await self._s.get(ToolCallORM, call_id)
        if o is None or _cross_tenant(o):
            return None
        return tool_call_orm_to_domain(o)
