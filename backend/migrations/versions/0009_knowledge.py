"""knowledge module — 0009 migration.

Adds 3 core tables + 1 vector mirror:

- ``knowledge_packages`` — curated collection
- ``knowledge_assets``   — uploaded artifact attached to a package
- ``knowledge_chunks``    — text slice of an asset with the
                            ``embedding vector(1536)`` column + HNSW
- ``knowledge_chunks_vec`` — mirror managed by ``qzdap_vector.PgVectorStore``
                            for payload-filtered retrieval

orchestration tables (plans / workflow_runs / workflow_step_runs) ship
in a follow-up migration (0010_orchestration) once the orchestration
module's ORM models land.

Cascade rules:
  - assets → packages (ON DELETE CASCADE)
  - chunks → assets, packages (ON DELETE CASCADE)

soft-delete (revoked) is enforced via filters on read; rows stay around
for audit / replay.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Register pgvector's Vector() type so ``postgresql.VECTOR(N)`` resolves
# the same way the ORM models do.
from qzdap_persistence.pgvector import register_pgvector

register_pgvector()
from pgvector.sqlalchemy import Vector


revision: str = "0009_knowledge"
down_revision: str | None = "0008_model_channel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBEDDING_DIM = 1536  # text-embedding-3-small default


def upgrade() -> None:
    # ── knowledge_packages ──────────────────────────────────────────────
    op.create_table(
        "knowledge_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "description",
            sa.Text,
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "asset_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
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
            "status IN ('active','archived','revoked')",
            name="ck_knowledge_packages_status_enum",
        ),
    )
    op.create_index(
        "ix_knowledge_packages_tenant_id",
        "knowledge_packages",
        ["tenant_id"],
    )
    op.create_index(
        "ix_knowledge_packages_tenant_id_workspace_id_status",
        "knowledge_packages",
        ["tenant_id", "workspace_id", "status"],
    )
    op.create_unique_constraint(
        "uq_knowledge_packages_tenant_id_name",
        "knowledge_packages",
        ["tenant_id", "name"],
    )

    # ── knowledge_assets ────────────────────────────────────────────────
    op.create_table(
        "knowledge_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "package_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column(
            "mime_type",
            sa.String(128),
            nullable=False,
            server_default=sa.text("'application/octet-stream'"),
        ),
        sa.Column("byte_size", sa.BigInteger, nullable=False),
        sa.Column("storage_uri", sa.String(512), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "chunk_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["knowledge_packages.id"],
            name="fk_knowledge_assets_package_id_knowledge_packages",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('text','document','webpage')",
            name="ck_knowledge_assets_kind_enum",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','ready','failed','revoked')",
            name="ck_knowledge_assets_status_enum",
        ),
    )
    op.create_index(
        "ix_knowledge_assets_tenant_id",
        "knowledge_assets",
        ["tenant_id"],
    )
    op.create_index(
        "ix_knowledge_assets_tenant_id_workspace_id_package_id_status",
        "knowledge_assets",
        ["tenant_id", "workspace_id", "package_id", "status"],
    )
    op.create_index(
        "ix_knowledge_assets_storage_uri",
        "knowledge_assets",
        ["storage_uri"],
    )

    # ── knowledge_chunks ────────────────────────────────────────────────
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "package_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("char_start", sa.Integer, nullable=False),
        sa.Column("char_end", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["knowledge_packages.id"],
            name="fk_knowledge_chunks_package_id_knowledge_packages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["knowledge_assets.id"],
            name="fk_knowledge_chunks_asset_id_knowledge_assets",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_tenant_id",
        "knowledge_chunks",
        ["tenant_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_tenant_id_workspace_id_asset_id_ordinal",
        "knowledge_chunks",
        ["tenant_id", "workspace_id", "asset_id", "ordinal"],
    )
    op.create_index(
        "ix_knowledge_chunks_tenant_id_workspace_id_package_id",
        "knowledge_chunks",
        ["tenant_id", "workspace_id", "package_id"],
    )
    # HNSW over cosine distance — pgvector default operator class.
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # ── knowledge_chunks_vec mirror (managed by qzdap_vector) ─────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE knowledge_chunks_vec (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL,
            workspace_id UUID,
            embedding vector({_EMBEDDING_DIM}) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
        """
    )
    op.execute("CREATE INDEX ix_knowledge_chunks_vec_tenant_id ON knowledge_chunks_vec (tenant_id)")
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_vec_embedding_hnsw "
        "ON knowledge_chunks_vec USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_chunks_vec")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
    op.drop_table("knowledge_chunks")
    op.drop_index(
        "ix_knowledge_assets_storage_uri",
        table_name="knowledge_assets",
    )
    op.drop_index(
        "ix_knowledge_assets_tenant_id_workspace_id_package_id_status",
        table_name="knowledge_assets",
    )
    op.drop_index("ix_knowledge_assets_tenant_id", table_name="knowledge_assets")
    op.drop_table("knowledge_assets")
    op.drop_constraint(
        "uq_knowledge_packages_tenant_id_name",
        "knowledge_packages",
        type_="unique",
    )
    op.drop_index(
        "ix_knowledge_packages_tenant_id_workspace_id_status",
        table_name="knowledge_packages",
    )
    op.drop_index("ix_knowledge_packages_tenant_id", table_name="knowledge_packages")
    op.drop_table("knowledge_packages")
