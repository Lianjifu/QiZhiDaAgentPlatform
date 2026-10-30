"""**唯一 turn 实现**（Session 方案 §6）—— 一轮的编排。

⚠️ **这是「唯一」的实现**：旧的两套（``copilot.py`` 的 turn 编排 X18 与
``use_cases/run_turn*.py`` X2）里，**治理语义取 Copilot 版**（claim / 幂等 /
取消 / 审批），use_cases 版的简化语义**丢掉** ✓。

**这一层只管「顺序与语义」，不管「怎么读、怎么写」** —— 全部走端口 ✓：

| 端口 | 职责 | 实现 |
|---|---|---|
| :class:`TurnExecutorPort` | 跑一轮并产出 chunk | 模块侧（现役的 graph runner） |
| :class:`TurnLifecyclePort` | 轮次行（新旧双写）+ 事件落库 + 轮次终态 | 模块侧 |
| :class:`SessionMessagePort` | 消息读写（会话内序号） | 模块侧 |
| :class:`SessionStatePort` | 会话行的读改（标题 / 预览 / 摘要 / graph_state） | 模块侧 |
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
import logging
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from qzdap_schema.dtos.errors import project_error_message
from qzdap_schema.dtos.turn import (
    ApprovalRequiredChunk,
    DoneChunk,
    ErrorChunk,
    UsageChunk,
)
from qzdap_schema.ids import ModelId

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
    rolling_summary: str = ""
    session_metadata: Mapping[str, Any] = field(default_factory=dict)
    graph_state: Mapping[str, Any] = field(default_factory=dict)
    route_decision: Mapping[str, Any] | None = None
    parent_span_context: Any = None
    trace_id: str | None = None


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


@runtime_checkable
class SessionStatePort(Protocol):
    """会话行的读改（实现在模块侧 ✓）。"""

    async def patch_session(
        self,
        *,
        session_id: UUID,
        metadata: Mapping[str, Any] | None = None,
        graph_state: Mapping[str, Any] | None = None,
        wait_status: str | None = None,
    ) -> None:
        """改会话的元数据 / 续传状态（**合并**，不是覆盖 ✓）。

        ⚠️ ``wait_status`` 是**过渡期**参数 —— 那列的互斥职责已迁走（台账 R3
        ✅），现在只剩「审批挂起」的语义；Stage 5 会把它换成
        ``session_turns.pending_approval`` 落库 ✓。
        """
        ...


@runtime_checkable
class CancelProbePort(Protocol):
    """取消标记（实现在模块侧 ✓）。"""

    async def is_cancel_requested(self, *, session_id: UUID) -> bool:
        """用户是否请求停止这一轮 ✓（跨进程可见）。"""
        ...


class TurnCancelled(Exception):
    """内部信号 —— 用户请求停止生成 ✓。"""


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
    ) -> None:
        self._executor = executor
        self._lifecycle = lifecycle
        self._messages = messages
        self._session_state = session_state
        self._cancel = cancel

    async def run(self, *, request: TurnRequest) -> AsyncIterator[Any]:
        """跑一轮 —— **产出 chunk 流** ✓。

        ⚠️ **事件序号由这里统一分配**：轮次内严格递增，与 SSE 的 ``id:`` 一致
        （客户端断线重连时把它作为 ``Last-Event-ID`` 带回来）✓。
        """
        # 本轮的 metadata 累加器 —— 快照 + 本轮的修改（标题 / 预览 / 摘要）。
        # ⚠️ **必须累加**：done 分支写回的是「快照 + 全部修改」，
        # 否则会把标题分支刚设的标题覆盖回旧值 ✗✗。
        metadata = dict(request.session_metadata)

        await self._lifecycle.start_turn(request=request)

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
        event_seq = 1
        emitted = False
        last_cancel_check = monotonic()
        try:
            async for chunk in self._executor.run(request=request):
                emitted = True
                now = monotonic()
                if now - last_cancel_check >= CANCEL_POLL_SECONDS:
                    last_cancel_check = now
                    if await self._cancel.is_cancel_requested(
                        session_id=request.session_id
                    ):
                        raise TurnCancelled("用户请求停止生成")
                stamped = await self._publish_chunk(
                    turn_id=request.turn_id, chunk=chunk, seq=event_seq
                )
                event_seq += 1
                yield stamped
                if getattr(stamped, "kind", None) == "message":
                    assistant_parts.append(getattr(stamped, "content", "") or "")
                if isinstance(stamped, ApprovalRequiredChunk):
                    metadata["preview"] = "等待确认操作"
                    await self._session_state.patch_session(
                        session_id=request.session_id,
                        metadata=metadata,
                        graph_state=self._executor.latest_state(),
                        wait_status="waiting_approval",
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
                    summary = str(
                        (request.graph_state or {}).get("rolling_summary")
                        or metadata.get("rolling_summary")
                        or ""
                    )
                    metadata["rolling_summary"] = summary
                    await self._session_state.patch_session(
                        session_id=request.session_id,
                        metadata=metadata,
                        graph_state=self._executor.latest_state(),
                        wait_status="idle",
                    )
                    await self._lifecycle.finish_turn(
                        turn_id=request.turn_id,
                        status="succeeded",
                        final_response=final,
                        input_tokens=turn_usage.input_tokens if turn_usage else None,
                        output_tokens=(
                            turn_usage.output_tokens if turn_usage else None
                        ),
                        cost_usd=turn_usage.cost_usd if turn_usage else None,
                    )
                    await self._lifecycle.mark_delivered(turn_id=request.turn_id)
        except TurnCancelled as exc:
            await self._lifecycle.fail_turn(
                turn_id=request.turn_id, code="TURN_CANCELLED", message=str(exc)
            )
            yield await self._publish_chunk(
                turn_id=request.turn_id,
                chunk=ErrorChunk(
                    turn_id=request.turn_id,
                    seq=0,
                    code="TURN_CANCELLED",
                    message="已停止生成",
                    retriable=True,
                ),
                seq=event_seq,
            )
        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断开 / 请求被取消 (GeneratorExit = 响应体生成器被关闭):
            # 轮次必须落到 failed, 否则它会永远停在 running, 任务列表里一直
            # 显示「执行中」.
            try:
                await asyncio.shield(
                    self._lifecycle.fail_turn(
                        turn_id=request.turn_id, code="TURN_CANCELLED"
                    )
                )
            except Exception:  # noqa: BLE001
                _log.exception("failed to close cancelled turn")
            raise
        except Exception as exc:  # 失败必须可见
            _log.warning("turn failed turn_id=%s", request.turn_id, exc_info=True)
            await self._lifecycle.fail_turn(
                turn_id=request.turn_id, code="TURN_FAILED", message=str(exc)
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
                    code="TURN_FAILED",
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
                seq=event_seq,
            )

    async def _publish_chunk(self, *, turn_id: UUID, chunk: Any, seq: int) -> Any:
        """把 chunk 落进事件流并重新编号 —— **落库先于投递**（Session §7）。

        ⚠️ **重新编号**：上游（graph runner）的 seq 有两套编号空间（chunk 序号
        与消息序号），还会出现重复 —— 直接拿它当事件主键会撞
        ``session_events`` 的 ``(turn_id, seq)``。
        """
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
    "SessionStatePort",
    "TurnCancelled",
    "TurnExecutorPort",
    "TurnLifecyclePort",
    "TurnRequest",
    "TurnRunner",
]
