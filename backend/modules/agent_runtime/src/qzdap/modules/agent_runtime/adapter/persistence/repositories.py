"""SQLAlchemy repository implementations of the application ports.

PK-only lookups additionally verify `tenant_id` against the value bound
via `bind_tenant_to_session` — defense in depth on top of the auto-filter
installed by `qzdap_persistence.tenant_guard.install_tenant_loader`.
"""

from __future__ import annotations

from uuid import UUID

from qzdap_observability.metrics import record_legacy_call
from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.agent_runtime.adapter.persistence.mappers import (
    session_orm_to_domain,
    session_turn_orm_to_domain,
)
from qzdap.modules.agent_runtime.adapter.persistence.models import (
    SessionORM,
    SessionTurnORM,
)
from qzdap.modules.agent_runtime.application.ports import (
    SessionRepository,
    TurnRepository,
)
from qzdap.modules.agent_runtime.domain import Session, Turn

# 一个轮次占用会话超过这个时长, 就认为上一轮已经异常退出 (可被接管).
CLAIM_STALE_MINUTES = 30


def _cross_tenant(o: object) -> bool:
    """True if the loaded ORM row's `tenant_id` doesn't match the
    session-bound tenant. Used to silently None-out PK-only lookups that
    would otherwise leak cross-tenant rows before the route-level check."""
    bound = current_tenant_id()
    if bound is None:
        return False
    return getattr(o, "tenant_id", None) != bound


class SqlSessionRepository(SessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, session: Session) -> None:
        record_legacy_call("X3")  # agent_sessions.graph_state 列
        self._s.add(
            SessionORM(
                id=session.id,
                tenant_id=session.tenant_id,
                workspace_id=session.workspace_id,
                owner_id=session.owner_id,
                agent_id=session.agent_id,
                agent_version=session.agent_version,
                status=session.status.value,
                created_at=session.created_at,
                closed_at=session.closed_at,
                metadata_=session.metadata,
                graph_state=dict(session.graph_state or {}),
            )
        )

    async def update(self, session: Session) -> None:
        record_legacy_call("X3")  # agent_sessions.graph_state 列
        o = await self._s.get(SessionORM, session.id)
        if o is None or _cross_tenant(o):
            return
        o.status = session.status.value
        o.closed_at = session.closed_at
        o.metadata_ = session.metadata
        o.graph_state = dict(session.graph_state or {})

    async def get(self, session_id: UUID) -> Session | None:
        o = await self._s.get(SessionORM, session_id)
        if o is None or _cross_tenant(o):
            return None
        return session_orm_to_domain(o)

    async def cancel_requested(self, session_id: UUID) -> bool:
        """Has the user asked for this session's turn to stop?

        Reads the column directly (not through the identity map) so the
        answer comes from the database — the flag is set by another
        request, possibly on another worker.
        """
        raw = await self._s.scalar(
            select(SessionORM.metadata_).where(SessionORM.id == session_id)
        )
        return bool((raw or {}).get("cancel_requested"))

    async def request_cancel(self, session_id: UUID) -> bool:
        """Ask the running turn to stop. Returns True when a turn was live.

        ⚠️ **「是否在飞」看 ``current_turn_id``** —— 不再看那个已退役的
        状态列（互斥职责已迁到 Session 层的 claim 端口 ✓，台账 R3）。
        """
        session = await self.get(session_id)
        if session is None:
            return False
        meta = dict(session.metadata or {})
        meta["cancel_requested"] = True
        await self.update(session.with_runtime(metadata=meta))
        await self._s.commit()
        return await self._s.scalar(
            select(SessionORM.current_turn_id).where(SessionORM.id == session_id)
        ) is not None

    async def clear_cancel(self, session_id: UUID) -> None:
        """Drop a stale cancel flag — a new turn starts fresh."""
        session = await self.get(session_id)
        if session is None:
            return
        meta = dict(session.metadata or {})
        if not meta.pop("cancel_requested", None):
            return
        await self.update(session.with_runtime(metadata=meta))
        await self._s.commit()

    async def list_for_owner(
        self, tenant_id: UUID, owner_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Session]:
        # 租户过滤**显式**写在 SQL 里 —— 不依赖请求上下文里绑定的租户
        # （没有绑定时 ORM 自动过滤退化成 no-op，查询会跨租户）。
        q = (
            select(SessionORM)
            .where(SessionORM.tenant_id == tenant_id, SessionORM.owner_id == owner_id)
            .order_by(SessionORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._s.execute(q)).scalars().all()
        return [session_orm_to_domain(o) for o in rows]

    async def list_for_owner_workspace(
        self,
        tenant_id: UUID,
        owner_id: UUID,
        workspace_id: UUID,
        *,
        limit: int = 200,
    ) -> list[Session]:
        """/api/tasks 派生用 — tenant + owner + workspace 复合过滤, 不返回 closed 状态之外的孤儿 session."""
        q = (
            select(SessionORM)
            .where(
                SessionORM.tenant_id == tenant_id,
                SessionORM.owner_id == owner_id,
                SessionORM.workspace_id == workspace_id,
            )
            .order_by(SessionORM.created_at.desc())
            .limit(limit)
        )
        rows = (await self._s.execute(q)).scalars().all()
        return [session_orm_to_domain(o) for o in rows]


class SqlTurnRepository(TurnRepository):
    """轮次读 —— **新表** ``session_turns`` ✓（停旧写 S-15b 之后它是唯一真相 ✓）。

    ⚠️ **只读** ✓ —— 轮次的写入归 :class:`SessionJournal` ✓（幂等键 / 版本
    冻结 / 审批挂起都在那边 ✓）；这里**不再有第二个写路径** ✗✗。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, turn_id: UUID) -> Turn | None:
        o = await self._s.get(SessionTurnORM, turn_id)
        if o is None or _cross_tenant(o):
            return None
        return session_turn_orm_to_domain(o)

    async def latest_for_session(self, session_id: UUID) -> Turn | None:
        """/api/tasks 派生用 — 取最新一轮 turn 用于状态翻译."""
        q = (
            select(SessionTurnORM)
            .where(SessionTurnORM.session_id == session_id)
            .order_by(SessionTurnORM.started_at.desc())
            .limit(1)
        )
        o = (await self._s.execute(q)).scalars().first()
        if o is None:
            return None
        return session_turn_orm_to_domain(o)
