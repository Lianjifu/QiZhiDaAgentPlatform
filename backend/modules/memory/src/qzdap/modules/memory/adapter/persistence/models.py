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


class MemoryL1ORM(TenantScopedMixin, Base):
    __tablename__ = "admin_memory_l1"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    user_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    buffer_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    ttl_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60, server_default=text("60"))
    ttl_remain_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default=text("'active'"))
    buffer_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))


class MemoryL2ORM(TenantScopedMixin, Base):
    __tablename__ = "admin_memory_l2"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    user_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="fact", server_default=text("'fact'"))
    source_session: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="confirmed", server_default=text("'confirmed'"))
    promoted_to_l3: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    usage_history: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))

    __table_args__ = (
        Index("ix_admin_memory_l2_tenant_workspace_status", "tenant_id", "workspace_id", "status"),
    )


class MemoryL3ORM(TenantScopedMixin, Base):
    __tablename__ = "admin_memory_l3"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    team: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    contributor: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="published", server_default=text("'published'"))
    hits_trend: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    promoted_from_l2_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class MemoryPromotionORM(TenantScopedMixin, Base):
    __tablename__ = "admin_memory_promotions"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    layer: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(512), nullable=False, default="", server_default=text("''"))
    operator: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))


class MemoryPolicyORM(TenantScopedMixin, Base):
    __tablename__ = "admin_memory_policies"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    layer: Mapped[str] = mapped_column(String(8), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    ttl_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60, server_default=text("60"))
    max_items: Mapped[int] = mapped_column(Integer, nullable=False, default=50, server_default=text("50"))
    storage_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=8, server_default=text("8"))
    eviction: Mapped[str] = mapped_column(String(16), nullable=False, default="lru", server_default=text("'lru'"))
    hit_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "workspace_id", "layer", name="uq_admin_memory_policies_tenant_ws_layer"
        ),
    )
