"""Gateway 的无感重放 —— 事件读取端口与一致性摘要。

依据：``docs/refactor/session-architecture/gateway-refactor-plan.md`` §4.5
（重复时返回什么）、§10 Stage 4b（启用无感重放）。

**这一层只定义契约**：重放读什么（:class:`StoredEvent`）、怎么读
（:class:`EventStore` 端口）、怎么证明「重放流 == 原流」
（:func:`event_digest`）。**没有 SQL、没有框架依赖** —— 表 ``session_events``
与 ``session_turns`` 归 Session 层，Gateway 只持端口。

**为什么重放要按 seq 而不是按时间**：客户端带 ``Last-Event-ID=N`` 回来时，
它要的是「我漏掉的那几段」。事件流的 ``seq`` 在同一轮次内**严格递增**
（Session 方案 §7），因此「seq > N」就是精确的续传位置。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from uuid import UUID


@dataclass(frozen=True, slots=True)
class StoredEvent:
    """一条已落库的事件 —— 重放的一帧。

    - ``seq`` —— 轮次内的事件序号（``session_events.seq``），**也是 SSE 的
      ``id:``** —— 客户端断线重连时把它作为 ``Last-Event-ID`` 带回来。
    - ``event_type`` —— 事件的种类（chunk 的 ``kind``），SSE 的 ``event:``。
    - ``payload`` —— 事件的载荷（chunk 的 JSON），SSE 的 ``data:``。
    """

    seq: int
    event_type: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """一次重放的结果 —— 事件流 + 轮次状态。

    ``status`` 是轮次的终态（``succeeded`` / ``failed`` / ``cancelled``），
    用来判断「这一轮已经结束了」—— 客户端要的片段之后没有新事件时，
    该回一个结束帧，而不是「还在跑」。
    """

    turn_id: UUID
    status: str | None
    events: list[StoredEvent]

    @property
    def is_finished(self) -> bool:
        """这一轮是否已经到终态。"""
        return self.status in {"succeeded", "failed", "cancelled"}


class EventStore(Protocol):
    """事件读取端口 —— **实现在 Session 侧**（表归 Session，§8）。

    ⚠️ **必须带租户**：``session_events`` 表本身没有 ``tenant_id`` 列
    （主键是 ``(turn_id, seq)``），事件行的租户归属由它的轮次决定 ——
    实现必须显式按租户过滤，否则就是跨租户读。
    """

    async def get_events(
        self, turn_id: UUID, *, tenant_id: UUID, after_seq: int = 0
    ) -> list[StoredEvent]:
        """读出 ``seq > after_seq`` 的事件，按 seq 升序。"""
        ...

    async def get_turn_status(self, turn_id: UUID, *, tenant_id: UUID) -> str | None:
        """读出该轮次的状态；轮次不存在（跨租户 / 不存在）时返回 ``None``。"""
        ...


def event_from_chunk(chunk: Any) -> StoredEvent:
    """把一个 chunk 转成「可落库 / 可比对」的事件。

    **载荷用 ``model_dump(mode="json")``** —— 与落库时用的是同一个方法，
    因此「原流」与「重放流」的载荷在语义上完全一致。
    """
    return StoredEvent(
        seq=int(chunk.seq),
        event_type=str(chunk.kind),
        payload=chunk.model_dump(mode="json"),
    )


def event_digest(events: list[StoredEvent]) -> str:
    """事件流的摘要 —— **重放一致性校验**用（§10 Stage 4b 的验收）。

    覆盖 ``(seq, event_type, payload)`` 三元组。载荷用 **sort_keys 的规范
    JSON**：``JSONB`` 不保序（PostgreSQL 会按长度 + 字节重排键），因此摘要
    必须与键序无关 —— 否则重放流与原流的摘要必然不等。
    """
    digest = hashlib.sha256()
    for event in events:
        digest.update(str(event.seq).encode())
        digest.update(b"|")
        digest.update(event.event_type.encode())
        digest.update(b"|")
        digest.update(
            json.dumps(
                event.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        )
        digest.update(b"\n")
    return digest.hexdigest()


__all__ = [
    "EventStore",
    "ReplayResult",
    "StoredEvent",
    "event_digest",
    "event_from_chunk",
]
