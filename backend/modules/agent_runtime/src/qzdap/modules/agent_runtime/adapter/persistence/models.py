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
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
