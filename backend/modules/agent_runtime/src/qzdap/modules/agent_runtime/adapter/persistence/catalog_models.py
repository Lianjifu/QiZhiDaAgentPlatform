from __future__ import annotations

from uuid import UUID

from qzdap_persistence.base import Base, TenantScopedMixin
from sqlalchemy import Boolean, Float, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class CatalogAgentORM(TenantScopedMixin, Base):
    __tablename__ = "admin_agents"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default=text("'draft'"))
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", server_default=text("'draft'"))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    tone: Mapped[str] = mapped_column(String(16), nullable=False, default="brand", server_default=text("'brand'"))
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    error_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    avg_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    visible_scope: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[\"部门\"]'::jsonb")
    )
    data_access: Mapped[str] = mapped_column(String(256), nullable=False, default="", server_default=text("''"))
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=8, server_default=text("8"))
    tools: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    versions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    evaluation_pass_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    evaluation_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    evaluation_failed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    trend: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    prompts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    custom_prompts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    knowledge_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    memory_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    flow_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))

    __table_args__ = (
        Index("ix_admin_agents_tenant_workspace_status", "tenant_id", "workspace_id", "status"),
        UniqueConstraint("tenant_id", "workspace_id", "name", name="uq_admin_agents_tenant_ws_name"),
    )


class CatalogAgentUserStateORM(TenantScopedMixin, Base):
    __tablename__ = "admin_agent_user_state"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    agent_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    favorited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "agent_id", name="uq_admin_agent_user_state"),
    )


class SessionMessageORM(TenantScopedMixin, Base):
    __tablename__ = "agent_session_messages"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    turn_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))

    __table_args__ = (Index("ix_agent_session_messages_session_seq", "session_id", "seq"),)
