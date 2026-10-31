"""**删掉 `subscriptions.workspace_id`** ✓（P-13 的 mypy 扫出来的真缺陷 ✓）。

⚠️ **为什么这列是多余的** ✓：
- **订阅是租户级的** ✓ —— 0014 的迁移注释就写着「per-tenant assignment to a
  Plan ✓ —— 一个租户一份订阅 ✓」，唯一约束也建在 ``tenant_id`` 上 ✓；
- **领域实体从来不带这个字段** ✓ —— `Subscription` 只有 ``tenant_id`` ✓；
- **ORM 却映射了它** ✓ —— 于是「写订阅」这条路径**必然抛 `AttributeError`**
  ✗✗（`subscription_to_orm` 读 ``entity.workspace_id` ✓ —— 实体没这个属性 ✓）。

⚠️ **这条路径以前没人走过** ✓ —— 表里一行数据都没有 ✓（dev 库 / demo 库都是 0 ✓）
→ 所以缺陷一直是**潜伏**的 ✓（不是「最近才坏」✗）。

⚠️ **回滚** ✓：``downgrade`` 把列加回来 ✓（**可空** ✓ —— 老数据本来就没有
这个值 ✓ —— 加成 NOT NULL 会让老行写不回去 ✗）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0060_platform_sub_workspace"
down_revision: str | Sequence[str] | None = "0059_memory_retire_l3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("subscriptions", "workspace_id")


def downgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
