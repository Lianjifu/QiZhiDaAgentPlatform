"""Application-layer ports (interfaces) for the agent runtime.

The adapter package implements these; use cases depend ONLY on ports.
Forward-compat `Protocol` stubs (Tool / Skill / Memory / Knowledge) are
declared so P2+ can plug in concrete adapters without touching the turn
runner.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Protocol
from uuid import UUID

from qzdap_kernel.events import DomainEvent
from qzdap_llm.client import ChatRequest, LLMChunk
from qzdap_schema.ids import ModelId
from qzdap_vault.actor import ActorContext

from qzdap.modules.agent_runtime.application.ports.catalog_model_resolver import (
    CatalogModelResolver as CatalogModelResolver,
)
from qzdap.modules.agent_runtime.domain import Session, Turn


class SessionRepository(ABC):
    """会话行的读写。

    ⚠️ **执行权（互斥）不在这里** —— 它归 Session 层的 ``TurnClaimPort``
    （``agent_sessions.current_turn_id`` + ``session_turns.status`` 推导 ✓，
    台账 R3）：旧实现是这一列上的 CAS，语义与「审批挂起」混装在一列 ✗
    （那一列已退役，台账 X6 ✅）。
    """

    @abstractmethod
    async def add(self, session: Session) -> None: ...
    @abstractmethod
    async def get(self, session_id: UUID) -> Session | None: ...
    @abstractmethod
    async def update(self, session: Session) -> None: ...
    @abstractmethod
    async def list_for_owner(
        self, tenant_id: UUID, owner_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Session]:
        """列出会话 —— **必须显式带租户**。

        租户过滤不能只靠 ORM 的自动过滤（那依赖请求上下文里绑定了租户）；
        没有绑定时自动过滤退化成 no-op，查询就会跨租户。
        """
        ...

    @abstractmethod
    async def list_for_owner_workspace(
        self,
        tenant_id: UUID,
        owner_id: UUID,
        workspace_id: UUID,
        *,
        limit: int = 200,
    ) -> list[Session]:
        """派生 /api/tasks: 多一层 workspace 过滤, 默认 limit 更大."""
        ...

    async def cancel_requested(self, session_id: UUID) -> bool:
        """Has the user asked for the running turn to stop?"""
        return False

    async def request_cancel(self, session_id: UUID) -> bool:
        """Ask the running turn to stop. Returns True when a turn was live."""
        return False

    async def clear_cancel(self, session_id: UUID) -> None:
        """Drop a stale cancel flag."""
        return


class TurnRepository(ABC):
    """轮次的**读**端口 ✓。

    ⚠️ **没有 ``add``** ✓ —— 轮次的写入归 ``SessionJournal`` ✓（新表
    ``session_turns`` 是唯一真相 ✓）；旧表的写路径在 Stage 6b 停掉了 ✓
    （S-15b ✓）—— 留着 ``add`` 就是第二条写路径 ✗✗。
    """

    @abstractmethod
    async def get(self, turn_id: UUID) -> Turn | None: ...
    @abstractmethod
    async def latest_for_session(self, session_id: UUID) -> Turn | None:
        """派生 /api/tasks: 取最新一轮 turn 用于状态映射."""
        ...


class LLMPort(ABC):
    """Async-iterator facade over `qzdap_llm.LLMClient.stream`.

    When ``model_id`` is supplied (P6), the adapter delegates to
    ``ModelService.stream`` for per-tenant routing, quota tracking, and
    credential decryption. When ``model_id`` is ``None``, the legacy
    default path is used (P0–P5 callers stay unchanged).
    """

    @abstractmethod
    def stream(
        self,
        req: ChatRequest,
        *,
        model_id: ModelId | None = None,
        fallback_model_ids: list[ModelId] | None = None,
        route_id: ModelId | None = None,
        actor: ActorContext | None = None,
    ) -> AsyncIterator[LLMChunk]: ...


class EventPublisher(ABC):
    """Wraps the messaging bus for application-layer emission.

    The use case passes a `DomainEvent`; the publisher wraps it into an
    `EventEnvelope` with the request's tenant/workspace/trace scope."""

    @abstractmethod
    async def publish(
        self,
        event: DomainEvent,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        trace_id: str | None = None,
    ) -> None: ...


