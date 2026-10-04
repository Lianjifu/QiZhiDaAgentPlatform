"""memory module: memory_entries + memory_embeddings tables.

Revision ID: 0006_memory
Revises: 0005_skill
Create Date: 2026-09-22

Two tables, one index for fast vector search:

- ``memory_entries`` — content + metadata + soft-delete (revoked) +
  expiry timestamp + scope (user/agent/workspace).  Embedding is held in
  a sibling row to keep the hot path off the wide table.
- ``memory_embeddings`` — one row per entry, ``embedding vector(1536)``.
  HNSW index over cosine distance covers the recall path; pgvector
  delivers P95 ≤ 200ms on small/medium datasets without pre-training.

soft-delete + expiry are enforced via filters on read, NOT via row
removal: an entry stays in the table after revoke / expiry so audits can
reconstruct what was once known.  A separate ``purge_expired`` use case
hard-deletes after the audit retention window (P10 governance policy).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0006_memory"
down_revision: str | None = "0005_skill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_EMBEDDING_DIM = 1536  # text-embedding-3-small default


def upgrade() -> None:
    # memory_entries — content + metadata + soft delete + expiry
    op.create_table(
        "memory_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "scope",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'workspace'"),
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "revoked",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "version_lock",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "scope IN ('user','agent','workspace')",
            name="ck_memory_entries_scope_enum",
        ),
    )
    op.create_index("ix_memory_entries_tenant_id", "memory_entries", ["tenant_id"])
    op.create_index("ix_memory_entries_workspace_id", "memory_entries", ["workspace_id"])
    op.create_index("ix_memory_entries_owner_id", "memory_entries", ["owner_id"])
    op.create_index(
        "ix_memory_entries_tenant_id_workspace_id_revoked_expires_at",
        "memory_entries",
        ["tenant_id", "workspace_id", "revoked", "expires_at"],
    )
    op.create_index(
        "ix_memory_entries_tenant_id_workspace_id_scope",
        "memory_entries",
        ["tenant_id", "workspace_id", "scope"],
    )

    # memory_embeddings — sibling table, holds the pgvector column.
    # Registered on `postgresql.base.ischema_names` by
    # ``qzdap_persistence.pgvector.register_pgvector``.
    op.create_table(
        "memory_embeddings",
        sa.Column(
            "memory_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("embedding", postgresql.VECTOR(_EMBEDDING_DIM), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["memory_id"],
            ["memory_entries.id"],
            name="fk_memory_embeddings_memory_id_memory_entries",
            ondelete="CASCADE",
        ),
    )
    # HNSW over cosine distance — pgvector default operator class.
    # m=16 / ef_construction=64 are sensible defaults; tune in P10
    # under real load.
    op.execute(
        "CREATE INDEX ix_memory_embeddings_hnsw ON memory_embeddings "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memory_embeddings_hnsw")
    op.drop_table("memory_embeddings")

    op.drop_index(
        "ix_memory_entries_tenant_id_workspace_id_scope",
        table_name="memory_entries",
    )
    op.drop_index(
        "ix_memory_entries_tenant_id_workspace_id_revoked_expires_at",
        table_name="memory_entries",
    )
    op.drop_index("ix_memory_entries_owner_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_workspace_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_tenant_id", table_name="memory_entries")
    op.drop_table("memory_entries")
