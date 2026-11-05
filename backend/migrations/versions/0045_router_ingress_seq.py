"""Router 会话内入站序号：agent_sessions 加 next_ingress_seq / last_completed_seq。

依据：docs/modules/agent-runtime.md（决策 #5）

- ``next_ingress_seq``：下一个待分配的入站序号，分配方式是会话行原子自增
  （``UPDATE ... SET next_ingress_seq = next_ingress_seq + 1 RETURNING``），
  跨 worker 有效，不需要分布式锁。
- ``last_completed_seq``：最后一个已完成轮次的 ingress_seq。**权威值在
  ``session_turns``**，本列是冗余快照 —— 轮次进入终态时在同一事务内更新两者，
  正常路径上不一致窗口为 0；万一落后，FIFO 放行判定走权威值兜底路径。

唯一索引（``agent_sessions`` 的 channel_session_key 部分唯一索引）**不归本迁移**
—— 会话创建归 Session，由迁移 0046 建（Router 决策 #10：Router 只派生 key）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_router_ingress_seq"
down_revision: str | Sequence[str] | None = "0044_gateway_inbox_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column(
            "next_ingress_seq",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "agent_sessions",
        sa.Column(
            "last_completed_seq",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_sessions", "last_completed_seq")
    op.drop_column("agent_sessions", "next_ingress_seq")
