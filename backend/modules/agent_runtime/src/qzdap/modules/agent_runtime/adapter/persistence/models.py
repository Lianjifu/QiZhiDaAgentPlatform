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
    Float,
    ForeignKey,
    Index,
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
    wait_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="idle",
        server_default=text("'idle'"),
    )

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

    __table_args__ = (
        make_composite_index("owner_id", "status"),
        make_composite_index("agent_id"),
        CheckConstraint(
            "status IN ('open','closed','running','waiting_approval','cancelled')",
            name="status_enum",
        ),
    )


class TurnORM(TenantScopedMixin, Base):
    __tablename__ = "agent_turns"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="running",
        server_default=text("'running'"),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    final_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        make_composite_index("session_id", "status"),
        make_composite_index("workspace_id"),
        Index(
            "ix_agent_turns_tenant_id_session_id_created_at",
            "tenant_id",
            "session_id",
            "created_at",
        ),
        CheckConstraint(
            "status IN ('running','succeeded','failed','denied')",
            name="status_enum",
        ),
    )


class SessionTurnORM(TenantScopedMixin, Base):
    """新架构的轮次表 —— ``session_turns``（迁移 0035 + 0046 + 0050）。

    ⚠️ **与旧的 ``agent_turns``（:class:`TurnORM`）并存** —— 这是 Session 层
    「双写期」的形态：旧表仍在写，新表同步写。旧表的删除在 Session Stage 6。

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