class SessionJournal(ABC):
    """新架构的**轮次 + 事件日志**（``session_turns`` / ``session_events``）。

    ⚠️ **轮次的唯一写入口** ✓ —— 旧表 ``agent_turns`` 已停写（S-15b ✓），
    新表 ``session_turns`` 是唯一真相 ✓（删表在 Session Stage 6 · S-36 ✓）。

    **事件先落库、再投递**（Session 方案 §7）—— 断线重连要能读到已发出的
    那一段，重放才有意义（Gateway 方案 §4.5 的硬依赖）。
    """

    @abstractmethod
    async def start_turn(
        self,
        *,
        turn_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        idempotency_key: str,
        key_strength: str,
        agent_version: str,
        model_version: str,
        user_input: str | None = None,
        trace_id: str | None = None,
        route_decision: dict[str, Any] | None = None,
    ) -> None:
        """写一行轮次（状态 ``running``）—— 事件行的外键父行。

        ``user_input`` 是这一轮用户说了什么 ✓（任务卡片要显示 ✓）。

        ``route_decision`` 是 **Router 产出的**路由决策留痕（§6.2 的
        ``session_turns.route_decision``）—— **产出者唯一是 Router**，
        这里只是把它带进轮次行。
        """
        ...

    @abstractmethod
    async def finish_turn(
        self,
        *,
        turn_id: UUID,
        status: str,
        error_code: str | None = None,
        cost_usd: float | None = None,
    ) -> None:
        """把轮次落到终态（``succeeded`` / ``failed`` / ``cancelled``）。"""
        ...

    @abstractmethod
    async def append_event(
        self,
        *,
        turn_id: UUID,
        seq: int,
        event_type: str,
        payload: dict,
    ) -> None:
        """写一条事件 —— 轮次内 ``seq`` 严格递增。"""
        ...

    @abstractmethod
    async def mark_delivered(self, *, turn_id: UUID) -> None:
        """把这一轮还挂着的 ``pending`` 事件标成 ``delivered``。"""
        ...

    @abstractmethod
    async def write_pending_approval(
        self, *, turn_id: UUID, pending: dict[str, Any]
    ) -> None:
        """轮次挂起等审批 —— **挂起信息落库** ✓（``session_turns.pending_approval``）。

        ⚠️ 恢复路径靠它校验「挂起的是哪个工具、参数有没有被改」✓
        （Session 方案 §8）。
        """
        ...

    @abstractmethod
    async def find_pending_approval(
        self, *, session_id: UUID, tenant_id: UUID
    ) -> tuple[UUID, dict[str, Any]] | None:
        """查这个会话**正在等审批**的那一轮 + 挂起信息 ✓（没有就 ``None``）。"""
        ...

    @abstractmethod
    async def list_waiting_approval_sessions(self, *, tenant_id: UUID) -> set[UUID]:
        """哪些会话**正在等审批** ✓（一次查询 —— 别按会话逐个查 ✗）。"""
        ...


# ── Forward-compat ports (Protocol stubs; concrete adapters land in P2/P3/P4) ──


class ToolPort(Protocol):
    async def invoke(
        self, *, call_id: UUID, tool_name: str, arguments: dict
    ) -> dict: ...

    async def list_tools(self) -> list[dict]:
        """Catalog of invocable tools.

        Each entry: ``{name, description, parameters, risk, needConfirm}``.
        ``parameters`` is a JSON-Schema object; the runtime turns it into the
        function schema handed to the model. Implementations that cannot
        enumerate a catalog may return ``[]`` — the runtime then exposes no
        catalog tools to the model (skills and ``sandbox_exec`` still work).
        """
        ...


