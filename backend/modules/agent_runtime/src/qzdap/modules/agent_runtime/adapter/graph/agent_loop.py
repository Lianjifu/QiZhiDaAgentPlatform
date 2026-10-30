"""**新循环接进模块侧** ✓（Agent Stage 5 · A-28 ✓）。

⚠️ **旧的手写 ReAct 循环退役** ✓ —— 这一轮跑的是 runtime 的
``AgentLoopRunner`` ✓（**六个终止条件的单一判定点** ✓ —— §3.4 ✓）。

⚠️ **本模块只做「翻译」** ✓ —— 三件事 ✓：

| # | 翻译 | 口径 |
|---|---|---|
| 1 | **actor** ✓ | runtime 的 ``ActorContext`` ↔ vault 的 ``ActorContext`` ✓ |
| 2 | **消息** ✓ | 契约形状 ``[{role, content}]`` ↔ LangChain 的 ``BaseMessage`` ✓ |
| 3 | **工具执行** ✓ | 模块侧的端口 → runtime 的 ``ToolRuntimePort`` ✓ |

⚠️ **工具执行只有一条路** ✓ —— 模块侧的端口最终都落到 ``modules/tool`` 的
``InvokeToolUseCase`` ✓（唯一权威 ✓ —— 幂等 / 重试 / 熔断在那儿 ✓）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from time import monotonic
from typing import Any
from uuid import UUID

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from opentelemetry import trace as _trace
from qzdap_agent_runtime.agent_router.classifier import TaskKind
from qzdap_agent_runtime.ports import (
    ActorContext,
    AgentRouterPort,
    AgentSelection,
    ToolInvocation,
    ToolInvocationResult,
    ToolRuntimePort,
)
from qzdap_llm.client import ChatRequest
from qzdap_observability.tracing import get_tracer
from qzdap_schema.ids import ModelId
from qzdap_vault.actor import ActorContext as VaultActorContext

from qzdap.modules.agent_runtime.adapter.graph.tools import execute_tool
from qzdap.modules.agent_runtime.application.ports import (
    CatalogModelResolver,
    LLMPort,
    SandboxPort,
    SkillPort,
    ToolPort,
)

_tracer = get_tracer("qzdap.agent_runtime")


class RuntimeLLMPort:
    """**模块侧的 ``LLMPort`` → runtime 的 ``LLMPort``** ✓。

    ⚠️ **只翻译 actor** ✓ —— 模型调用本身**原样透传** ✓（失败转移链 ✓ /
    策略路由 ✓ 都在模块侧的端口里 ✓）。
    """

    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    def stream(
        self,
        request: ChatRequest,
        *,
        model_id: Any = None,
        route_id: Any = None,
        fallback_model_ids: list[Any] | None = None,
        actor: ActorContext | None = None,
    ) -> AsyncIterator[Any]:
        """**透传** ✓（actor 换成 vault 的形状 ✓）。

        ⚠️ **每次模型调用一个 span** ✓（``agent.llm`` ✓）—— 它是
        ``agent.turn`` 的子 span ✓（观测树不变 ✓）。
        """
        return self._stream(
            request,
            model_id=model_id,
            route_id=route_id,
            fallback_model_ids=fallback_model_ids,
            actor=actor,
        )

    async def _stream(
        self,
        request: ChatRequest,
        *,
        model_id: Any,
        route_id: Any,
        fallback_model_ids: list[Any] | None,
        actor: ActorContext | None,
    ) -> AsyncIterator[Any]:
        """**真正发起调用** ✓（span 包住整段流 ✓）。"""
        span = _tracer.start_span("agent.llm")
        span.set_attribute("llm.model", request.model)
        try:
            async for chunk in self._llm.stream(
                request,
                model_id=model_id,
                route_id=route_id,
                fallback_model_ids=fallback_model_ids,
                actor=to_vault_actor(actor),
            ):
                yield chunk
        except Exception:
            span.set_status(_trace.Status(_trace.StatusCode.ERROR))
            raise
        finally:
            span.end()


class ModuleToolRuntime(ToolRuntimePort):
    """**模块侧的工具执行口 → runtime 的 ``ToolRuntimePort``** ✓。

    ⚠️ **执行顺序与旧路径一致** ✓（沙箱 ✓ → skill ✓ → 目录工具 ✓）——
    同名时**先 skill** ✓（旧路径的口径 ✓）。

    ⚠️ **失败不抛穿** ✓ —— 返回带 ``error_code`` 的结果 ✓（§5.4 ✓）。
    """

    def __init__(
        self,
        *,
        skill_port: SkillPort | None = None,
        sandbox_port: SandboxPort | None = None,
        tool_port: ToolPort | None = None,
        tenant_id: UUID | None = None,
    ) -> None:
        self._skills = skill_port
        self._sandbox = sandbox_port
        self._tools = tool_port
        self._tenant_id = tenant_id

    async def invoke(
        self,
        invocation: ToolInvocation,
        *,
        actor: ActorContext,
    ) -> ToolInvocationResult:
        """**执行一次调用** ✓。

        ⚠️ **执行只有一份** ✓ —— 走 ``execute_tool`` ✓（旧的执行器 ✓）——
        这里只做**翻译** ✓（端口形状 ✓）。
        """
        # ⚠️ **执行必须带真实 actor** ✓ —— 工具执行是**谁的权限**就得用**谁的
        # actor** ✗✗（用别人的身份调工具 ✗✗✗）。
        if not actor.actor_id:
            return ToolInvocationResult(
                ok=False, error_code="TOOL_ACTOR_MISSING", is_error=True
            )
        if (
            self._tenant_id is not None
            and actor.tenant_id
            and actor.tenant_id != str(self._tenant_id)
        ):
            return ToolInvocationResult(
                ok=False, error_code="TOOL_ACTOR_TENANT_MISMATCH", is_error=True
            )
        arguments = dict(invocation.arguments or {})
        # ⚠️ **派生子会话的工具要父会话 id** ✓（旧路径由 runner 注入 ✓ ——
        # 模型不该凭空造一个归属 ✗✗）。
        if invocation.tool_name == "delegate_to_agent" and invocation.session_id:
            arguments.setdefault("parent_session_id", invocation.session_id)
        span = _tracer.start_span("agent.tool")
        span.set_attribute("tool.name", invocation.tool_name)
        started = monotonic()
        try:
            result = await execute_tool(
                name=invocation.tool_name,
                arguments=arguments,
                skill_port=self._skills,
                sandbox_port=self._sandbox,
                tool_port=self._tools,
                confirmed=invocation.confirmed,
                turn_id=_as_uuid(invocation.turn_id or ""),
                idempotency_key=invocation.idempotency_key,
                call_id=_as_uuid(invocation.tool_call_id),
            )
        except Exception:
            span.set_status(_trace.Status(_trace.StatusCode.ERROR))
            raise
        finally:
            span.set_attribute("tool.latency_ms", int((monotonic() - started) * 1000))
            span.end()
        span.set_attribute("tool.ok", result.get("ok") is not False)
        return _to_result(result)

class SessionAgentRouter(AgentRouterPort):
    """**不选专家** ✓ —— 直接用会话绑定的 agent ✓。

    ⚠️ **它是「没有专家目录」时的兜底** ✓（测试 ✓ / 没有装配专家路由的
    部署 ✓）—— **落回**语义 ✓（§4.1 规则 2 ✓）。

    ⚠️ **不报错** ✓ —— 拿不到就落回 ✓。
    """

    def __init__(
        self,
        *,
        agent_id: UUID,
        agent_version: str = "",
        model_name: str = "",
        instruction: str = "",
    ) -> None:
        self._agent_id = agent_id
        self._agent_version = agent_version
        self._model_name = model_name
        self._instruction = instruction

    async def select(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_agent_id: UUID,
        task_kind: TaskKind,
        confidence: float,
        tool_names: tuple[str, ...] = (),
    ) -> AgentSelection:
        """**落回会话绑定的 agent** ✓。"""
        _ = (tenant_id, workspace_id, session_agent_id, tool_names)
        return AgentSelection(
            agent_id=self._agent_id,
            agent_version=self._agent_version,
            task_kind=task_kind,
            confidence=confidence,
            instruction=self._instruction,
            fell_back=True,
            model_name=self._model_name or "default",
        )


class RuntimeModelResolver:
    """**模块侧的模型解析器 → runtime 的 ``ModelResolverPort``** ✓。

    ⚠️ **查表不是决策** ✓（§5.2.1 ✓）—— 查不到就是「环境默认模型」 ✓
    （**不是错误** ✓）。
    """

    def __init__(self, resolver: CatalogModelResolver | None = None) -> None:
        self._resolver = resolver

    async def resolve(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        upstream_model: str,
    ) -> ModelId | None:
        """**查表** ✓（没有解析器就是查不到 ✓）。"""
        if self._resolver is None:
            return None
        return await self._resolver.resolve(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            upstream_model=upstream_model,
        )


class AgentToolsReader:
    """**会话绑定 agent 的工具声明** ✓（兜底装配器用 ✓）。

    ⚠️ **它不是目录** ✓ —— 是**这一轮**手上那个 agent 配置 ✓（请求作用域 ✓）。
    """

    def __init__(self, agent: Any | None = None) -> None:
        self._agent = agent

    async def declared(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        agent_id: UUID,
        agent_version: str,
    ) -> tuple[str, ...]:
        """**这个 agent 声明了哪些工具** ✓。"""
        _ = (tenant_id, workspace_id, agent_id, agent_version)
        names: list[str] = []
        for entry in getattr(self._agent, "tools", None) or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name or not entry.get("enabled", True):
                continue
            if name not in names:
                names.append(name)
        return tuple(names)


def to_runtime_actor(actor: VaultActorContext) -> ActorContext:
    """**vault 的 actor → runtime 的 actor** ✓（同一件事的两种形状 ✓）。"""
    return ActorContext(
        actor_id=str(actor.principal_id or ""),
        tenant_id=str(actor.tenant_id),
        workspace_id=str(actor.workspace_id or ""),
        roles=tuple(sorted(actor.roles or ())),
    )


def to_vault_actor(actor: ActorContext | None) -> VaultActorContext | None:
    """**runtime 的 actor → vault 的 actor** ✓（没有就 ``None`` ✓）。"""
    if actor is None:
        return None
    return VaultActorContext(
        tenant_id=_as_uuid(actor.tenant_id) or UUID(int=0),
        workspace_id=_as_uuid(actor.workspace_id),
        principal_id=_as_uuid(actor.actor_id),
        roles=frozenset(actor.roles or ()),
    )


def to_base_messages(messages: list[dict[str, Any]]) -> list[BaseMessage]:
    """**契约消息 → LangChain 消息** ✓（角色映射 ✓）。"""
    result: list[BaseMessage] = []
    for item in messages:
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "")
        if role == "assistant":
            calls = item.get("tool_calls") or []
            result.append(
                AIMessage(
                    content=content,
                    tool_calls=list(calls) if isinstance(calls, list) else [],
                )
            )
        elif role == "system":
            result.append(SystemMessage(content=content))
        elif role == "tool":
            result.append(
                ToolMessage(
                    content=content,
                    tool_call_id=str(item.get("tool_call_id") or ""),
                    name=str(item.get("name") or "") or None,
                )
            )
        else:
            result.append(HumanMessage(content=content))
    return result


def to_dict_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """**LangChain 消息 → 契约消息** ✓（形状与旧路径一致 ✓）。"""
    result: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, dict):
            # ⚠️ **已经是契约形状** ✓（原样带走 ✓）。
            result.append(dict(message))
            continue
        if isinstance(message, AIMessage):
            item: dict[str, Any] = {"role": "assistant", "content": str(message.content or "")}
            if message.tool_calls:
                item["tool_calls"] = [dict(call) for call in message.tool_calls]
            result.append(item)
            continue
        if isinstance(message, ToolMessage):
            result.append(
                {
                    "role": "tool",
                    "content": str(message.content or ""),
                    "name": message.name or "",
                    "tool_call_id": str(message.tool_call_id or ""),
                }
            )
            continue
        role = "system" if isinstance(message, SystemMessage) else "user"
        result.append({"role": role, "content": str(message.content or "")})
    return result


def _to_result(result: dict[str, Any]) -> ToolInvocationResult:
    """**模块侧的结果 → runtime 的结果** ✓（形状对齐 §5.4 ✓）。"""
    ok = result.get("ok") is not False
    return ToolInvocationResult(
        ok=ok,
        output=_result_text(result),
        error_code=str(result.get("error_code") or "") or None,
        error_message=str(result.get("error_message") or ""),
        is_error=not ok,
        latency_ms=int(result.get("latency_ms") or 0),
    )


def _result_text(result: dict[str, Any]) -> str:
    """**结果 → 文本** ✓（与旧路径同口径 ✓ —— 失败带上错误码 ✓）。"""
    if result.get("ok") is False:
        return f"ERROR {result.get('error_code')}: {result.get('error_message')}"
    output = result.get("output")
    if output is None:
        output = result.get("stdout") or result.get("content") or result
    if isinstance(output, (dict, list)):
        import json

        return json.dumps(output, ensure_ascii=False)[:8000]
    return str(output)[:8000]


def _as_uuid(raw: Any) -> UUID | None:
    """**字符串 → UUID** ✓（不是 UUID 就是 ``None`` ✓）。"""
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


__all__ = [
    "AgentToolsReader",
    "ModuleToolRuntime",
    "RuntimeModelResolver",
    "SessionAgentRouter",
    "to_base_messages",
    "to_dict_messages",
    "to_runtime_actor",
    "to_vault_actor",
]
