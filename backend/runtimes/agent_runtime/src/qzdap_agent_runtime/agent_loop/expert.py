"""``ExpertAssembler`` —— **专家实例的装配** ✓（Agent 方案 §4.2 ✓ / §5.2.1 ✓ / §5.3.1 ✓）。

⚠️ **专家 Agent 的实例 = 模型 + 指令 + 工具集** ✓（§4.2 规则 1 ✓）——
**不是一个独立进程** ✓，是一次**受约束的模型调用** ✓。

⚠️ **本模块只「取」不「选」** ✓（决策 #4 ✓）——
选专家是 ``AgentRouterPort`` 的事 ✓；模型是**查表**得到的 ✓（§5.2.1 ✓）；
工具是**绑定集 + 治理过滤**的结果 ✓（§5.3.1 ✓）。

```
专家选择（AgentRouterPort ✓）
   → 专家配置里的模型名 / model_id / route_id ✓
      → 取值链（LLMCaller.resolve ✓ —— §5.2.1 ✓）→ QZDAPChatModel ✓
   → 专家配置里的绑定集（ToolBindingPort ✓）
      → 治理过滤（ToolBindingResolver ✓ —— §5.3.1 ✓）→ BaseTool 列表 ✓
   → 指令（专家的 system prompt ✓）
```

⚠️ **端口不重复治理规则** ✓ —— 过滤只有 Execution 这一侧一份 ✓。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool

from ..agent_router.classifier import TaskKind
from ..execution.chat_model import QZDAPChatModel
from ..execution.llm_client import LLMCaller, ResolvedModel
from ..execution.tool_binding import BindingPolicy, ToolBindingResolver
from ..ports import (
    ActorContext,
    AgentRouterPort,
    AgentSelection,
    LLMPort,
    ModelResolverPort,
    ToolBindingPort,
    ToolRuntimePort,
)


@dataclass(frozen=True, slots=True)
class ExpertInstance:
    """**专家的一次调用上下文** ✓（模型 ✓ + 指令 ✓ + 工具集 ✓）。"""

    selection: AgentSelection
    model: QZDAPChatModel
    tools: tuple[BaseTool, ...] = ()
    #: **留痕载荷** ✓（A-24 ✓ —— 记「用了什么」✓ 不记「为什么」✓）。
    decision: dict[str, Any] = field(default_factory=dict)

    @property
    def instruction(self) -> str:
        """**专家的指令** ✓（进 system prompt ✓）。"""
        return self.selection.instruction


def decision_payload(
    *,
    selection: AgentSelection,
    resolved: ResolvedModel,
    tool_names: tuple[str, ...],
) -> dict[str, Any]:
    """**专家选择的留痕载荷** ✓（A-24 ✓）。

    ⚠️ **只记「用了什么」** ✓ —— 专家 ✓ 解析出的模型 ✓ 工具集 ✓ ——
    **不记「为什么挑了它」** ✓（理由会变 ✓ 用法是事实 ✓）。
    ⚠️ **不写 `route_decision`** ✓ —— 那是 Router 层的列 ✓（两列两写者 ✓）。
    """
    return {
        "expert_agent_id": str(selection.agent_id),
        "expert_agent_version": selection.agent_version,
        "task_kind": selection.task_kind.value,
        "confidence": selection.confidence,
        "fell_back": selection.fell_back,
        "model": {
            "name": resolved.model_name,
            "model_id": str(resolved.model_id) if resolved.model_id else None,
            "route_id": str(resolved.route_id) if resolved.route_id else None,
            "fallback_model_ids": [str(item) for item in resolved.fallback_model_ids],
        },
        "tools": list(tool_names),
    }


class ExpertAssembler:
    """**装配专家实例** ✓（§4.2 ✓）。

    ⚠️ **五个端口都从这里过** ✓ —— runtime 不认识任何具体实现 ✓。
    """

    def __init__(
        self,
        *,
        router: AgentRouterPort,
        bindings: ToolBindingPort,
        llm: LLMPort,
        resolver: ModelResolverPort | None = None,
        tool_runtime: ToolRuntimePort | None = None,
    ) -> None:
        self._router = router
        self._bindings = bindings
        self._llm = llm
        self._caller = LLMCaller(llm, resolver=resolver)
        self._tools = ToolBindingResolver(tool_runtime)

    async def assemble(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_agent_id: UUID,
        task_kind: TaskKind,
        confidence: float,
        protected: bool = True,
        actor: ActorContext | None = None,
        tool_names: tuple[str, ...] = (),
    ) -> ExpertInstance:
        """**装配一个专家** ✓（模型 ✓ + 工具 ✓）。

        ⚠️ **选专家 → 取模型 → 取工具** ✓ —— 三步都**不决策** ✓：
        选专家是路由端口 ✓；模型是查表 ✓；工具是绑定集 + 治理 ✓。
        """
        selection = await self._router.select(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            session_agent_id=session_agent_id,
            task_kind=task_kind,
            confidence=confidence,
            tool_names=tool_names,
        )
        resolved = await self._caller.resolve(
            model_name=selection.model_name,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            model_id=selection.model_id,
            route_id=selection.route_id,
            fallback_model_ids=list(selection.fallback_model_ids),
        )
        model = QZDAPChatModel(
            llm=self._llm,
            model_name=resolved.model_name,
            model_id=resolved.model_id,
            route_id=resolved.route_id,
            fallback_model_ids=resolved.fallback_model_ids,
            actor=actor,
        )
        bindings = await self._bindings.bindings(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            agent_id=selection.agent_id,
            agent_version=selection.agent_version,
        )
        tools = self._tools.resolve(
            bindings, policy=BindingPolicy(unprotected=not protected)
        )
        return ExpertInstance(
            selection=selection,
            model=model,
            tools=tuple(tools),
            decision=decision_payload(
                selection=selection,
                resolved=resolved,
                tool_names=tuple(tool.name for tool in tools),
            ),
        )


__all__ = ["ExpertAssembler", "ExpertInstance", "decision_payload"]
