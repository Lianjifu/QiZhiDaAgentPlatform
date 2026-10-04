"""Agent factory domain entities.

Three aggregate roots:

- :class:`AgentTemplate` — a tenant-scoped named template.  Carries
  default prompt + model that new versions inherit.  Mutable: status
  can transition ``active ↔ archived``.
- :class:`AgentVersion` — a typed snapshot of an agent's prompt /
  model / allowed tools / skills / knowledge packages / plan DSL.
  IMMUTABLE once ``status != DRAFT``.  State machine
  ``draft → published → released → retired``.
- :class:`Release` — a record of a successful gate-passed release.
  Carries the eval run that authorized the release + the score.

All entities are frozen dataclasses with ``slots=True``; mutation goes
through ``with_*`` methods that return a new instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalRunId,
    ReleaseId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_factory.domain.value_objects import (
    MAX_ALLOWED_SKILLS,
    MAX_ALLOWED_TOOLS,
    MAX_DESCRIPTION_LEN,
    MAX_KNOWLEDGE_PACKAGE_IDS,
    MAX_NAME_LEN,
    MAX_PROMPT_LEN,
    MAX_REVIEW_LEN,
    MAX_VERSION_TAG_LEN,
    AgentTemplateStatus,
    AgentVersionStatus,
    ReleaseStatus,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── AgentTemplate ─────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class AgentTemplate:
    """A named, tenant-scoped Agent template.

    Defaults are inherited by new :class:`AgentVersion` rows on first
    publish — the version row snapshots the prompt and model so a later
    edit to the template does NOT mutate historical versions.
    """

    id: AgentTemplateId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    name: str
    description: str
    default_model_id: str
    default_system_prompt: str
    status: AgentTemplateStatus
    metadata: dict[str, Any]
    created_by: UserId
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        name: str,
        description: str,
        default_model_id: str,
        default_system_prompt: str,
        metadata: dict[str, Any] | None = None,
        created_by: UserId,
        template_id: AgentTemplateId | None = None,
        now: datetime | None = None,
    ) -> AgentTemplate:
        if not name or not name.strip():
            raise ValueError("AgentTemplate.name must be non-empty")
        if len(name) > MAX_NAME_LEN:
            raise ValueError(
                f"AgentTemplate.name must be <= {MAX_NAME_LEN} chars, got {len(name)}"
            )
        if len(description) > MAX_DESCRIPTION_LEN:
            raise ValueError(
                f"AgentTemplate.description must be <= {MAX_DESCRIPTION_LEN} chars, "
                f"got {len(description)}"
            )
        if not default_model_id or not default_model_id.strip():
            raise ValueError("AgentTemplate.default_model_id must be non-empty")
        if len(default_system_prompt) > MAX_PROMPT_LEN:
            raise ValueError(
                f"AgentTemplate.default_system_prompt must be <= {MAX_PROMPT_LEN} chars"
            )
        ts = now or _utcnow()
        return cls(
            id=template_id or AgentTemplateId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            description=description,
            default_model_id=default_model_id,
            default_system_prompt=default_system_prompt,
            status=AgentTemplateStatus.ACTIVE,
            metadata=dict(metadata or {}),
            created_by=created_by,
            created_at=ts,
            updated_at=ts,
        )

    def with_status(
        self, status: AgentTemplateStatus, *, now: datetime | None = None
    ) -> AgentTemplate:
        ts = now or _utcnow()
        return AgentTemplate(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            name=self.name,
            description=self.description,
            default_model_id=self.default_model_id,
            default_system_prompt=self.default_system_prompt,
            status=status,
            metadata=self.metadata,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=ts,
        )


# ── AgentVersion ──────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class AgentVersion:
    """An immutable snapshot of an Agent's runtime config.

    Carries the typed columns chosen by the user (typed-columns
    decision, see plan §P8 user decision #1).  Once ``status != DRAFT``
    the row is immutable — even ``release_notes`` cannot be edited.
    """

    id: AgentVersionId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    template_id: AgentTemplateId
    version_tag: str
    status: AgentVersionStatus
    system_prompt: str
    model_id: str
    allowed_tools: tuple[str, ...]
    allowed_skills: tuple[str, ...]
    knowledge_package_ids: tuple[
        str, ...
    ]  # stored as str to avoid UUID NewType in tuple
    plan_dsl_snapshot: dict[str, Any] | None
    max_total_steps: int | None
    release_notes: str
    published_at: datetime | None
    released_at: datetime | None
    metadata: dict[str, Any]
    created_by: UserId
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create_draft(
        cls,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        template_id: AgentTemplateId,
        version_tag: str,
        system_prompt: str,
        model_id: str,
        allowed_tools: tuple[str, ...] = (),
        allowed_skills: tuple[str, ...] = (),
        knowledge_package_ids: tuple[str, ...] = (),
        plan_dsl_snapshot: dict[str, Any] | None = None,
        max_total_steps: int | None = None,
        release_notes: str = "",
        metadata: dict[str, Any] | None = None,
        created_by: UserId,
        version_id: AgentVersionId | None = None,
        now: datetime | None = None,
    ) -> AgentVersion:
        if not version_tag or not version_tag.strip():
            raise ValueError("AgentVersion.version_tag must be non-empty")
        if len(version_tag) > MAX_VERSION_TAG_LEN:
            raise ValueError(
                f"AgentVersion.version_tag must be <= {MAX_VERSION_TAG_LEN} chars"
            )
        if not system_prompt:
            raise ValueError("AgentVersion.system_prompt must be non-empty")
        if len(system_prompt) > MAX_PROMPT_LEN:
            raise ValueError(
                f"AgentVersion.system_prompt must be <= {MAX_PROMPT_LEN} chars"
            )
        if not model_id or not model_id.strip():
            raise ValueError("AgentVersion.model_id must be non-empty")
        if len(allowed_tools) > MAX_ALLOWED_TOOLS:
            raise ValueError(
                f"AgentVersion.allowed_tools must be <= {MAX_ALLOWED_TOOLS}"
            )
        if len(allowed_skills) > MAX_ALLOWED_SKILLS:
            raise ValueError(
                f"AgentVersion.allowed_skills must be <= {MAX_ALLOWED_SKILLS}"
            )
        if len(knowledge_package_ids) > MAX_KNOWLEDGE_PACKAGE_IDS:
            raise ValueError(
                f"AgentVersion.knowledge_package_ids must be <= {MAX_KNOWLEDGE_PACKAGE_IDS}"
            )
        if len(release_notes) > MAX_REVIEW_LEN:
            raise ValueError(
                f"AgentVersion.release_notes must be <= {MAX_REVIEW_LEN} chars"
            )
        ts = now or _utcnow()
        return cls(
            id=version_id or AgentVersionId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            template_id=template_id,
            version_tag=version_tag,
            status=AgentVersionStatus.DRAFT,
            system_prompt=system_prompt,
            model_id=model_id,
            allowed_tools=tuple(allowed_tools),
            allowed_skills=tuple(allowed_skills),
            knowledge_package_ids=tuple(knowledge_package_ids),
            plan_dsl_snapshot=dict(plan_dsl_snapshot) if plan_dsl_snapshot else None,
            max_total_steps=max_total_steps,
            release_notes=release_notes,
            published_at=None,
            released_at=None,
            metadata=dict(metadata or {}),
            created_by=created_by,
            created_at=ts,
            updated_at=ts,
        )

    def with_release_notes(
        self, release_notes: str, *, now: datetime | None = None
    ) -> AgentVersion:
        if self.status is not AgentVersionStatus.DRAFT:
            from qzdap.modules.agent_factory.domain.errors import AgentVersionImmutable

            raise AgentVersionImmutable(
                f"cannot edit release_notes on version in status {self.status.value!r}"
            )
        if len(release_notes) > MAX_REVIEW_LEN:
            raise ValueError(
                f"AgentVersion.release_notes must be <= {MAX_REVIEW_LEN} chars"
            )
        ts = now or _utcnow()
        return AgentVersion(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            template_id=self.template_id,
            version_tag=self.version_tag,
            status=self.status,
            system_prompt=self.system_prompt,
            model_id=self.model_id,
            allowed_tools=self.allowed_tools,
            allowed_skills=self.allowed_skills,
            knowledge_package_ids=self.knowledge_package_ids,
            plan_dsl_snapshot=self.plan_dsl_snapshot,
            max_total_steps=self.max_total_steps,
            release_notes=release_notes,
            published_at=self.published_at,
            released_at=self.released_at,
            metadata=self.metadata,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=ts,
        )

    def publish(self, *, now: datetime | None = None) -> AgentVersion:
        if self.status is not AgentVersionStatus.DRAFT:
            from qzdap.modules.agent_factory.domain.errors import (
                AgentVersionInvalidTransition,
            )

            raise AgentVersionInvalidTransition(
                f"can only publish from draft; current status={self.status.value!r}"
            )
        ts = now or _utcnow()
        return AgentVersion(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            template_id=self.template_id,
            version_tag=self.version_tag,
            status=AgentVersionStatus.PUBLISHED,
            system_prompt=self.system_prompt,
            model_id=self.model_id,
            allowed_tools=self.allowed_tools,
            allowed_skills=self.allowed_skills,
            knowledge_package_ids=self.knowledge_package_ids,
            plan_dsl_snapshot=self.plan_dsl_snapshot,
            max_total_steps=self.max_total_steps,
            release_notes=self.release_notes,
            published_at=ts,
            released_at=None,
            metadata=self.metadata,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=ts,
        )

    def release(self, *, now: datetime | None = None) -> AgentVersion:
        if self.status is not AgentVersionStatus.PUBLISHED:
            from qzdap.modules.agent_factory.domain.errors import (
                AgentVersionInvalidTransition,
            )

            raise AgentVersionInvalidTransition(
                f"can only release from published; current status={self.status.value!r}"
            )
        ts = now or _utcnow()
        return AgentVersion(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            template_id=self.template_id,
            version_tag=self.version_tag,
            status=AgentVersionStatus.RELEASED,
            system_prompt=self.system_prompt,
            model_id=self.model_id,
            allowed_tools=self.allowed_tools,
            allowed_skills=self.allowed_skills,
            knowledge_package_ids=self.knowledge_package_ids,
            plan_dsl_snapshot=self.plan_dsl_snapshot,
            max_total_steps=self.max_total_steps,
            release_notes=self.release_notes,
            published_at=self.published_at,
            released_at=ts,
            metadata=self.metadata,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=ts,
        )

    def retire(self, *, now: datetime | None = None) -> AgentVersion:
        if self.status is not AgentVersionStatus.RELEASED:
            from qzdap.modules.agent_factory.domain.errors import (
                AgentVersionInvalidTransition,
            )

            raise AgentVersionInvalidTransition(
                f"can only retire from released; current status={self.status.value!r}"
            )
        ts = now or _utcnow()
        return AgentVersion(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            template_id=self.template_id,
            version_tag=self.version_tag,
            status=AgentVersionStatus.RETIRED,
            system_prompt=self.system_prompt,
            model_id=self.model_id,
            allowed_tools=self.allowed_tools,
            allowed_skills=self.allowed_skills,
            knowledge_package_ids=self.knowledge_package_ids,
            plan_dsl_snapshot=self.plan_dsl_snapshot,
            max_total_steps=self.max_total_steps,
            release_notes=self.release_notes,
            published_at=self.published_at,
            released_at=self.released_at,
            metadata=self.metadata,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=ts,
        )

    def is_immutable(self) -> bool:
        return self.status is not AgentVersionStatus.DRAFT


# ── Release ───────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class Release:
    """A successful gate-passed release record.

    Created by :class:`ReleaseAgentVersionUseCase` once the eval check
    passes.  The ``eval_run_id`` + ``eval_score`` are snapshotted at
    release time for audit.
    """

    id: ReleaseId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    template_id: AgentTemplateId
    version_id: AgentVersionId
    eval_run_id: EvalRunId | None
    eval_score: float | None
    status: ReleaseStatus
    released_by: UserId
    released_at: datetime
    notes: str

    @classmethod
    def create(
        cls,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
        eval_run_id: EvalRunId | None,
        eval_score: float | None,
        released_by: UserId,
        notes: str,
        release_id: ReleaseId | None = None,
        now: datetime | None = None,
    ) -> Release:
        if len(notes) > MAX_REVIEW_LEN:
            raise ValueError(f"Release.notes must be <= {MAX_REVIEW_LEN} chars")
        ts = now or _utcnow()
        return cls(
            id=release_id or ReleaseId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            template_id=template_id,
            version_id=version_id,
            eval_run_id=eval_run_id,
            eval_score=eval_score,
            status=ReleaseStatus.RELEASED,
            released_by=released_by,
            released_at=ts,
            notes=notes,
        )


__all__ = [
    "AgentTemplate",
    "AgentVersion",
    "Release",
]
