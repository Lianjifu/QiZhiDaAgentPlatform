"""``admin_agents``: 持久化 ``route_id`` + ``route_strategy`` ✓。

⚠️ **为什么要有这两列** ✓ —— 路由策略之前**只有两个入口** ✓：
- HTTP 请求体临时传 ``route_id`` ✓（每轮现传 ✓ —— 换个客户端就没了 ✗✗）；
- ``agent_versions.route_id`` ✓（迁移 0042 ✓ —— 但那套是 **agent_factory**
  自己的版本存储 ✓，**对话路径从不读它** ✗✗ → 一直**存着不生效** ✗✗）。

本迁移把同一组字段补到**真正被跑的那个 agent** ✓（``admin_agents`` ✓ ——
``session.agent_id`` 指向的就是它 ✓），并由 **factory release 事件**同步过来 ✓
（见 ``agent_factory_release_subscriber`` ✓ —— 那个 subscriber 本来就在把
factory 的发布结果搬进 catalog ✓，顺手把路由也搬过来 ✓）。

⚠️ **不建外键** ✓ —— 与 0042 同一口径 ✓：路由可能被删 ✓，但**删路由不该
连带删 agent** ✗✗（路由没了就退化成「走默认模型」✓ —— 这是可接受的降级 ✓）。

⚠️ **不建索引** ✓ —— 这两列**不参与查询** ✓（读的是**按 id 查出来的那一行**
✓ —— 主键已经够快 ✓）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0066_admin_agent_route"
down_revision: str | Sequence[str] | None = "0065_buffer_updated_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_agents",
        sa.Column("route_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "admin_agents",
        sa.Column(
            "route_strategy",
            sa.String(16),
            nullable=True,
            server_default=sa.text("NULL"),
        ),
    )


def downgrade() -> None:
    op.drop_column("admin_agents", "route_strategy")
    op.drop_column("admin_agents", "route_id")
