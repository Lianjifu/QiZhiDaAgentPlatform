"""agent_versions.model_id + agent_templates.default_model_id → UUID (nullable).

Phase 2: 把 model_id 从 VARCHAR(128) (上游模型名字符串) 改成 UUID,
对应 admin_models.id (数据库 FK). 不强制 FOREIGN KEY 约束 — 避免历史
agent 行因 catalog 中找不到对应 model 而 migration 失败; 改成 nullable
+ 加 model_migration_status 列, 让 application 层在 catalog 缺失时报错
而不是 boot 失败.

数据现状 (alembic 0039 之后):
- agent_templates 表空 (企业智能体表还没建)
- agent_versions 表空
- admin_models 表有 active 行 (deepseek-flash, etc.)

迁移内容:
  1. 加列 model_id_new UUID (nullable)
  2. data migration: 不做 (空表) — 留 placeholder 给以后脚本回填
  3. drop old model_id (String(128))
  4. rename model_id_new → model_id
  5. 加 model_migration_status VARCHAR(16) (default 'migrated')
  6. 加 ix (workspace_id, model_id) (方便 JOIN 查询)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040_agent_model_id_uuid"
down_revision: str | Sequence[str] | None = "0039_add_updated_at_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── agent_templates.default_model_id ─────────────────────────────
    op.add_column(
        "agent_templates",
        sa.Column("default_model_id_new", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.drop_column("agent_templates", "default_model_id")
    op.alter_column(
        "agent_templates",
        "default_model_id_new",
        new_column_name="default_model_id",
    )
    op.add_column(
        "agent_templates",
        sa.Column(
            "model_migration_status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'migrated'"),
        ),
    )
    op.create_index(
        "ix_agent_templates_workspace_model",
        "agent_templates",
        ["workspace_id", "default_model_id"],
    )

    # ── agent_versions.model_id ──────────────────────────────────────
    op.add_column(
        "agent_versions",
        sa.Column("model_id_new", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.drop_column("agent_versions", "model_id")
    op.alter_column(
        "agent_versions",
        "model_id_new",
        new_column_name="model_id",
    )
    op.add_column(
        "agent_versions",
        sa.Column(
            "model_migration_status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'migrated'"),
        ),
    )
    op.create_index(
        "ix_agent_versions_workspace_model",
        "agent_versions",
        ["workspace_id", "model_id"],
    )


def downgrade() -> None:
    # ── agent_versions.model_id ──────────────────────────────────────
    op.drop_index("ix_agent_versions_workspace_model", table_name="agent_versions")
    op.drop_column("agent_versions", "model_migration_status")
    op.add_column(
        "agent_versions",
        sa.Column("model_id_old", sa.String(128), nullable=True),
    )
    op.drop_column("agent_versions", "model_id")
    op.alter_column(
        "agent_versions",
        "model_id_old",
        new_column_name="model_id",
    )

    # ── agent_templates.default_model_id ─────────────────────────────
    op.drop_index("ix_agent_templates_workspace_model", table_name="agent_templates")
    op.drop_column("agent_templates", "model_migration_status")
    op.add_column(
        "agent_templates",
        sa.Column("default_model_id_old", sa.String(128), nullable=True),
    )
    op.drop_column("agent_templates", "default_model_id")
    op.alter_column(
        "agent_templates",
        "default_model_id_old",
        new_column_name="default_model_id",
    )
