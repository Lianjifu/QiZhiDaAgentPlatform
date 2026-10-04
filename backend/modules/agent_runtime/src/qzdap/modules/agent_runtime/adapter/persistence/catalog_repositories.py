from __future__ import annotations

from uuid import UUID

from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.agent_runtime.adapter.persistence.catalog_models import (
    CatalogAgentORM,
    CatalogAgentUserStateORM,
    SessionMessageORM,
)
from qzdap.modules.agent_runtime.application.catalog_ports import (
    CatalogAgentRepository,
    CatalogAgentUserStateRepository,
)
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent


def _cross_tenant(row: object) -> bool:
    bound = current_tenant_id()
    if bound is None:
        return False
    return getattr(row, "tenant_id", None) != bound


def _to_domain(row: CatalogAgentORM) -> CatalogAgent:
    return CatalogAgent(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        category=row.category,
        owner=row.owner,
        status=row.status,  # type: ignore[arg-type]
        version=row.version,
        updated_at=row.updated_at,
        created_at=row.created_at,
        tags=list(row.tags or []),
        tone=row.tone,  # type: ignore[arg-type]
        calls=row.calls,
        success_rate=row.success_rate,
        error_rate=row.error_rate,
        avg_latency_ms=row.avg_latency_ms,
        rating=row.rating,
        starred=row.starred,
        visible_scope=list(row.visible_scope or ["部门"]),
        data_access=row.data_access,
        model=row.model,
        max_steps=row.max_steps,
        tools=list(row.tools or []),
        versions=list(row.versions or []),
        evaluation_pass_rate=row.evaluation_pass_rate,
        evaluation_runs=row.evaluation_runs,
        evaluation_failed_cases=row.evaluation_failed_cases,
        trend=list(row.trend or []),
        prompts=dict(row.prompts or {}),
        custom_prompts=list(row.custom_prompts or []),
        knowledge_refs=list(row.knowledge_refs or []),
        memory_policy=dict(row.memory_policy or {}),
        flow_refs=list(row.flow_refs or []),
    )


def _apply(row: CatalogAgentORM, agent: CatalogAgent) -> None:
    row.name = agent.name
    row.description = agent.description
    row.category = agent.category
    row.owner = agent.owner
    row.status = agent.status
    row.version = agent.version
    row.tags = list(agent.tags)
    row.tone = agent.tone
    row.calls = agent.calls
    row.success_rate = agent.success_rate
    row.error_rate = agent.error_rate
    row.avg_latency_ms = agent.avg_latency_ms
    row.rating = agent.rating
    row.starred = agent.starred
    row.visible_scope = list(agent.visible_scope)
    row.data_access = agent.data_access
    row.model = agent.model
    row.max_steps = agent.max_steps
    row.tools = list(agent.tools)
    row.versions = list(agent.versions)
    row.evaluation_pass_rate = agent.evaluation_pass_rate
    row.evaluation_runs = agent.evaluation_runs
    row.evaluation_failed_cases = agent.evaluation_failed_cases
    row.trend = list(agent.trend)
    row.prompts = dict(agent.prompts)
    row.custom_prompts = list(agent.custom_prompts)
    row.knowledge_refs = list(agent.knowledge_refs)
    row.memory_policy = dict(agent.memory_policy)
    row.flow_refs = list(agent.flow_refs)
    row.updated_at = agent.updated_at


class SqlCatalogAgentRepository(CatalogAgentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, agent: CatalogAgent) -> None:
        row = CatalogAgentORM(
            id=agent.id,
            tenant_id=agent.tenant_id,
            workspace_id=agent.workspace_id,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )
        _apply(row, agent)
        self._s.add(row)

    async def get(self, agent_id: UUID) -> CatalogAgent | None:
        row = await self._s.get(CatalogAgentORM, agent_id)
        if row is None or _cross_tenant(row):
            return None
        return _to_domain(row)

    async def list_for_workspace(self, workspace_id: UUID) -> list[CatalogAgent]:
        result = await self._s.execute(
            select(CatalogAgentORM).where(CatalogAgentORM.workspace_id == workspace_id)
        )
        return [_to_domain(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def update(self, agent: CatalogAgent) -> None:
        row = await self._s.get(CatalogAgentORM, agent.id)
        if row is None or _cross_tenant(row):
            return
        _apply(row, agent)

    async def delete(self, agent_id: UUID) -> None:
        row = await self._s.get(CatalogAgentORM, agent_id)
        if row is None or _cross_tenant(row):
            return
        await self._s.delete(row)


class SqlCatalogAgentUserStateRepository(CatalogAgentUserStateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def set_favorite(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        agent_id: UUID,
        on: bool,
    ) -> None:
        result = await self._s.execute(
            select(CatalogAgentUserStateORM).where(
                CatalogAgentUserStateORM.user_id == user_id,
                CatalogAgentUserStateORM.agent_id == agent_id,
            )
        )
        row = result.scalars().first()
        if row is None:
            self._s.add(
                CatalogAgentUserStateORM(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    favorited=on,
                )
            )
            return
        row.favorited = on


class SqlSessionMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_for_session(self, session_id: UUID) -> list[dict]:
        result = await self._s.execute(
            select(SessionMessageORM)
            .where(SessionMessageORM.session_id == session_id)
            .order_by(SessionMessageORM.seq.asc())
        )
        out = []
        for row in result.scalars().all():
            if _cross_tenant(row):
                continue
            out.append(
                {
                    "id": str(row.id),
                    "role": row.role,
                    "content": row.content,
                    "toolName": row.tool_name,
                    "seq": row.seq,
                    "turnId": str(row.turn_id) if row.turn_id else None,
                }
            )
        return out

    async def append(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        turn_id: UUID | None,
        seq: int,
        role: str,
        content: str,
        tool_name: str = "",
        extra: dict | None = None,
    ) -> None:
        self._s.add(
            SessionMessageORM(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                session_id=session_id,
                turn_id=turn_id,
                seq=seq,
                role=role,
                content=content,
                tool_name=tool_name,
                extra=extra or {},
            )
        )


__all__ = [
    "SqlCatalogAgentRepository",
    "SqlCatalogAgentUserStateRepository",
    "SqlSessionMessageRepository",
]
