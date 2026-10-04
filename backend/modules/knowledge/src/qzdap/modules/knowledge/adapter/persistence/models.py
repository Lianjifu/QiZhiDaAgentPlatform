from __future__ import annotations

from uuid import UUID

from qzdap_persistence.base import Base, TenantScopedMixin
from sqlalchemy import (
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


class KnowledgeBaseORM(TenantScopedMixin, Base):
    __tablename__ = "admin_knowledge_kbs"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default=text("''"))
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="部门", server_default=text("'部门'"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="indexing", server_default=text("'indexing'")
    )
    doc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    vector_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    tone: Mapped[str] = mapped_column(String(16), nullable=False, default="info", server_default=text("'info'"))
    eval_hit_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    bound_sources: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    retrieval: Mapped[str] = mapped_column(
        String(16), nullable=False, default="hybrid", server_default=text("'hybrid'")
    )
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=8, server_default=text("8"))

    __table_args__ = (
        Index("ix_admin_knowledge_kbs_tenant_workspace_status", "tenant_id", "workspace_id", "status"),
        UniqueConstraint("tenant_id", "workspace_id", "name", name="uq_admin_knowledge_kbs_tenant_ws_name"),
    )


class KnowledgeDocORM(TenantScopedMixin, Base):
    __tablename__ = "admin_knowledge_docs"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    kb_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="manual", server_default=text("'manual'"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'")
    )
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    size_kb: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    citations: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    chunks_preview: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    __table_args__ = (
        Index("ix_admin_knowledge_docs_tenant_workspace_kb", "tenant_id", "workspace_id", "kb_id"),
    )


class KnowledgeChunkORM(TenantScopedMixin, Base):
    __tablename__ = "admin_knowledge_chunks"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    kb_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    doc_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    heading: Mapped[str] = mapped_column(String(256), nullable=False, default="", server_default=text("''"))
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    __table_args__ = (
        Index(
            "ix_admin_knowledge_chunks_tenant_workspace_kb",
            "tenant_id",
            "workspace_id",
            "kb_id",
        ),
        Index("ix_admin_knowledge_chunks_doc_id", "doc_id"),
    )


class KnowledgeSourceORM(TenantScopedMixin, Base):
    __tablename__ = "admin_knowledge_sources"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="api", server_default=text("'api'"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="online", server_default=text("'online'")
    )
    schedule: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "workspace_id", "name", name="uq_admin_knowledge_sources_tenant_ws_name"
        ),
    )


class KnowledgeTaskORM(TenantScopedMixin, Base):
    __tablename__ = "admin_knowledge_tasks"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    kb_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="index", server_default=text("'index'"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'")
    )
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    items: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    duration: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default=text("''"))
    failure_reason: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))


class KnowledgeEvalCaseORM(TenantScopedMixin, Base):
    __tablename__ = "admin_knowledge_eval_cases"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    expected_kb: Mapped[str] = mapped_column(String(256), nullable=False, default="", server_default=text("''"))
    actual_kb: Mapped[str] = mapped_column(String(256), nullable=False, default="", server_default=text("''"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="skipped", server_default=text("'skipped'"))
    latency: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    mrr: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
