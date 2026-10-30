"""``tool_executions`` —— **幂等的唯一权威** ✓（Agent 方案 §5.3.2 ✓）。

⚠️ **这张表的列在迁移 0035 就建齐了** ✓ —— **不需要新迁移** ✓ —— 本模块
只负责**开始写它** ✓（此前**从未被写** ✓ —— 幂等只在进程内 dict 里 ✗✗ →
跨 worker / 重启后失效 ✗）。

⚠️ **表归会话域** ✓（``turn_id`` 外键指向 ``session_turns`` ✓ —— 迁移 0035
是会话域的迁移 ✓）→ ORM 落在 agent_runtime（``session_turns`` 的主人 ✓）。

⚠️ **不用 ``TenantScopedMixin``** ✓ —— 那会凭空多出 ``id`` 列 ✗（这张表的
主键是 ``tool_call_id`` ✓）→ 租户过滤**显式写** ✓。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from qzdap.modules.tool.application.ports import ToolExecutionClaim
from qzdap_persistence.base import Base
from sqlalchemy import DateTime, ForeignKey, String, select, text, update
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class ToolExecutionORM(Base):
    """``tool_executions`` ✓（迁移 0035 建列 ✓ + 0039 补 ``updated_at`` ✓）。"""

    __tablename__ = "tool_executions"

    #: ⚠️ **是 ``String(64)`` 不是 UUID** ✓ —— ``tool_calls.id`` 是 UUID ✓ →
    #: 写入时必须 ``str(id)`` ✓（方案 §5.3.2 明确警告过 ✓）。
    tool_call_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'")
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: **结果指针不是正文** ✓ —— 正文在 ``tool_calls.result`` ✓（有意设计 ✓）。
    result_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reconcile_endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    turn_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("session_turns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class PostgresToolExecutionStore:
    """**幂等占位的 SQL 实现** ✓（跨 worker 有效 ✓ —— 唯一索引说了算 ✓）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def begin(
        self,
        *,
        idempotency_key: str,
        request_hash: str,
        tool_call_id: str,
        turn_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
    ) -> ToolExecutionClaim:
        """**占一次执行权** ✓。

        ⚠️ **冲突读回** ✓ —— 抢不到就把既有行读出来 ✓（由调用方判断「同参复用」
        还是「异参拒绝」✓ —— **这里不做判断** ✓ —— 端口不重复那份规则 ✗✗）。
        """
        stmt = (
            insert(ToolExecutionORM)
            .values(
                tool_call_id=tool_call_id,
                idempotency_key=idempotency_key,
                status="running",
                request_hash=request_hash,
                turn_id=turn_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                started_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(ToolExecutionORM.tool_call_id)
        )
        inserted = (await self._session.execute(stmt)).scalar_one_or_none()
        if inserted is not None:
            await self._session.flush()
            return ToolExecutionClaim(
                claimed=True, status="running", request_hash=request_hash, tool_call_id=inserted
            )

        existing = await self._get(idempotency_key=idempotency_key, tenant_id=tenant_id)
        if existing is None:
            # ⚠️ **插不进去又读不到** —— 只可能是**别的租户用了同一个键** ✓
            # （唯一索引是全局的 ✓）→ **拒绝** ✓（当冲突处理 ✓ —— 绝不执行 ✗）。
            return ToolExecutionClaim(claimed=False, status="unknown")
        return ToolExecutionClaim(
            claimed=False,
            status=existing.status,
            request_hash=existing.request_hash,
            result_ref=existing.result_ref,
            tool_call_id=existing.tool_call_id,
        )

    async def finish(
        self,
        *,
        idempotency_key: str,
        status: str,
        result_ref: str | None = None,
    ) -> None:
        """**收尾** ✓（状态 + 结果指针 ✓）。"""
        # ⚠️ **按幂等键更新** ✓（主键是 ``tool_call_id`` ✓ —— 调用方未必知道它 ✓）
        await self._session.execute(
            update(ToolExecutionORM)
            .where(ToolExecutionORM.idempotency_key == idempotency_key)
            .values(
                status=status,
                result_ref=result_ref,
                finished_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await self._session.flush()

    async def _get(
        self, *, idempotency_key: str, tenant_id: UUID
    ) -> ToolExecutionORM | None:
        result = await self._session.execute(
            select(ToolExecutionORM).where(
                ToolExecutionORM.idempotency_key == idempotency_key,
                ToolExecutionORM.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()


__all__ = ["PostgresToolExecutionStore", "ToolExecutionORM"]
