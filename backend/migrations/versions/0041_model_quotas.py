"""model_quotas + model_quota_usage 表.

Phase 4: 每 tenant / model / period 的配额, 防止单 model 被滥用.

表设计:
  - model_quotas: 配置 (max_tokens, max_requests) per (tenant, model, period)
  - model_quota_usage: 当前 period 的实际使用 (per tenant+model)
    - period_start TIMESTAMPTZ 标记当前周期开始
    - period_key 字符串 (例如 "2026-10-17T10:00") 简化滑动窗口
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041_model_quotas"
down_revision: str | Sequence[str] | None = "0040_agent_model_id_uuid"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── model_quotas (config) ─────────────────────────────────────────
    op.create_table(
        "model_quotas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "model_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(16), nullable=False),  # minute|hour|day
        sa.Column("max_tokens_in", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("max_tokens_out", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("max_requests", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text, nullable=False, server_default="''"),
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
            "tenant_id", "workspace_id", "model_id", "period",
            name="uq_model_quotas_tenant_ws_model_period",
        ),
        sa.CheckConstraint(
            "period IN ('minute','hour','day')",
            name="ck_model_quotas_period_enum",
        ),
    )
    op.create_index(
        "ix_model_quotas_workspace_model",
        "model_quotas",
        ["workspace_id", "model_id"],
    )

    # ── model_quota_usage (sliding window) ────────────────────────────
    op.create_table(
        "model_quota_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "model_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("period_key", sa.String(32), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tokens_in", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("requests", sa.BigInteger, nullable=False, server_default="0"),
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
            "tenant_id",
            "workspace_id",
            "model_id",
            "period",
            "period_key",
            name="uq_model_quota_usage_window",
        ),
    )
    op.create_index(
        "ix_model_quota_usage_workspace_model_period",
        "model_quota_usage",
        ["workspace_id", "model_id", "period", "period_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_quota_usage_workspace_model_period",
        table_name="model_quota_usage",
    )
    op.drop_table("model_quota_usage")
    op.drop_index("ix_model_quotas_workspace_model", table_name="model_quotas")
    op.drop_table("model_quotas")
