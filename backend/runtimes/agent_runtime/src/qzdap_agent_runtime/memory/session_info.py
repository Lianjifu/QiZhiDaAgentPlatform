"""**会话信息**的窄端口 ✓（管理端要显示「谁 ↔ 哪个 agent」✓）。

⚠️ **Memory 不查会话表** ✓ —— 那是 agent_runtime 模块的表 ✗✗ → 走窄端口
✓（同 ``SessionActivityPort`` 的做法 ✓ —— §5 的边界 ✓）。

⚠️ **agent 名字取自会话 metadata** ✓（``agentName`` ✓）—— 与会话列表的
口径**一致** ✓（不 join agents ✓ —— 那是刻意的选择 ✓）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """**一个会话的展示信息** ✓。"""

    session_id: UUID
    #: **会话的主人** ✓（= 会话行的 owner ✓）。
    owner_id: UUID | None = None
    #: **agent 名字** ✓（会话 metadata 里的 ``agentName`` ✓）。
    agent_name: str = ""


@runtime_checkable
class SessionInfoPort(Protocol):
    """**按会话 id 查展示信息** ✓（实现在 agent_runtime 模块 ✓）。"""

    async def describe(self, session_ids: tuple[UUID, ...]) -> dict[UUID, SessionInfo]:
        """**批量查** ✓（查不到的**不在结果里** ✓ —— 不猜 ✓）。"""
        ...


__all__ = ["SessionInfo", "SessionInfoPort"]
