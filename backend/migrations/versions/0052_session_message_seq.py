"""Session 会话内消息序号：agent_sessions 加 next_message_seq。

依据：docs/refactor/session-architecture/session-refactor-plan.md §5.2（消息序）

- ``next_message_seq``：下一个待分配的会话内消息序号，分配方式是会话行
  **原子自增**（``UPDATE ... SET next_message_seq = next_message_seq + 1
  RETURNING``），跨 worker 有效，不需要分布式锁。

⚠️ **为什么必须是计数器列，而不是 ``MAX(session_seq) + 1``**：
  分配与写入若不在同一个原子步骤里，两个并发的写者会拿到**同一个**
  ``session_seq`` → 撞上迁移 0046 的唯一索引 ``(session_id, session_seq)``
  → 整条消息写失败 ✗✗。计数器列把「取号」与「写号」放进**同一个事务** ✓。

⚠️ **DDL 归属**：``agent_sessions`` 的列归 **Session 层**（迁移 0046 建了唯一
索引，0045 由 **Router** 加了 ``next_ingress_seq`` / ``last_completed_seq``）。
本迁移加的是**消息**侧的计数器 —— 语义归 Session（Session 方案 §5.2）✓。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_session_message_seq"
down_revision: str | Sequence[str] | None = "0051_gateway_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column(
            "next_message_seq",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_sessions", "next_message_seq")
