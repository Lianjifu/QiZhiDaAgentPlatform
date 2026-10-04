"""Knowledge chunk table + pgvector mirror for catalog RAG.

Revision ID: 0022_knowledge_rag
Revises: 0021_admin_knowledge
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from qzdap_persistence.pgvector import register_pgvector

register_pgvector()

revision: str = "0022_knowledge_rag"
down_revision: str | Sequence[str] | None = "0021_admin_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.create_table(
        "admin_knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("heading", sa.String(256), nullable=False, server_default=sa.text("''")),
        sa.Column("content", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("tokens", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_admin_knowledge_chunks_tenant_id", "admin_knowledge_chunks", ["tenant_id"])
    op.create_index(
        "ix_admin_knowledge_chunks_workspace_id", "admin_knowledge_chunks", ["workspace_id"]
    )
    op.create_index("ix_admin_knowledge_chunks_kb_id", "admin_knowledge_chunks", ["kb_id"])
    op.create_index("ix_admin_knowledge_chunks_doc_id", "admin_knowledge_chunks", ["doc_id"])
    op.create_index(
        "ix_admin_knowledge_chunks_tenant_workspace_kb",
        "admin_knowledge_chunks",
        ["tenant_id", "workspace_id", "kb_id"],
    )

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE admin_knowledge_chunks_vec (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL,
            workspace_id UUID,
            embedding vector({_EMBEDDING_DIM}) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_admin_knowledge_chunks_vec_tenant_id "
        "ON admin_knowledge_chunks_vec (tenant_id)"
    )
    op.execute(
        "CREATE INDEX ix_admin_knowledge_chunks_vec_embedding_hnsw "
        "ON admin_knowledge_chunks_vec USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    raise NotImplementedError("0022_knowledge_rag does not support downgrade")
