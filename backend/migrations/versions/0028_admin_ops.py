"""Admin ops console documents.

Revision ID: 0028_admin_ops
Revises: 0027_admin_agents
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_admin_ops"
down_revision: str | Sequence[str] | None = "0027_admin_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_ops_docs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection", sa.String(64), nullable=False),
        sa.Column("doc_key", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "collection",
            "doc_key",
            name="uq_admin_ops_docs_ws_collection_key",
        ),
    )
    op.create_index(
        "ix_admin_ops_docs_tenant_ws_collection",
        "admin_ops_docs",
        ["tenant_id", "workspace_id", "collection"],
    )
    op.create_index("ix_admin_ops_docs_workspace_id", "admin_ops_docs", ["workspace_id"])
    op.create_index("ix_admin_ops_docs_collection", "admin_ops_docs", ["collection"])
    op.create_index("ix_admin_ops_docs_tenant_id", "admin_ops_docs", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("admin_ops_docs")
