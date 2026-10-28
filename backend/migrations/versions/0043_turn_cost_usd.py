"""agent_turns.cost_usd —— 一轮对话的成本.

之前 UsageChunk.cost_usd 恒为 0, admin_models.price_in / price_out 也从来没有
被读过 —— 模型的单价字段存着却没人用. 这一列把「按模型单价算出来的成本」
落到轮次上, 让 /api/tasks 和后台统计能按轮次算钱.

价格口径: 每 1K token 的单价 (price_in / price_out), 与 admin_models 一致.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_turn_cost_usd"
down_revision: str | Sequence[str] | None = "0042_agent_version_route"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_turns",
        sa.Column("cost_usd", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_turns", "cost_usd")