class MemoryPort(Protocol):
    """P4: recall relevant memories before constructing the system prompt.

    Returns a list of dicts with at least `id`, `content`, `score` keys.
    Concrete adapter: ``MemoryServiceAdapter`` wraps ``MemoryService``.
    """

    async def recall(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query: str,
        top_k: int,
        user_id: UUID | None = None,
    ) -> list[dict]: ...

    async def write_turn(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        session_id: UUID,
        turn_id: UUID | None = None,
        user_input: str,
        assistant_reply: str = "",
    ) -> dict:
        """**新 Writer** ✓ —— 沉淀**一轮**对话 ✓（Memory Stage 3 ✓）。

        ⚠️ **输入只有本轮对话** ✓ —— 不含召回结果 ✓（Memory 方案 §4.6 ✓：
        从召回结果反推会造成**记忆的自我强化循环** ✗✗）。
        """
        ...


class SkillPort(Protocol):
    """Catalog skill invoke — runs published Skill.runtime in sandbox_runtime."""

    async def invoke(
        self,
        *,
        call_id: UUID,
        skill_name: str,
        arguments: dict,
        confirmed: bool = False,
    ) -> dict: ...

    async def list_executable(self) -> list[dict]: ...


class SandboxPort(Protocol):
    """Generic gVisor exec for the agent (`sandbox_exec` tool)."""

    async def exec(
        self,
        *,
        call_id: UUID,
        language: str,
        code: str,
        timeout_ms: int = 30_000,
    ) -> dict: ...


class KnowledgePort(Protocol):
    """P7: recall relevant knowledge chunks before constructing the
    system prompt. Returns a list of dicts with at least ``id``,
    ``asset_id``, ``package_id``, ``package_name``, ``asset_name``,
    ``content``, ``score``, ``ordinal`` keys.

    Concrete adapter: ``KnowledgeServiceAdapter`` wraps ``KnowledgeService``.
    The signature is intentionally tenant/workspace scoped so cross-tenant
    reads are impossible from the use case side.
    """

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query: str,
        top_k: int,
        package_ids: tuple[UUID, ...] = (),
    ) -> list[dict]: ...


class SubAgentPort(Protocol):
    """P7: orchestration-layer reverse-call into agent_runtime.

    The orchestration ``WorkflowExecutor`` invokes a sub-agent via this
    port without importing agent_runtime directly. Adapter:
    ``SubAgentAdapter`` drains ``RunTurnUseCase.execute`` until the
    ``DoneChunk`` and packages ``{final_message, turn_id, input_tokens,
    output_tokens}`` for the executor.
    """

    async def run_turn_to_completion(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        agent_id: UUID,
        agent_version: str,
        user_input: str,
        model_override: str | None = None,
        timeout_seconds: int = 60,
    ) -> dict: ...


class PolicyPort(Protocol):
    """Approval + governance gate. P5; declared here so the use case can
    surface `ApprovalRequiredError` for gated actions."""

    async def evaluate_action(
        self, *, tenant_id: UUID, action: str, context: dict
    ) -> bool: ...


class AgentBindingReader(Protocol):
    """Agent 方案 §5.3.1 —— **取一个 agent 配置里声明的绑定集** ✓。

    ⚠️ **只返回名字** ✓ —— 「这个 agent 允许用哪些工具 / skill」✓；
    **真实参数契约**由 ``ToolPort.list_tools()`` 那一侧给 ✓（那里才有 spec ✓）。

    ⚠️ **绑定集为空不是错误** ✓ —— 返回空元组即可 ✓（那一步就是纯对话 ✓）。
    """

    async def declared(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        agent_id: UUID,
        agent_version: str,
    ) -> tuple[str, ...]:
        """返回该 agent 声明的工具 / skill 名 ✓。"""
        ...
