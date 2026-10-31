"""退役 ``admin_memory_l1`` ✓（台账 **X13** ✓ —— 决策 #5 ✓ —— **M-46** ✓）。

⚠️ **为什么现在能删** ✓：
- **写侧早就没了** ✓（旧写入点随 `_remember` 一起删了 ✓ —— 迁移 0048 之后
  就没有人写它 ✓）；
- **读侧也切走了** ✓（管理端的 4 个 L1 端点改读 **会话缓冲**
  ``session_memory_buffer`` ✓ —— 决策 #5 的落点 ✓ —— 契约**没变** ✓
  （前端那套 ``L1Session`` 形状照旧 ✓））；
- **ORM 不再映射它** ✓；**种子不再种它** ✓。

⚠️ **表里的旧数据是什么** ✓：老 L1 会话缓冲 ✓（上下文窗口的落盘副本 ✓）——
**没人读** ✓（读端已切 ✓）→ 直接丢 ✓（L2 里的事实才是长期记忆 ✓）。

⚠️ **回滚要能恢复** ✓：``downgrade`` 把表建回来 ✓（列与索引照原样 ✓）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057_memory_retire_l1"
down_revision: str | Sequence[str] | None = "0056_session_retire_graph_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("admin_memory_l1")


def downgrade() -> None:
    op.create_table(
        "admin_memory_l1",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_name", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("agent_name", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("buffer_size", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("ttl_minutes", sa.Integer, nullable=False, server_default=sa.text("60")),
        sa.Column("ttl_remain_min", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("buffer_text", sa.Text, nullable=False, server_default=sa.text("''")),
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
    )
    op.create_index("ix_admin_memory_l1_tenant_id", "admin_memory_l1", ["tenant_id"])
    op.create_index("ix_admin_memory_l1_workspace_id", "admin_memory_l1", ["workspace_id"])
