"""Session Manager —— **会话生命周期**（Session 方案 §3）。

**Router 只派生 key、选 agent；会话的创建与查回归这里**（决策 #10：Router
不直接写会话表 ✓）。

**两步流程**（§3.1）——

1. ``lookup(session_key)`` → **只读**：查既有会话与它的 agent 绑定；**不创建、
   不写任何表**、查不到返回 ``None``（**不抛错** ✓）。这是 Router **粘性规则**
   （规则 1）的唯一依据来源 ✓；
2. 未命中 → Router 走完策略链选出 agent → ``resolve_or_create(session_key,
   agent_binding)`` → 创建或复用（**并发靠唯一约束** ✓）。

> ⚠️ **为什么必须是两步**：``resolve_or_create`` 需要 ``agent_binding`` 作为
> 入参 —— 若只能靠它拿到绑定，就是**鸡生蛋**（§3.1 的审查修正 ✓）。

**这一层是契约层** —— 不引框架、不引模块；DB 访问走 :class:`SessionStorePort`
（实现在模块侧 ✓）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from qzdap_agent_runtime.session.state import TERMINAL_SESSION_STATUSES, SessionStatus


class CloseReason(StrEnum):
    """会话为什么结束（§3.2 / §3.3）。"""

    USER = "user"
    ARCHIVED = "archived"
    IDLE_TIMEOUT = "idle_timeout"


@dataclass(frozen=True, slots=True)
class SessionIdentity:
    """外部会话的身份 —— **不含 agent**（agent 由策略链选 ✓）。"""

    tenant_id: UUID
    workspace_id: UUID
    owner_id: UUID
    channel_session_key: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentBinding:
    """会话绑定的 agent（id + 版本）—— 版本一起绑，避免中途换版本 ✓。"""

    agent_id: UUID
    agent_version: str


@dataclass(frozen=True, slots=True)
class SessionRef:
    """会话实例的引用 + 它的 agent 绑定（Router 拿到的就是这个 ✓）。"""

    session_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    owner_id: UUID
    agent_id: UUID
    agent_version: str
    status: SessionStatus
    created: bool = False


class SessionCreationConflict(RuntimeError):
    """并发建会话：唯一约束冲突后**重查仍查不到**（对方事务还没提交完 ✓）。

    ⚠️ 这是**罕见**路径（有界重试后仍失败）—— 不吞掉，报出来 ✓。
    """


@runtime_checkable
class SessionStorePort(Protocol):
    """Manager 需要的存储能力（实现在模块侧 ✓）。"""

    async def find_by_channel_key(
        self, *, tenant_id: UUID, channel_session_key: str
    ) -> SessionRef | None:
        """**只读**查既有会话；查不到返回 ``None`` ✓。"""
        ...

    async def insert_session(
        self, *, identity: SessionIdentity, agent: AgentBinding
    ) -> UUID | None:
        """建会话；**唯一约束冲突**（别人先建了）返回 ``None`` ✓。"""
        ...

    async def release_channel_key(self, *, session_id: UUID, tenant_id: UUID) -> None:
        """**释放会话占着的外部会话键** ✓（复活路径用 ✓）。

        ⚠️ **置 NULL 而不是删行** ✓ —— 旧会话保持 ``closed`` 终态 ✓（它是
        历史 ✓）；**部分唯一索引允许多行 NULL** ✓（迁移 0046 ✓）→ 旧行释放
        键 ✓ → 新会话占用同一个键 ✓ **不会冲突** ✓。
        """
        ...

    async def close_session(
        self, *, session_id: UUID, tenant_id: UUID, reason: CloseReason
    ) -> None: ...

    async def archive_session(self, *, session_id: UUID, tenant_id: UUID) -> None: ...


@runtime_checkable
class SessionManagerPort(Protocol):
    """**Router → Session** 的端口（§9 的边界契约 ✓）。"""

    async def lookup(self, *, session_key: str, tenant_id: UUID) -> SessionRef | None:
        """**只读**查既有会话（不创建）✓ —— 粘性规则的依据 ✓。"""
        ...

    async def resolve_or_create(
        self, *, identity: SessionIdentity, agent: AgentBinding
    ) -> SessionRef: ...

    async def close(self, *, session_id: UUID, tenant_id: UUID, reason: CloseReason) -> None: ...

    async def archive(self, *, session_id: UUID, tenant_id: UUID) -> None: ...


class SessionManager(SessionManagerPort):
    """会话的创建 / 查回 / 关闭（§3.1 / §3.2）。"""

    def __init__(
        self,
        *,
        store: SessionStorePort,
        retry_attempts: int = 5,
        retry_delay_s: float = 0.05,
    ) -> None:
        self._store = store
        self._retry_attempts = retry_attempts
        self._retry_delay_s = retry_delay_s

    async def lookup(self, *, session_key: str, tenant_id: UUID) -> SessionRef | None:
        """**只读**查既有会话 —— 不创建、不写表、查不到返回 ``None`` ✓。

        ⚠️ **失败也返回 ``None``**（不抛错）—— Router 的粘性规则是「有就粘、
        没有就走策略链」，不是「查不到就报错」✓。
        """
        return await self._store.find_by_channel_key(
            tenant_id=tenant_id, channel_session_key=session_key
        )

    async def resolve_or_create(
        self, *, identity: SessionIdentity, agent: AgentBinding
    ) -> SessionRef:
        """外部会话 → 会话实例（复用优先 ✓；并发靠唯一约束 ✓）。

        ⚠️ **终态会话会被「复活」** ✓（方案 §3.4 ✓）—— 旧会话是 ``closed``
        ✓ → **不是状态转移** ✓（``closed`` 是终态 ✓）→ **新建一个接管**
        ✓ → 旧行**释放外部会话键** ✓（置 NULL ✓ —— 部分唯一索引 ✓）。
        ⚠️ **没有复活路径之前不做这件事** ✓ —— 只关不复活 = 用户「隔了一周
        再问一句」就得到一个死会话 ✗✗（IM 渠道尤其致命 ✓）。
        """
        existing = await self.lookup(
            session_key=identity.channel_session_key, tenant_id=identity.tenant_id
        )
        if existing is not None and existing.status not in TERMINAL_SESSION_STATUSES:
            return existing
        if existing is not None:
            # ⚠️ **旧会话是终态** ✓ → 让出键 ✓ → 新会话接管 ✓。
            await self._store.release_channel_key(
                session_id=existing.session_id, tenant_id=identity.tenant_id
            )

        session_id = await self._store.insert_session(identity=identity, agent=agent)
        if session_id is not None:
            return SessionRef(
                session_id=session_id,
                tenant_id=identity.tenant_id,
                workspace_id=identity.workspace_id,
                owner_id=identity.owner_id,
                agent_id=agent.agent_id,
                agent_version=agent.agent_version,
                status=SessionStatus.OPEN,
                created=True,
            )

        # 并发：唯一约束挡住了我们 —— **对方已经建过** ✓ → 重查 ✓。
        # ⚠️ 对方的事务可能还没提交 → 读不到 → **有界重试** ✓。
        for attempt in range(self._retry_attempts):
            await asyncio.sleep(self._retry_delay_s * (attempt + 1))
            existing = await self.lookup(
                session_key=identity.channel_session_key,
                tenant_id=identity.tenant_id,
            )
            # ⚠️ **终态的不算「对方建好了」** ✓ —— 它是旧的终态会话 ✓
            # （键已被释放 ✓）→ 继续等 ✓（对方的新会话还没可见 ✓）。
            if existing is not None and existing.status not in TERMINAL_SESSION_STATUSES:
                return existing
        raise SessionCreationConflict(
            "session creation conflicted and the winner is still not visible "
            f"(session_key={identity.channel_session_key!r})"
        )

    async def close(self, *, session_id: UUID, tenant_id: UUID, reason: CloseReason) -> None:
        await self._store.close_session(session_id=session_id, tenant_id=tenant_id, reason=reason)

    async def archive(self, *, session_id: UUID, tenant_id: UUID) -> None:
        await self._store.archive_session(session_id=session_id, tenant_id=tenant_id)


__all__ = [
    "AgentBinding",
    "CloseReason",
    "SessionCreationConflict",
    "SessionIdentity",
    "SessionManager",
    "SessionManagerPort",
    "SessionRef",
    "SessionStorePort",
]
