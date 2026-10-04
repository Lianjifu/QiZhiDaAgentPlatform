"""Application ports for the evaluation module."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalCaseId,
    EvalDatasetId,
    EvalRunId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.evaluation.domain.entities import (
    EvalCase,
    EvalDataset,
    EvalRun,
)

__all__ = [
    "AgentFactoryQueryPort",
    "EvalDatasetRepository",
    "EvalRunRepository",
    "EvaluationEventPublisher",
    "SubAgentPort",
]


# ── Persistence ──────────────────────────────────────────────────────────


@runtime_checkable
class EvalDatasetRepository(Protocol):
    async def get(
        self, *, tenant_id: TenantId, dataset_id: EvalDatasetId
    ) -> EvalDataset | None: ...

    async def get_by_name(
        self, *, tenant_id: TenantId, name: str
    ) -> EvalDataset | None: ...

    async def list_records(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvalDataset]: ...

    async def add(self, dataset: EvalDataset) -> EvalDataset: ...

    async def update(self, dataset: EvalDataset) -> EvalDataset: ...

    async def add_case(self, case: EvalCase) -> EvalCase: ...

    async def list_cases(
        self, *, tenant_id: TenantId, dataset_id: EvalDatasetId
    ) -> list[EvalCase]: ...


@runtime_checkable
class EvalRunRepository(Protocol):
    async def get(
        self, *, tenant_id: TenantId, run_id: EvalRunId
    ) -> EvalRun | None: ...

    async def get_by_idempotency_key(
        self, *, tenant_id: TenantId, idempotency_key: str
    ) -> EvalRun | None: ...

    async def list_records(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        template_id: AgentTemplateId | None = None,
        version_id: AgentVersionId | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvalRun]: ...

    async def add(self, run: EvalRun) -> EvalRun: ...

    async def update(self, run: EvalRun) -> EvalRun: ...


# ── Cross-module ──────────────────────────────────────────────────────────


@runtime_checkable
class SubAgentPort(Protocol):
    """Adapter that lets the evaluation runner drive agent_runtime.

    One call = one ephemeral session running one turn to completion
    against the agent under test.
    """

    async def run_turn_to_completion(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        owner_id: UserId,
        agent_id: AgentTemplateId,
        agent_version: str,
        user_input: str,
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


@runtime_checkable
class AgentFactoryQueryPort(Protocol):
    """Adapter the runner uses to verify (template_id, version_id) exists.

    Optional; when the runtime adapter fails (template missing, version
    not published), the runner surfaces a clear error instead of running
    cases against nothing.  Not implemented by default — falls through.
    """

    async def get_agent_version(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
    ) -> dict[str, Any] | None: ...


# ── Eventing ─────────────────────────────────────────────────────────────


@runtime_checkable
class EvaluationEventPublisher(Protocol):
    async def publish(self, event: object) -> None: ...


_ = (EvalCaseId,)  # type-only reference to silence unused-import warnings
