from abc import ABC, abstractmethod
from uuid import UUID

from qzdap.modules.orchestration.domain.entities import FlowRun, Workflow


class WorkflowRepository(ABC):
    @abstractmethod
    async def add(self, workflow: Workflow) -> None: ...

    @abstractmethod
    async def get(self, workflow_id: UUID) -> Workflow | None: ...

    @abstractmethod
    async def list_for_workspace(self, workspace_id: UUID) -> list[Workflow]: ...

    @abstractmethod
    async def update(self, workflow: Workflow) -> None: ...

    @abstractmethod
    async def delete(self, workflow_id: UUID) -> None: ...


class WorkflowUserStateRepository(ABC):
    @abstractmethod
    async def set_favorite(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        workflow_id: UUID,
        on: bool,
    ) -> None: ...


class WorkflowRunRepository(ABC):
    @abstractmethod
    async def add(self, run: FlowRun) -> None: ...

    @abstractmethod
    async def list_for_user(
        self, *, workspace_id: UUID, user_id: UUID, limit: int = 50
    ) -> list[FlowRun]: ...


__all__ = ["WorkflowRepository", "WorkflowRunRepository", "WorkflowUserStateRepository"]
