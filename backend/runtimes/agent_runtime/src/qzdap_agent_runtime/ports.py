"""Port 协议 — runtime 与外部能力域的稳定边界。

§3.1 决议：runtime library 向上只暴露 SessionEngine / ChannelGateway
和端口协议。新 runtime 不得 import FastAPI Request / SQLAlchemy model /
具体 channel adapter；通过 Protocol 与外部能力对接。

本文件聚合下列协议：

- ToolRegistry / ToolMeta（§13.3）
- LayeredMemory / RecallHit（§13.4）
- PolicyGuard / ApprovalDecision（§5.7）
- ActorContext（来自 qzdap_vault 的最小接口）

⚠️ **Agent 层补的五个端口**（Agent 方案 §8.1 · A-01 ✓）：

- ``LLMPort`` —— 模型调用 ✓（**不含模型选择** ✓ —— 决策 #4 ✓）
- ``ModelResolverPort`` —— 上游模型名 → ``ModelId`` ✓（**查表** ✓）
- ``ToolBindingPort`` —— 取**当前 agent 配置里**的绑定集 ✓（不做选择 ✓）
- ``AgentRouterPort`` —— **这一步交给哪个专家** ✓
- ``ToolRuntimePort`` —— 工具执行 ✓（幂等 / 重试 / 熔断在 ``modules/tool`` ✓）

⚠️ **没有 ``ToolRouterPort``** ✓（决策 #4 取消了「工具路由」这个概念 ✓）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID

from qzdap_llm.client import ChatRequest, LLMChunk
from qzdap_schema.ids import ModelId

from .agent_router.classifier import TaskKind

# ---------------------------------------------------------------------------
# Tool registry（§13.3）
# ---------------------------------------------------------------------------


Risk = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class ToolMeta:
    """Tool 注册表元数据：治理/路由/观测/执行只读此表。"""

    name: str
    description: str
    args_schema: type  # Pydantic BaseModel subclass
    risk: Risk
    requires_approval: bool
    timeout_ms: int
    max_retries: int
    backoff_ms: int
    idempotent: bool
    side_effect: bool
    policy_id: str | None = None
    max_cost_usd: float | None = None


@runtime_checkable
class ToolRegistry(Protocol):
    """§13.3 ToolRegistry Protocol — 注册表元数据 + tools 集合。"""

    def register(self, meta: ToolMeta, tool: Any) -> None: ...

    def get(self, name: str) -> tuple[ToolMeta, Any]: ...

    def schemas_for(self, actor: ActorContext) -> list[dict[str, Any]]: ...

    def list_by_risk(self, risk: Risk) -> list[str]: ...


# ---------------------------------------------------------------------------
# Memory / Knowledge（§13.4）
# ---------------------------------------------------------------------------


RecallLayer = Literal["l1", "l2", "l3"]


@dataclass(frozen=True, slots=True)
class RecallHit:
    """§13.4 统一召回结果。L3 必须携带 knowledge_asset_id / chunk_id。

    ⚠️ **Memory 层补了四个字段** ✓（Memory 方案 §10.3 ✓ —— 契约**扩字段**，
    不是「不变」✓）：``scope`` / ``used_count`` / ``ref_id`` / ``version`` ——
    后两个是 **Context 的 manifest 组装所依赖** ✓（§3.5 ✓：召回项要能
    追到来源与版本 ✓）。
    """

    layer: RecallLayer
    content: str
    score: float
    source_id: str
    citation: str | None
    metadata: dict[str, Any]
    #: 作用域 ✓（session / user / workspace ✓ —— Memory §3.2 ✓）。
    scope: str = "user"
    #: 被用过的次数 ✓（统计 ✓ —— Memory §3.5 provenance ✓）。
    used_count: int = 0
    #: **命中项 ID** ✓（记忆 id / 知识 chunk id ✓ —— Context manifest 用 ✓）。
    ref_id: str = ""
    #: **版本** ✓（记忆批次版本 / 知识包版本 ✓ —— Context manifest 用 ✓）。
    version: str = ""


@runtime_checkable
class LayeredMemory(Protocol):
    """§13.4 LayeredMemory — recall_memory + recall_knowledge 拆分。"""

    async def recall_memory(
        self,
        *,
        query: str,
        tenant_id: str,
        workspace_id: str,
        user_id: str,
        session_id: str,
        policy: dict[str, Any],
    ) -> list[RecallHit]: ...

    async def recall_knowledge(
        self,
        *,
        query: str,
        tenant_id: str,
        workspace_id: str,
        package_ids: tuple[str, ...] | None = None,
    ) -> list[RecallHit]: ...

    async def write_l1(self, event: dict[str, Any]) -> None: ...

    async def write_l2(self, fact: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# Governance / PolicyGuard（§5.7）
# ---------------------------------------------------------------------------


ApprovalDecision = Literal["allow", "approve_required", "deny"]


@dataclass(frozen=True, slots=True)
class ActorContext:
    """调用者身份最小接口（避免 runtime 反向 import qzdap_vault）。"""

    actor_id: str
    tenant_id: str
    workspace_id: str
    roles: tuple[str, ...] = ()


@runtime_checkable
class PolicyGuard(Protocol):
    """§5.7 PolicyGuard — 工具执行前的统一治理端口。"""

    async def decide(
        self,
        *,
        actor: ActorContext,
        tool_call_id: str,
        tool_meta: ToolMeta,
        arguments: dict[str, Any],
    ) -> tuple[ApprovalDecision, str | None]:
        """返回 (decision, approval_id_or_reason)。"""
        ...


# ---------------------------------------------------------------------------
# Execution（§13.3 / §5.8）
# ---------------------------------------------------------------------------


@runtime_checkable
class ToolExecutor(Protocol):
    """§5.8 统一执行器：retry / timeout / idempotency / 熔断 / 降级。"""

    async def execute(
        self,
        *,
        tool_call_id: str,
        tool: Any,
        arguments: dict[str, Any],
        meta: ToolMeta,
        turn_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Agent 层（Agent 方案 §8.1 · A-01）
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMPort(Protocol):
    """模型调用 ✓ —— **只管「调」不管「选」** ✓（决策 #4 ✓）。

    ⚠️ **模型是谁**由 ``ModelResolverPort`` 查表得到 ✓（§5.2.1 ✓）——
    这个端口**不做任何模型选择** ✗✗（没有「按任务难度挑模型」这回事 ✓）。
    """

    def stream(
        self,
        request: ChatRequest,
        *,
        model_id: ModelId | None = None,
        route_id: ModelId | None = None,
        fallback_model_ids: list[ModelId] | None = None,
        actor: ActorContext | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """流式产出增量 ✓（工具调用的 delta 分片到达 ✓ —— §5.2.2 ✓）。"""
        ...


@runtime_checkable
class ModelResolverPort(Protocol):
    """上游模型名 → ``ModelId`` ✓（**查表** ✓ —— §5.2.1 ✓）。

    ⚠️ **租户守卫在实现里** ✓ —— 查询条件必须含 ``tenant_id`` ✓。
    """

    async def resolve(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        upstream_model: str,
    ) -> ModelId | None:
        """查不到就返回 ``None`` ✓（调用方回退环境默认模型 ✓ —— §5.2.1 ✓）。"""
        ...


@dataclass(frozen=True, slots=True)
class ToolBinding:
    """一个工具的**绑定声明** ✓ —— 「这份 agent 配置允许用它」✓。

    ⚠️ **这里只声明「允许」** ✓ —— 治理过滤（风险 ∩ 作用域 ∩ 副作用 ✓）在
    ⑨ Execution 那一侧做 ✓（§5.3.1 ✓）—— 端口不重复那份规则 ✗✗。
    """

    name: str
    kind: Literal["tool", "mcp", "skill"] = "tool"
    risk: Risk = "low"
    requires_approval: bool = False
    side_effect: bool = False
    #: **是否受保护** ✓ —— `unprotected` 的**副作用工具**要被剔除 ✓（§5.3.1 ✓）。
    protected: bool = True
    #: 工具的**真实 spec** ✓（从 ``tools`` 表读 ✓ —— Stage 2 的空 schema 修复 ✓）。
    spec: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class ToolBindingPort(Protocol):
    """**取当前 agent 配置里的绑定集** ✓（§5.3.1 ✓）。

    ⚠️ **不做「选择」** ✓（决策 #4 ✓）—— 只把配置里声明的东西**取出来** ✓
    （挑哪个是执行期的事 ✗✗ —— 这里没有「挑」这个概念 ✓）。
    """

    async def bindings(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        agent_id: UUID,
        agent_version: str,
    ) -> list[ToolBinding]:
        """返回该 agent 的绑定集 ✓（tool / mcp / skill 统一成一种形状 ✓）。"""
        ...


@dataclass(frozen=True, slots=True)
class AgentSelection:
    """**这一步交给哪个专家** ✓（§4.1 ✓）。

    ⚠️ **专家 = 一份 agent 配置** ✓（§4.2 ✓）—— 不是会话绑定 agent 的子集 ✓。
    """

    agent_id: UUID
    agent_version: str
    task_kind: TaskKind
    confidence: float
    #: 专家的指令片段 ✓（§4.1 的输出 ✓）。
    instruction: str = ""
    #: **是不是落回了会话绑定的 agent** ✓（§4.1 规则 2 ✓—— 没有专家可路由时
    #: **落回**而不是报错 ✓）。
    fell_back: bool = False
    #: **专家配置里的模型名** ✓（§5.2.1 的取值链输入 ✓ —— **查表，不是决策** ✓）。
    model_name: str = ""
    #: **专家配置里钉的模型 id** ✓（版本冻结 ✓ —— 有就用它 ✓ 不查表 ✓）。
    model_id: ModelId | None = None
    #: **专家配置里绑的策略路由** ✓（**优先于** `model_id` ✓ —— §5.2.1 第 3 条 ✓）。
    route_id: ModelId | None = None
    #: **失败转移链** ✓（§5.2.1 第 5 条 ✓ —— 交给端口执行 ✓）。
    fallback_model_ids: tuple[ModelId, ...] = ()


@runtime_checkable
class AgentRouterPort(Protocol):
    """**每一步选专家** ✓（§4.1 ✓）。

    ⚠️ **与 Router 层（⑤）的边界** ✓ —— 那是**会话入口**选「跟谁聊」✓，
    这里是**每步**选「这一步交给谁」✓（§4.0 ✓）。
    """

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
        """选出本步的专家 ✓（**没有专家就落回** ✓ —— §4.1 规则 2 ✓）。"""
        ...


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    """一次工具调用 ✓（**参数形状** ✓ —— 不是执行语义 ✓）。

    ⚠️ **字段与方案 §5.4 的统一契约一一对应** ✓（`tool_call_id` /
    `tool_name` / `arguments` / `idempotency_key` / `turn_id` / `protected` ✓）——
    **口径统一** ✓（别各写一套 ✗✗）。
    """

    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    tool_call_id: str = ""
    #: 幂等键 ✓（**由调用方给** ✓ —— `tool_executions` 的唯一权威 ✓）。
    idempotency_key: str | None = None
    #: 轮次 id ✓（`tool_executions.turn_id` 的外键 ✓ —— 幂等记录挂在轮次上 ✓）。
    turn_id: str | None = None
    #: 这一轮**是不是受保护** ✓（False = unprotected ✓ —— 副作用工具**已被剔除** ✓，
    #: 这里只是把事实带上 ✓ —— 执行侧据此**再确认一次** ✓)。
    protected: bool = True


@dataclass(frozen=True, slots=True)
class ToolInvocationResult:
    """一次工具调用的结果 ✓（方案 §5.4 ✓）。"""

    ok: bool
    output: str = ""
    error_code: str | None = None
    error_message: str = ""
    is_error: bool = False
    #: 建议的重试等待 ✓（熔断 / 限流时给出 ✓ —— 调用方据此退避 ✓）。
    retry_after_ms: int = 0
    latency_ms: int = 0
    #: **实际尝试了几次** ✓（幂等命中 → 1 ✓；重试 → >1 ✓）。
    attempts: int = 1


@runtime_checkable
class ToolRuntimePort(Protocol):
    """工具执行 ✓。

    ⚠️ **幂等 / 重试 / 熔断在 ``modules/tool`` 那一侧** ✓（决策 #6 ✓ ——
    ``tool_executions`` 是唯一权威 ✓）—— 这里只是**调它** ✓。
    """

    async def invoke(
        self,
        invocation: ToolInvocation,
        *,
        actor: ActorContext,
    ) -> ToolInvocationResult:
        """执行一次调用 ✓（失败要有 ``error_code`` ✓ —— 不静默吞 ✓）。"""
        ...


__all__ = [
    "ActorContext",
    "AgentRouterPort",
    "AgentSelection",
    "ApprovalDecision",
    "LLMPort",
    "LayeredMemory",
    "ModelResolverPort",
    "PolicyGuard",
    "RecallHit",
    "RecallLayer",
    "Risk",
    "ToolBinding",
    "ToolBindingPort",
    "ToolExecutor",
    "ToolInvocation",
    "ToolInvocationResult",
    "ToolMeta",
    "ToolRegistry",
    "ToolRuntimePort",
]