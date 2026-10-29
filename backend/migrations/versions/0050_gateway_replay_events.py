"""Gateway Stage 4b：重放的落点 —— session_turns 补两列 + 幂等唯一索引换成部分索引。

依据：docs/refactor/session-architecture/gateway-refactor-plan.md §10 Stage 4b
（无感重放）、§4.2（决策 #5：weak 键只记录不抑制）、§4.6（三层键的传递链）。

1) ``session_turns.created_at`` —— 0035 建表时给了 ``started_at`` 却漏了
   ``created_at``，而项目的 ORM 约定（``TenantScopedMixin``）要求
   ``created_at`` / ``updated_at`` 成对（0039 只补了 ``updated_at``）。

2) ``session_turns.key_strength`` —— 幂等键的**强度**必须跟着轮次一起落库：
   原来的唯一约束 ``(session_id, idempotency_key)`` 覆盖**全部**行，而 weak
   键（内容指纹）在同一会话里会重复 —— 两条内容相同的消息，第二条会被唯一
   约束直接拒绝，**直接违反决策 #5**（weak 不抑制）。

3) 唯一约束换成**部分唯一索引**，口径与 ``session_inbox`` 的
   ``uq_session_inbox_idem_strong`` 一致（决策 #5），并且**只覆盖在飞的轮次**
   （``status IN ('queued','running','waiting')``）：

   - 只覆盖 strong → weak 永不互相抑制；
   - 只覆盖在飞的轮次 → 同一把键在 TTL（24h）过期后重发时，旧行已是终态、
     不在索引里 → 新轮次照常起（**「过期不误杀」不被这层约束反噬**）。

   幂等的**权威**仍是 ``session_inbox``（带 TTL 与强弱分层的那个）；本索引
   只是「同一会话里不得有两个在飞的同键轮次」的兜底。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050_gateway_replay_events"
down_revision: str | Sequence[str] | None = "0049_gateway_service_account"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 在飞轮次的状态集合 —— 只有这些状态进唯一索引（见文件说明第 3 点）。
IN_FLIGHT_STATUSES = ("queued", "running", "waiting")


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) created_at —— ORM 约定要求它与 updated_at 成对。
    # ------------------------------------------------------------------
    op.add_column(
        "session_turns",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # ------------------------------------------------------------------
    # 2) key_strength —— 幂等键的强弱分层。
    # ------------------------------------------------------------------
    op.add_column(
        "session_turns",
        sa.Column(
            "key_strength",
            sa.String(8),
            nullable=False,
            server_default=sa.text("'strong'"),
        ),
    )
    # ------------------------------------------------------------------
    # 3) 唯一约束 → 只覆盖 strong 且只覆盖在飞轮次的部分唯一索引。
    # ------------------------------------------------------------------
    op.drop_constraint("uq_session_turns_session_idem", "session_turns", type_="unique")
    op.create_index(
        "uq_session_turns_session_idem_strong",
        "session_turns",
        ["session_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text(
            "key_strength = 'strong' AND status IN ('queued','running','waiting')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_session_turns_session_idem_strong", "session_turns")
    op.create_unique_constraint(
        "uq_session_turns_session_idem", "session_turns", ["session_id", "idempotency_key"]
    )
    op.drop_column("session_turns", "key_strength")
    op.drop_column("session_turns", "created_at")
