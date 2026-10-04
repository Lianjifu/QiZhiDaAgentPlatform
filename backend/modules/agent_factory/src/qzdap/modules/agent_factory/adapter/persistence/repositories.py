"""Async-SQLAlchemy implementation of the agent_factory ports.

- :class:`SqlAgentTemplateRepository` — agent_templates
- :class:`SqlAgentVersionRepository`  — agent_versions (immutable once non-draft)
- :class:`SqlReleaseRepository`       — releases

The repositories write via the injected ``AsyncSession``.  Event emission
goes through ``AgentFactoryEventPublisher`` from the application layer
(use cases own event publication).
"""

from __future__ import annotations

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    ReleaseId,
    TenantId,
    WorkspaceId,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.agent_factory.adapter.persistence.mappers import (
    release_to_domain,
    release_to_orm,
    template_to_domain,
    template_to_orm,
    version_to_domain,
    version_to_orm,
)
from qzdap.modules.agent_factory.adapter.persistence.models import (
    AgentTemplateORM,
    AgentVersionORM,
    ReleaseORM,
)
from qzdap.modules.agent_factory.application.ports import (
    AgentTemplateRepository,
    AgentVersionRepository,
    ReleaseRepository,
)
from qzdap.modules.agent_factory.domain.entities import (
    AgentTemplate,
    AgentVersion,
    Release,
)
from qzdap.modules.agent_factory.domain.errors import (
    AgentTemplateNameConflict,
    AgentVersionTagConflict,
)

# ── AgentTemplateRepository ───────────────────────────────────────────────


class SqlAgentTemplateRepository(AgentTemplateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, *, tenant_id: TenantId, template_id: AgentTemplateId
    ) -> AgentTemplate | None:
        result = await self._session.execute(
            select(AgentTemplateORM).where(
                AgentTemplateORM.tenant_id == tenant_id,
                AgentTemplateORM.id == template_id,
            )
        )
        row = result.scalar_one_or_none()
        return template_to_domain(row) if row is not None else None

    async def get_by_name(
        self, *, tenant_id: TenantId, name: str
    ) -> AgentTemplate | None:
        result = await self._session.execute(
            select(AgentTemplateORM).where(
                AgentTemplateORM.tenant_id == tenant_id,
                AgentTemplateORM.name == name,
            )
        )
        row = result.scalar_one_or_none()
        return template_to_domain(row) if row is not None else None

    async def list(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentTemplate]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        result = await self._session.execute(
            select(AgentTemplateORM)
            .where(
                AgentTemplateORM.tenant_id == tenant_id,
                AgentTemplateORM.workspace_id == workspace_id,
            )
            .order_by(AgentTemplateORM.created_at.desc())
            .limit(limit)
            .offset(max(0, offset))
        )
        return [template_to_domain(r) for r in result.scalars().all()]

    async def add(self, template: AgentTemplate) -> AgentTemplate:
        row = template_to_orm(template)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise AgentTemplateNameConflict(
                f"agent template name {template.name!r} already exists in tenant"
            ) from exc
        return template_to_domain(row)

    async def update(self, template: AgentTemplate) -> AgentTemplate:
        existing = await self._session.get(AgentTemplateORM, template.id)
        if existing is None or existing.tenant_id != template.tenant_id:
            from qzdap.modules.agent_factory.domain.errors import AgentTemplateNotFound

            raise AgentTemplateNotFound(f"agent template {template.id} not found")
        existing.name = template.name
        existing.description = template.description
        existing.default_model_id = template.default_model_id
        existing.default_system_prompt = template.default_system_prompt
        existing.status = template.status.value
        existing.metadata_ = dict(template.metadata)
        existing.updated_at = template.updated_at
        await self._session.flush()
        return template_to_domain(existing)


# ── AgentVersionRepository ────────────────────────────────────────────────


class SqlAgentVersionRepository(AgentVersionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, *, tenant_id: TenantId, version_id: AgentVersionId
    ) -> AgentVersion | None:
        result = await self._session.execute(
            select(AgentVersionORM).where(
                AgentVersionORM.tenant_id == tenant_id,
                AgentVersionORM.id == version_id,
            )
        )
        row = result.scalar_one_or_none()
        return version_to_domain(row) if row is not None else None

    async def get_by_tag(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_tag: str,
    ) -> AgentVersion | None:
        result = await self._session.execute(
            select(AgentVersionORM).where(
                AgentVersionORM.tenant_id == tenant_id,
                AgentVersionORM.template_id == template_id,
                AgentVersionORM.version_tag == version_tag,
            )
        )
        row = result.scalar_one_or_none()
        return version_to_domain(row) if row is not None else None

    async def list_for_template(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentVersion]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        result = await self._session.execute(
            select(AgentVersionORM)
            .where(
                AgentVersionORM.tenant_id == tenant_id,
                AgentVersionORM.template_id == template_id,
            )
            .order_by(AgentVersionORM.created_at.desc())
            .limit(limit)
            .offset(max(0, offset))
        )
        return [version_to_domain(r) for r in result.scalars().all()]

    async def add(self, version: AgentVersion) -> AgentVersion:
        row = version_to_orm(version)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise AgentVersionTagConflict(
                f"version_tag {version.version_tag!r} already exists for this template"
            ) from exc
        return version_to_domain(row)

    async def update(self, version: AgentVersion) -> AgentVersion:
        existing = await self._session.get(AgentVersionORM, version.id)
        if existing is None or existing.tenant_id != version.tenant_id:
            from qzdap.modules.agent_factory.domain.errors import AgentVersionNotFound

            raise AgentVersionNotFound(f"agent version {version.id} not found")
        existing.status = version.status.value
        existing.system_prompt = version.system_prompt
        existing.model_id = version.model_id
        existing.allowed_tools = list(version.allowed_tools)
        existing.allowed_skills = list(version.allowed_skills)
        existing.knowledge_package_ids = list(version.knowledge_package_ids)
        existing.plan_dsl_snapshot = (
            dict(version.plan_dsl_snapshot)
            if version.plan_dsl_snapshot is not None
            else None
        )
        existing.max_total_steps = version.max_total_steps
        existing.release_notes = version.release_notes
        existing.published_at = version.published_at
        existing.released_at = version.released_at
        existing.metadata_ = dict(version.metadata)
        existing.updated_at = version.updated_at
        await self._session.flush()
        return version_to_domain(existing)


# ── ReleaseRepository ─────────────────────────────────────────────────────


class SqlReleaseRepository(ReleaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, *, tenant_id: TenantId, release_id: ReleaseId
    ) -> Release | None:
        result = await self._session.execute(
            select(ReleaseORM).where(
                ReleaseORM.tenant_id == tenant_id,
                ReleaseORM.id == release_id,
            )
        )
        row = result.scalar_one_or_none()
        return release_to_domain(row) if row is not None else None

    async def list_for_template(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Release]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        result = await self._session.execute(
            select(ReleaseORM)
            .where(
                ReleaseORM.tenant_id == tenant_id,
                ReleaseORM.template_id == template_id,
            )
            .order_by(ReleaseORM.released_at.desc())
            .limit(limit)
            .offset(max(0, offset))
        )
        return [release_to_domain(r) for r in result.scalars().all()]

    async def add(self, release: Release) -> Release:
        row = release_to_orm(release)
        self._session.add(row)
        await self._session.flush()
        return release_to_domain(row)


__all__ = [
    "SqlAgentTemplateRepository",
    "SqlAgentVersionRepository",
    "SqlReleaseRepository",
]
