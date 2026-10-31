"""**Session Manager** 的单测（Session 方案 §3.1）。

⚠️ 这里测的是**契约层**的语义 —— 存储是替身。真正的 DB 行为（唯一约束冲突）
在集成测试里验 ✓。

三个必须成立的不变式：

1. ``lookup`` **只读** —— 不创建、不写表 ✓；
2. ``resolve_or_create`` **优先复用** —— 已有会话就不建第二个 ✓；
3. 并发建会话 —— 唯一约束挡住我们时**重查**拿到赢家建的那一个 ✓。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from qzdap_agent_runtime.session.manager import (
    AgentBinding,
    CloseReason,
    SessionCreationConflict,
    SessionIdentity,
    SessionManager,
    SessionRef,
)
from qzdap_agent_runtime.session.state import SessionStatus

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
OWNER = UUID("00000000-0000-0000-0000-000000000010")
AGENT = UUID("00000000-0000-0000-0000-000000000099")
KEY = "sha256-key"


class _Store:
    """存储替身 —— 能模拟「唯一约束冲突」✓。"""

    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, str], SessionRef] = {}
        self.insert_calls = 0
        self.closed: list[tuple[UUID, CloseReason]] = []
        self.archived: list[UUID] = []
        #: 第一次 insert 时返回冲突（模拟别人先建了 ✓）。
        self.conflict_once = False
        #: 冲突后重查是否可见。
        self.visible_after_conflict = True

    async def find_by_channel_key(self, *, tenant_id, channel_session_key):  # type: ignore[no-untyped-def]
        return self.rows.get((tenant_id, channel_session_key))

    async def insert_session(self, *, identity, agent):  # type: ignore[no-untyped-def]
        self.insert_calls += 1
        if self.conflict_once:
            self.conflict_once = False
            if self.visible_after_conflict:
                self.rows[(identity.tenant_id, identity.channel_session_key)] = self._ref(
                    identity, agent, session_id=uuid4()
                )
            return None
        ref = self._ref(identity, agent, session_id=uuid4())
        self.rows[(identity.tenant_id, identity.channel_session_key)] = ref
        return ref.session_id

    async def close_session(self, *, session_id, tenant_id, reason):  # type: ignore[no-untyped-def]
        self.closed.append((session_id, reason))

    async def archive_session(self, *, session_id, tenant_id):  # type: ignore[no-untyped-def]
        self.archived.append(session_id)

    @staticmethod
    def _ref(identity: SessionIdentity, agent: AgentBinding, *, session_id: UUID) -> SessionRef:
        return SessionRef(
            session_id=session_id,
            tenant_id=identity.tenant_id,
            workspace_id=identity.workspace_id,
            owner_id=identity.owner_id,
            agent_id=agent.agent_id,
            agent_version=agent.agent_version,
            status=SessionStatus.OPEN,
        )


def _identity() -> SessionIdentity:
    return SessionIdentity(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        channel_session_key=KEY,
    )


def _agent() -> AgentBinding:
    return AgentBinding(agent_id=AGENT, agent_version="v1")


def _manager(store: _Store, **kwargs) -> SessionManager:
    return SessionManager(store=store, retry_delay_s=0.0, **kwargs)


async def test_lookup_is_read_only() -> None:
    """**只读** —— 查不到就返回 ``None``，不创建任何东西 ✓。"""
    store = _Store()
    manager = _manager(store)

    ref = await manager.lookup(session_key=KEY, tenant_id=TENANT)

    assert ref is None
    assert store.insert_calls == 0


async def test_resolve_or_create_creates_a_session() -> None:
    store = _Store()
    manager = _manager(store)

    ref = await manager.resolve_or_create(identity=_identity(), agent=_agent())

    assert ref.created is True
    assert ref.agent_id == AGENT
    assert ref.status is SessionStatus.OPEN
    assert store.insert_calls == 1


async def test_resolve_or_create_reuses_an_existing_session() -> None:
    """已有会话 → **不建第二个** ✓（外部会话 ↔ 会话实例是一对一 ✓）。"""
    store = _Store()
    manager = _manager(store)

    first = await manager.resolve_or_create(identity=_identity(), agent=_agent())
    second = await manager.resolve_or_create(identity=_identity(), agent=_agent())

    assert second.session_id == first.session_id
    assert second.created is False
    assert store.insert_calls == 1


async def test_a_concurrent_creation_resolves_to_the_winners_session() -> None:
    """唯一约束挡住我们 → **重查**拿到赢家建的那一个 ✓。"""
    store = _Store()
    store.conflict_once = True
    manager = _manager(store)

    ref = await manager.resolve_or_create(identity=_identity(), agent=_agent())

    assert ref.created is False
    assert ref.agent_id == AGENT


async def test_a_conflict_that_stays_invisible_raises() -> None:
    """冲突后对方迟迟不可见 → **报错**，不静默返回一个不存在的会话 ✓。"""
    store = _Store()
    store.conflict_once = True
    store.visible_after_conflict = False
    manager = _manager(store, retry_attempts=2)

    with pytest.raises(SessionCreationConflict):
        await manager.resolve_or_create(identity=_identity(), agent=_agent())


async def test_close_and_archive_delegate_to_the_store() -> None:
    store = _Store()
    manager = _manager(store)
    session_id = uuid4()

    await manager.close(session_id=session_id, tenant_id=TENANT, reason=CloseReason.USER)
    await manager.archive(session_id=session_id, tenant_id=TENANT)

    assert store.closed == [(session_id, CloseReason.USER)]
    assert store.archived == [session_id]
