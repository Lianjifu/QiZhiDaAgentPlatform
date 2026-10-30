"""SQLAlchemy ORM models for the agent runtime.

Both tables inherit `TenantScopedMixin` so:
  - the `do_orm_execute` listener in `install_tenant_loader` auto-filters
    every query by the request's bound tenant id;
  - the `tenant_id` index is added by the mixin.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from qzdap_persistence.base import Base, TenantScopedMixin, make_composite_index
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class SessionORM(TenantScopedMixin, Base):
    __tablename__ = "agent_sessions"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    owner_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    agent_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default=text("'open'")
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    graph_state: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    # ⚠️ **``wait_status`` 已退役**（台账 X6 ✅）—— 互斥归 ``current_turn_id``
    # （R3），审批挂起归 ``session_turns.pending_approval``（方案 §8）。
    # 迁移 0053 DROP 掉这一列；ORM 也不再映射它 ✓。

    # Stage 2 新增字段（§14.1）— migration 0035
    current_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    current_turn_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    agent_version_pinned: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    channel_session_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True, index=True
    )
    # 会话内的两个序列的**计数器**（Session 方案 §5.2）——
    #   next_ingress_seq：轮次序（DDL 归 Router，迁移 0045）；
    #   next_message_seq：消息序（DDL 归 Session，迁移 0052）。
    # ⚠️ 分配方式是**原子自增**（``UPDATE ... SET x = x + 1 RETURNING``）——
    # ``MAX(x) + 1`` 在两个写者之间会撞唯一索引 ✗✗。
    next_ingress_seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_message_seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (
        make_composite_index("owner_id", "status"),
        make_composite_index("agent_id"),
        CheckConstraint(
            "status IN ('open','closed','running','waiting_approval','cancelled')",
            name="status_enum",
        ),
    )


class SessionTurnORM(TenantScopedMixin, Base):
    """新架构的轮次表 —— ``session_turns``（迁移 0035 + 0046 + 0050 + 0055）。

    ✅ **它是轮次的唯一真相** —— 旧表 ``agent_turns`` 已停写（S-15b ✓）
    （S-15b ✓），读端也一并切过来 ✓。

    这张表在 Gateway Stage 4b 里承担两件事：① ``session_events`` 的外键父行；
    ② 重放时判断「这一轮是否已到终态」。
    """

    __tablename__ = "session_turns"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    key_strength: Mapped[str] = mapped_column(
        String(8), nullable=False, default="strong", server_default=text("'strong'")
    )
    # ⚠️ **这一轮用户说了什么** ✓ —— 停旧写（S-15b）之后，``agent_turns`` 不再
    # 被写 ✓，任务卡片的描述只能从这里取 ✓（迁移 0055 ✓）。
    user_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", server_default=text("'running'")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    expected_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pending_approval: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    ingress_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    route_decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    agent_decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','waiting','succeeded','failed','cancelled')",
            name="status_enum",
        ),
    )


class SessionMessageORM(Base):
    """**新表** ``session_messages``（迁移 0035 + 0046）—— 会话消息的**规范真相**。

    ⚠️ **这张表没有 ``tenant_id`` 列** —— 租户归属由它的**轮次**决定
    （``session_turns.tenant_id``），读它必须按租户过滤 ✓。

    ⚠️ **不继承 ``TenantScopedMixin``** —— 那会凭空多出 ``id`` / ``tenant_id``
    两个表里没有的列（同 ``session_events`` ✓）。

    **两个序号**（Session 方案 §5.2）：
    - ``seq``：**轮次内**序号（PK 的一部分 → ``(turn_id, seq)``）；
    - ``session_seq``：**会话内**序号（唯一索引 ``(session_id, session_seq)``）
      → 上下文重建与重放靠它单表有序扫描 ✓。
    """

    __tablename__ = "session_messages"

    turn_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("session_turns.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata_", JSONB, nullable=True
    )
    session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    session_seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class SessionEventORM(Base):
    """事件流 —— ``session_events``（迁移 0035）。

    ⚠️ **这张表没有 ``tenant_id`` 列**（主键是 ``(turn_id, seq)``）—— 事件行
    的租户归属由它的**轮次**决定。因此读它必须**按租户过滤**（JOIN
    ``session_turns``），见 :class:`PostgresSessionJournal`。

    ⚠️ **不继承 ``TenantScopedMixin``** —— 那会凭空多出 ``id`` / ``tenant_id``
    两个表里没有的列。
    """

    __tablename__ = "session_events"

    turn_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("session_turns.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    delivery_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'")
    )
    delivery_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )
