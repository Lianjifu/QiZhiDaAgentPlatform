"""**退役 `admin_memory_l3`** ✓（台账 **X15** ✓ —— 决策 #1 ✓ —— **M-47** ✓）。

⚠️ **为什么现在能删** ✓：
- **写侧早已没了** ✓（``promote_l2`` 早就改写 **knowledge** 候选 ✓）；
- **读侧也切走了** ✓（管理端的 5 个 L3 端点删了 ✓；召回路径不再查 L3 ✓
  → 团队知识只从 **knowledge** 进「相关知识」✓ → **运行时双份注入没了** ✓）；
- **数据已经搬过去了** ✓（迁移 **0058** ✓ —— 逐行搬进 KB / Doc / Chunk ✓）；
- **ORM 不再映射它** ✓；**种子不再种它** ✓。

⚠️ **回滚** ✓：``downgrade`` 把表建回来 ✓（**空表** ✓ —— 数据在
**0058 的 downgrade** 里从 knowledge 还原 ✓ —— 顺序是反着走的 ✓：
**0059 先把表建出来 ✓ → 0058 再把行填回去 ✓**）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0059_memory_retire_l3"
down_revision: str | Sequence[str] | None = "0058_knowledge_absorb_l3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ⚠️ **L3 的向量也一起清掉** ✓ —— 那些行本来就没用了 ✓
    # （孤儿向量 ✓ —— id 与 L3 行对不上 ✓ —— 留着只是占地方 ✗✗）。
    op.execute("DELETE FROM admin_memory_vec WHERE payload->>'layer' = 'l3'")
    op.drop_table("admin_memory_l3")


def downgrade() -> None:
    op.create_table(
        "admin_memory_l3",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("summary", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("category", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("hits", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("contributor", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'published'")),
        sa.Column(
            "hits_trend", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "promoted_from_l2_ids",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
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
    )
    op.create_index("ix_admin_memory_l3_tenant_id", "admin_memory_l3", ["tenant_id"])
    op.create_index("ix_admin_memory_l3_workspace_id", "admin_memory_l3", ["workspace_id"])
