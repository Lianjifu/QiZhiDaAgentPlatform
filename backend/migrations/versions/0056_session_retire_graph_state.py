"""退役 ``agent_sessions`` 的**旧续传状态列**（台账 **X3** ✓）。

⚠️ **为什么现在能删**：新的循环**不再写它** ✓（续传状态归
``metadata["resume"]`` ✓ —— 会话 metadata ✓），ORM **不再映射它** ✓，
扫描规则 **X3 已启用** ✓（``modules/`` 里不再有那个符号 ✓）。

⚠️ **列里的旧数据是什么**：老 LangGraph 图的续传状态 ✓（19 节点图的
产物 ✓ —— 那张图已随 Agent Stage 7 删除 ✓）→ **没人读** ✓。

⚠️ **回滚要能恢复**：``downgrade`` 把列加回来 ✓（默认 ``{}`` ✓）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0056_session_retire_graph_state"
down_revision: str | Sequence[str] | None = "0055_session_turn_user_input"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("agent_sessions", "graph_state")


def downgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column(
            "graph_state",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
