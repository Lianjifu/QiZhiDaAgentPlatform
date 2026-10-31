"""**工作流的执行端口** ✓ —— 引擎只认这三个口 ✓。

⚠️ **引擎不直接碰工具 / 模型** ✓ —— 那是别的模块的领域 ✓（编排模块**只
编排** ✓ —— 工具归工具 ✓ / 智能体归会话 ✓）。

| # | 端口 | 谁实现 | 干什么 |
|---|---|---|---|
| 1 | `WorkflowToolPort` | **组合根接工具模块** ✓ | 「工具节点」真调一次工具 ✓ |
| 2 | `WorkflowAgentPort` | **组合根接会话模块** ✓ | 「智能体节点」真跑一轮对话 ✓ |
| 3 | `WorkflowRunRepository` | 模块侧 ✓ | 跑完落一条运行记录 ✓ |

⚠️ **没有端口就不执行那类节点** ✓ —— 而不是**假装跑过** ✗✗（那是 theater ✗）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
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


@dataclass(frozen=True, slots=True)
class WorkflowRunContext:
    """**一次运行的归属** ✓ —— 工具 / 智能体都要用它取身份 ✓。"""

    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID
    workflow_id: UUID
    workflow_name: str = ""


class WorkflowToolPort(ABC):
    """**「工具节点」的执行口** ✓ —— 真调一次工具 ✓。

    ⚠️ **没有它就不执行工具节点** ✓ —— 而不是编一个结果 ✗✗。
    """

    @abstractmethod
    async def invoke(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: WorkflowRunContext,
    ) -> dict[str, Any]:
        """跑一次工具 ✓ —— 返回工具的结果 ✓（原样 ✓）。"""
        ...


class WorkflowAgentPort(ABC):
    """**「智能体节点」的执行口** ✓ —— 真跑一轮对话 ✓。

    ⚠️ **没有它就不执行智能体节点** ✓ —— 而不是编一句文案 ✗✗。
    """

    @abstractmethod
    async def run(
        self,
        *,
        agent: str,
        prompt: str,
        context: WorkflowRunContext,
    ) -> str:
        """跑一轮对话 ✓ —— 返回这一轮的最终回复 ✓。"""
        ...


__all__ = [
    "WorkflowAgentPort",
    "WorkflowRepository",
    "WorkflowRunContext",
    "WorkflowRunRepository",
    "WorkflowToolPort",
    "WorkflowUserStateRepository",
]
