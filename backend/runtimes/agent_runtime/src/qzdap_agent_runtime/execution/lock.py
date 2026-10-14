"""Execution 层：LockManager + ToolExecutor（§5.7 / §4.2 / §4.3）。

Stage 2 PR C 范围：

- `LockManager` 协议：抽象 turn 锁接口，生产用 Postgres advisory lock，
  测试用 `InMemoryLockManager`。
- `LockToken` dataclass：锁拥有权证明，节点可释放。
- `InMemoryLockManager`：纯内存实现，单测用。
- `acquire_turn_lock` 节点实现：advisory lock + revision 乐观并发校验
  + 锁拥有权写入 state。
- `release_turn_lock` 节点实现：释放锁（释放失败仅记日志，不影响 turn）。

§4.2 / §4.3 决议：

- 同一 session 默认只允许一个活动 turn。
- 并发输入返回 `SESSION_BUSY` 或进入显式队列。
- 使用 advisory lock（`pg_advisory_xact_lock(hashtext('session:' || session_id::text))`）。
- `start_turn(expected_revision=N)` 与 `current_revision` 不匹配返回 `REVISION_CONFLICT`。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Lock token
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LockToken:
    """锁拥有权证明，节点可凭 token 释放。"""

    session_id: str
    turn_id: str
    holder_id: str  # 谁拿到锁（advisory lock 用 hash 标识）


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LockManager(Protocol):
    """turn 锁抽象接口。"""

    def acquire(
        self,
        *,
        session_id: str,
        turn_id: str,
        expected_revision: int,
        current_revision: int,
    ) -> LockToken:
        """尝试获取锁。

        Returns:
            LockToken：成功获取。

        Raises:
            SessionBusyError：已有活动 turn。
            RevisionConflictError：revision 不匹配。
        """
        ...

    def release(self, token: LockToken) -> None:
        """释放锁。失败仅记日志，不影响已成功的 turn 状态。"""
        ...


# ---------------------------------------------------------------------------
# 错误
# ---------------------------------------------------------------------------


class SessionBusyError(Exception):
    """SESSION_BUSY: 同一 session 已有活动 turn（§5.9 错误码）。"""

    def __init__(self, session_id: str, current_turn_id: str | None) -> None:
        self.session_id = session_id
        self.current_turn_id = current_turn_id
        super().__init__(
            f"session {session_id} busy (current turn: {current_turn_id})"
        )


class RevisionConflictError(Exception):
    """REVISION_CONFLICT: state-level revision 不匹配。"""

    def __init__(
        self, session_id: str, expected: int, current: int
    ) -> None:
        self.session_id = session_id
        self.expected = expected
        self.current = current
        super().__init__(
            f"session {session_id} revision conflict: "
            f"expected {expected}, current {current}"
        )


# ---------------------------------------------------------------------------
# In-memory 实现（单测 / 本地 dev）
# ---------------------------------------------------------------------------


def _holder_id_for(session_id: str) -> int:
    """把 session_id 映射到 PostgreSQL `hashtext` 等价的 int64 持有者 ID。

    Postgres hashtext 返回 int32；这里用 sha256 前 8 字节作为稳定 hash，
    再 mod 2^31 截到 int32 范围。
    """
    h = hashlib.sha256(session_id.encode("utf-8")).digest()
    val = int.from_bytes(h[:4], "big", signed=False)
    return val & 0x7FFFFFFF  # 截到 int32 正数范围


@dataclass
class _InMemoryLockEntry:
    token: LockToken
    current_revision: int


class InMemoryLockManager:
    """进程内 lock manager（单测 / 本地 dev 用）。

    线程安全由调用方保证（LangGraph node 都在同一 asyncio loop 内运行）。
    """

    def __init__(self) -> None:
        self._locks: dict[str, _InMemoryLockEntry] = {}

    def acquire(
        self,
        *,
        session_id: str,
        turn_id: str,
        expected_revision: int,
        current_revision: int,
    ) -> LockToken:
        # 已有活动 turn → SESSION_BUSY
        existing = self._locks.get(session_id)
        if existing is not None and existing.token.turn_id != turn_id:
            raise SessionBusyError(session_id, existing.token.turn_id)

        # revision 不匹配 → REVISION_CONFLICT
        if expected_revision != current_revision:
            raise RevisionConflictError(session_id, expected_revision, current_revision)

        token = LockToken(
            session_id=session_id,
            turn_id=turn_id,
            holder_id=str(_holder_id_for(session_id)),
        )
        self._locks[session_id] = _InMemoryLockEntry(
            token=token, current_revision=current_revision
        )
        return token

    def release(self, token: LockToken) -> None:
        existing = self._locks.get(token.session_id)
        if existing is None or existing.token.turn_id != token.turn_id:
            # 锁不存在或已被其他人释放/抢占：仅静默忽略（§13.2 节点 19 失败处理）
            return
        del self._locks[token.session_id]

    def peek(self, session_id: str) -> LockToken | None:
        """单测辅助：查询当前持有者。"""
        entry = self._locks.get(session_id)
        return entry.token if entry else None


__all__ = [
    "InMemoryLockManager",
    "LockManager",
    "LockToken",
    "RevisionConflictError",
    "SessionBusyError",
]