"""``SessionStorePort`` 的 SQL 实现 —— 会话行的读写。

依据：Session 方案 §3.1（Manager 的两步流程 + 并发创建靠唯一约束）。

⚠️ **唯一索引的 arbiter 必须带同一个谓词**：迁移 0046 建的是**部分**唯一索引
``(tenant_id, channel_session_key) WHERE channel_session_key IS NOT NULL``
→ ``ON CONFLICT`` 的目标也得带 ``WHERE channel_session_key IS NOT NULL``，
否则 Postgres 认不出这个索引（``there is no unique or exclusion constraint
matching the ON CONFLICT specification`` ✓）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from qzdap.modules.agent_runtime.adapter.persistence.models import SessionORM
from qzdap_agent_runtime.session.manager import (
    AgentBinding,
    CloseReason,
    SessionIdentity,
    SessionRef,
)
from qzdap_agent_runtime.session.state import SessionStatus


class PostgresSessionStore:
    """会话行的存储实现（DB 会话由调用方持有 ✓）。"""

    def __init__(self, session: Any) -> None:
        self._s = session

    async def find_by_channel_key(
        self, *, tenant_id: UUID, channel_session_key: str
    ) -> SessionRef | None:
        """**只读**查既有会话 ✓ —— 查不到返回 ``None`` ✓。"""
        result = await self._s.execute(
            select(SessionORM).where(
                SessionORM.tenant_id == tenant_id,
                SessionORM.channel_session_key == channel_session_key,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_ref(row)

    async def insert_session(
        self, *, identity: SessionIdentity, agent: AgentBinding
    ) -> UUID | None:
        """建会话 —— 唯一约束冲突（别人先建了）返回 ``None`` ✓。

        ⚠️ **只吞「同 key 重复」这一种冲突**：``ON CONFLICT DO NOTHING`` 只针对
        那个唯一索引 ✓；其它约束违反照常抛 ✓。
        """
        stmt = (
            pg_insert(SessionORM)
            .values(
                id=uuid4(),
                tenant_id=identity.tenant_id,
                workspace_id=identity.workspace_id,
                owner_id=identity.owner_id,
                agent_id=agent.agent_id,
                agent_version=agent.agent_version,
                status=SessionStatus.OPEN.value,
                metadata_=dict(identity.metadata),
                channel_session_key=identity.channel_session_key,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "channel_session_key"],
                index_where=SessionORM.channel_session_key.isnot(None),
            )
            .returning(SessionORM.id)
        )
        result = await self._s.execute(stmt)
        return result.scalar_one_or_none()

    async def close_session(
        self, *, session_id: UUID, tenant_id: UUID, reason: CloseReason
    ) -> None:
        """关闭会话（终态 ✓）—— 已是终态就**不动**（幂等 ✓）。"""
        result = await self._s.execute(
            update(SessionORM)
            .where(
                SessionORM.id == session_id,
                SessionORM.tenant_id == tenant_id,
                SessionORM.status.notin_(
                    [SessionStatus.CLOSED.value, SessionStatus.CANCELLED.value]
                ),
            )
            .values(
                status=SessionStatus.CLOSED.value,
                closed_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        if result.rowcount:
            await self._s.commit()

    async def archive_session(self, *, session_id: UUID, tenant_id: UUID) -> None:
        """归档 = 关闭 + 打归档标记（§3.2 ✓）。

        ⚠️ `metadata` 是 JSONB —— 用「读出来改一改再写回」而不是 SQL 侧的
        JSON 拼接（那个方言依赖太重 ✗）。
        """
        row = await self._s.get(SessionORM, session_id)
        if row is None or row.tenant_id != tenant_id:
            return
        metadata = dict(row.metadata_ or {})
        metadata["archived"] = True
        row.metadata_ = metadata
        row.status = SessionStatus.CLOSED.value
        if row.closed_at is None:
            row.closed_at = datetime.now(UTC)
        await self._s.commit()


def _to_ref(row: SessionORM) -> SessionRef:
    return SessionRef(
        session_id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        owner_id=row.owner_id,
        agent_id=row.agent_id,
        agent_version=row.agent_version,
        status=SessionStatus(row.status),
    )


__all__ = ["PostgresSessionStore"]
