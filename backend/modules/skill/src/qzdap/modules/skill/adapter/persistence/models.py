from __future__ import annotations

from uuid import UUID

from qzdap_persistence.base import Base, TenantScopedMixin
from sqlalchemy import (
    Boolean,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class SkillORM(TenantScopedMixin, Base):
    __tablename__ = "admin_skills"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="Skill", server_default=text("'Skill'"))
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default=text("'draft'"))
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", server_default=text("'draft'"))
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    error_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    avg_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    risk: Mapped[str] = mapped_column(String(16), nullable=False, default="low", server_default=text("'low'"))
    need_confirm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    visible_scope: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[\"部门\"]'::jsonb"))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    input_schema: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    output_schema: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    versions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    trend: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    used_by_agents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    audit_log: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    runtime: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        Index("ix_admin_skills_tenant_workspace_status", "tenant_id", "workspace_id", "status"),
        UniqueConstraint("tenant_id", "workspace_id", "name", name="uq_admin_skills_tenant_ws_name"),
    )


class SkillUserStateORM(TenantScopedMixin, Base):
    __tablename__ = "admin_skill_user_state"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    skill_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    favorited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    last_used: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "skill_id", name="uq_admin_skill_user_state"),
        Index("ix_admin_skill_user_state_user_skill", "tenant_id", "user_id", "skill_id"),
    )
