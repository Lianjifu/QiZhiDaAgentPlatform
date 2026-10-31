"""**会话信息**的模块侧实现 ✓（窄端口的落点 ✓ —— M-46 ✓）。

⚠️ **会话表归 agent_runtime 模块** ✓ —— Memory 侧只通过窄端口问 ✓
（不跨模块查表 ✓ —— 边界 ✓）。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.agent_runtime.adapter.persistence.models import SessionORM
from qzdap_agent_runtime.memory.session_info import SessionInfo


class PostgresSessionInfo:
    """**按会话 id 查展示信息** ✓（会话行 + metadata ✓）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def describe(self, session_ids: tuple[UUID, ...]) -> dict[UUID, SessionInfo]:
        """**批量查** ✓（查不到的**不在结果里** ✓）。"""
        if not session_ids:
            return {}
        rows = (
            (await self._s.execute(select(SessionORM).where(SessionORM.id.in_(session_ids))))
            .scalars()
            .all()
        )
        described: dict[UUID, SessionInfo] = {}
        for row in rows:
            metadata = row.metadata_ or {}
            described[row.id] = SessionInfo(
                session_id=row.id,
                owner_id=row.owner_id,
                agent_name=str(metadata.get("agentName") or ""),
            )
        return described


__all__ = ["PostgresSessionInfo"]
