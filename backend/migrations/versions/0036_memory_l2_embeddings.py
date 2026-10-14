"""Stage 3 PR C: L2 向量嵌入表 (§14.1 / §5.4)。

- memory_l2_embeddings: tenant/workspace/user scope + content hash + embedding
  + confidence + source turn + expiry + policy_version
- 同 content_hash 写入幂等 (UNIQUE 约束)
- 与 InMemoryLayeredMemory §5.4 决议对齐
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0036_memory_l2_embeddings"
down_revision = "0035_session_stage2_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "memory_l2_embeddings",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False, index=True),
        sa.Column("workspace_id", uuid, nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False, server_default="*"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source_turn_id", uuid, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_version", sa.String(16), nullable=False, server_default="v1"),
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
        sa.UniqueConstraint(
            "tenant_id", "content_hash",
            name="uq_memory_l2_embeddings_tenant_hash",
        ),
        sa.CheckConstraint(
            "user_id IN ('*') OR length(user_id) > 0",
            name="memory_l2_user_id_nonempty",
        ),
    )
    op.create_index(
        "ix_memory_l2_embeddings_tenant_user",
        "memory_l2_embeddings",
        ["tenant_id", "workspace_id", "user_id"],
    )
    op.create_index(
        "ix_memory_l2_embeddings_expires",
        "memory_l2_embeddings",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_l2_embeddings_expires", "memory_l2_embeddings")
    op.drop_index("ix_memory_l2_embeddings_tenant_user", "memory_l2_embeddings")
    op.drop_table("memory_l2_embeddings")