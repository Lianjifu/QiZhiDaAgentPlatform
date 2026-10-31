"""会话缓冲的**提炼** ✓（M-29 ✓ —— Memory 方案 Stage 5 ✓）。

⚠️ **会话级策略的记忆先落在缓冲里** ✓（§7.1 ✓ + 决策 #5 ✓）——
会话结束后**提炼成用户级 L2** ✓（或按 TTL **丢弃** ✓ —— 不留垃圾 ✓）。

⚠️ **触发者必须明确** ✓（§5 的要求 ✓ —— 「没有触发者 = 这个能力不存在」✓）——
由 **sweeper** 触发 ✓（与 Session 层的清扫器**同批调度** ✓）。

⚠️ **「会话还在不在」由 Session 层回答** ✓ —— Memory **不查会话表** ✓
（那是别人的表 ✗✗）→ 走一个**窄端口** ✓（`SessionActivityPort` ✓）。

⚠️ **这一层是契约层** —— 端口 + 编排 ✓（落库归模块侧 ✓）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable
from uuid import UUID

from qzdap_agent_runtime.memory.writer import WriteOutcome


@dataclass(frozen=True, slots=True)
class BufferRow:
    """缓冲里的一条待提炼记忆 ✓。"""

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    session_id: UUID
    user_id: UUID
    turn_id: UUID | None
    content: str
    content_hash: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RefineReport:
    """一次提炼的结果 ✓。"""

    #: **提炼成 L2** 的条数 ✓。
    promoted: int = 0
    #: **重复跳过** 的条数 ✓（已有同样的记忆 ✓）。
    deduplicated: int = 0
    #: **被闸门拒绝** 的条数 ✓。
    rejected: int = 0
    #: **过期丢弃** 的条数 ✓（TTL 到期 ✓ —— 不留垃圾 ✓）。
    discarded: int = 0

    @property
    def total(self) -> int:
        return self.promoted + self.deduplicated + self.rejected + self.discarded


@runtime_checkable
class BufferPort(Protocol):
    """**会话缓冲**的存取 ✓（实现在模块侧 ✓ —— 它要碰那张表 ✓）。"""

    async def add(self, row: BufferRow) -> None: ...

    async def list_pending(self, *, before: datetime, limit: int = 100) -> list[BufferRow]:
        """**待提炼** 的行 ✓（按创建时间 ✓）。"""
        ...

    async def delete(self, row_ids: tuple[UUID, ...]) -> None:
        """**删掉已处理的行** ✓（提炼完 / 丢弃后 ✓）。"""
        ...

    # ── 管理面要看的（**L1 表退役后的唯一来源** ✓ —— M-46 ✓）────────
    async def list_workspace_views(self, *, workspace_id: UUID) -> list[SessionBufferView]:
        """**工作区下每个会话的缓冲概览** ✓（管理端列的就是它 ✓）。"""
        ...

    async def list_session_rows(self, *, session_id: UUID) -> list[BufferRow]:
        """**某个会话的缓冲条目** ✓（详情页 ✓）。"""
        ...

    async def delete_session(self, *, session_id: UUID) -> int:
        """**冲掉一个会话的缓冲** ✓（返回**冲掉几条** ✓ —— 「冲了但其实没东西」要看得见 ✓）。"""
        ...

    async def delete_user(self, *, workspace_id: UUID, user_id: UUID) -> int:
        """**删掉某个用户的缓冲行** ✓（数据治理的删除范围 ✓ —— C9 ✓）。"""
        ...


@dataclass(frozen=True, slots=True)
class SessionBufferView:
    """**一个会话的缓冲概览** ✓（管理端看的就是它 ✓ —— 不再有 L1 表 ✓）。

    ⚠️ **它不是「L1 会话」** ✓ —— 那是旧模型 ✓（一个会话一条 ✓）——
    现在是**按会话聚合** ✓（会话里可能有多条待提炼的记忆 ✓）。
    """

    session_id: UUID
    workspace_id: UUID
    user_id: UUID
    #: **缓冲里的条目数** ✓。
    items: int
    #: **内容的总长度** ✓（字符数 ✓ —— 够前端显示「占了多大」✓）。
    total_chars: int
    #: **最早写入** ✓（≈ 会话开始时间 ✓）。
    created_at: datetime
    #: **最近一次写入** ✓。
    last_write_at: datetime


@runtime_checkable
class SessionActivityPort(Protocol):
    """**会话还在不在** ✓（实现在 Session 层那侧 ✓ —— 它拥有会话表 ✓）。

    ⚠️ **Memory 不查会话表** ✓ —— 那是别人的表 ✗✗ → 走窄端口 ✓。
    """

    async def active_session_ids(self, *, session_ids: tuple[UUID, ...]) -> set[UUID]:
        """**还在跑**的会话 ✓（空的 = 都结束了 ✓）。"""
        ...


class BufferRefiner:
    """**会话缓冲的提炼者** ✓（M-29 ✓）。

    ⚠️ **判据是「会话没活动轮次了」** ✓（由 Session 层回答 ✓）——
    还在跑的会话**不动** ✓（否则会把进行中的对话提炼掉 ✗✗）。
    """

    def __init__(
        self,
        *,
        buffer: BufferPort,
        activity: SessionActivityPort,
        writer: object,
        ttl: timedelta = timedelta(hours=24),
    ) -> None:
        self._buffer = buffer
        self._activity = activity
        self._writer = writer
        self._ttl = ttl

    async def refine(self, *, now: datetime, limit: int = 100) -> RefineReport:
        """**提炼一批** ✓。

        ⚠️ **过期先丢** ✓（TTL 到期 → 丢弃 ✓ —— 不留垃圾 ✓）；
        ⚠️ **会话还在跑就跳过** ✓（不动进行中的对话 ✓）。
        """
        rows = await self._buffer.list_pending(before=now, limit=limit)
        if not rows:
            return RefineReport()
        expired = [row for row in rows if now - row.created_at > self._ttl]
        if expired:
            await self._buffer.delete(tuple(row.id for row in expired))
        pending = [row for row in rows if row not in expired]
        if not pending:
            return RefineReport(discarded=len(expired))
        active = await self._activity.active_session_ids(
            session_ids=tuple({row.session_id for row in pending})
        )
        finished = [row for row in pending if row.session_id not in active]
        promoted = 0
        deduplicated = 0
        rejected = 0
        done: list[UUID] = []
        for row in finished:
            outcome: WriteOutcome = await self._writer.write_fact(  # type: ignore[attr-defined]
                tenant_id=row.tenant_id,
                workspace_id=row.workspace_id,
                user_id=row.user_id,
                session_id=row.session_id,
                turn_id=row.turn_id,
                content=row.content,
                confidence_source="rule",
            )
            promoted += len(outcome.written)
            deduplicated += len(outcome.deduplicated)
            rejected += len(outcome.rejected)
            done.append(row.id)
        if done:
            await self._buffer.delete(tuple(done))
        return RefineReport(
            promoted=promoted,
            deduplicated=deduplicated,
            rejected=rejected,
            discarded=len(expired),
        )


__all__ = [
    "BufferPort",
    "BufferRefiner",
    "BufferRow",
    "RefineReport",
    "SessionActivityPort",
    "SessionBufferView",
]
