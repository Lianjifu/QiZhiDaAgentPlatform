"""Session 状态字段归一：agent_sessions 删掉 wait_status 列。

依据：docs/modules/agent-runtime.md（状态与字段的
归一：废弃 ``wait_status``）+ §10（表终态）

⚠️ **为什么现在才 DROP**：
- 互斥职责（``wait_status`` 的 CAS）已在 **Stage 3a** 迁到
  ``agent_sessions.current_turn_id`` + ``session_turns.status``（台账 **R3** ✅）；
- 「审批挂起」的语义已在 **Stage 5a** 落到 ``session_turns.pending_approval``
  （Session 方案 §8 · 决策 #6 ✅）；
- 读端（会话卡片 / 任务列表的「等你确认」）已改成**从轮次表推导** ✓。

→ 三个依赖都摘掉了，这一列**没有任何读者** ✓，可以物理删除 ✓。

⚠️ **不可逆**：DROP 之后那一列的历史值找不回来 ✓（方案 §10 的「物理不可逆」
条目要求：备份恢复**演练过**才能执行 —— 本迁移在 dev 库先行验证 ✓）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_session_drop_wait_status"
down_revision: str | Sequence[str] | None = "0052_session_message_seq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("agent_sessions", "wait_status")


def downgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column(
            "wait_status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'idle'"),
        ),
    )
