"""Session 轮次表补一列：``session_turns.user_input``。

⚠️ **为什么需要**：停旧写（S-15b）之后 ``agent_turns`` 不再被写 ✓，
而 ``/api/tasks`` 的任务卡片要显示**用户这一轮说了什么** ✓ ——
旧表有 ``user_input`` 列 ✓，新表没有 ✗。

⚠️ **不补这一列会怎样**：卡片描述会退化成会话的 preview（助手回复的摘要 ✗）——
**那是个静默的降级** ✗✗（用户看到的东西变了，却没人知道 ✓）。

⚠️ 列可空 ✓ —— 历史行没有这一列的内容 ✓（迁移 0054 回填的历史轮次 ✗），
读取时按「空」处理 ✓。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0055_session_turn_user_input"
down_revision: str | Sequence[str] | None = "0054_session_legacy_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_turns",
        sa.Column("user_input", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_turns", "user_input")
