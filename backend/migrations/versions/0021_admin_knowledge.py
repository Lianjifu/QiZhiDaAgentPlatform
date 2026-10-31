"""Replace RAG knowledge_packages with the admin catalog tables.

Revision ID: 0021_admin_knowledge
Revises: 0020_admin_skills
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_admin_knowledge"
down_revision: str | Sequence[str] | None = "0020_admin_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
        "admin_knowledge_kbs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("owner", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("scope", sa.String(16), nullable=False, server_default=sa.text("'部门'")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'indexing'")),
        sa.Column("doc_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("vector_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tone", sa.String(16), nullable=False, server_default=sa.text("'info'")),
        sa.Column("eval_hit_rate", sa.Float, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "bound_sources",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("retrieval", sa.String(16), nullable=False, server_default=sa.text("'hybrid'")),
        sa.Column("top_k", sa.Integer, nullable=False, server_default=sa.text("8")),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "name", name="uq_admin_knowledge_kbs_tenant_ws_name"
        ),
    )
    op.create_index("ix_admin_knowledge_kbs_tenant_id", "admin_knowledge_kbs", ["tenant_id"])
    op.create_index("ix_admin_knowledge_kbs_workspace_id", "admin_knowledge_kbs", ["workspace_id"])
    op.create_index(
        "ix_admin_knowledge_kbs_tenant_workspace_status",
        "admin_knowledge_kbs",
        ["tenant_id", "workspace_id", "status"],
    )

    op.create_table(
        "admin_knowledge_docs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("type", sa.String(16), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("source_id", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("size_kb", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("chunks", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("citations", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "chunks_preview",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        *_timestamps(),
    )
    op.create_index("ix_admin_knowledge_docs_tenant_id", "admin_knowledge_docs", ["tenant_id"])
    op.create_index(
        "ix_admin_knowledge_docs_workspace_id", "admin_knowledge_docs", ["workspace_id"]
    )
    op.create_index("ix_admin_knowledge_docs_kb_id", "admin_knowledge_docs", ["kb_id"])
    op.create_index(
        "ix_admin_knowledge_docs_tenant_workspace_kb",
        "admin_knowledge_docs",
        ["tenant_id", "workspace_id", "kb_id"],
    )

    op.create_table(
        "admin_knowledge_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("type", sa.String(32), nullable=False, server_default=sa.text("'api'")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'online'")),
        sa.Column("schedule", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("item_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text, nullable=False, server_default=sa.text("''")),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "name",
            name="uq_admin_knowledge_sources_tenant_ws_name",
        ),
    )
    op.create_index(
        "ix_admin_knowledge_sources_tenant_id", "admin_knowledge_sources", ["tenant_id"]
    )
    op.create_index(
        "ix_admin_knowledge_sources_workspace_id", "admin_knowledge_sources", ["workspace_id"]
    )

    op.create_table(
        "admin_knowledge_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default=sa.text("'index'")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("source_id", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("progress", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("items", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("duration", sa.String(32), nullable=False, server_default=sa.text("''")),
        sa.Column("failure_reason", sa.Text, nullable=False, server_default=sa.text("''")),
        *_timestamps(),
    )
    op.create_index("ix_admin_knowledge_tasks_tenant_id", "admin_knowledge_tasks", ["tenant_id"])
    op.create_index(
        "ix_admin_knowledge_tasks_workspace_id", "admin_knowledge_tasks", ["workspace_id"]
    )
    op.create_index("ix_admin_knowledge_tasks_kb_id", "admin_knowledge_tasks", ["kb_id"])

    op.create_table(
        "admin_knowledge_eval_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("query", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("expected_kb", sa.String(256), nullable=False, server_default=sa.text("''")),
        sa.Column("actual_kb", sa.String(256), nullable=False, server_default=sa.text("''")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'skipped'")),
        sa.Column("latency", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("mrr", sa.Float, nullable=False, server_default=sa.text("0")),
        *_timestamps(),
    )
    op.create_index(
        "ix_admin_knowledge_eval_cases_tenant_id", "admin_knowledge_eval_cases", ["tenant_id"]
    )
    op.create_index(
        "ix_admin_knowledge_eval_cases_workspace_id",
        "admin_knowledge_eval_cases",
        ["workspace_id"],
    )

    op.execute("DROP TABLE IF EXISTS knowledge_chunks_vec")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_assets")
    op.drop_table("knowledge_packages")


def downgrade() -> None:
    raise NotImplementedError("0021_admin_knowledge does not support downgrade")
