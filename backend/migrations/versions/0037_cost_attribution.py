"""Stage 7a PR B: cost_attribution 表 (§14.1 / §5.10)。

- tenant_id / workspace_id / user_id / agent_id / agent_version / model_version
  / period / input_tokens / output_tokens / cost_usd / attribution_status
- attribution_status: 'ok' | 'degraded' (cost_attribution_degraded)
- 唯一 (tenant, workspace, user, agent_id, agent_version, period)
- down_revision = 0036_memory_l2_embeddings
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_cost_attribution"
down_revision = "0036_memory_l2_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "cost_attribution",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False, index=True),
        sa.Column("workspace_id", uuid, nullable=False),
        sa.Column("user_id", uuid, nullable=False),
        sa.Column("agent_id", uuid, nullable=False),
        sa.Column("agent_version", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("period", sa.String(16), nullable=False, server_default="daily"),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "attribution_status",
            sa.String(16),
            nullable=False,
            server_default="ok",
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
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "user_id", "agent_id",
            "agent_version", "model_version", "period",
            name="uq_cost_attribution_scope",
        ),
        sa.CheckConstraint(
            "attribution_status IN ('ok','degraded')",
            name="cost_attribution_status_enum",
        ),
    )
    op.create_index(
        "ix_cost_attribution_period",
        "cost_attribution",
        ["period", "tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cost_attribution_period", "cost_attribution")
    op.drop_table("cost_attribution")