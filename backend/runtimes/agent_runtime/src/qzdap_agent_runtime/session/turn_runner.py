"""**唯一 turn 实现**（Session 方案 §6）—— 一轮的编排。

⚠️ **这是「唯一」的实现**：旧的两套（``copilot.py`` 的 turn 编排 X18 与
``use_cases/run_turn*.py`` X2）里，**治理语义取 Copilot 版**（claim / 幂等 /
取消 / 审批），use_cases 版的简化语义**丢掉** ✓。

**这一层只管「顺序与语义」，不管「怎么读、怎么写」** —— 全部走端口 ✓：

| 端口 | 职责 | 实现 |
|---|---|---|
| :class:`TurnExecutorPort` | 跑一轮并产出 chunk | 模块侧（现役的 graph runner） |
| :class:`TurnLifecyclePort` | 轮次行（新表）+ 事件落库 + 轮次终态 | 模块侧 |
| :class:`SessionMessagePort` | 消息读写（会话内序号） | 模块侧 |
| :class:`SessionStatePort` | 会话行的读改（标题 / 预览 / 摘要 / 续传状态 ✓） | 模块侧 |
| :class:`CancelProbePort` | 取消标记 | 模块侧 |

⚠️ **为什么用「窄端口 + DTO」而不是把领域对象搬进契约层**：契约层不引模块
（架构测试把关 ✓），而 agent / session / turn 的领域实体都住在模块侧 —— 把它们
搬进契约层是一次大得多的重构，且**不解决任何当前的问题** ✓。这里让**模块侧
组装** :class:`TurnRequest`（读都在那边 ✓），契约层只编排 ✓。

**关键顺序**（Session 方案 §7「落库先于投递」）：

```
开始一轮 → 轮次行落库 → 用户消息落库 → 执行 → 每个 chunk：**先落事件库**
         再投递给客户端 → 终态（成功 / 失败 / 取消）落库
```
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from qzdap_agent_runtime.gateway.idempotency import (
    IdempotencyGuard,
    InboxScope,
    payload_hash_of,
)
from qzdap_agent_runtime.gateway.normalizer import resolve_idempotency_key
from qzdap_agent_runtime.gateway.types import ChannelType, IdempotencyKey
from qzdap_agent_runtime.session.approval import PendingApproval, arguments_digest
from qzdap_agent_runtime.session.claim import TurnClaimPort
from qzdap_agent_runtime.session.queue import (
    QueueCancelled,
    QueueFullError,
    QueueTimeoutError,
    TurnQueuePort,
    wait_for_turn_slot,
)
from qzdap_agent_runtime.session.sequence import SessionSequencePort
from qzdap_agent_runtime.session.state import TurnStatus
from qzdap_kernel.contextvars import current_trace_id
from qzdap_kernel.error_codes import ErrorCode, project_error_message
from qzdap_kernel.ids import ModelId
from qzdap_schema.dtos.turn import (
    ApprovalRequiredChunk,
    DoneChunk,
    ErrorChunk,
    QueuedChunk,
    UsageChunk,
)

_log = logging.getLogger(__name__)

#: 取消标记的检查间隔（秒）—— 与旧实现同值 ✓。
CANCEL_POLL_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class AgentSnapshot:
    """执行所需的 agent 快照。

    ⚠️ ``raw`` 是**模块侧的对象**（``CatalogAgent``）—— 契约层**不解释**它，
    只原样递给执行器 ✓（执行器需要它才能拿工具/模型配置）。
    """

    agent_id: UUID
    agent_version: str
    model: str
    name: str = ""
    raw: Any = None


@runtime_checkable
class CancelProbePort(Protocol):
    """取消标记（实现在模块侧 ✓）。"""

    async def is_cancel_requested(self, *, session_id: UUID) -> bool:
        """用户是否请求停止这一轮 ✓（跨进程可见）。"""
        ...


@dataclass(frozen=True, slots=True)
class TurnRequest:
    """一轮的**输入** —— 由模块侧组装（读都在那边 ✓）。"""

    tenant_id: UUID
    workspace_id: UUID
    owner_id: UUID
    session_id: UUID
    turn_id: UUID
    user_input: str
    idempotency_key: str
    key_strength: str
    agent: AgentSnapshot
    history: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    resume: dict[str, Any] | None = None
    route_id: ModelId | None = None
    #: **路由策略覆盖** ✓（agent 自带的 ✓ —— 覆盖 route 自带的 strategy ✓）。
    route_strategy: str | None = None
    rolling_summary: str = ""
    session_metadata: Mapping[str, Any] = field(default_factory=dict)
    #: **续传状态** ✓（上一轮的循环状态 ✓）—— ⚠️ **不再存 ``graph_state`` 列**
    #: ✓（台账 **X3** ✓ —— 那是旧图的落点 ✓ —— 新的续传状态进会话的
    #: ``metadata["resume"]`` ✓ —— §8 ✓）。
    resume_state: Mapping[str, Any] = field(default_factory=dict)
    route_decision: Mapping[str, Any] | None = None
    parent_span_context: Any = None
    trace_id: str | None = None
    #: **入站序号** ✓（Router 方案 §4.2 ✓）—— **有值就排队** ✓
    #: （``None`` = 不排队 ✓ —— 开关关掉时的旧语义 ✓）。
    ingress_seq: int | None = None
    #: **这一轮能不能挂起审批** ✓（默认能 ✓ —— web 侧由人在前端点 ✓）。
    #:
    #: ⚠️ **IM 渠道置 False** ✓ —— IM 侧**没有人能完成审批** ✓（入站没有
    #: 审批回调 ✓ —— 卡片点了回不来 ✓；而且 IM 的 actor 是**服务账号** ✓ =
    #: 发起人 ✓ → 治理域的「审批人不能是发起人」✓ 会直接拒掉 ✓）→
    #: 挂起一个**永远不会被批准**的审批 ✓ = **这一轮永远卡住** ✗✗ →
    #: **需要审批的工具不暴露给模型** ✓ + 真被调到就**明确拒绝** ✓。
    allow_approval: bool = True
    #: **取消探测** ✓（循环内要用 ✓）—— ⚠️ **之前没传** ✓ →
    #: 循环里的取消条件①**永远为 False** ✗✗（用户点「停止生成」✓
    #: 轮次内部不知道 ✓ —— 只有 turn_runner 在**收到 chunk 时**查一次 ✗
    #: —— 长流式生成期间无响应 ✓）。
    #:
    #: ⚠️ **端口在实现侧** ✓ —— 契约层不碰 DB ✓。
    cancel_probe: CancelProbePort | None = None


@runtime_checkable
class TurnExecutorPort(Protocol):
    """执行器 —— **跑一轮，产出 chunk 流**（实现在模块侧 ✓）。"""

    def run(self, *, request: TurnRequest) -> AsyncIterator[Any]:
        """产出 chunk —— 类型是 ``qzdap_schema.dtos.turn`` 的那几种 ✓。"""
        ...

    def latest_state(self) -> Mapping[str, Any]:
        """执行器的**最新状态**（续传状态 / 摘要）✓。

        ⚠️ 轮次结束时要把它存进会话 —— 审批挂起时也要（恢复路径靠它 ✓）。
        """
        ...


@runtime_checkable
class TurnLifecyclePort(Protocol):
    """轮次行 + 事件流 + 轮次终态（实现在模块侧 ✓）。"""

    async def start_turn(self, *, request: TurnRequest) -> None:
        """开始这一轮 —— **轮次行落库 + 发「轮次开始」事件** ✓。

        ⚠️ **必须先落库再执行** —— 事件表的外键父行就是它 ✓。
        """
        ...

    async def append_event(
        self, *, turn_id: UUID, seq: int, event_type: str, payload: dict[str, Any]
    ) -> None:
        """把一个 chunk 落进事件流（**落库先于投递** ✓）。"""
        ...

    async def next_event_seq(self, *, turn_id: UUID) -> int:
        """这一轮的**下一个事件序号** ✓（库里已有事件的 max+1 ✓）。

        ⚠️ **不能从 1 开始数** ✓ —— 事件表主键是 ``(turn_id, seq)`` ✓，
        而**专家选择留痕**（``agent.expert.selected`` ✓）先落了一条 ✓——
        runner 再从 1 数就撞唯一键 ✓ → 整轮 500 ✓。
        """
        ...

    async def finish_turn(
        self,
        *,
        turn_id: UUID,
        status: str,
        final_response: str = "",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
        error_code: str | None = None,
    ) -> None:
        """轮次落到终态（``succeeded`` / ``failed`` / ``cancelled``）✓。

        ⚠️ **成本归属**写 ``session_turns.cost_usd``（S-19 ✓）。
        """
        ...

    async def fail_turn(self, *, turn_id: UUID, code: str, message: str = "") -> None:
        """失败落库 —— **尽力而为，不抛**（失败也得留下痕迹 ✓）。"""
        ...

    async def mark_delivered(self, *, turn_id: UUID) -> None:
        """事件已投递（重放判据用 —— 见 Session 方案 §7）。"""
        ...

    async def mark_waiting_approval(self, *, turn_id: UUID, pending: Mapping[str, Any]) -> None:
        """轮次挂起等审批 —— **挂起信息落库** ✓（``session_turns.pending_approval``）。

        ⚠️ **必须落库**：进程重启后审批要能恢复 ✓（只在内存里 = 永久卡死 ✗✗）。
        """
        ...


@runtime_checkable
class SessionStatePort(Protocol):
    """会话行的读改（实现在模块侧 ✓）。"""

    async def patch_session(
        self,
        *,
        session_id: UUID,
        metadata: Mapping[str, Any] | None = None,
        resume_state: Mapping[str, Any] | None = None,
    ) -> None:
        """改会话的元数据 / 续传状态（**合并**，不是覆盖 ✓）。

        ⚠️ **续传状态归 ``metadata["resume"]``** ✓（不再有 ``graph_state``
        列 ✓ —— 台账 **X3** ✓）。
        """
        ...


class TurnCancelled(Exception):
    """内部信号 —— 用户请求停止生成 ✓。"""


class DuplicateTurnRequest(Exception):
    """**同一个幂等键又来了** ✓ —— 重复到达（双击 / 网络重试）✓。

    ⚠️ **这不是「错误」** ✓ —— 上层据此**重放上一轮的事件流** ✓
    （Gateway 方案 §4.5 ✓ —— 客户端无感 ✓）。
    """

    def __init__(self, *, turn_id: UUID | None = None) -> None:
        super().__init__("duplicate turn request")
        self.turn_id = turn_id


class TurnBusy(Exception):
    """**会话已有轮次在飞** ✓ —— 上层翻成 409 ``SESSION_BUSY`` ✓。"""


#: **轮次行里保留具体码的那些** ✓ —— 平台自己判的闸门 ✓（超时 ✓ / 配额 ✓ /
#: 预算 ✓）—— 运维要能从轮次行一眼看出「为什么停」✓。
#: ⚠️ **供应商侧的错不算** ✓ —— 那就是「这一轮失败了」✓（``TURN_FAILED`` ✓）。
_LOOP_ERROR_CODES = frozenset(
    {
        ErrorCode.AGENT_STEP_TIMEOUT.value,
        ErrorCode.AGENT_TURN_TIMEOUT.value,
        ErrorCode.AGENT_TOOL_QUOTA_EXCEEDED.value,
        "DEEP_AGENT_BUDGET_EXCEEDED",
    }
)


class TurnTimeout(Exception):
    """**这一轮超时了** ✓（跑太久 ✓ —— 连接还占着 ✗✗）。

    ⚠️ **与「取消」分开** ✓ —— 取消是用户点的 ✓（``TURN_CANCELLED`` ✓），
    超时是系统判的 ✓（``AGENT_TURN_TIMEOUT`` ✓）—— 排查时要看得出区别 ✓。
    """


@dataclass(frozen=True, slots=True)
class TurnContext:
    """跑一轮的**输入** ✓ —— 模块侧读完会话之后交给契约层的东西 ✓。

    ⚠️ **这里不放领域对象** ✓ —— 契约层不认模块侧的实体 ✓（§0 的规矩 ✓）；
    需要模块侧数据的地方由 :class:`TurnRequestFactoryPort` 去读 ✓。
    """

    tenant_id: UUID
    workspace_id: UUID
    owner_id: UUID
    session_id: UUID
    user_input: str
    model: str | None = None
    route_id: ModelId | None = None
    resume: dict[str, Any] | None = None
    client_request_id: str = ""
    channel: ChannelType = ChannelType.WEB
    idempotency_key: IdempotencyKey | None = None
    parent_span_context: Any = None


@runtime_checkable
class TurnRequestFactoryPort(Protocol):
    """**模块侧组装这一轮的请求** ✓（读会话 / 历史 / agent → :class:`TurnRequest`）✓。

    ⚠️ **契约层不读模块侧的表** ✓ —— 它要什么就**问模块侧要** ✓
    （这正是「窄端口 + DTO」的延续 ✓ —— Session 方案 §6 ✓）。
    """

    async def build(
        self,
        *,
        context: TurnContext,
        turn_id: UUID,
        idempotency_key: IdempotencyKey,
        ingress_seq: int | None,
    ) -> TurnRequest: ...


class TurnRunner:
    """一轮的编排（**唯一** turn 实现 ✓）。"""

    def __init__(
        self,
        *,
        executor: TurnExecutorPort,
        lifecycle: TurnLifecyclePort,
        messages: Any,
        session_state: SessionStatePort,
        cancel: CancelProbePort,
        # ⚠️ **排队端口** ✓（Router Stage 3 ✓）—— **没有它就不排队** ✓
        # （开关关掉时的旧语义 ✓ —— 「拒绝 409」✓）。
        queue: TurnQueuePort | None = None,
        # ⚠️ **入站序号分配器** ✓（Router 方案 §4.2 ✓）—— **排队时才用** ✓。
        sequence: SessionSequencePort | None = None,
        # ⚠️ **幂等守卫 + 会话占用** ✓（S-21b ✓）—— **准入归编排** ✓
        # （薄壳只管「读 + 组装」✓ —— 台账 X18 的最后一层 ✓）。
        idempotency: IdempotencyGuard | None = None,
        claim: TurnClaimPort | None = None,
        # ⚠️ **整轮超时** ✓（0 = 不限 ✓）—— 之前**没有整轮预算** ✓ →
        # 上游挂住 ✓ → 连接一直占着 ✓ → 用户干等 ✗✗。
        timeout_seconds: float = 0.0,
    ) -> None:
        self._executor = executor
        self._lifecycle = lifecycle
        self._messages = messages
        self._session_state = session_state
        self._cancel = cancel
        self._queue = queue
        self._sequence = sequence
        self._idempotency = idempotency
        self._claim = claim
        self._timeout_seconds = float(timeout_seconds or 0.0)

    async def run_turn(
        self,
        *,
        context: TurnContext,
        factory: TurnRequestFactoryPort,
    ) -> AsyncIterator[Any]:
        """**跑一轮的入口** ✓ —— 幂等 + claim + 转发都在这里 ✓（S-21b ✓）。

        顺序 ✓（与旧薄壳同口径 ✓ —— 一行不多一行不少 ✓）：

        1. **幂等 accept** ✓ —— 重复 → :class:`DuplicateTurnRequest` ✓；
        2. **轮次 id** ✓；
        3. **排队模式** → 分配入站序号 ✓（放行由轮次行的状态 CAS 决定 ✓），
           **非排队模式** → 抢会话占用 ✓（抢不到 → :class:`TurnBusy` ✓，
           **键要释放** ✓ —— 否则调用方用同一个键重试会被误判成重复 ✗）；
        4. **模块侧组装**这一轮的请求 ✓（:class:`TurnRequestFactoryPort` ✓）；
        5. **跑** ✓；
        6. **收尾**：幂等键落成 ✓ + 释放占用 ✓。
        """
        if self._idempotency is None or self._claim is None:
            raise RuntimeError("turn admission ports are not wired")
        key = context.idempotency_key or resolve_idempotency_key(
            client_request_id=context.client_request_id or None,
            channel=str(context.channel),
            chat_id=str(context.session_id),
            user_id=str(context.owner_id),
            text=context.user_input,
        )
        scope = InboxScope.for_web(
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            channel=context.channel,
        )
        decision = await self._idempotency.accept(
            scope,
            key,
            payload_hash=payload_hash_of(str(context.session_id), context.user_input),
            trace_id=current_trace_id() or "",
        )
        if decision.is_duplicate:
            # 同一个键又来了 —— 双击或网络重试, 不跑第二轮.
            raise DuplicateTurnRequest(turn_id=decision.turn_id)
        turn_id = uuid4()
        ingress_seq: int | None = None
        queueing = self._queue is not None and self._sequence is not None
        if queueing and self._sequence is not None:
            ingress_seq = await self._sequence.next_ingress_seq(
                tenant_id=context.tenant_id, session_id=context.session_id
            )
        else:
            claimed = await self._claim.claim(
                tenant_id=context.tenant_id, session_id=context.session_id, turn_id=turn_id
            )
            if not claimed:
                # 这一轮根本没跑起来 → 键不能被消费, 否则调用方用同一个键重试
                # 会被误判成重复请求.
                with contextlib.suppress(Exception):
                    await self._idempotency.release(decision)
                raise TurnBusy(f"session {context.session_id} already has a turn in flight")
        try:
            request = await factory.build(
                context=context,
                turn_id=turn_id,
                idempotency_key=key,
                ingress_seq=ingress_seq,
            )
            # ⚠️ **内层生成器要显式关掉** ✓ —— 客户端断开时 ``GeneratorExit``
            # 落在**这一层**的 ``yield`` 上 ✓（不是内层 ✓）—— 不显式关的话
            # 内层的 ``fail_turn`` 只能等 GC 收尾 ✓（轮次会停在 running ✗✗）。
            stream = self.run(request=request)
            try:
                async for chunk in stream:
                    yield chunk
            finally:
                with contextlib.suppress(Exception):
                    await stream.aclose()
        finally:
            with contextlib.suppress(Exception):
                await asyncio.shield(self._idempotency.complete(decision, turn_id=turn_id))
            with contextlib.suppress(Exception):
                await asyncio.shield(
                    self._claim.release(
                        tenant_id=context.tenant_id,
                        session_id=context.session_id,
                        turn_id=turn_id,
                    )
                )

    async def run(self, *, request: TurnRequest) -> AsyncIterator[Any]:
        """跑一轮 —— **产出 chunk 流** ✓。

        ⚠️ **事件序号由这里统一分配**：轮次内严格递增，与 SSE 的 ``id:`` 一致
        （客户端断线重连时把它作为 ``Last-Event-ID`` 带回来）✓。
        """
        # 本轮的 metadata 累加器 —— 快照 + 本轮的修改（标题 / 预览 / 摘要）。
        # ⚠️ **必须累加**：done 分支写回的是「快照 + 全部修改」，
        # 否则会把标题分支刚设的标题覆盖回旧值 ✗✗。
        metadata = dict(request.session_metadata)

        # ⚠️ **取消探测装进请求** ✓ —— 循环内要用它 ✓（取消条件① ✓）。
        # ⚠️ **这里做** ✓ —— probe 是本类的 ✓（它持有跨进程的取消标记 ✓）
        # —— 模块侧组装请求时还没有它 ✓。
        if request.cancel_probe is None:
            request = replace(request, cancel_probe=self._cancel)

        await self._lifecycle.start_turn(request=request)

        # ⚠️ **排队** ✓（Router Stage 3 · 决策 #1「S1 严格排队」✓）——
        # **开关关掉时这段不跑** ✓（旧语义：「拒绝 409 SESSION_BUSY」✓）。
        if self._queue is not None and request.ingress_seq is not None:
            async for queued in self._wait_for_slot(request=request):
                yield queued

        seq = await self._messages.next_seq(session_id=request.session_id)
        if not request.resume:
            await self._messages.append(
                tenant_id=request.tenant_id,
                workspace_id=request.workspace_id,
                session_id=request.session_id,
                turn_id=request.turn_id,
                seq=seq,
                role="user",
                content=request.user_input,
            )
            seq += 1
            # 会话标题还没定的话, 用第一句话当标题 —— 会话列表里全是
            # 「与 XX 对话」根本没法认.
            if metadata.get("title_auto"):
                metadata["title"] = _auto_title(request.user_input)
                metadata["title_auto"] = False
                await self._session_state.patch_session(
                    session_id=request.session_id, metadata=metadata
                )

        assistant_parts: list[str] = []
        turn_usage: UsageChunk | None = None
        # ⚠️ **这一轮见过的错误码** ✓ —— 有错 ✓ → 轮次**不算成功** ✓
        # （之前错误事件一过 ✓ → 轮次照样落 succeeded ✗✗ —— 排查时看到的
        # 是「成功」✓ 但用户看到的是报错 ✗✗）。
        seen_error_code: str | None = None
        emitted = False
        last_cancel_check = monotonic()
        # ⚠️ **整轮预算** ✓ —— 0 = 不限 ✓。
        deadline = monotonic() + self._timeout_seconds if self._timeout_seconds > 0 else None
        try:
            async for chunk in self._chunks_with_deadline(request=request, deadline=deadline):
                emitted = True
                now = monotonic()
                if now - last_cancel_check >= CANCEL_POLL_SECONDS:
                    last_cancel_check = now
                    if await self._cancel.is_cancel_requested(session_id=request.session_id):
                        raise TurnCancelled("用户请求停止生成")
                if isinstance(chunk, ErrorChunk):
                    # ⚠️ **错误事件的文案要投影** ✓ —— 与异常路径同一口径 ✓
                    # （已知码给人话 ✓ / 未知码保留细节 ✓）。
                    chunk = chunk.model_copy(
                        update={
                            "message": project_error_message(
                                str(chunk.code or ""), str(chunk.message or ""), "web"
                            )
                        }
                    )
                    seen_error_code = str(chunk.code or "")
                stamped = await self._publish_chunk(turn_id=request.turn_id, chunk=chunk)
                yield stamped
                if getattr(stamped, "kind", None) == "message":
                    assistant_parts.append(getattr(stamped, "content", "") or "")
                if isinstance(stamped, ApprovalRequiredChunk):
                    metadata["preview"] = "等待确认操作"
                    await self._session_state.patch_session(
                        session_id=request.session_id,
                        metadata=metadata,
                        resume_state=self._executor.latest_state(),
                    )
                    # 审批挂起信息**落库**（Session 方案 §8 · 决策 #6）——
                    # 恢复时要靠它校验「挂起的是哪个工具、参数有没有被改」✓。
                    pending = PendingApproval(
                        approval_id=stamped.approval_id,
                        tool_name=stamped.tool_name,
                        arguments_digest=arguments_digest(stamped.arguments),
                        session_id=request.session_id,
                        turn_id=request.turn_id,
                        created_at=datetime.now(UTC),
                    )
                    await self._lifecycle.mark_waiting_approval(
                        turn_id=request.turn_id, pending=pending.to_json()
                    )
                if isinstance(stamped, UsageChunk):
                    turn_usage = stamped
                if isinstance(stamped, DoneChunk):
                    final = stamped.final_message or "".join(assistant_parts)
                    await self._messages.append(
                        tenant_id=request.tenant_id,
                        workspace_id=request.workspace_id,
                        session_id=request.session_id,
                        turn_id=request.turn_id,
                        seq=seq,
                        role="assistant",
                        content=final,
                    )
                    metadata["preview"] = final[:80]
                    # ⚠️ **摘要不写这里** ✓（Context 方案 §5.1 ✓）—— 它的
                    # **唯一落点**是 `agent_sessions.rolling_summary` ✓（写者 =
                    # Context 层 ✓ —— 旧副本的读写点到此**全部归零** ✓）。
                    await self._session_state.patch_session(
                        session_id=request.session_id,
                        metadata=metadata,
                        resume_state=self._executor.latest_state(),
                    )
                    # ⚠️ **出过错就不算成功** ✓ —— 轮次行要如实反映 ✓。
                    turn_failed = seen_error_code is not None
                    await self._lifecycle.finish_turn(
                        turn_id=request.turn_id,
                        status=(
                            TurnStatus.FAILED.value if turn_failed else TurnStatus.SUCCEEDED.value
                        ),
                        final_response=final,
                        input_tokens=turn_usage.input_tokens if turn_usage else None,
                        output_tokens=(turn_usage.output_tokens if turn_usage else None),
                        cost_usd=turn_usage.cost_usd if turn_usage else None,
                        error_code=(
                            seen_error_code
                            if seen_error_code in _LOOP_ERROR_CODES
                            else ErrorCode.TURN_FAILED.value
                        )
                        if turn_failed
                        else None,
                    )
                    await self._lifecycle.mark_delivered(turn_id=request.turn_id)
        except TurnTimeout as exc:
            await self._lifecycle.fail_turn(
                turn_id=request.turn_id, code=ErrorCode.AGENT_TURN_TIMEOUT.value, message=str(exc)
            )
            yield await self._publish_chunk(
                turn_id=request.turn_id,
                chunk=ErrorChunk(
                    turn_id=request.turn_id,
                    seq=0,
                    code=ErrorCode.AGENT_TURN_TIMEOUT.value,
                    message="本轮生成超时，请重试",
                    retriable=True,
                ),
            )
        except TurnCancelled as exc:
            await self._lifecycle.fail_turn(
                turn_id=request.turn_id, code=ErrorCode.TURN_CANCELLED.value, message=str(exc)
            )
            yield await self._publish_chunk(
                turn_id=request.turn_id,
                chunk=ErrorChunk(
                    turn_id=request.turn_id,
                    seq=0,
                    code=ErrorCode.TURN_CANCELLED.value,
                    message="已停止生成",
                    retriable=True,
                ),
            )
        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断开 / 请求被取消 (GeneratorExit = 响应体生成器被关闭):
            # 轮次必须落到 failed, 否则它会永远停在 running, 任务列表里一直
            # 显示「执行中」.
            try:
                await asyncio.shield(
                    self._lifecycle.fail_turn(
                        turn_id=request.turn_id, code=ErrorCode.TURN_CANCELLED.value
                    )
                )
            except Exception:
                _log.exception("failed to close cancelled turn")
            raise
        except Exception as exc:  # 失败必须可见
            _log.warning("turn failed turn_id=%s", request.turn_id, exc_info=True)
            await self._lifecycle.fail_turn(
                turn_id=request.turn_id, code=ErrorCode.TURN_FAILED.value, message=str(exc)
            )
            if not emitted:
                # 一个 chunk 都没产出 → 轮次根本没起来. 抛给 HTTP 层, 让状态码
                # 表达失败 (而不是 200 + error 事件).
                raise
            yield await self._publish_chunk(
                turn_id=request.turn_id,
                chunk=ErrorChunk(
                    turn_id=request.turn_id,
                    seq=0,
                    code=ErrorCode.TURN_FAILED.value,
                    # web 投放面：**没写消息的领域异常** → 用投影文案
                    # （别把 "EXTERNAL_SERVICE_ERROR" 甩到聊天气泡里）；
                    # 有具体消息的保留原样，技术细节留在日志 ✓。
                    message=project_error_message(
                        str(getattr(exc, "code", "")),
                        str(exc) or type(exc).__name__,
                        "web",
                    ),
                    retriable=False,
                ),
            )

    async def _chunks_with_deadline(
        self, *, request: TurnRequest, deadline: float | None
    ) -> AsyncIterator[Any]:
        """**按整轮预算取 chunk** ✓（``deadline is None`` = 不限 ✓）。

        ⚠️ **超时卡在「等下一片」上** ✓ —— 与单步超时同一口径 ✓：
        **消费者自己的处理时间不算进去** ✓（慢客户端不该被误杀 ✗✗）。
        """
        iterator = self._executor.run(request=request).__aiter__()
        try:
            while True:
                try:
                    if deadline is None:
                        chunk = await iterator.__anext__()
                    else:
                        remaining = deadline - monotonic()
                        if remaining <= 0:
                            raise TimeoutError
                        chunk = await asyncio.wait_for(iterator.__anext__(), remaining)
                except StopAsyncIteration:
                    return
                except TimeoutError as exc:
                    raise TurnTimeout(f"turn exceeded {self._timeout_seconds:.0f}s") from exc
                yield chunk
        finally:
            close = getattr(iterator, "aclose", None)
            if close is not None:
                with contextlib.suppress(Exception):
                    await close()

    async def _wait_for_slot(self, *, request: TurnRequest) -> AsyncIterator[Any]:
        """**等 FIFO 位** ✓（Router 方案 §4.2 ✓）。

        ⚠️ **等待期间要发「排队中」** ✓（Router 方案 §0.7 ✓）—— 否则前端
        只能一直转圈到首 chunk 到达 ✓。
        """
        assert self._queue is not None
        assert request.ingress_seq is not None
        seq = 1
        try:
            async for decision in wait_for_turn_slot(
                self._queue,
                tenant_id=request.tenant_id,
                session_id=request.session_id,
                turn_id=request.turn_id,
                ingress_seq=request.ingress_seq,
                cancelled=lambda: self._cancel.is_cancel_requested(session_id=request.session_id),
            ):
                yield await self._publish_chunk(
                    turn_id=request.turn_id,
                    chunk=QueuedChunk(
                        turn_id=request.turn_id,
                        seq=0,
                        position=decision.position,
                        waited_ms=decision.waited_ms,
                        estimated_wait_seconds=decision.estimated_wait_seconds,
                    ),
                    seq=seq,
                )
                seq += 1
        except QueueCancelled as exc:
            # ⚠️ **取消 = 轮次落终态** ✓（不留一行 running ✗✗）。
            await self._lifecycle.finish_turn(
                turn_id=request.turn_id, status=TurnStatus.CANCELLED.value
            )
            raise TurnCancelled(str(exc)) from exc
        except (QueueFullError, QueueTimeoutError):
            # ⚠️ **超限 / 超时 → 轮次落 cancelled** ✓（可查 ✓ —— 决策 #7 ✓）
            # —— **不静默丢弃** ✓。
            await self._lifecycle.finish_turn(
                turn_id=request.turn_id, status=TurnStatus.CANCELLED.value
            )
            raise

    async def _publish_chunk(self, *, turn_id: UUID, chunk: Any) -> Any:
        """把 chunk 落进事件流并重新编号 —— **落库先于投递**（Session §7）。

        ⚠️ **重新编号**：上游（graph runner）的 seq 有两套编号空间（chunk 序号
        与消息序号），还会出现重复 —— 直接拿它当事件主键会撞
        ``session_events`` 的 ``(turn_id, seq)``。

        ⚠️ **号从库里取** ✓（不是本地从 1 数 ✓）—— **同一轮还有别人写
        事件** ✓（专家选择留痕 ✓）—— 两边各自数数会撞唯一键 ✓ →
        整轮 500 ✓（开发环境没配模型时必现 ✓）。
        """
        seq = await self._lifecycle.next_event_seq(turn_id=turn_id)
        stamped = chunk.model_copy(update={"seq": seq})
        await self._lifecycle.append_event(
            turn_id=turn_id,
            seq=seq,
            event_type=str(stamped.kind),
            payload=stamped.model_dump(mode="json"),
        )
        return stamped


def _auto_title(user_input: str) -> str:
    """Derive a session title from the first user message."""
    text = " ".join(str(user_input or "").split())
    if len(text) <= 24:
        return text or "新对话"
    return text[:24] + "…"


__all__ = [
    "AgentSnapshot",
    "CancelProbePort",
    "DuplicateTurnRequest",
    "SessionStatePort",
    "TurnBusy",
    "TurnCancelled",
    "TurnContext",
    "TurnExecutorPort",
    "TurnLifecyclePort",
    "TurnRequest",
    "TurnRequestFactoryPort",
    "TurnRunner",
]
