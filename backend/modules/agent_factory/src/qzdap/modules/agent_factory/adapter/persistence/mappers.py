"""Domain ↔ ORM mappers for the agent_factory module.

Pure functions; SQL repositories call these from inside the session.
"""

from __future__ import annotations

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalRunId,
    ReleaseId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_factory.adapter.persistence.models import (
    AgentTemplateORM,
    AgentVersionORM,
    ReleaseORM,
)
from qzdap.modules.agent_factory.domain.entities import (
    AgentTemplate,
    AgentVersion,
    Release,
)
from qzdap.modules.agent_factory.domain.value_objects import (
    AgentTemplateStatus,
    AgentVersionStatus,
    ReleaseStatus,
)

# ── AgentTemplate ─────────────────────────────────────────────────────────


def template_to_domain(row: AgentTemplateORM) -> AgentTemplate:
    return AgentTemplate(
        id=AgentTemplateId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=WorkspaceId(row.workspace_id),
        name=row.name,
        description=row.description or "",
        default_model_id=row.default_model_id,
        default_system_prompt=row.default_system_prompt,
        status=AgentTemplateStatus(row.status),
        metadata=dict(row.metadata_ or {}),
        created_by=UserId(row.created_by) if row.created_by else UserId(row.id),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def template_to_orm(entity: AgentTemplate) -> AgentTemplateORM:
    return AgentTemplateORM(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        name=entity.name,
        description=entity.description,
        default_model_id=entity.default_model_id,
        default_system_prompt=entity.default_system_prompt,
        status=entity.status.value,
        metadata_=dict(entity.metadata),
        created_by=entity.created_by,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


# ── AgentVersion ──────────────────────────────────────────────────────────


def version_to_domain(row: AgentVersionORM) -> AgentVersion:
    return AgentVersion(
        id=AgentVersionId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=WorkspaceId(row.workspace_id),
        template_id=AgentTemplateId(row.template_id),
        version_tag=row.version_tag,
        status=AgentVersionStatus(row.status),
        system_prompt=row.system_prompt,
        model_id=row.model_id,
        allowed_tools=tuple(row.allowed_tools or []),
        allowed_skills=tuple(row.allowed_skills or []),
        knowledge_package_ids=tuple(row.knowledge_package_ids or []),
        plan_dsl_snapshot=dict(row.plan_dsl_snapshot)
        if row.plan_dsl_snapshot is not None
        else None,
        max_total_steps=row.max_total_steps,
        release_notes=row.release_notes or "",
        published_at=row.published_at,
        released_at=row.released_at,
        metadata=dict(row.metadata_ or {}),
        created_by=UserId(row.created_by) if row.created_by else UserId(row.id),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def version_to_orm(entity: AgentVersion) -> AgentVersionORM:
    return AgentVersionORM(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        template_id=entity.template_id,
        version_tag=entity.version_tag,
        status=entity.status.value,
        system_prompt=entity.system_prompt,
        model_id=entity.model_id,
        allowed_tools=list(entity.allowed_tools),
        allowed_skills=list(entity.allowed_skills),
        knowledge_package_ids=list(entity.knowledge_package_ids),
        plan_dsl_snapshot=dict(entity.plan_dsl_snapshot)
        if entity.plan_dsl_snapshot is not None
        else None,
        max_total_steps=entity.max_total_steps,
        release_notes=entity.release_notes,
        published_at=entity.published_at,
        released_at=entity.released_at,
        metadata_=dict(entity.metadata),
        created_by=entity.created_by,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


# ── Release ───────────────────────────────────────────────────────────────


def release_to_domain(row: ReleaseORM) -> Release:
    return Release(
        id=ReleaseId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=WorkspaceId(row.workspace_id),
        template_id=AgentTemplateId(row.template_id),
        version_id=AgentVersionId(row.version_id),
        eval_run_id=EvalRunId(row.eval_run_id) if row.eval_run_id else None,
        eval_score=float(row.eval_score) if row.eval_score is not None else None,
        status=ReleaseStatus(row.status),
        released_by=UserId(row.released_by) if row.released_by else UserId(row.id),
        released_at=row.released_at,
        notes=row.notes or "",
    )


def release_to_orm(entity: Release) -> ReleaseORM:
    return ReleaseORM(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        template_id=entity.template_id,
        version_id=entity.version_id,
        eval_run_id=entity.eval_run_id,
        eval_score=entity.eval_score,
        status=entity.status.value,
        released_by=entity.released_by,
        released_at=entity.released_at,
        notes=entity.notes,
    )


__all__ = [
    "release_to_domain",
    "release_to_orm",
    "template_to_domain",
    "template_to_orm",
    "version_to_domain",
    "version_to_orm",
]
