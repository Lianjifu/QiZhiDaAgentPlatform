"""Domain ↔ HTTP DTO mappers for agent_factory."""

from __future__ import annotations

from qzdap.modules.agent_factory.adapter.http.dto import (
    ReleaseResponse,
    TemplateResponse,
    VersionResponse,
)
from qzdap.modules.agent_factory.domain.entities import (
    AgentTemplate,
    AgentVersion,
    Release,
)


def _iso(value) -> str:  # type: ignore[no-untyped-def]
    return value.isoformat() if value is not None else ""


def template_to_dto(entity: AgentTemplate) -> TemplateResponse:
    return TemplateResponse(
        id=str(entity.id),
        tenant_id=str(entity.tenant_id),
        workspace_id=str(entity.workspace_id),
        name=entity.name,
        description=entity.description,
        default_model_id=entity.default_model_id,
        default_system_prompt=entity.default_system_prompt,
        status=entity.status.value,
        metadata=dict(entity.metadata),
        created_by=str(entity.created_by),
        created_at=_iso(entity.created_at),
        updated_at=_iso(entity.updated_at),
    )


def version_to_dto(entity: AgentVersion) -> VersionResponse:
    return VersionResponse(
        id=str(entity.id),
        tenant_id=str(entity.tenant_id),
        workspace_id=str(entity.workspace_id),
        template_id=str(entity.template_id),
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
        published_at=_iso(entity.published_at),
        released_at=_iso(entity.released_at),
        metadata=dict(entity.metadata),
        created_by=str(entity.created_by),
        created_at=_iso(entity.created_at),
        updated_at=_iso(entity.updated_at),
    )


def release_to_dto(entity: Release) -> ReleaseResponse:
    return ReleaseResponse(
        id=str(entity.id),
        tenant_id=str(entity.tenant_id),
        workspace_id=str(entity.workspace_id),
        template_id=str(entity.template_id),
        version_id=str(entity.version_id),
        eval_run_id=str(entity.eval_run_id) if entity.eval_run_id else None,
        eval_score=entity.eval_score,
        status=entity.status.value,
        released_by=str(entity.released_by),
        released_at=_iso(entity.released_at),
        notes=entity.notes,
    )


__all__ = [
    "release_to_dto",
    "template_to_dto",
    "version_to_dto",
]
