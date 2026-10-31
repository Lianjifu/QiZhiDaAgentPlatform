"""**工作流执行口的接线** ✓（组合根 ✓ —— 唯一能同时看到两个模块的地方 ✓）。

⚠️ **为什么放在组合根** ✓ —— 「工具节点」要调**工具模块** ✓、「智能体节点」
要跑**会话模块** ✓ —— 编排模块**不该反向依赖**它们 ✓（依赖方向 ✓）。

| # | 端口 | 接到哪 |
|---|---|---|
| 1 | `WorkflowToolPort` | 工具模块的 `ToolService.invoke_tool` ✓（真调一次 ✓） |
| 2 | `WorkflowAgentPort` | 会话模块的 `CopilotSessionService` ✓（真跑一轮对话 ✓） |

⚠️ **两个口都是请求作用域** ✓ —— 工具服务与对话服务都持有**这一个请求的
DB 会话** ✓（跨请求复用会串租户 ✗✗）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from qzdap.modules.orchestration.application.ports import (
    WorkflowAgentPort,
    WorkflowRunContext,
    WorkflowToolPort,
)
from qzdap_kernel.ids import TenantId, UserId, WorkspaceId


class ToolWorkflowPort(WorkflowToolPort):
    """**「工具节点」→ 工具模块** ✓ —— 真调一次工具 ✓。"""

    def __init__(self, tool_service: Any) -> None:
        self._svc = tool_service

    async def invoke(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: WorkflowRunContext,
    ) -> dict[str, Any]:
        call = await self._svc.invoke_tool().execute(
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            owner_id=UserId(context.user_id),
            tool_name=tool_name,
            arguments=arguments,
            # ⚠️ **工作流不是一轮对话** ✓ —— 没有轮次 id ✓（工具的幂等键
            # 因此按「参数指纹」算 ✓ —— 同参重跑会命中幂等 ✓）。
            turn_id=None,
        )
        result = getattr(call, "result", None)
        return dict(result) if isinstance(result, dict) else {"result": result}


class AgentWorkflowPort(WorkflowAgentPort):
    """**「智能体节点」→ 会话模块** ✓ —— 真跑一轮对话 ✓。

    ⚠️ **按名字找智能体** ✓（节点配置里写的是名字 ✓）—— 找不到就**报错**
    ✓（不静默跳过 ✓ —— 跳过了流程看起来是跑通了 ✗✗）。
    """

    def __init__(
        self,
        *,
        session: Any,
        copilot_factory: Any,
        catalog_factory: Any,
    ) -> None:
        self._session = session
        self._copilots = copilot_factory
        self._catalogs = catalog_factory

    async def run(
        self,
        *,
        agent: str,
        prompt: str,
        context: WorkflowRunContext,
    ) -> str:
        agent_id = await self._resolve_agent(context, agent)
        copilot = self._copilots.for_session(self._session)
        detail = await copilot.create_session(
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            owner_id=context.user_id,
            agent_id=agent_id,
            title=f"工作流：{context.workflow_name}",
        )
        session_id = UUID(str(detail["id"]))
        parts: list[str] = []
        async for chunk in copilot.turn_entry.stream(
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            owner_id=context.user_id,
            session_id=session_id,
            user_input=prompt,
        ):
            if getattr(chunk, "kind", "") == "message":
                parts.append(str(getattr(chunk, "content", "") or ""))
        return "".join(parts)

    async def _resolve_agent(self, context: WorkflowRunContext, name: str) -> UUID:
        """**按名字找智能体** ✓ —— 只认**已发布**的 ✓。"""
        catalog = self._catalogs.for_session(self._session)
        rows = await catalog.list_catalog(workspace_id=context.workspace_id)
        for row in rows:
            if str(row.get("name") or "") == name:
                return UUID(str(row.get("id")))
        raise ValueError(f"找不到智能体：{name}")


__all__ = ["AgentWorkflowPort", "ToolWorkflowPort"]
