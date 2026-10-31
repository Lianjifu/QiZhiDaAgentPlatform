"""给 ``session_memory_buffer`` 补 ``updated_at`` 列。

⚠️ **同一个坑的第二次** ✓（迁移 0039 修过一次 ✓ —— 见那次的说明 ✓）：
``TenantScopedMixin`` 用 ``@declared_attr`` 给所有子类注入 ``updated_at`` ✓，
但**迁移 0048**（Memory runtime）建 ``session_memory_buffer`` 时用的是**裸
DDL** ✓ —— 漏了那一列 ✗✗。

后果 ✓：**会话缓冲一条都读不出来** ✗✗ ——

```text
asyncpg.exceptions.UndefinedColumnError: column session_memory_buffer.updated_at does not exist
```

ORM 每次 SELECT 都会带上那一列 ✓ → 提炼器（会话缓冲 → 用户级 L2 ✓）每轮
清扫都失败 ✗✗（日志里每 5 分钟一条 ``memory buffer refinement failed`` ✓）。

⚠️ **只补这一张表** ✓ —— 全库扫过 ✓（dev 库 64 张带 ``tenant_id`` 的表 ✓）：
其余缺 ``updated_at`` 的几张都**不是** ``TenantScopedMixin`` 映射的 ✓
（``user_workspaces`` 是普通 ``Base`` ✓ · ``admin_memory_vec`` /
``admin_knowledge_chunks_vec`` 是向量表 ✓ · ``session_context_manifests``
走裸 SQL ✓ · ``data_subject_deletion_log`` 没有 ORM ✓）→ 不给它们乱加列 ✓。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0065_buffer_updated_at"
down_revision: str | Sequence[str] | None = "0064_session_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE session_memory_buffer "
            "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE "
            "NOT NULL DEFAULT now()"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE session_memory_buffer DROP COLUMN IF EXISTS updated_at"))


__all__: Sequence[str] = ()
