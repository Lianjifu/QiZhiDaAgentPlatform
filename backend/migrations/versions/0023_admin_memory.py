"""Replace memory_entries with the admin L1/L2/L3 catalog.

Revision ID: 0023_admin_memory
Revises: 0022_knowledge_rag
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from qzdap_persistence.pgvector import register_pgvector

register_pgvector()

revision: str = "0023_admin_memory"
down_revision: str | Sequence[str] | None = "0022_knowledge_rag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBEDDING_DIM = 1536


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "admin_memory_l1",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_name", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("agent_name", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("buffer_size", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("ttl_minutes", sa.Integer, nullable=False, server_default=sa.text("60")),
        sa.Column("ttl_remain_min", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("buffer_text", sa.Text, nullable=False, server_default=sa.text("''")),
        *_timestamps(),
    )
    op.create_index("ix_admin_memory_l1_tenant_id", "admin_memory_l1", ["tenant_id"])
    op.create_index("ix_admin_memory_l1_workspace_id", "admin_memory_l1", ["workspace_id"])

    op.create_table(
        "admin_memory_l2",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_name", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("key", sa.String(256), nullable=False),
        sa.Column("value", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("category", sa.String(32), nullable=False, server_default=sa.text("'fact'")),
        sa.Column("source_session", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("confidence", sa.Float, nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'confirmed'")),
        sa.Column("promoted_to_l3", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "usage_history",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        *_timestamps(),
    )
    op.create_index("ix_admin_memory_l2_tenant_id", "admin_memory_l2", ["tenant_id"])
    op.create_index("ix_admin_memory_l2_workspace_id", "admin_memory_l2", ["workspace_id"])
    op.create_index(
        "ix_admin_memory_l2_tenant_workspace_status",
        "admin_memory_l2",
        ["tenant_id", "workspace_id", "status"],
    )

    op.create_table(
        "admin_memory_l3",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("summary", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("category", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("hits", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("contributor", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'published'")),
        sa.Column(
            "hits_trend", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "promoted_from_l2_ids",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        *_timestamps(),
    )
    op.create_index("ix_admin_memory_l3_tenant_id", "admin_memory_l3", ["tenant_id"])
    op.create_index("ix_admin_memory_l3_workspace_id", "admin_memory_l3", ["workspace_id"])

    op.create_table(
        "admin_memory_promotions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("layer", sa.String(16), nullable=False),
        sa.Column("label", sa.String(512), nullable=False, server_default=sa.text("''")),
        sa.Column("operator", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("target_id", sa.String(64), nullable=False, server_default=sa.text("''")),
        *_timestamps(),
    )
    op.create_index("ix_admin_memory_promotions_tenant_id", "admin_memory_promotions", ["tenant_id"])
    op.create_index(
        "ix_admin_memory_promotions_workspace_id", "admin_memory_promotions", ["workspace_id"]
    )

    op.create_table(
        "admin_memory_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("layer", sa.String(8), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("ttl_minutes", sa.Integer, nullable=False, server_default=sa.text("60")),
        sa.Column("max_items", sa.Integer, nullable=False, server_default=sa.text("50")),
        sa.Column("storage_mb", sa.Integer, nullable=False, server_default=sa.text("8")),
        sa.Column("eviction", sa.String(16), nullable=False, server_default=sa.text("'lru'")),
        sa.Column("hit_rate", sa.Float, nullable=False, server_default=sa.text("0")),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "layer", name="uq_admin_memory_policies_tenant_ws_layer"
        ),
    )
    op.create_index("ix_admin_memory_policies_tenant_id", "admin_memory_policies", ["tenant_id"])
    op.create_index(
        "ix_admin_memory_policies_workspace_id", "admin_memory_policies", ["workspace_id"]
    )

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE admin_memory_vec (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL,
            workspace_id UUID,
            embedding vector({_EMBEDDING_DIM}) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
        """
    )
    op.execute("CREATE INDEX ix_admin_memory_vec_tenant_id ON admin_memory_vec (tenant_id)")
    op.execute(
        "CREATE INDEX ix_admin_memory_vec_embedding_hnsw "
        "ON admin_memory_vec USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    op.execute("DROP TABLE IF EXISTS memory_embeddings_vec")
    op.execute("DROP INDEX IF EXISTS ix_memory_embeddings_hnsw")
    op.execute("DROP TABLE IF EXISTS memory_embeddings")
    op.execute("DROP TABLE IF EXISTS memory_entries")


def downgrade() -> None:
    raise NotImplementedError("0023_admin_memory does not support downgrade")
