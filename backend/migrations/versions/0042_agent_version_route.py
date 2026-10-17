"""agent_versions: 持久化 route_id + route_strategy.

Phase 15: 把 chat 时临时传入的 route_id 变成 agent 版本的一等公民.

为什么需要:
  - 之前 route_id 只通过 chat body 临时传入 (Phase 12), 关闭浏览器后丢失
  - admin 在 agent 编辑界面配好策略路由 (例如 deepseek + qwen fallback,
    latency-first), 后续所有 chat 自动沿用, 不需要用户每次挑
  - 同样需要 route_strategy 显式存 (与 route_id 共生, 但允许只配
    strategy 不绑具体 route)

数据现状 (alembic 0041 之后):
  - agent_templates / agent_versions 表通常空, 已有列 model_id (UUID nullable)
  - 不需要 data migration

迁移内容:
  1. agent_versions.route_id UUID (nullable, FK→ admin_model_routes.id 不强制)
  2. agent_versions.route_strategy VARCHAR(16) (nullable, 与 Phase 7 strategy 匹配)
  3. ix (workspace_id, route_id) 方便查询
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042_agent_version_route"
down_revision: str | Sequence[str] | None = "0041_model_quotas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_versions",
        sa.Column("route_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agent_versions",
        sa.Column(
            "route_strategy",
            sa.String(16),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_agent_versions_workspace_route",
        "agent_versions",
        ["workspace_id", "route_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_versions_workspace_route", table_name="agent_versions")
    op.drop_column("agent_versions", "route_strategy")
    op.drop_column("agent_versions", "route_id")
