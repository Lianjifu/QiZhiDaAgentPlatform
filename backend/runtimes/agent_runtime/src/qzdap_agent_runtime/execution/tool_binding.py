"""工具绑定集 → **统一成 ``BaseTool``** ✓ + 治理过滤 ✓。

依据：Agent 方案 §5.3.1（绑定集读取与治理过滤 ✓ —— 「**不是选择**」✓）、
§8.1（``execution/tool_binding.py`` ✓）。

⚠️ **最终暴露给模型的工具集** ✓（§5.3.1 ✓）：

```
agent 配置的绑定集
  ∩ 风险策略允许集（PolicyGuard 的 risk 维度 ✓）
  ∩ 作用域可见集（工具所属的工作区 ✓ —— **过滤下推到端口** ✓）
  − unprotected 轮次的副作用工具（✓）
```

| # | 规则 | 落点 |
|---|---|---|
| 1 | 绑定集为空 → **不报错** ✓ | 这里返回空列表 ✓（本步就是纯对话 ✓） |
| 2 | 过滤**不得**因为「筛不出工具」而阻断轮次 ✓ | 降级为「无工具」✓ |
| 3 | **`unprotected` 轮次必须剔除副作用工具** ✓ | **剔除，不是执行时拦截** ✓（§5.3.1 规则 3 ✓） |
| 4 | 高风险工具即使在绑定集里，也要等 `PolicyGuard` 判定 ✓ | 这里**不筛高风险** ✓（**筛不等于批** ✓） |
| 5 | **tool / mcp / skill 统一成 `BaseTool`** ✓ | 三种来源对模型是同一种东西 ✓ |
| 6 | **专家 Agent 的工具集 = 专家自己配置里的绑定集** ✓ | 不做二次裁剪 ✓（§5.3.1 规则 6 ✓） |

⚠️ **作用域不在这里过滤** ✓ —— 端口的查询本身已经按工作区限定 ✓（过滤下推
✓ —— 别在这里逐行过滤 ✗✗ —— 那是全量拉回来再筛 ✗）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from ..ports import ActorContext, ToolBinding, ToolInvocation, ToolRuntimePort

#: 风险等级 ✓（与 ``ports.ToolMeta`` 的 ``Risk`` 同口径 ✓）。
RISK_ORDER: tuple[str, ...] = ("low", "medium", "high")


@dataclass(frozen=True, slots=True)
class BindingPolicy:
    """治理过滤的输入 ✓（**不是** agent 的配置 ✓ —— 是这一轮的执行条件 ✓）。"""

    #: **这一轮是不是 unprotected** ✓（Gateway 决策 #5 的兑现点 ✓）。
    unprotected: bool = False
    #: **允许的风险等级** ✓（默认全允许 ✓ —— 高风险的**筛不等于批** ✓）。
    allowed_risks: frozenset[str] = frozenset(RISK_ORDER)


class ToolBindingResolver:
    """**绑定集 → 暴露给模型的工具集** ✓（§5.3.1 ✓）。"""

    def __init__(self, tool_runtime: ToolRuntimePort | None = None) -> None:
        self._runtime = tool_runtime

    def resolve(
        self,
        bindings: Sequence[ToolBinding],
        *,
        policy: BindingPolicy | None = None,
    ) -> list[BaseTool]:
        """**统一 + 过滤** ✓。

        ⚠️ **返回空列表不是错误** ✓（规则 1 ✓ / 规则 2 ✓）。
        """
        active = policy or BindingPolicy()
        resolved: list[BaseTool] = []
        for binding in bindings:
            if active.unprotected and binding.side_effect:
                # ⚠️ **剔除** ✓（不是执行时拦截 ✓ —— 未受保护的轮次**根本不
                # 该看见**副作用工具 ✗✗ —— 看见了就会想去调 ✗）。
                continue
            if binding.risk not in active.allowed_risks:
                continue
            resolved.append(self._to_base_tool(binding))
        return resolved

    def _to_base_tool(self, binding: ToolBinding) -> BaseTool:
        """**一种来源 → 一个 ``BaseTool``** ✓（§5.3.1 规则 5 ✓）。"""

        async def _invoke(**arguments: Any) -> str:
            """**执行走 `ToolRuntimePort`** ✓ —— 不在这里直接调工具 ✗。

            ⚠️ **没有 runtime 就明确报错** ✓（而不是悄悄返回空 ✗✗ —— 那会
            让模型以为「工具执行了但没结果」✗）。
            """
            if self._runtime is None:
                raise RuntimeError(
                    f"tool {binding.name} has no runtime — bind a ToolRuntimePort"
                )
            scope = current_tool_scope()
            result = await self._runtime.invoke(
                ToolInvocation(
                    tool_name=binding.name,
                    arguments=arguments,
                    tool_call_id=scope.tool_call_id,
                    idempotency_key=scope.idempotency_key,
                    turn_id=scope.turn_id,
                    protected=scope.protected,
                ),
                actor=current_actor(),
            )
            if not result.ok:
                raise RuntimeError(result.error_code or "TOOL_FAILED")
            return result.output

        schema = _args_schema(binding.spec)
        return StructuredTool.from_function(
            coroutine=_invoke,
            name=binding.name,
            description=str(binding.spec.get("description") or binding.name),
            args_schema=schema,
        )


#: **当前调用的 actor** ✓ —— `BaseTool` 的函数签名里带不了 actor ✓（LangChain
#: 的工具参数就是模型的参数 ✓），所以用上下文变量挂上 ✓。
#:
#: ⚠️ **必须是 `ContextVar`** ✓ —— 并发的两轮各挂各的 actor ✓（用普通全局
#: 变量会互相覆盖 ✗✗ —— 那就等于用错了人的身份调工具 ✗✗✗)。
#:
#: ⚠️ **取不到 actor 就拒绝执行工具** ✓（Gateway 决策：工具执行必须有真实
#: 调用者 ✓）—— 见 ``require_actor`` ✓。
_CURRENT_ACTOR: ContextVar[ActorContext | None] = ContextVar(
    "qzdap_current_actor", default=None
)


def set_current_actor(actor: ActorContext | None) -> Token[ActorContext | None]:
    """**设置当前 actor** ✓ —— 返回 token ✓（调用方负责 reset ✓）。"""
    return _CURRENT_ACTOR.set(actor)


def reset_current_actor(token: Token[ActorContext | None]) -> None:
    """**还原 actor** ✓ —— 轮次结束时必须还原 ✓（否则下一个请求会继承上一个 ✓✗）。"""
    _CURRENT_ACTOR.reset(token)


def current_actor() -> ActorContext:
    """**当前 actor** ✓ —— 没有就**拒绝** ✓（不静默降级成匿名 ✗✗）。"""
    actor = _CURRENT_ACTOR.get()
    if actor is None:
        raise RuntimeError(
            "tool execution requires a real actor — 没有真实调用者就不许执行工具"
        )
    return actor


def require_actor(actor: ActorContext | None) -> ActorContext:
    """**必须有真实 actor** ✓ —— 没有就**拒绝** ✓（不静默降级成匿名 ✗✗）。"""
    if actor is None:
        raise RuntimeError(
            "tool execution requires a real actor — 没有真实调用者就不许执行工具"
        )
    return actor


@dataclass(frozen=True, slots=True)
class ToolScope:
    """**这一轮工具调用的上下文** ✓（幂等键 ✓ / 轮次 ✓ / 是否受保护 ✓）。

    ⚠️ **挂在上下文变量上** ✓ —— 与 actor 同一个理由 ✓：`BaseTool` 的函数
    签名里只有**模型的参数** ✓，带不进调用 id ✓。
    """

    tool_call_id: str = ""
    idempotency_key: str | None = None
    turn_id: str | None = None
    protected: bool = True


_CURRENT_TOOL_SCOPE: ContextVar[ToolScope | None] = ContextVar(
    "qzdap_current_tool_scope", default=None
)


def set_current_tool_scope(scope: ToolScope) -> Token[ToolScope | None]:
    """**设置当前工具上下文** ✓ —— 返回 token ✓（调用方负责 reset ✓）。"""
    return _CURRENT_TOOL_SCOPE.set(scope)


def reset_current_tool_scope(token: Token[ToolScope | None]) -> None:
    """**还原工具上下文** ✓（一步做完就还原 ✓ —— 否则下一步会继承上一步的幂等键 ✗✗）。"""
    _CURRENT_TOOL_SCOPE.reset(token)


def current_tool_scope() -> ToolScope:
    """**当前工具上下文** ✓（没有就是空上下文 ✓ —— 不报错 ✓）。"""
    return _CURRENT_TOOL_SCOPE.get() or ToolScope()


def _args_schema(spec: Mapping[str, Any]) -> dict[str, Any]:
    """**绑定声明 → 参数 schema** ✓。

    ⚠️ **优先用 `spec` 里的真实 schema** ✓（admin 注册的 OpenAPI / MCP 工具有
    真实 spec ✓ —— 旧路径给它们的是**空 schema** ✗✗）。
    """
    schema = spec.get("parameters") or spec.get("args_schema") or spec.get("input_schema")
    if isinstance(schema, Mapping) and schema:
        return dict(schema)
    properties = spec.get("properties")
    if isinstance(properties, Mapping) and properties:
        return {
            "type": "object",
            "properties": dict(properties),
            "required": list(spec.get("required") or []),
        }
    return {"type": "object", "properties": {}}


def tool_schema(tool: BaseTool) -> dict[str, Any]:
    """**`BaseTool` → 模型的工具 schema** ✓（OpenAI 形状 ✓）。

    ⚠️ **参数 schema 可能是 dict** ✓（LangChain 收到 JSON Schema 时会原样留着
    ✓）—— 两种形状都要认 ✓（只认 pydantic 会直接崩 ✗✗）。
    """
    args = tool.args_schema
    if isinstance(args, Mapping):
        parameters = dict(args)
    elif args is not None and hasattr(args, "model_json_schema"):
        parameters = args.model_json_schema()
    else:
        parameters = {}
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": parameters,
        },
    }


__all__ = [
    "RISK_ORDER",
    "BindingPolicy",
    "ToolBindingResolver",
    "ToolScope",
    "current_actor",
    "current_tool_scope",
    "require_actor",
    "reset_current_actor",
    "reset_current_tool_scope",
    "set_current_actor",
    "set_current_tool_scope",
    "tool_schema",
]
