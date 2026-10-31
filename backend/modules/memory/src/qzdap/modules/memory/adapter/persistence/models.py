from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from qzdap_persistence.base import Base, TenantScopedMixin


class MemoryL2ORM(TenantScopedMixin, Base):
    __tablename__ = "admin_memory_l2"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    user_name: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default=text("''")
    )
    # 归属用户（迁移 0048）。nullable：存量自动沉淀的记忆没有归属，不回填。
    user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    category: Mapped[str] = mapped_column(
        String(32), nullable=False, default="fact", server_default=text("'fact'")
    )
    source_session: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=text("''")
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="confirmed",
        server_default=text("'confirmed'"),
    )
    promoted_to_l3: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    usage_history: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # ── 以下四列由迁移 0048 建好 ✓（ORM 当时没映射 ✗ —— 现在补上 ✓）──
    #: 内容哈希 ✓（去重用 ✓ —— §4.4 ✓）；**存量行是 NULL** ✓（存量不参与去重 ✓）
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: 哈希的规范化规则版本 ✓（规则变了要能区分 ✓ —— §4.4 ✓）
    content_hash_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default=text("1")
    )
    #: 来源轮次 ✓（可追溯 ✓ —— §4.1 ✓）
    source_turn_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    #: 最后一次被用到的时刻 ✓（统计 ✓ —— §3.5 ✓）
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: 被用过多少次 ✓（统计 ✓ —— §3.5 ✓）
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    #: 置信度来源 ✓（`explicit` / `rule` / `llm` ✓ —— §4.5 ✓）
    confidence_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="rule", server_default=text("'rule'")
    )
    #: 版本 ✓（召回要带出去 ✓ —— Context manifest 用 ✓）
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __table_args__ = (
        Index(
            "ix_admin_memory_l2_tenant_workspace_status",
            "tenant_id",
            "workspace_id",
            "status",
        ),
        # ⚠️ 去重的唯一约束**只对有 hash 的行生效** ✓（存量行为 NULL ✓
        # —— 存量不参与去重 ✓ —— §4.4 ✓）。
        Index(
            "uq_admin_memory_l2_content_hash",
            "tenant_id",
            "workspace_id",
            "user_id",
            "content_hash",
            unique=True,
            postgresql_where=text("content_hash IS NOT NULL"),
        ),
    )


class SessionMemoryBufferORM(TenantScopedMixin, Base):
    """**会话缓冲** ✓（决策 #5 ✓ —— L1 退役的落点 ✓）。

    ⚠️ **会话级策略的记忆先落这里** ✓（§7.1 ✓）—— 会话结束后**提炼成
    用户级 L2** ✓（或按 TTL 丢弃 ✓）。
    """

    __tablename__ = "session_memory_buffer"
    __table_args__ = (
        UniqueConstraint("session_id", "content_hash", name="uq_session_memory_buffer_hash"),
    )

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    turn_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    candidates: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="buffer", server_default=text("'buffer'")
    )


class MemoryPromotionORM(TenantScopedMixin, Base):
    __tablename__ = "admin_memory_promotions"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    layer: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", server_default=text("''")
    )
    operator: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default=text("''")
    )
    target_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=text("''")
    )
    # ⚠️ **补三列** ✓（迁移 0048 建了 ✓ —— ORM 当时没映射 ✗ —— M-30 ✓）。
    from_layer: Mapped[str] = mapped_column(
        String(8), nullable=False, default="l1", server_default=text("'l1'")
    )
    to_layer: Mapped[str] = mapped_column(
        String(8), nullable=False, default="l2", server_default=text("'l2'")
    )
    reason: Mapped[str] = mapped_column(
        String(256), nullable=False, default="", server_default=text("''")
    )


class MemoryPolicyORM(TenantScopedMixin, Base):
    __tablename__ = "admin_memory_policies"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    layer: Mapped[str] = mapped_column(String(8), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    ttl_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default=text("60")
    )
    max_items: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50, server_default=text("50")
    )
    storage_mb: Mapped[int] = mapped_column(
        Integer, nullable=False, default=8, server_default=text("8")
    )
    eviction: Mapped[str] = mapped_column(
        String(16), nullable=False, default="lru", server_default=text("'lru'")
    )
    hit_rate: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "layer",
            name="uq_admin_memory_policies_tenant_ws_layer",
        ),
    )
