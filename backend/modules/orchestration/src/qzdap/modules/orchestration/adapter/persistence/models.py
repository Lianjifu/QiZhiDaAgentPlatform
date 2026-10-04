from __future__ import annotations

from uuid import UUID

from qzdap_persistence.base import Base, TenantScopedMixin
from sqlalchemy import Boolean, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class WorkflowORM(TenantScopedMixin, Base):
    __tablename__ = "admin_workflows"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    scene: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    trigger: Mapped[str] = mapped_column(
        String(16), nullable=False, default="消息触发", server_default=text("'消息触发'")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default=text("'draft'"))
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    inputs: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    outputs: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    bound_agents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    versions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    initial_nodes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    initial_edges: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))

    __table_args__ = (
        Index("ix_admin_workflows_tenant_workspace_status", "tenant_id", "workspace_id", "status"),
        UniqueConstraint("tenant_id", "workspace_id", "name", name="uq_admin_workflows_tenant_ws_name"),
    )


class WorkflowUserStateORM(TenantScopedMixin, Base):
    __tablename__ = "admin_workflow_user_state"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    workflow_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    favorited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "workflow_id", name="uq_admin_workflow_user_state"),
        Index("ix_admin_workflow_user_state_user", "tenant_id", "user_id", "workflow_id"),
    )


class WorkflowRunORM(TenantScopedMixin, Base):
    __tablename__ = "admin_workflow_runs"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    workflow_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    time: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    result: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))

    __table_args__ = (
        Index("ix_admin_workflow_runs_user_created", "tenant_id", "user_id", "created_at"),
    )
