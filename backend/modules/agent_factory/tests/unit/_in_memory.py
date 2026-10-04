"""In-memory fakes for agent_factory unit tests."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalRunId,
    ReleaseId,
    TenantId,
    WorkspaceId,
)

from qzdap.modules.agent_factory.application.ports import (
    AgentFactoryEventPublisher,
    AgentTemplateRepository,
    AgentVersionRepository,
    EvalRunSummary,
    EvaluationQueryPort,
    ReleaseRepository,
)
from qzdap.modules.agent_factory.domain.entities import (
    AgentTemplate,
    AgentVersion,
    Release,
)


class InMemoryAgentTemplateRepository(AgentTemplateRepository):
    """Dict-backed repository; uniqueness enforced on add."""

    def __init__(self) -> None:
        self._by_id: dict[tuple[UUID, UUID], AgentTemplate] = {}
        self._by_name: dict[tuple[UUID, str], UUID] = {}

    async def get(
        self, *, tenant_id: TenantId, template_id: AgentTemplateId
    ) -> AgentTemplate | None:
        return self._by_id.get((tenant_id, template_id))

    async def get_by_name(
        self, *, tenant_id: TenantId, name: str
    ) -> AgentTemplate | None:
        tid = self._by_name.get((tenant_id, name))
        return self._by_id.get((tenant_id, tid)) if tid else None

    async def list(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentTemplate]:
        rows = [
            t
            for (tid, _), t in self._by_id.items()
            if tid == tenant_id and t.workspace_id == workspace_id
        ]
        rows.sort(key=lambda t: t.created_at, reverse=True)
        return rows[offset : offset + limit]

    async def add(self, template: AgentTemplate) -> AgentTemplate:
        if (template.tenant_id, template.id) in self._by_id:
            raise RuntimeError("template already added")
        self._by_id[(template.tenant_id, template.id)] = template
        self._by_name[(template.tenant_id, template.name)] = template.id
        return template

    async def update(self, template: AgentTemplate) -> AgentTemplate:
        self._by_id[(template.tenant_id, template.id)] = template
        return template


class InMemoryAgentVersionRepository(AgentVersionRepository):
    """Dict-backed repository; tag uniqueness per (tenant, template) enforced."""

    def __init__(self) -> None:
        self._by_id: dict[tuple[UUID, UUID], AgentVersion] = {}
        self._by_tag: dict[tuple[UUID, UUID, str], UUID] = {}

    async def get(
        self, *, tenant_id: TenantId, version_id: AgentVersionId
    ) -> AgentVersion | None:
        return self._by_id.get((tenant_id, version_id))

    async def get_by_tag(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_tag: str,
    ) -> AgentVersion | None:
        vid = self._by_tag.get((tenant_id, template_id, version_tag))
        return self._by_id.get((tenant_id, vid)) if vid else None

    async def list_for_template(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentVersion]:
        rows = [
            v
            for (tid, _), v in self._by_id.items()
            if tid == tenant_id and v.template_id == template_id
        ]
        rows.sort(key=lambda v: v.created_at, reverse=True)
        return rows[offset : offset + limit]

    async def add(self, version: AgentVersion) -> AgentVersion:
        self._by_id[(version.tenant_id, version.id)] = version
        self._by_tag[(version.tenant_id, version.template_id, version.version_tag)] = (
            version.id
        )
        return version

    async def update(self, version: AgentVersion) -> AgentVersion:
        self._by_id[(version.tenant_id, version.id)] = version
        return version


class InMemoryReleaseRepository(ReleaseRepository):
    def __init__(self) -> None:
        self._by_id: dict[tuple[UUID, UUID], Release] = {}

    async def get(
        self, *, tenant_id: TenantId, release_id: ReleaseId
    ) -> Release | None:
        return self._by_id.get((tenant_id, release_id))

    async def list_for_template(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Release]:
        rows = [
            r
            for (tid, _), r in self._by_id.items()
            if tid == tenant_id and r.template_id == template_id
        ]
        rows.sort(key=lambda r: r.released_at, reverse=True)
        return rows[offset : offset + limit]

    async def add(self, release: Release) -> Release:
        self._by_id[(release.tenant_id, release.id)] = release
        return release


class InMemoryEvaluationQuery(EvaluationQueryPort):
    """Pre-canned eval summary list; tests push (template_id, version_id, summary)."""

    def __init__(self) -> None:
        self._runs: dict[tuple[UUID, UUID, UUID], EvalRunSummary] = {}

    def add(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
        summary: EvalRunSummary,
    ) -> None:
        self._runs[(tenant_id, template_id, version_id)] = summary

    async def latest_passed_run(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
    ) -> EvalRunSummary | None:
        return self._runs.get((tenant_id, template_id, version_id))


class RecordingPublisher(AgentFactoryEventPublisher):
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish(self, event: object) -> None:
        self.published.append(event)


def make_eval_summary(
    *,
    run_id: EvalRunId,
    status: str = "passed",
    mean_score: float | None = 0.8,
    completed_at: Any = None,
) -> EvalRunSummary:
    """Build an EvalRunSummary with a default completed_at set."""
    from datetime import UTC, datetime

    return EvalRunSummary(
        run_id=run_id,
        status=status,
        mean_score=mean_score,
        completed_at=completed_at or datetime.now(UTC),
    )


__all__ = [
    "InMemoryAgentTemplateRepository",
    "InMemoryAgentVersionRepository",
    "InMemoryEvaluationQuery",
    "InMemoryReleaseRepository",
    "RecordingPublisher",
    "make_eval_summary",
]
