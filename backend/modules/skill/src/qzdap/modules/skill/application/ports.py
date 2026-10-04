from abc import ABC, abstractmethod
from typing import Protocol
from uuid import UUID

from qzdap.modules.skill.domain.entities import Skill


class SkillRepository(ABC):
    @abstractmethod
    async def add(self, skill: Skill) -> None: ...

    @abstractmethod
    async def get(self, skill_id: UUID) -> Skill | None: ...

    @abstractmethod
    async def get_by_name(self, *, workspace_id: UUID, name: str) -> Skill | None: ...

    @abstractmethod
    async def list_for_workspace(self, workspace_id: UUID) -> list[Skill]: ...

    @abstractmethod
    async def update(self, skill: Skill) -> None: ...

    @abstractmethod
    async def delete(self, skill_id: UUID) -> None: ...


class SkillUserStateRepository(ABC):
    @abstractmethod
    async def get(
        self, *, user_id: UUID, skill_id: UUID
    ) -> tuple[bool, str | None]: ...

    @abstractmethod
    async def set_favorite(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        skill_id: UUID,
        on: bool,
    ) -> None: ...

    @abstractmethod
    async def record_use(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        skill_id: UUID,
        at: str,
    ) -> None: ...


class SandboxJobPort(Protocol):
    async def run_job(
        self,
        *,
        kind: str,
        tenant_id: UUID,
        workspace_id: UUID,
        call_id: UUID,
        image: str,
        command: list[str],
        files: dict[str, str],
        timeout_ms: int,
        network: str,
        memory_mb: int,
        stdin: str = "",
        env: dict[str, str] | None = None,
        agent_id: UUID | None = None,
    ) -> dict: ...


__all__ = ["SandboxJobPort", "SkillRepository", "SkillUserStateRepository"]
