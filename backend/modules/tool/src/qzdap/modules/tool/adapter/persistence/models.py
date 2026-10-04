"""SQLAlchemy ORM models for the tool module.

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
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class ToolORM(TenantScopedMixin, Base):
    __tablename__ = "tools"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    protocol: Mapped[str] = mapped_column(String(16), nullable=False)
    spec: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    spec_operations: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    auth_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tools_tenant_id_name"),
        make_composite_index("enabled"),
        make_composite_index("protocol"),
        CheckConstraint("protocol IN ('custom','openapi','mcp')", name="protocol_enum"),
    )


class ToolCallORM(TenantScopedMixin, Base):
    __tablename__ = "tool_calls"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    arguments: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="running",
        server_default=text("'running'"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        make_composite_index("tool_name", "status"),
        CheckConstraint(
            "status IN ('running','succeeded','failed')", name="status_enum"
        ),
    )
