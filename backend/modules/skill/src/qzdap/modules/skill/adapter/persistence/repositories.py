from __future__ import annotations

from uuid import UUID

from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.skill.adapter.persistence.models import SkillORM, SkillUserStateORM
from qzdap.modules.skill.application.ports import (
    SkillRepository,
    SkillUserStateRepository,
)
from qzdap.modules.skill.domain.entities import (
    AuditEntry,
    SchemaField,
    Skill,
    SkillRuntime,
    VersionEntry,
)


def _cross_tenant(row: object) -> bool:
    bound = current_tenant_id()
    if bound is None:
        return False
    return getattr(row, "tenant_id", None) != bound


def skill_to_domain(row: SkillORM) -> Skill:
    return Skill(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        type=row.type,  # type: ignore[arg-type]
        owner=row.owner,
        status=row.status,  # type: ignore[arg-type]
        version=row.version,
        updated_at=row.updated_at,
        created_at=row.created_at,
        calls=row.calls,
        success_rate=row.success_rate,
        error_rate=row.error_rate,
        avg_latency_ms=row.avg_latency_ms,
        rating=row.rating,
        risk=row.risk,  # type: ignore[arg-type]
        need_confirm=row.need_confirm,
        visible_scope=list(row.visible_scope or ["部门"]),
        tags=list(row.tags or []),
        starred=row.starred,
        input_schema=[SchemaField.from_dict(item) for item in (row.input_schema or [])],
        output_schema=[SchemaField.from_dict(item) for item in (row.output_schema or [])],
        versions=[VersionEntry.from_dict(item) for item in (row.versions or [])],
        trend=list(row.trend or [0] * 12),
        used_by_agents=list(row.used_by_agents or []),
        audit_log=[AuditEntry.from_dict(item) for item in (row.audit_log or [])],
        runtime=SkillRuntime.from_dict(row.runtime if isinstance(row.runtime, dict) else {}),
    )


def _apply(row: SkillORM, skill: Skill) -> None:
    row.name = skill.name
    row.description = skill.description
    row.type = skill.type
    row.owner = skill.owner
    row.status = skill.status
    row.version = skill.version
    row.calls = skill.calls
    row.success_rate = skill.success_rate
    row.error_rate = skill.error_rate
    row.avg_latency_ms = skill.avg_latency_ms
    row.rating = skill.rating
    row.risk = skill.risk
    row.need_confirm = skill.need_confirm
    row.visible_scope = list(skill.visible_scope)
    row.tags = list(skill.tags)
    row.starred = skill.starred
    row.input_schema = [item.to_dict() for item in skill.input_schema]
    row.output_schema = [item.to_dict() for item in skill.output_schema]
    row.versions = [item.to_dict() for item in skill.versions]
    row.trend = list(skill.trend)
    row.used_by_agents = list(skill.used_by_agents)
    row.audit_log = [item.to_dict() for item in skill.audit_log]
    row.runtime = skill.runtime.to_dict()
    row.updated_at = skill.updated_at


class SqlSkillRepository(SkillRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, skill: Skill) -> None:
        row = SkillORM(
            id=skill.id,
            tenant_id=skill.tenant_id,
            workspace_id=skill.workspace_id,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
        )
        _apply(row, skill)
        self._s.add(row)

    async def get(self, skill_id: UUID) -> Skill | None:
        row = await self._s.get(SkillORM, skill_id)
        if row is None or _cross_tenant(row):
            return None
        return skill_to_domain(row)

    async def get_by_name(self, *, workspace_id: UUID, name: str) -> Skill | None:
        result = await self._s.execute(
            select(SkillORM).where(SkillORM.workspace_id == workspace_id, SkillORM.name == name)
        )
        row = result.scalars().first()
        if row is None or _cross_tenant(row):
            return None
        return skill_to_domain(row)

    async def list_for_workspace(self, workspace_id: UUID) -> list[Skill]:
        result = await self._s.execute(
            select(SkillORM).where(SkillORM.workspace_id == workspace_id)
        )
        return [skill_to_domain(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def update(self, skill: Skill) -> None:
        row = await self._s.get(SkillORM, skill.id)
        if row is None or _cross_tenant(row):
            return
        _apply(row, skill)

    async def delete(self, skill_id: UUID) -> None:
        row = await self._s.get(SkillORM, skill_id)
        if row is None or _cross_tenant(row):
            return
        await self._s.delete(row)


class SqlSkillUserStateRepository(SkillUserStateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _row(self, *, user_id: UUID, skill_id: UUID) -> SkillUserStateORM | None:
        result = await self._s.execute(
            select(SkillUserStateORM).where(
                SkillUserStateORM.user_id == user_id,
                SkillUserStateORM.skill_id == skill_id,
            )
        )
        row = result.scalars().first()
        if row is None or _cross_tenant(row):
            return None
        return row

    async def get(self, *, user_id: UUID, skill_id: UUID) -> tuple[bool, str | None]:
        row = await self._row(user_id=user_id, skill_id=skill_id)
        if row is None:
            return False, None
        return row.favorited, row.last_used or None

    async def set_favorite(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        skill_id: UUID,
        on: bool,
    ) -> None:
        row = await self._row(user_id=user_id, skill_id=skill_id)
        if row is None:
            self._s.add(
                SkillUserStateORM(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    skill_id=skill_id,
                    favorited=on,
                )
            )
            return
        row.favorited = on

    async def record_use(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        skill_id: UUID,
        at: str,
    ) -> None:
        row = await self._row(user_id=user_id, skill_id=skill_id)
        if row is None:
            self._s.add(
                SkillUserStateORM(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    skill_id=skill_id,
                    last_used=at,
                )
            )
            return
        row.last_used = at
