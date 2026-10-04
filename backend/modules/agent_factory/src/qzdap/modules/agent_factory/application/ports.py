"""Ports the application layer depends on.

Concrete adapters live in ``adapter/``; tests use in-memory fakes from
``tests/unit/_in_memory.py``.  Each port is satisfied by exactly one
production adapter (or in-memory fake in tests).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalRunId,
    ReleaseId,
    TenantId,
    WorkspaceId,
)

from qzdap.modules.agent_factory.domain.entities import (
    AgentTemplate,
    AgentVersion,
    Release,
)

__all__ = [
    "AgentFactoryEventPublisher",
    "AgentTemplateRepository",
    "AgentVersionRepository",
    "EvaluationQueryPort",
    "ReleaseRepository",
]


# ── Persistence ──────────────────────────────────────────────────────────


@runtime_checkable
class AgentTemplateRepository(Protocol):
    """Persistence for :class:`AgentTemplate`."""

    async def get(
        self, *, tenant_id: TenantId, template_id: AgentTemplateId
    ) -> AgentTemplate | None: ...

    async def get_by_name(
        self, *, tenant_id: TenantId, name: str
    ) -> AgentTemplate | None: ...

    async def list(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentTemplate]: ...

    async def add(self, template: AgentTemplate) -> AgentTemplate: ...

    async def update(self, template: AgentTemplate) -> AgentTemplate: ...


@runtime_checkable
class AgentVersionRepository(Protocol):
    """Persistence for :class:`AgentVersion`."""

    async def get(
        self, *, tenant_id: TenantId, version_id: AgentVersionId
    ) -> AgentVersion | None: ...

    async def get_by_tag(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_tag: str,
    ) -> AgentVersion | None: ...

    async def list_for_template(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentVersion]: ...

    async def add(self, version: AgentVersion) -> AgentVersion: ...

    async def update(self, version: AgentVersion) -> AgentVersion: ...


@runtime_checkable
class ReleaseRepository(Protocol):
    """Persistence for :class:`Release`."""

    async def get(
        self, *, tenant_id: TenantId, release_id: ReleaseId
    ) -> Release | None: ...

    async def list_for_template(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Release]: ...

    async def add(self, release: Release) -> Release: ...


# ── Cross-module ──────────────────────────────────────────────────────────


@runtime_checkable
class EvaluationQueryPort(Protocol):
    """Adapter that lets agent_factory ask evaluation for an eval run.

    Implemented by ``EvaluationServiceAdapter`` in the evaluation module
    (``modules/evaluation/adapter/agent_factory_adapter.py``).  P8-6
    closes the agent_factory ↔ evaluation loop by inverting the
    evaluation runner's dependency: agent_factory never imports
    evaluation's ORM; it talks to this port only.
    """

    async def latest_passed_run(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
    ) -> EvalRunSummary | None: ...


class EvalRunSummary:
    """Lightweight view of an EvalRun that crossed the agent_factory boundary.

    Avoids leaking the full evaluation module's :class:`EvalRun` entity
    — the gate only needs id + status + mean_score + completed_at.
    """

    __slots__ = ("completed_at", "id", "mean_score", "status")

    def __init__(
        self,
        *,
        run_id: EvalRunId,
        status: str,
        mean_score: float | None,
        completed_at: Any | None,
    ) -> None:
        self.id = run_id
        self.status = status
        self.mean_score = mean_score
        self.completed_at = completed_at

    def is_gate_passed(self, threshold: float) -> bool:
        return (
            self.status == "passed"
            and self.mean_score is not None
            and self.mean_score >= threshold
            and self.completed_at is not None
        )


# ── Eventing ─────────────────────────────────────────────────────────────


@runtime_checkable
class AgentFactoryEventPublisher(Protocol):
    """Publishes agent_factory events onto the in-process bus."""

    async def publish(self, event: object) -> None: ...
